from fastapi import APIRouter

router = APIRouter()

@router.get("/get")
async def get_params():
    return {"params": {}}
