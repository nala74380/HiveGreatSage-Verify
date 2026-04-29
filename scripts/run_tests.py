r"""
文件位置: scripts/run_tests.py
名称: 自动化测试运行器 + Markdown 报告生成
作者: 蜂巢·大圣 (Hive-GreatSage)
时间: 2026-04-22
版本: V1.0.1
功能说明:
    一条命令运行所有测试，生成结构化 Markdown 报告。
    输出文件：logs/test_report_YYYYMMDD_HHMMSS.md
    同时打印到控制台（可直接粘贴给 Claude）。

    报告保留策略：只保留最近 3 份，自动删除更早的历史报告。

    运行命令：python scripts/run_tests.py

改进历史:
    V1.0.1 (2026-04-25) - 新增报告保留策略：只保留最近 3 份，自动清理历史报告
    V1.0.0 - 初始版本
"""

import json
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path


def run_tests() -> dict:
    """运行 pytest 并返回 JSON 报告数据。"""
    report_file = "logs/test_result_raw.json"
    os.makedirs("logs", exist_ok=True)

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/",
            "-v",
            "--tb=short",
            f"--json-report",
            f"--json-report-file={report_file}",
            "--json-report-indent=2",
            "-q",
        ],
        capture_output=True,
        text=True,
        encoding=None,
        errors="replace",
    )

    with open(report_file, "r", encoding="utf-8") as f:
        return json.load(f), result.stdout, result.stderr


def cleanup_old_reports(logs_dir: Path, keep: int = 3) -> None:
    """
    删除旧的测试报告，只保留最近 keep 份。
    只处理 test_report_*.md 格式的文件，不影响其他日志文件。
    """
    reports = sorted(
        logs_dir.glob("test_report_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,   # 最新的在前
    )
    to_delete = reports[keep:]   # 保留前 keep 个，其余删除
    for old_report in to_delete:
        try:
            old_report.unlink()
        except OSError:
            pass   # 删除失败静默忽略


def generate_report(data: dict, stdout: str) -> str:
    """将 pytest JSON 报告转换为 Markdown 格式。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = data.get("summary", {})
    tests = data.get("tests", [])

    total    = summary.get("total", 0)
    passed   = summary.get("passed", 0)
    failed   = summary.get("failed", 0)
    error    = summary.get("error", 0)
    skipped  = summary.get("skipped", 0)
    duration = data.get("duration", 0)

    status_icon = "✅" if failed == 0 and error == 0 else "❌"

    lines = [
        "# HiveGreatSage-Verify 测试报告",
        "",
        f"**生成时间**: {now}  ",
        "**环境**: development | PostgreSQL:15432 | Redis:16379",
        "",
        f"## 概览 {status_icon}",
        "",
        "| 总计 | 通过 | 失败 | 错误 | 跳过 | 耗时 |",
        "|------|------|------|------|------|------|",
        f"| {total} | {passed} | {failed} | {error} | {skipped} | {duration:.2f}s |",
        "",
    ]

    # 按模块分组
    modules: dict[str, list] = {}
    for t in tests:
        node_id = t.get("nodeid", "")
        module = node_id.split("::")[0].replace("tests/", "").replace(".py", "")
        modules.setdefault(module, []).append(t)

    lines.append("## 详细结果")
    lines.append("")

    for module, module_tests in modules.items():
        mod_passed = sum(1 for t in module_tests if t.get("outcome") == "passed")
        mod_failed = sum(1 for t in module_tests if t.get("outcome") in ("failed", "error"))
        mod_icon = "✅" if mod_failed == 0 else "❌"
        lines.append(f"### {mod_icon} {module} ({mod_passed}/{len(module_tests)} 通过)")
        lines.append("")

        for t in module_tests:
            outcome = t.get("outcome", "unknown")
            duration_t = t.get("duration", 0)
            name = t.get("nodeid", "").split("::")[-1]

            icon = "✓" if outcome == "passed" else ("✗" if outcome in ("failed", "error") else "○")
            lines.append(f"  {icon} `{name}` ({duration_t:.3f}s)")

            if outcome in ("failed", "error"):
                longrepr = ""
                for phase in ("setup", "call", "teardown"):
                    phase_data = t.get(phase, {})
                    if phase_data.get("longrepr"):
                        longrepr = f"[{phase}] " + phase_data["longrepr"]
                        break
                if longrepr:
                    error_lines = [l for l in longrepr.strip().split("\n") if l.strip()]
                    short_error = "\n".join(error_lines[-3:])
                    lines.append("    ```")
                    lines.append(f"    {short_error}")
                    lines.append("    ```")

        lines.append("")

    # 失败汇总
    failed_tests = [t for t in tests if t.get("outcome") in ("failed", "error")]
    if failed_tests:
        lines.append("## ❌ 失败明细")
        lines.append("")
        for t in failed_tests:
            lines.append(f"**{t.get('nodeid', '')}**")
            call = t.get("call", {})
            longrepr = call.get("longrepr", "")
            if longrepr:
                lines.append("```")
                lines.append(longrepr[-500:])
                lines.append("```")
            lines.append("")

    lines.append("---")
    lines.append("*由 `scripts/run_tests.py` 自动生成*")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print(" HiveGreatSage-Verify 自动化测试")
    print("=" * 60)
    print()

    try:
        data, stdout, stderr = run_tests()
    except Exception as e:
        print(f"❌ 测试运行失败: {e}")
        sys.exit(1)

    report = generate_report(data, stdout)

    # 保存新报告
    logs_dir = Path("logs")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = logs_dir / f"test_report_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")

    # 清理旧报告（保留最近 3 份）
    cleanup_old_reports(logs_dir, keep=3)

    # 打印到控制台
    print(report)
    print()
    print(f"📄 报告已保存至: {report_path}（logs/ 目录保留最近 3 份）")
    print()
    print("将以上报告内容粘贴给 Claude 即可。")


if __name__ == "__main__":
    main()
