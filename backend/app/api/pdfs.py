from fastapi import APIRouter, HTTPException

from app.services.s3_service import list_pdfs, delete_pdf_from_s3
from app.services.rag_service import delete_document_vectors, get_document_status


router = APIRouter(
    prefix="/pdfs",
    tags=["PDFs"]
)


@router.get("/")
def get_pdfs():
    """List every PDF uploaded to S3 so the frontend can show them."""
    return {"pdfs": list_pdfs()}


@router.get("/status/{key:path}")
def pdf_status(key: str):
    """Tell the frontend whether a PDF has finished embedding into PGVector.

    Returns {"ready": bool, "chunks": int}.
    """
    if not key:
        raise HTTPException(status_code=400, detail="Missing document key.")

    try:
        return get_document_status(key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{key:path}")
def delete_pdf(key: str):
    """Delete a PDF everywhere: the S3 object and its vectors in PGVector.

    `key` is the full S3 object key, e.g. "uploads/report.pdf" (== source_key).
    """
    if not key:
        raise HTTPException(status_code=400, detail="Missing document key.")

    try:
        delete_pdf_from_s3(key)
        removed_chunks = delete_document_vectors(key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": key, "removed_chunks": removed_chunks}
