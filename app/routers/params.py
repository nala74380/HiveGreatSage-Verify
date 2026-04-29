r"""
文件位置: app/routers/params.py
文件名称: params.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.0.0
功能说明:
    脚本参数路由（薄层）：
      GET  /api/params/get  — 安卓脚本拉取当前用户的全部脚本参数
      POST /api/params/set  — PC 中控保存用户修改的参数值

    调用方：
      GET  → 安卓脚本（每次启动时拉取一次，作为运行参数）
      POST → PC 中控（用户在界面修改参数后提交）

    路由层职责：
      1. 鉴权（get_current_user + get_game_project_code）
      2. 获取游戏库 Session（按 game_project_code 动态路由）
      3. 调用 ParamsService，返回 HTTP 响应
      不包含任何业务判断逻辑。

关联文档:
    [[01-网络验证系统/架构设计]] 9. API 端点清单

改进历史:
    V1.0.0 - 从空桩重写为完整实现
调试信息:
    已知问题: 无
    404：param_key 不存在时单项返回 success=False（不抛 HTTP 404，部分成功模式）
    401：Token 无效或游戏项目信息缺失
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_game_project_code
from app.database import get_game_db
from app.models.main.models import User
from app.schemas.params import ParamsGetResponse, ParamsSetRequest, ParamsSetResponse
from app.services.params_service import get_user_params, set_user_params

router = APIRouter()


@router.get("/get", response_model=ParamsGetResponse, summary="拉取脚本参数")
async def get_params(
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
) -> ParamsGetResponse:
    """
    安卓脚本启动时调用，拉取当前用户在本游戏下的全部脚本参数。

    返回所有参数定义与用户值的合并结果：
    - 用户已设置的参数返回用户值（is_default=False）
    - 未设置的参数返回默认值（is_default=True）
    - 无默认值且未设置的参数 value="" 占位

    安卓脚本建议在每次启动后调用一次，无需高频轮询。
    """
    game_db_factory = get_game_db(game_project_code)
    async for game_db in game_db_factory():
        return await get_user_params(
            user_id=current_user.id,
            game_project_code=game_project_code,
            game_db=game_db,
        )


@router.post("/set", response_model=ParamsSetResponse, summary="保存脚本参数")
async def set_params(
    body: ParamsSetRequest,
    current_user: User = Depends(get_current_user),
    game_project_code: str = Depends(get_game_project_code),
) -> ParamsSetResponse:
    """
    PC 中控在用户修改参数后调用，保存参数值到游戏库。

    支持部分成功：列表中每一项独立验证，某项失败不影响其他项写入。
    响应中 results 字段返回每一项的成功/失败明细。

    参数值格式（JSON 字符串）：
    - int:    "42"
    - float:  "3.14"
    - bool:   "true" 或 "false"
    - string: "北境"（直接传字符串，不需要额外 JSON 转义）
    - enum:   "1"（枚举项的 value 字段值）
    """
    game_db_factory = get_game_db(game_project_code)
    async for game_db in game_db_factory():
        return await set_user_params(
            user_id=current_user.id,
            game_project_code=game_project_code,
            body=body,
            game_db=game_db,
        )
