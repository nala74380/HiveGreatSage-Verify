from fastapi import APIRouter

router = APIRouter()

@router.get("/check")
async def check_update():
    return {"need_update": False}
