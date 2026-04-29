r"""
文件位置: app/models/game/__init__.py
文件名称: __init__.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-22
版本: V1.0.0
功能说明:
    游戏库模型包的公开接口。
    显式导出 GameBase 和所有游戏库模型，供 init_data.py 和
    admin/projects 接口调用 GameBase.metadata.create_all() 建表。

    注意：此包不导出到主库 Alembic 迁移，env.py 只使用主库 Base.metadata。

改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

from app.models.game.models import (  # noqa: F401
    DeviceRuntime,
    GameBase,
    ProjectConfig,
    ScriptParamDef,
    UserScriptParam,
    VersionRecord,
)

__all__ = [
    "GameBase",
    "ProjectConfig",
    "ScriptParamDef",
    "UserScriptParam",
    "DeviceRuntime",
    "VersionRecord",
]
