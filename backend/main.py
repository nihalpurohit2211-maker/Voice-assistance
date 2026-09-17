from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.routers import auth, memories, chat, chats, voice

app = FastAPI(title="Voice Assistant Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(memories.router)
app.include_router(chat.router)
app.include_router(chats.router)
app.include_router(voice.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
