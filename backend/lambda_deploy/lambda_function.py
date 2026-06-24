"""
PDF ingestion Lambda.

Flow:
    User uploads PDF -> S3 -> S3 event -> SQS -> N8N -> invokes this Lambda
    (or SQS triggers this Lambda directly).

This function:
    1. Reads the S3 object key(s) from the incoming event (SQS-wrapped S3 events).
    2. Streams the PDF out of S3.
    3. Extracts text and splits it into chunks by heading.
    4. Creates a vector embedding for each chunk (AWS Bedrock Titan by default).
    5. Upserts the chunks + embeddings into a PGVector table.

Environment variables
----------------------
    AWS_REGION              AWS region for S3 + Bedrock          (default: eu-north-1)
    BEDROCK_EMBED_MODEL     Bedrock embedding model id           (default: amazon.titan-embed-text-v2:0)
    EMBED_DIM               Embedding dimensionality             (default: 1024)
    PGVECTOR_DSN            Postgres connection string           (required)
    PGVECTOR_TABLE          Destination table                    (default: pdf_chunks)
    MAX_CHUNK_CHARS         Soft cap before a heading section is sub-split (default: 4000)

Packaging notes
---------------
    Bundle `pypdf` and `psycopg2-binary` into the deployment package / layer.
    boto3 is provided by the Lambda runtime.
"""

import io
import json
import logging
import os
import re
from urllib.parse import unquote_plus

import boto3
import psycopg2
from psycopg2.extras import execute_values
from pypdf import PdfReader

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---- Configuration ---------------------------------------------------------

AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
BEDROCK_EMBED_MODEL = os.environ.get("BEDROCK_EMBED_MODEL", "amazon.titan-embed-text-v2:0")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
PGVECTOR_DSN = os.environ.get("PGVECTOR_DSN")
PGVECTOR_TABLE = os.environ.get("PGVECTOR_TABLE", "pdf_chunks")
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "4000"))

# Reused across warm invocations.
s3_client = boto3.client("s3", region_name=AWS_REGION)
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)


# ---- Event parsing ---------------------------------------------------------

def _iter_s3_records(event):
    """Yield (bucket, key) pairs from an SQS-wrapped (or raw) S3 event.

    S3 -> SQS delivery nests the S3 event JSON inside each SQS record's body.
    A direct S3 -> Lambda trigger puts the records at the top level. Handle both.
    """
    records = event.get("Records", [])
    for record in records:
        # SQS-wrapped: the S3 event is a JSON string in `body`.
        if "body" in record:
            try:
                body = json.loads(record["body"])
            except (ValueError, TypeError):
                logger.warning("Skipping SQS record with non-JSON body")
                continue
            inner = body.get("Records", [])
            # Some pipelines (e.g. SNS->SQS) add another wrapper; unwrap once more.
            if not inner and "Message" in body:
                try:
                    inner = json.loads(body["Message"]).get("Records", [])
                except (ValueError, TypeError):
                    inner = []
            for s3_record in inner:
                yield _extract_bucket_key(s3_record)
        else:
            # Direct S3 trigger.
            yield _extract_bucket_key(record)


def _extract_bucket_key(s3_record):
    s3 = s3_record.get("s3", {})
    bucket = s3.get("bucket", {}).get("name")
    key = s3.get("object", {}).get("key")
    if key:
        key = unquote_plus(key)  # S3 keys arrive URL-encoded (spaces -> '+').
    return bucket, key


# ---- PDF -> text -----------------------------------------------------------

def stream_pdf_text(bucket, key):
    """Stream the PDF out of S3 and return per-page text."""
    logger.info("Streaming s3://%s/%s", bucket, key)
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()  # Body is a stream; read into memory for pypdf.
    reader = PdfReader(io.BytesIO(data))
    return [(page.extract_text() or "") for page in reader.pages]


# ---- Chunking by heading ---------------------------------------------------

# A heading is a short, standalone line: numbered (1, 1.2), all-caps, or a
# Title Cased line with no terminating punctuation.
_HEADING_RE = re.compile(
    r"""^\s*
        (?:
            (?:\d+(?:\.\d+)*\.?\s+\S.*)      # 1  /  1.2  /  3.4.5 Heading text
          | (?:[A-Z][A-Z0-9 \-/&]{2,}\s*)    # ALL CAPS HEADING
          | (?:[A-Z][\w&\- ]{2,60})          # Title Case line
        )
        \s*$""",
    re.VERBOSE,
)


