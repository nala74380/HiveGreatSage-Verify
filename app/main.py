from fastapi import FastAPI
from app.config import settings
from app.database import engine
from app.routers import auth, users, agents, device, params, update, admin

app = FastAPI(title="HiveGreatSage Verify", version="0.1.0")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(device.router, prefix="/api/device", tags=["device"])
app.include_router(params.router, prefix="/api/params", tags=["params"])
app.include_router(update.router, prefix="/api/update", tags=["update"])
app.include_router(admin.router, prefix="/admin/api", tags=["admin"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
