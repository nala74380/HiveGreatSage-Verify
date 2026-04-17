r"""
文件位置: app/main.py
文件名称: main.py
作者: HiveGreatSage Dev
日期/时间: 2026-04-16
版本: v1.0.0
功能说明:
    FastAPI 应用入口。负责：
      1. 应用生命周期管理（lifespan：启动检查 + 关闭清理）
      2. 中间件注册（CORS、请求日志）
      3. 路由注册（所有子路由）
      4. 日志初始化（loguru）
      5. Sentry 集成（生产环境）
      6. 生产环境安全检查（DEBUG=False、SECRET_KEY 强度）
改进历史: 无
调试信息:
    启动命令（开发）：uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    访问 API 文档：http://localhost:8000/docs
    若 SENTRY_DSN 为空则 Sentry 不启动（正常现象）。
"""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.database import dispose_all_engines


# ── 日志初始化（loguru）──────────────────────────────────────
def _setup_logging() -> None:
    """配置 loguru：控制台 + 文件轮转（生产环境输出 JSON）。"""
    logger.remove()  # 移除默认 handler

    # 控制台输出
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        colorize=True,
    )

    # 文件输出（按天轮转，保留 30 天）
    if settings.LOG_FILE:
        import os
        os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
        logger.add(
            settings.LOG_FILE,
            level=settings.LOG_LEVEL,
            rotation="00:00",       # 每天午夜轮转
            retention="30 days",
            compression="zip",
            serialize=settings.ENVIRONMENT == "production",  # 生产环境输出 JSON
            encoding="utf-8",
        )


# ── Sentry 初始化（D6 决策，DSN 为空则跳过）──────────────────
def _setup_sentry() -> None:
    if not settings.SENTRY_DSN:
        logger.info("Sentry DSN 未配置，跳过初始化")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            environment=settings.ENVIRONMENT,
            traces_sample_rate=0.1,  # 采样 10% 的事务用于性能监控
        )
        logger.info("Sentry 已初始化")
    except ImportError:
        logger.warning("sentry-sdk 未安装，跳过 Sentry 初始化")


# ── 生产环境安全检查 ──────────────────────────────────────────
def _production_safety_check() -> None:
    if settings.ENVIRONMENT != "production":
        return
    errors = []
    if settings.DEBUG:
        errors.append("生产环境 DEBUG 必须为 False")
    if settings.SECRET_KEY == "change-this-to-a-random-32-byte-string-in-production":
        errors.append("生产环境 SECRET_KEY 必须更换为随机强密钥")
    if len(settings.SECRET_KEY) < 32:
        errors.append("SECRET_KEY 长度不足 32 字节，存在安全风险")
    if errors:
        for err in errors:
            logger.critical(f"[安全检查失败] {err}")
        raise RuntimeError("生产环境安全检查未通过，拒绝启动")


# ── 应用生命周期 ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动和关闭的钩子函数。"""
    # ── 启动 ──────────────────────────────────────────────
    _setup_logging()
    _setup_sentry()
    _production_safety_check()

    logger.info(
        f"HiveGreatSage-Verify 启动 | "
        f"环境={settings.ENVIRONMENT} | "
        f"AT有效期={settings.ACCESS_TOKEN_EXPIRE_MINUTES}min | "
        f"RT有效期={settings.REFRESH_TOKEN_EXPIRE_DAYS}天"
    )

    yield  # 应用运行中

    # ── 关闭 ──────────────────────────────────────────────
    logger.info("关闭数据库连接池...")
    await dispose_all_engines()
    logger.info("HiveGreatSage-Verify 已关闭")


# ── FastAPI 应用实例 ───────────────────────────────────────────
app = FastAPI(
    title="HiveGreatSage-Verify",
    description="蜂巢·大圣平台 — 网络验证系统（中枢）",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,    # 生产环境关闭 Swagger UI
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── CORS 中间件 ───────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由注册 ──────────────────────────────────────────────────
from app.routers import auth, users, agents, device, params, update, admin  # noqa: E402

app.include_router(auth.router,   prefix="/api/auth",   tags=["认证"])
app.include_router(users.router,  prefix="/api/users",  tags=["用户管理"])
app.include_router(agents.router, prefix="/api/agents", tags=["代理管理"])
app.include_router(device.router, prefix="/api/device", tags=["设备数据"])
app.include_router(params.router, prefix="/api/params", tags=["脚本参数"])
app.include_router(update.router, prefix="/api/update", tags=["热更新"])
app.include_router(admin.router,  prefix="/admin/api",  tags=["管理后台"])


# ── 健康检查 ──────────────────────────────────────────────────
@app.get("/health", tags=["系统"])
async def health_check():
    """服务健康检查（nginx upstream check / 部署监控使用）。"""
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
    }