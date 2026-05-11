r"""
文件位置: scripts/export_openapi.py
名称: OpenAPI 快照导出脚本
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-05-11
版本: V1.0.0
功能及相关说明:
  从 FastAPI app 实例生成 OpenAPI schema，输出 JSON 快照和 Markdown 路由清单。
  纳入质量门禁：paths 数量为 0 时以非零退出码失败。

用法:
  python scripts/export_openapi.py
  python scripts/export_openapi.py --output-dir docs/openapi

改进内容:
  V1.0.0 - 初始版本

调试信息:
  依赖安装: pip install -r requirements.txt
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_OUTPUT_DIR = ROOT / "docs" / "openapi"


def export_openapi(output_dir: Path | None = None) -> dict:
    target_dir = output_dir or _OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # 延迟导入，确保 sys.path 已设置
    from app.main import app

    schema = app.openapi()
    paths_count = len(schema.get("paths", {}))
    schemas_count = len(schema.get("components", {}).get("schemas", {}))

    if paths_count == 0:
        print("错误：OpenAPI paths 数量为 0，拒绝生成空快照")
        sys.exit(1)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = target_dir / f"openapi_{timestamp}.json"
    json_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")

    md_path = target_dir / f"openapi_routes_{timestamp}.md"
    _write_routes_markdown(md_path, schema, paths_count, schemas_count, timestamp)

    print(f"OpenAPI 快照已生成:")
    print(f"  标题:     {schema.get('info', {}).get('title', 'N/A')}")
    print(f"  版本:     {schema.get('info', {}).get('version', 'N/A')}")
    print(f"  paths:    {paths_count}")
    print(f"  schemas:  {schemas_count}")
    print(f"  JSON:     {json_path}")
    print(f"  Markdown: {md_path}")

    return {"paths": paths_count, "schemas": schemas_count}


def _write_routes_markdown(
    path: Path, schema: dict, paths_count: int, schemas_count: int, timestamp: str
) -> None:
    paths_data = schema.get("paths", {})
    lines = [
        f"# Verify OpenAPI 路由清单 — {timestamp}",
        f"",
        f"**paths**: {paths_count} | **schemas**: {schemas_count}",
        f"",
        f"| 方法 | 路径 | summary |",
        f"|------|------|---------|",
    ]
    for route_path, methods in sorted(paths_data.items()):
        for method, detail in sorted(methods.items()):
            summary = detail.get("summary", "").replace("|", "\\|")
            lines.append(f"| {method.upper()} | {route_path} | {summary} |")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify OpenAPI 快照导出")
    parser.add_argument("--output-dir", type=Path, default=None, help="输出目录")
    args = parser.parse_args()
    export_openapi(args.output_dir)
