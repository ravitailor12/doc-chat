from app.core.aws import s3_client
from app.core.config import settings


def upload_pdf_to_s3(file):
    print("Current bucket:", settings.S3_BUCKET_NAME)
    file_key = f"uploads/{file.filename}"

    s3_client.upload_fileobj(
        file.file,
        settings.S3_BUCKET_NAME,
        file_key,
        ExtraArgs={
            "ContentType": "application/pdf"
        }
    )


    return f"s3://{settings.S3_BUCKET_NAME}/{file_key}"


def list_pdfs():
    """Return the PDFs currently stored under the uploads/ prefix in S3."""
    response = s3_client.list_objects_v2(
        Bucket=settings.S3_BUCKET_NAME,
        Prefix="uploads/",
    )

    pdfs = []
    for obj in response.get("Contents", []):
        key = obj["Key"]

        # Skip the "folder" placeholder object and anything that is not a PDF.
        if key.endswith("/") or not key.lower().endswith(".pdf"):
            continue

        pdfs.append({
            "key": key,                              # e.g. "uploads/report.pdf" (== source_key)
            "name": key.split("/")[-1],              # e.g. "report.pdf"
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
        })

    # Most recently uploaded first.
    pdfs.sort(key=lambda p: p["last_modified"], reverse=True)
    return pdfs


def delete_pdf_from_s3(key):
    """Permanently remove a single PDF object from the S3 bucket."""
    s3_client.delete_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
    )