from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard")
async def admin_dashboard():
    return {"stats": {}}
