r"""
文件位置: app/services/params_service.py
文件名称: params_service.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.0.0
功能说明:
    脚本参数管理服务层，包含全部业务逻辑：
      - get_user_params()  拉取用户参数（定义 + 用户值合并）
      - set_user_params()  保存用户参数值（UPSERT，逐项验证）

    数据流说明：
      参数定义（script_param_def）由管理员/运维通过数据库直接维护，
      记录游戏有哪些可配置参数、类型、默认值。

      用户参数值（user_script_param）由 PC 中控通过接口写入，
      安卓脚本通过接口读取后与默认值合并作为运行参数。

    参数值类型校验规则：
      int:    值须能转换为 int
      float:  值须能转换为 float
      bool:   值须为 "true" 或 "false"（大小写不敏感）
      string: 不做格式校验
      enum:   值须在 options[].value 列表内

    跨库设计注意：
      user_id 跨库引用 hive_platform.user.id，无数据库外键，
      调用方（路由层）已通过 get_current_user 依赖确保 user_id 合法。

关联文档:
    [[01-网络验证系统/架构设计]] 9. API 端点清单
    [[01-网络验证系统/数据库设计]] 游戏库表结构

改进历史:
    V1.0.0 - 初始版本
调试信息:
    已知问题: 无
"""

import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game.models import ScriptParamDef, UserScriptParam
from app.schemas.params import (
    ParamItem,
    ParamSetItem,
    ParamSetResult,
    ParamsGetResponse,
    ParamsSetResponse,
    ParamsSetRequest,
)


# ─────────────────────────────────────────────────────────────
# 公开接口
# ─────────────────────────────────────────────────────────────

async def get_user_params(
    user_id: int,
    game_project_code: str,
    game_db: AsyncSession,
) -> ParamsGetResponse:
    """
    拉取指定用户在当前游戏下的所有脚本参数（定义 + 用户值合并）。

    合并规则：
      - 用户已设置过的参数：使用用户值，is_default=False
      - 用户未设置的参数：使用 default_value，is_default=True
      - 无默认值且用户未设置：value="" 占位，is_default=True

    按 sort_order 升序排列，保证 PC 中控显示顺序一致。
    """
    # 一次查询获取全部参数定义
    defs_result = await game_db.execute(
        select(ScriptParamDef).order_by(ScriptParamDef.sort_order, ScriptParamDef.id)
    )
    defs = defs_result.scalars().all()

    if not defs:
        return ParamsGetResponse(
            game_project_code=game_project_code,
            params=[],
            total=0,
        )

    # 一次查询获取该用户的所有已设置参数值（避免 N+1）
    def_ids = [d.id for d in defs]
    user_vals_result = await game_db.execute(
        select(UserScriptParam).where(
            UserScriptParam.user_id == user_id,
            UserScriptParam.param_def_id.in_(def_ids),
        )
    )
    # 构建 param_def_id → UserScriptParam 的映射
    user_val_map: dict[int, UserScriptParam] = {
        usp.param_def_id: usp for usp in user_vals_result.scalars().all()
    }

    # 合并定义和用户值
    items: list[ParamItem] = []
    for d in defs:
        user_val = user_val_map.get(d.id)
        if user_val is not None:
            value = user_val.param_value
            is_default = False
        else:
            value = d.default_value or ""
            is_default = True

        items.append(ParamItem(
            param_key=d.param_key,
            param_type=d.param_type,
            value=value,
            is_default=is_default,
            display_name=d.display_name,
            description=d.description,
            options=d.options,
            sort_order=d.sort_order,
        ))

    return ParamsGetResponse(
        game_project_code=game_project_code,
        params=items,
        total=len(items),
    )


async def set_user_params(
    user_id: int,
    game_project_code: str,
    body: ParamsSetRequest,
    game_db: AsyncSession,
) -> ParamsSetResponse:
    """
    保存用户脚本参数值（逐项验证 + UPSERT）。

    处理流程：
      1. 批量查询 body 中所有 param_key 对应的 ScriptParamDef
      2. 逐项验证：键名是否存在、值类型是否合法
      3. 对通过验证的参数执行 INSERT ... ON CONFLICT DO UPDATE
      4. 返回每项的成功/失败明细

    失败的参数不影响其他参数的写入（部分成功）。
    """
    # 批量查询参数定义（一次查询，避免 N+1）
    keys = [item.param_key for item in body.params]
    defs_result = await game_db.execute(
        select(ScriptParamDef).where(ScriptParamDef.param_key.in_(keys))
    )
    def_map: dict[str, ScriptParamDef] = {
        d.param_key: d for d in defs_result.scalars().all()
    }

    results: list[ParamSetResult] = []
    to_upsert: list[dict] = []   # 通过验证、待写入的记录

    for item in body.params:
        # 验证键名存在
        param_def = def_map.get(item.param_key)
        if not param_def:
            results.append(ParamSetResult(
                param_key=item.param_key,
                success=False,
                error=f"参数键名 '{item.param_key}' 不存在",
            ))
            continue

        # 验证值类型
        error = _validate_value(item.param_value, param_def)
        if error:
            results.append(ParamSetResult(
                param_key=item.param_key,
                success=False,
                error=error,
            ))
            continue

        # 通过验证，加入待写入列表
        to_upsert.append({
            "user_id": user_id,
            "param_def_id": param_def.id,
            "param_value": item.param_value,
        })
        results.append(ParamSetResult(param_key=item.param_key, success=True))

    # 批量 UPSERT（PostgreSQL INSERT ... ON CONFLICT DO UPDATE）
    if to_upsert:
        stmt = pg_insert(UserScriptParam).values(to_upsert)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "param_def_id"],
            set_={"param_value": stmt.excluded.param_value},
        )
        await game_db.execute(stmt)
        await game_db.flush()

    updated_count = sum(1 for r in results if r.success)
    failed_count = len(results) - updated_count

    return ParamsSetResponse(
        game_project_code=game_project_code,
        updated_count=updated_count,
        failed_count=failed_count,
        results=results,
    )


# ─────────────────────────────────────────────────────────────
# 内部辅助函数
# ─────────────────────────────────────────────────────────────

def _validate_value(value: str, param_def: ScriptParamDef) -> str | None:
    """
    验证参数值与参数定义的类型是否匹配。
    返回 None 表示验证通过，返回错误描述字符串表示失败。
    """
    t = param_def.param_type

    if t == "int":
        try:
            int(value)
        except (ValueError, TypeError):
            return f"类型错误：期望 int，收到 '{value}'"

    elif t == "float":
        try:
            float(value)
        except (ValueError, TypeError):
            return f"类型错误：期望 float，收到 '{value}'"

    elif t == "bool":
        if value.lower() not in ("true", "false"):
            return f"类型错误：期望 bool（true/false），收到 '{value}'"

    elif t == "enum":
        options = param_def.options
        if options:
            valid_values = [str(opt.get("value", "")) for opt in options]
            if value not in valid_values:
                return f"枚举值错误：'{value}' 不在可选项 {valid_values} 中"

    # string 类型：不做格式校验，任何非空字符串都合法
    elif t == "string":
        pass

    return None
