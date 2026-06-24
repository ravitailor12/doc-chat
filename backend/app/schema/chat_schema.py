from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):

    question: str

    # When set, the answer is restricted to chunks from this single PDF
    # (its value is the S3 object key, e.g. "uploads/report.pdf").
    source_key: Optional[str] = None
