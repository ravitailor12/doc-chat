from pydantic import BaseModel


class UploadResponse(BaseModel):

    file_name: str
    s3_location: str
    message: str