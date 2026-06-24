from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str

    S3_BUCKET_NAME: str

    GOOGLE_API_KEY: str
    PGVECTOR_DSN: str
    PGVECTOR_TABLE: str = "pdf_chunks"


    class Config:
        env_file = ".env"


settings = Settings()