from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.api.upload import router as upload_router
from app.api.chat import router as chat_router
from app.api.pdfs import router as pdfs_router



app=FastAPI()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)



app.include_router(upload_router)

app.include_router(chat_router)

app.include_router(pdfs_router)



@app.get("/")
def health():

    return {
        "status":"running"
    }