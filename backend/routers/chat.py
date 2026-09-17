from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from backend.services.pipeline import run_pipeline
from backend.db.models import User
from backend.routers.auth import get_current_user

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

@router.post("/chat")
async def stateless_chat(request: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        result = await run_pipeline(current_user.id, request.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