def _looks_like_heading(line):
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if stripped.endswith((".", ",", ";", ":")):
        return False
    if len(stripped.split()) > 12:
        return False
    return bool(_HEADING_RE.match(stripped))


def chunk_by_headings(pages):
    """Split full document text into chunks, one per heading section.

    Returns a list of {"heading", "text", "page"} dicts. Sections longer than
    MAX_CHUNK_CHARS are sub-split on paragraph boundaries so no single chunk
    blows past the embedding model's input limit.
    """
    chunks = []
    current_heading = "Introduction"
    current_lines = []
    current_page = 1

    def flush(heading, lines, page):
        text = "\n".join(lines).strip()
        if not text:
            return
        for piece in _split_oversized(text):
            chunks.append({"heading": heading, "text": piece, "page": page})

    for page_num, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            if _looks_like_heading(line):
                flush(current_heading, current_lines, current_page)
                current_heading = line.strip()
                current_lines = []
                current_page = page_num
            else:
                current_lines.append(line)

    flush(current_heading, current_lines, current_page)
    return chunks


def _split_oversized(text):
    """Split a section into <= MAX_CHUNK_CHARS pieces on paragraph boundaries."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    pieces = []
    buf = ""
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue
        if len(buf) + len(paragraph) + 2 > MAX_CHUNK_CHARS and buf:
            pieces.append(buf.strip())
            buf = ""
        buf = f"{buf}\n\n{paragraph}" if buf else paragraph
    if buf.strip():
        pieces.append(buf.strip())
    return pieces


# ---- Embeddings (AWS Bedrock Titan) ----------------------------------------

def embed_text(text):
    """Return the embedding vector for a single chunk via Bedrock Titan."""
    response = bedrock_client.invoke_model(
        modelId=BEDROCK_EMBED_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True}),
    )
    payload = json.loads(response["body"].read())
    return payload["embedding"]


# ---- PGVector storage ------------------------------------------------------

def _get_connection():
    if not PGVECTOR_DSN:
        raise RuntimeError("PGVECTOR_DSN environment variable is not set")
    return psycopg2.connect(PGVECTOR_DSN)


def _ensure_schema(conn):
    """Create the pgvector extension and destination table if missing."""
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PGVECTOR_TABLE} (
                id          BIGSERIAL PRIMARY KEY,
                source_key  TEXT NOT NULL,
                heading     TEXT,
                page        INTEGER,
                chunk_index INTEGER NOT NULL,
                content     TEXT NOT NULL,
                embedding   vector({EMBED_DIM}) NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (source_key, chunk_index)
            );
            """
        )
    conn.commit()


def store_chunks(conn, source_key, chunks):
    """Replace any existing rows for this PDF, then bulk-insert the new chunks."""
    rows = []
    for index, chunk in enumerate(chunks):
        embedding = embed_text(chunk["text"])
        # pgvector accepts the literal '[1,2,3]' text form.
        vector_literal = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
        rows.append(
            (source_key, chunk["heading"], chunk["page"], index, chunk["text"], vector_literal)
        )

    with conn.cursor() as cur:
        # Re-ingestion of the same key should overwrite, not duplicate.
        cur.execute(f"DELETE FROM {PGVECTOR_TABLE} WHERE source_key = %s;", (source_key,))
        execute_values(
            cur,
            f"""
            INSERT INTO {PGVECTOR_TABLE}
                (source_key, heading, page, chunk_index, content, embedding)
            VALUES %s
            """,
            rows,
        )
    conn.commit()
    return len(rows)


# ---- Handler ---------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("Received event with %d record(s)", len(event.get("Records", [])))

    conn = _get_connection()
    try:
        _ensure_schema(conn)

        processed = []
        for bucket, key in _iter_s3_records(event):
            if not bucket or not key:
                logger.warning("Skipping record with missing bucket/key")
                continue
            if not key.lower().endswith(".pdf"):
                logger.info("Skipping non-PDF object: %s", key)
                continue

            pages = stream_pdf_text(bucket, key)
            chunks = chunk_by_headings(pages)
            if not chunks:
                logger.warning("No extractable text in s3://%s/%s", bucket, key)
                continue

            stored = store_chunks(conn, key, chunks)
            logger.info("Stored %d chunk(s) for s3://%s/%s", stored, bucket, key)
            processed.append({"key": key, "chunks": stored})

        return {
            "statusCode": 200,
            "body": json.dumps({"processed": processed}),
        }
    finally:
        conn.close()
