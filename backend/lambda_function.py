import io
import json
import logging
import os
import re
from urllib.parse import unquote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import psycopg2
from psycopg2.extras import execute_values
from pypdf import PdfReader
from google import genai

# ---------------- LOGGING ----------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------- CONFIG ----------------

AWS_REGION = os.environ.get("AWS_REGION", "eu-north-1")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
PGVECTOR_DSN = os.environ.get("PGVECTOR_DSN")
PGVECTOR_TABLE = os.environ.get("PGVECTOR_TABLE", "pdf_chunks")
MAX_CHUNK_WORDS = int(os.environ.get("MAX_CHUNK_WORDS", "400"))
OVERLAP_LINES = int(os.environ.get("OVERLAP_LINES", "2"))
EMBED_WORKERS = int(os.environ.get("EMBED_WORKERS", "5"))

# ---------------- CLIENTS ----------------

s3_client = boto3.client("s3", region_name=AWS_REGION)
google_client = genai.Client(api_key=GOOGLE_API_KEY)

# ---------------- EVENT PARSER ----------------

def get_s3_files(event):
    logger.info("EVENT: %s", json.dumps(event))

    if event.get("bucket") and event.get("key"):
        yield (event["bucket"], event["key"])
        return

    for record in event.get("Records", []):
        if "body" in record:
            body = json.loads(record["body"])
            for s3_record in body.get("Records", []):
                yield extract_s3(s3_record)
        else:
            yield extract_s3(record)


def extract_s3(record):
    s3 = record["s3"]
    bucket = s3["bucket"]["name"]
    key = unquote_plus(s3["object"]["key"])
    return bucket, key

# ---------------- PDF ----------------

def read_pdf(bucket, key):
    logger.info("Reading s3://%s/%s", bucket, key)
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    logger.info("Read %d pages", len(pages))
    return pages

# ---------------- HEADING DETECTION ----------------

def is_heading(line):
    stripped = line.strip()

    if not stripped:
        return False
    if len(stripped) > 80:
        return False
    if stripped.endswith((".", ",", ";", ":", "!", "?")):
        return False
    if len(stripped.split()) > 12:
        return False
    if re.match(r"^\d+(\.\d+)*\.?\s+\S", stripped):
        return True
    if stripped.isupper() and len(stripped) >= 3:
        return True

    words = stripped.split()
    if len(words) >= 2 and all(
        w[0].isupper() for w in words if w.isalpha()
    ):
        return True

    return False

# ---------------- CHUNKING ----------------

def chunk_by_headings(pages):
    chunks = []
    current_heading = "Introduction"
    current_lines = []
    last_lines_for_overlap = []

    def flush(heading, lines, overlap):
        if not lines:
            return

        full_text = " ".join(
            line.strip() for line in lines if line.strip()
        )

        if not full_text.strip():
            return

        word_count = len(full_text.split())

        if word_count <= MAX_CHUNK_WORDS:
            overlap_text = " ".join(
                line.strip() for line in overlap if line.strip()
            )
            final_text = (
                f"{overlap_text}\n\n{heading}\n{full_text}"
                if overlap_text
                else f"{heading}\n{full_text}"
            )
            chunks.append(final_text.strip())
        else:
            sub_chunks = split_on_sentences(full_text, heading, overlap)
            chunks.extend(sub_chunks)

    def split_on_sentences(text, heading, overlap):
        sub_chunks = []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        current_words = []
        current_sentences = []
        is_first = True

        for sentence in sentences:
            sentence_words = sentence.split()

            if (
                len(current_words) + len(sentence_words) > MAX_CHUNK_WORDS
                and current_words
            ):
                chunk_text = " ".join(current_words)
                overlap_text = " ".join(
                    line.strip() for line in overlap if line.strip()
                )
                final = (
                    f"{overlap_text}\n\n{heading}\n{chunk_text}"
                    if is_first and overlap_text
                    else f"{heading}\n{chunk_text}"
                )
                sub_chunks.append(final.strip())
                overlap_sentences = current_sentences[-OVERLAP_LINES:]
                current_words = " ".join(overlap_sentences).split()
                current_sentences = overlap_sentences
                is_first = False

            current_words.extend(sentence_words)
            current_sentences.append(sentence)

        if current_words:
            chunk_text = " ".join(current_words)
            overlap_text = " ".join(
                line.strip() for line in overlap if line.strip()
            )
            final = (
                f"{overlap_text}\n\n{heading}\n{chunk_text}"
                if is_first and overlap_text
                else f"{heading}\n{chunk_text}"
            )
            sub_chunks.append(final.strip())

        return sub_chunks

    for page_text in pages:
        for line in page_text.splitlines():
            if is_heading(line):
                overlap = current_lines[-OVERLAP_LINES:] if current_lines else []
                flush(current_heading, current_lines, last_lines_for_overlap)
                last_lines_for_overlap = overlap
                current_heading = line.strip()
                current_lines = []
            else:
                if line.strip():
                    current_lines.append(line)

    flush(current_heading, current_lines, last_lines_for_overlap)
    logger.info("Total chunks: %d", len(chunks))
    return chunks

