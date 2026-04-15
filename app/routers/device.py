from fastapi import APIRouter

router = APIRouter()

@router.post("/heartbeat")
async def heartbeat():
    return {"status": "received"}
