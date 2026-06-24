from fastapi import APIRouter

from app.schema.chat_schema import ChatRequest

from app.services.rag_service import ask_question


router=APIRouter(
    prefix="/chat",
    tags=["Chat"]
)



@router.post("/")
def chat(
    request:ChatRequest
):

    return ask_question(
        request.question,
        source_key=request.source_key
    )