# ---------------- EMBEDDING ----------------

def create_embedding(text):
    response = google_client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=text,
        config={"output_dimensionality": 1024}
    )
    return response.embeddings[0].values


def create_embeddings_parallel(chunks):
    """
    Call Google embedding API in parallel.
    Returns list of (index, text, vector) in correct order.
    """
    results = [None] * len(chunks)

    def embed_one(index, text):
        vector = create_embedding(text)
        return index, text, vector

    logger.info(
        "Creating embeddings for %d chunks with %d workers",
        len(chunks),
        EMBED_WORKERS
    )

    with ThreadPoolExecutor(max_workers=EMBED_WORKERS) as executor:
        futures = {
            executor.submit(embed_one, i, text): i
            for i, text in enumerate(chunks)
        }

        for future in as_completed(futures):
            index, text, vector = future.result()
            results[index] = (text, vector)
            logger.info("Embedded chunk %d/%d", index + 1, len(chunks))

    return results

# ---------------- DATABASE ----------------

def get_db():
    if not PGVECTOR_DSN:
        raise Exception("PGVECTOR_DSN missing")
    return psycopg2.connect(PGVECTOR_DSN)


def save_vectors(conn, source_key, chunks):
    # Create all embeddings in parallel
    embedded = create_embeddings_parallel(chunks)

    rows = []
    for index, (text, vector) in enumerate(embedded):
        vector_string = "[" + ",".join(str(v) for v in vector) + "]"
        rows.append((source_key, index, text, vector_string))

    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PGVECTOR_TABLE} (
                id          BIGSERIAL PRIMARY KEY,
                source_key  TEXT,
                chunk_index INTEGER,
                content     TEXT,
                embedding   vector({EMBED_DIM}),
                UNIQUE (source_key, chunk_index)
            );
            """
        )
        cur.execute(
            f"DELETE FROM {PGVECTOR_TABLE} WHERE source_key = %s",
            (source_key,)
        )
        execute_values(
            cur,
            f"""
            INSERT INTO {PGVECTOR_TABLE}
                (source_key, chunk_index, content, embedding)
            VALUES %s
            ON CONFLICT (source_key, chunk_index) DO UPDATE
                SET content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding
            """,
            rows
        )

    conn.commit()
    logger.info("Saved %d chunks for %s", len(rows), source_key)
    return len(rows)

# ---------------- LAMBDA ----------------

def lambda_handler(event, context):
    processed = []
    conn = None

    try:
        conn = get_db()

        for bucket, key in get_s3_files(event):
            if not key.lower().endswith(".pdf"):
                continue

            pages = read_pdf(bucket, key)
            chunks = chunk_by_headings(pages)

            if not chunks:
                logger.warning("No text found in %s", key)
                continue

            count = save_vectors(conn, key, chunks)
            processed.append({"key": key, "chunks": count})

        return {
            "statusCode": 200,
            "body": json.dumps({"processed": processed})
        }

    except Exception as e:
        logger.exception(e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

    finally:
        if conn:
            conn.close()