r"""
文件位置: app/services/project_service.py
名称: 项目管理服务层
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-25
版本: V1.0.0
功能及相关说明:
    项目 CRUD + 代理项目授权 CRUD。
    游戏项目创建时自动填充 db_name；验证项目 db_name=None。

改进内容:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 游戏项目数据库的实际创建（CREATE DATABASE）在 Phase 2 实现，
              当前仅填写 db_name 字段，不自动建库。
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.main.models import Agent, AgentProjectAuth, Authorization, GameProject
from app.models.game.models import GameBase
from app.schemas.project import (
    AgentProjectAuthCreateRequest,
    AgentProjectAuthResponse,
    AgentProjectAuthUpdateRequest,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)

logger = logging.getLogger(__name__)


async def _provision_game_database(db_name: str) -> None:
    """
    为新游戏项目完整初始化其独立数据库。

    执行顺序：
      1. 创建数据库（已存在则跳过）
      2. 在游戏库中创建所有表
      3. 授予 hive_user 完整权限

    异常处理：建库失败时抛出 HTTPException，
    调用方没有 commit，主库中的 game_project 记录也不会路进库。
    """
    base_url = settings.DATABASE_MAIN_URL

    # Step 1: CREATE DATABASE——必须在 AUTOCOMMIT 连接中执行
    try:
        auto_url = make_url(base_url).set(database="postgres")
        auto_engine = create_async_engine(
            auto_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
            connect_args={"ssl": False},
        )
        async with auto_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": db_name},
            )
            if not result.scalar():
                await conn.execute(
                    text(f"CREATE DATABASE {db_name} OWNER hive_user")
                )
                logger.info("游戏库已创建: %s", db_name)
            else:
                logger.info("游戏库已存在，跳过: %s", db_name)
        await auto_engine.dispose()
    except Exception as e:
        logger.error("创建游戏库失败: %s, 原因: %s", db_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"游戏项目数据库创建失败: {e}",
        )

    # Step 2: 建表
    try:
        game_url = make_url(base_url).set(database=db_name)
        game_engine = create_async_engine(
            game_url,
            poolclass=NullPool,
            connect_args={"ssl": False},
        )
        async with game_engine.begin() as conn:
            await conn.run_sync(GameBase.metadata.create_all)
        await game_engine.dispose()
        logger.info("游戏库建表完成: %s", db_name)
    except Exception as e:
        logger.error("游戏库建表失败: %s, 原因: %s", db_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"游戏项目数据表创建失败: {e}",
        )

    # Step 3: 授权 hive_user
    try:
        grant_url = make_url(base_url).set(database=db_name)
        grant_engine = create_async_engine(
            grant_url,
            poolclass=NullPool,
            connect_args={"ssl": False},
        )
        async with grant_engine.begin() as conn:
            await conn.execute(text("GRANT USAGE ON SCHEMA public TO hive_user"))
            await conn.execute(
                text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hive_user")
            )
            await conn.execute(
                text("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hive_user")
            )
            await conn.execute(text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT ALL ON TABLES TO hive_user"
            ))
        await grant_engine.dispose()
        logger.info("游戏库授权完成: %s", db_name)
    except Exception as e:
        # 授权失败不阻断项目创建，仅记录警告
        logger.warning("游戏库授权失败（可手动执行 setup_game_db.sql 修复）: %s", e)


# ── 工具函数 ──────────────────────────────────────────────────

async def _project_to_response(
    project: GameProject,
    db: AsyncSession,
) -> ProjectResponse:
    user_count_result = await db.execute(
        select(func.count(Authorization.id))
        .where(
            Authorization.game_project_id == project.id,
            Authorization.status == "active",
        )
    )
    user_count = user_count_result.scalar_one()

    agent_count_result = await db.execute(
        select(func.count(AgentProjectAuth.id))
        .where(
            AgentProjectAuth.project_id == project.id,
            AgentProjectAuth.status == "active",
        )
    )
    agent_count = agent_count_result.scalar_one()

    return ProjectResponse(
        id=project.id,
        project_uuid=project.project_uuid,
        code_name=project.code_name,
        display_name=project.display_name,
        project_type=project.project_type,
        db_name=project.db_name,
        is_active=project.is_active,
        created_at=project.created_at,
        authorized_user_count=user_count,
        authorized_agent_count=agent_count,
    )


# ── 项目 CRUD ─────────────────────────────────────────────────

async def create_project(
    body: ProjectCreateRequest,
    db: AsyncSession,
) -> ProjectResponse:
    # code_name 唯一性检查
    existing = await db.execute(
        select(GameProject).where(GameProject.code_name == body.code_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"项目代号 '{body.code_name}' 已存在",
        )

    # 游戏项目：db_name = hive_{code_name}，验证项目为 None
    db_name = None
    if body.project_type == "game":
        db_name = f"hive_{body.code_name}"

    project = GameProject(
        code_name=body.code_name,
        display_name=body.display_name,
        project_type=body.project_type,
        db_name=db_name,
        is_active=True,
    )
    db.add(project)
    await db.flush()   # 先 flush 获取 project.id，建库失败可回滚

    # 游戏项目：自动创建独立数据库 + 建表 + 授权
    if body.project_type == "game" and db_name:
        await _provision_game_database(db_name)

    await db.commit()
    await db.refresh(project)

    return await _project_to_response(project, db)


async def list_projects(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    project_type: str | None = None,
    is_active: bool | None = None,
) -> ProjectListResponse:
    query = select(GameProject)
    if project_type:
        query = query.where(GameProject.project_type == project_type)
    if is_active is not None:
        query = query.where(GameProject.is_active == is_active)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(GameProject.id.desc()).offset(offset).limit(page_size)
    )
    projects = result.scalars().all()

    return ProjectListResponse(
        projects=[await _project_to_response(p, db) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_project(project_id: int, db: AsyncSession) -> ProjectResponse:
    project = await db.get(GameProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return await _project_to_response(project, db)


async def update_project(
    project_id: int,
    body: ProjectUpdateRequest,
    db: AsyncSession,
) -> ProjectResponse:
    project = await db.get(GameProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if body.display_name is not None:
        project.display_name = body.display_name
    if body.is_active is not None:
        project.is_active = body.is_active
    await db.commit()
    await db.refresh(project)
    return await _project_to_response(project, db)


# ── 代理项目授权 CRUD ─────────────────────────────────────────

async def grant_agent_project_auth(
    agent_id: int,
    body: AgentProjectAuthCreateRequest,
    db: AsyncSession,
) -> AgentProjectAuthResponse:
    # 代理存在检查
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")

    # 项目存在检查
    project = await db.get(GameProject, body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 已有授权检查
    existing = (await db.execute(
        select(AgentProjectAuth).where(
            AgentProjectAuth.agent_id == agent_id,
            AgentProjectAuth.project_id == body.project_id,
        )
    )).scalar_one_or_none()

    if existing:
        # 已存在则激活并更新到期时间
        existing.status = "active"
        existing.valid_until = body.valid_until
        auth = existing
    else:
        auth = AgentProjectAuth(
            agent_id=agent_id,
            project_id=body.project_id,
            valid_until=body.valid_until,
            status="active",
        )
        db.add(auth)

    await db.commit()
    await db.refresh(auth)
    return _auth_to_response(auth, project)


async def list_agent_project_auths(
    agent_id: int,
    db: AsyncSession,
) -> list[AgentProjectAuthResponse]:
    result = await db.execute(
        select(AgentProjectAuth, GameProject)
        .join(GameProject, AgentProjectAuth.project_id == GameProject.id)
        .where(AgentProjectAuth.agent_id == agent_id)
        .order_by(AgentProjectAuth.granted_at.desc())
    )
    rows = result.all()
    return [_auth_to_response(auth, project) for auth, project in rows]


async def update_agent_project_auth(
    auth_id: int,
    body: AgentProjectAuthUpdateRequest,
    db: AsyncSession,
) -> AgentProjectAuthResponse:
    auth = await db.get(AgentProjectAuth, auth_id)
    if not auth:
        raise HTTPException(status_code=404, detail="授权记录不存在")
    if body.status is not None:
        auth.status = body.status
    if "valid_until" in body.model_fields_set:
        auth.valid_until = body.valid_until
    await db.commit()
    await db.refresh(auth)
    project = await db.get(GameProject, auth.project_id)
    return _auth_to_response(auth, project)


async def revoke_agent_project_auth(auth_id: int, db: AsyncSession) -> None:
    auth = await db.get(AgentProjectAuth, auth_id)
    if not auth:
        raise HTTPException(status_code=404, detail="授权记录不存在")
    auth.status = "suspended"
    await db.commit()


def _auth_to_response(
    auth: AgentProjectAuth,
    project: GameProject,
) -> AgentProjectAuthResponse:
    return AgentProjectAuthResponse(
        id=auth.id,
        agent_id=auth.agent_id,
        project_id=auth.project_id,
        project_display_name=project.display_name,
        project_type=project.project_type,
        valid_until=auth.valid_until,
        status=auth.status,
        granted_at=auth.granted_at,
    )
