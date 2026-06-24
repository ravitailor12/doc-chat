from fastapi import APIRouter, UploadFile, File

from app.utils.file_validator import validate_pdf
from app.services.s3_service import upload_pdf_to_s3
from app.schema.upload_schema import UploadResponse


router = APIRouter(
    prefix="/upload",
    tags=["PDF Upload"]
)


@router.post("/", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...)
):

    validate_pdf(file)


    s3_path = upload_pdf_to_s3(file)


    return UploadResponse(
        file_name=file.filename,
        s3_location=s3_path,
        message="PDF uploaded successfully"
    )