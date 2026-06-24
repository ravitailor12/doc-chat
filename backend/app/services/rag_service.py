import json
import logging
import psycopg2
from google import genai

from app.core.config import settings

# ---------------- LOGGING & CONFIG ----------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

GOOGLE_API_KEY = settings.GOOGLE_API_KEY
PGVECTOR_DSN = settings.PGVECTOR_DSN
PGVECTOR_TABLE = settings.PGVECTOR_TABLE

# Initialize the Gemini Client
google_client = genai.Client(api_key=GOOGLE_API_KEY)


def get_db():
    if not PGVECTOR_DSN:
        raise Exception("PGVECTOR_DSN missing from environment variables.")
    return psycopg2.connect(PGVECTOR_DSN)


# ---------------- DELETE A DOCUMENT'S VECTORS ----------------
def delete_document_vectors(source_key):
    """Remove every chunk/embedding belonging to a single PDF from PGVector."""
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            # Table may not exist yet if no PDF has ever been processed.
            cur.execute("SELECT to_regclass(%s)", (PGVECTOR_TABLE,))
            if cur.fetchone()[0] is None:
                return 0

            cur.execute(
                f"DELETE FROM {PGVECTOR_TABLE} WHERE source_key = %s",
                (source_key,),
            )
            deleted = cur.rowcount
        conn.commit()
        return deleted
    finally:
        if conn:
            conn.close()


# ---------------- DOCUMENT PROCESSING STATUS ----------------
def get_document_status(source_key):
    """Report whether a PDF has finished being embedded into PGVector.

    Returns {"ready": bool, "chunks": int}. The document is considered ready
    once at least one chunk exists for its source_key.
    """
    conn = None
    try:
        conn = get_db()
        with conn.cursor() as cur:
            # Table may not exist yet if no PDF has ever been processed.
            cur.execute("SELECT to_regclass(%s)", (PGVECTOR_TABLE,))
            if cur.fetchone()[0] is None:
                return {"ready": False, "chunks": 0}

            cur.execute(
                f"SELECT COUNT(*) FROM {PGVECTOR_TABLE} WHERE source_key = %s",
                (source_key,),
            )
            count = cur.fetchone()[0]
        return {"ready": count > 0, "chunks": count}
    finally:
        if conn:
            conn.close()


# ---------------- 1. EMBED THE QUESTION ----------------
def embed_question(question_text):
    """Converts user query into a matching 1024-dimension vector."""
    response = google_client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=question_text,
        config={
            "output_dimensionality": 1024  # Must match your DB schema sizing!
        }
    )
    return response.embeddings[0].values


# ---------------- 2. RETRIEVE FROM PGVECTOR ----------------
def retrieve_top_chunks(conn, question_vector, limit=5, source_key=None):
    """Queries PGVector using Cosine Distance (<=>) for closest matches.

    When source_key is provided, retrieval is restricted to chunks belonging to
    that single PDF, so the answer only draws from that document.
    """
    # Convert Python float list to Postgres vector format string: '[0.1, 0.2, ...]'
    vector_string = "[" + ",".join(str(v) for v in question_vector) + "]"

    chunks = []
    with conn.cursor() as cur:
        # Cosine distance operator (<=>). Smaller distance = higher semantic similarity.
        if source_key:
            query = f"""
                SELECT content, source_key
                FROM {PGVECTOR_TABLE}
                WHERE source_key = %s
                ORDER BY embedding <=> %s
                LIMIT %s;
            """
            params = (source_key, vector_string, limit)
        else:
            query = f"""
                SELECT content, source_key
                FROM {PGVECTOR_TABLE}
                ORDER BY embedding <=> %s
                LIMIT %s;
            """
            params = (vector_string, limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        
        for row in rows:
            chunks.append({
                "content": row[0],
                "source_key": row[1]
            })
            
    return chunks


# ---------------- 3. GENERATE ANSWER VIA LLM ----------------
def generate_answer(question, chunks):
    """Combines matching chunks into context and asks Gemini to generate an answer."""
    
    # Merge the text content blocks cleanly
    context_text = "\n\n---\n\n".join([c["content"] for c in chunks])
    
    system_instruction = (
        "You are an expert AI document assistant. Answer the user's question "
        "strictly using only the provided Context details extracted from a PDF document. "
        "If the answer cannot be confidently derived from the context, state: "
        "'I cannot find the answer to that question within the uploaded document.'"
    )
    
    user_prompt = f"""
Context:
{context_text}

Question:
{question}
"""

    # Call your choice of generation model (gemini-2.5-flash is fast and ideal for RAG)
    response = google_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=user_prompt,
        config={
            "system_instruction": system_instruction,
            "temperature": 0.2, # Lower temperature makes the model stick closely to the context
        }
    )
    
    return response.text


# ---------------- MAIN ASK FUNCTION ----------------
def ask_question(question, source_key=None):
    logger.info("Processing user question: %s (source_key=%s)", question, source_key)
    conn = None

    try:
        # Step 1: Vectorize the query text
        question_vector = embed_question(question)

        # Step 2: Fetch matches from DB (scoped to one PDF when source_key is set)
        conn = get_db()
        matched_chunks = retrieve_top_chunks(conn, question_vector, limit=5, source_key=source_key)
        
        if not matched_chunks:
            return {
                "answer": "No reference documents found in the database. Please process a PDF first.",
                "sources": []
            }
            
        # Step 3: Synthesis
        answer = generate_answer(question, matched_chunks)
        
        # Pull distinct PDF filenames/keys that contributed to the context
        sources = list(set([c["source_key"] for c in matched_chunks]))
        
        return {
            "answer": answer,
            "sources": sources
        }

    except Exception as e:
        logger.exception("Failed to execute RAG pipeline.")
        return {
            "answer": f"An error occurred while answering your question: {str(e)}",
            "sources": []
        }
        
    finally:
        if conn:
            conn.close()