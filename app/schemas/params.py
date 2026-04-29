r"""
文件位置: app/schemas/params.py
文件名称: params.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-04-24
版本: V1.0.0
功能说明:
    脚本参数接口的 Pydantic v2 请求/响应模型。

    调用方说明：
      GET  /api/params/get  — 安卓脚本拉取参数（含完整定义 + 用户值）
      POST /api/params/set  — PC 中控保存参数值（逐项 UPSERT）

    参数值统一使用 JSON 字符串格式存储和传输：
      int:    "42"
      float:  "3.14"
      string: "\"北境\""
      bool:   "true"
      enum:   "1"  （枚举值的 value 字段）

关联文档:
    [[01-网络验证系统/架构设计]] 9. API 端点清单
    [[01-网络验证系统/数据库设计]] 游戏库 script_param_def / user_script_param

改进历史:
    V1.0.0 - 初始版本
"""

from pydantic import BaseModel, Field


# ── GET /api/params/get 响应 ──────────────────────────────────

class ParamItem(BaseModel):
    """单个参数的完整信息（定义 + 用户值）。"""
    param_key: str = Field(description="参数键名，如 farm_map_id")
    param_type: str = Field(description="参数类型：int / float / string / bool / enum")
    value: str = Field(description="当前生效值（用户已设置则用用户值，否则用默认值）")
    is_default: bool = Field(description="当前值是否为默认值（未被用户覆盖）")
    display_name: str | None = Field(default=None, description="PC 中控显示名称")
    description: str | None = Field(default=None, description="参数说明")
    options: list | None = Field(default=None, description="enum 类型的可选项列表")
    sort_order: int = Field(default=0, description="显示排序")


class ParamsGetResponse(BaseModel):
    """GET /api/params/get 响应体。"""
    game_project_code: str = Field(description="当前游戏项目代码名")
    params: list[ParamItem] = Field(description="所有参数列表（含用户值与默认值合并后的结果）")
    total: int = Field(description="参数总数")


# ── POST /api/params/set 请求 / 响应 ─────────────────────────

class ParamSetItem(BaseModel):
    """单个参数设置项。"""
    param_key: str = Field(
        ...,
        description="要修改的参数键名",
        examples=["farm_map_id"],
    )
    param_value: str = Field(
        ...,
        description="要设置的值（JSON 字符串格式），如 '42' / 'true' / '\"北境\"'",
        examples=["1"],
    )


class ParamsSetRequest(BaseModel):
    """POST /api/params/set 请求体。"""
    params: list[ParamSetItem] = Field(
        ...,
        min_length=1,
        description="要设置的参数列表，至少包含一项",
    )


class ParamSetResult(BaseModel):
    """单个参数设置结果。"""
    param_key: str
    success: bool
    error: str | None = None   # 设置失败时的原因（如键名不存在、类型校验失败）


class ParamsSetResponse(BaseModel):
    """POST /api/params/set 响应体。"""
    game_project_code: str
    updated_count: int = Field(description="成功设置的参数数量")
    failed_count: int = Field(description="设置失败的参数数量")
    results: list[ParamSetResult] = Field(description="每个参数的设置结果明细")
