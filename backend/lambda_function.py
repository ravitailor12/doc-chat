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

from google import genai


# ---------------- LOGGING ----------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)



# ---------------- CONFIG ----------------


AWS_REGION = os.environ.get(
    "AWS_REGION",
    "eu-north-1"
)


GOOGLE_API_KEY = os.environ.get(
    "GOOGLE_API_KEY"
)


EMBED_DIM = int(
    os.environ.get(
        "EMBED_DIM",
        "768"
    )
)


PGVECTOR_DSN = os.environ.get(
    "PGVECTOR_DSN"
)


PGVECTOR_TABLE = os.environ.get(
    "PGVECTOR_TABLE",
    "pdf_chunks"
)


MAX_CHUNK_CHARS = int(
    os.environ.get(
        "MAX_CHUNK_CHARS",
        "4000"
    )
)



# ---------------- CLIENTS ----------------


s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION
)


google_client = genai.Client(
    api_key=GOOGLE_API_KEY
)




# ---------------- EVENT PARSER ----------------


def get_s3_files(event):


    logger.info(
        "EVENT: %s",
        json.dumps(event)
    )


    # n8n direct payload

    if (
        event.get("bucket")
        and
        event.get("key")
    ):

        yield (
            event["bucket"],
            event["key"]
        )

        return



    # SQS/S3 event

    for record in event.get(
        "Records",
        []
    ):


        if "body" in record:


            body = json.loads(
                record["body"]
            )


            for s3_record in body.get(
                "Records",
                []
            ):

                yield extract_s3(
                    s3_record
                )


        else:

            yield extract_s3(
                record
            )




def extract_s3(record):

    s3 = record["s3"]

    bucket = s3["bucket"]["name"]

    key = unquote_plus(
        s3["object"]["key"]
    )

    return bucket, key




# ---------------- PDF ----------------


def read_pdf(bucket,key):


    logger.info(
        "Reading s3://%s/%s",
        bucket,
        key
    )


    obj = s3_client.get_object(
        Bucket=bucket,
        Key=key
    )


    data = obj["Body"].read()


    logger.info(
        "PDF SIZE %s",
        len(data)
    )


    reader = PdfReader(
        io.BytesIO(data)
    )


    pages=[]


    logger.info(
        "PAGES %s",
        len(reader.pages)
    )


    for page in reader.pages:


        text = page.extract_text() or ""

        pages.append(text)



    return pages




# ---------------- CHUNKING ----------------


def chunk_text(pages):


    text = "\n".join(
        pages
    )


    chunks=[]


    for part in re.split(
        r"\n\s*\n",
        text
    ):


        part = part.strip()


        if not part:

            continue



        while len(part) > MAX_CHUNK_CHARS:


            chunks.append(
                part[:MAX_CHUNK_CHARS]
            )


            part = part[
                MAX_CHUNK_CHARS:
            ]



        chunks.append(
            part
        )



    logger.info(
        "CHUNKS %s",
        len(chunks)
    )


    return chunks




# ---------------- GOOGLE EMBEDDING ----------------


def create_embedding(text):


    response = google_client.models.embed_content(

        model="models/gemini-embedding-001",

        contents=text,

        config={
            "output_dimensionality": 1024  # <-- Forces the API to output 1024 dimensions instead of 3072
        }

    )


    # The new SDK wraps values inside a structural list object
    return response.embeddings[0].values



# ---------------- DATABASE ----------------


def get_db():

    if not PGVECTOR_DSN:

        raise Exception(
            "PGVECTOR_DSN missing"
        )


    return psycopg2.connect(
        PGVECTOR_DSN
    )




def save_vectors(
    conn,
    source_key,
    chunks
):


    rows=[]


    for index,text in enumerate(chunks):


        vector = create_embedding(
            text
        )


        vector_string = (

            "["

            +

            ",".join(
                str(v)
                for v in vector
            )

            +

            "]"

        )


        rows.append(
            (
                source_key,
                index,
                text,
                vector_string
            )
        )



    with conn.cursor() as cur:


        cur.execute(
            f"""
            CREATE EXTENSION IF NOT EXISTS vector;


            CREATE TABLE IF NOT EXISTS {PGVECTOR_TABLE}
            (

            id BIGSERIAL PRIMARY KEY,

            source_key TEXT,

            chunk_index INTEGER,

            content TEXT,

            embedding vector({EMBED_DIM})

            );

            """
        )



        cur.execute(
            f"""
            DELETE FROM {PGVECTOR_TABLE}
            WHERE source_key=%s
            """,
            (
                source_key,
            )
        )



        execute_values(

            cur,

            f"""
            INSERT INTO {PGVECTOR_TABLE}
            (
            source_key,
            chunk_index,
            content,
            embedding
            )

            VALUES %s

            """,

            rows

        )



    conn.commit()



    return len(rows)




# ---------------- LAMBDA ----------------


def lambda_handler(event,context):


    processed=[]

    conn=None


    try:


        conn=get_db()



        for bucket,key in get_s3_files(event):


            if not key.lower().endswith(
                ".pdf"
            ):

                continue



            pages = read_pdf(
                bucket,
                key
            )



            chunks = chunk_text(
                pages
            )



            if not chunks:


                logger.warning(
                    "No text found"
                )

                continue




            count = save_vectors(

                conn,

                key,

                chunks

            )



            processed.append({

                "key":key,

                "chunks":count

            })




        return {


            "statusCode":200,


            "body":json.dumps({

                "processed":
                processed

            })


        }




    except Exception as e:


        logger.exception(e)


        return {


            "statusCode":500,


            "body":json.dumps({

                "error":
                str(e)

            })

        }



    finally:


        if conn:

            conn.close()