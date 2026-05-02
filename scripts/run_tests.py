r"""
文件位置: scripts/run_tests.py
文件名称: run_tests.py
作者: 蜂巢·大圣 (Hive-GreatSage)
日期/时间: 2026-05-02
版本: V1.1.0
功能说明:
    自动化测试运行器与 Markdown 测试报告生成器。

    当前定位:
      1. 本脚本用于开发期 / 测试期运行 pytest。
      2. 本脚本生成的 Markdown 报告与 JSON 原始结果均属于运行产物。
      3. 报告产物不得进入源码真相源。
      4. 报告产物目录应被 .gitignore 忽略。

    默认输出:
      logs/test_reports/test_result_raw_latest.json
      logs/test_reports/test_report_YYYYMMDD_HHMMSS.md

    安全与治理要求:
      1. 报告不使用彩色 emoji。
      2. 报告不硬编码 PostgreSQL / Redis 地址。
      3. 报告只记录必要环境摘要，不输出数据库密码、Redis 密码、Token、密钥。
      4. 测试失败报告只能说明测试结果，不代表源码整改已完成。

运行方式:
    python scripts/run_tests.py

可选参数:
    python scripts/run_tests.py --report-dir logs/test_reports
    python scripts/run_tests.py --keep 5
    python scripts/run_tests.py --pytest-args "-k test_auth -v"

改进历史:
    V1.1.0 (2026-05-02) - 去除彩色 emoji；移除硬编码环境信息；报告目录改为运行产物目录。
    V1.0.1 (2026-04-25) - 新增报告保留策略：只保留最近 3 份，自动清理历史报告。
    V1.0.0 - 初始版本。
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_REPORT_DIR = Path("logs/test_reports")
DEFAULT_KEEP_REPORTS = 3
RAW_REPORT_FILENAME = "test_result_raw_latest.json"


@dataclass(frozen=True)
class TestRunOptions:
    report_dir: Path
    keep_reports: int
    pytest_args: list[str]


@dataclass(frozen=True)
class TestRunResult:
    data: dict[str, Any]
    stdout: str
    stderr: str
    returncode: int
    raw_report_path: Path


def _mask_url(value: str | None) -> str:
    if not value:
        return "not configured"

    try:
        parsed = urlparse(value)
    except Exception:
        return "configured"

    if not parsed.scheme:
        return "configured"

    host = parsed.hostname or "unknown-host"
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path.lstrip("/") if parsed.path else ""

    if database:
        return f"{parsed.scheme}://{host}{port}/{database}"

    return f"{parsed.scheme}://{host}{port}"


def _read_environment_summary() -> dict[str, str]:
    environment = (
        os.getenv("ENVIRONMENT")
        or os.getenv("APP_ENV")
        or os.getenv("HGS_ENV")
        or "not configured"
    )

    database_url = (
        os.getenv("DATABASE_MAIN_URL")
        or os.getenv("DATABASE_URL")
        or "not configured"
    )

    redis_url = os.getenv("REDIS_URL") or os.getenv("HGS_REDIS_URL")

    return {
        "environment": environment,
        "database": _mask_url(database_url),
        "redis": _mask_url(redis_url),
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }


def _ensure_report_dir(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)


def _build_pytest_command(options: TestRunOptions, raw_report_path: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--json-report",
        f"--json-report-file={raw_report_path}",
        "--json-report-indent=2",
        "-q",
    ]

    command.extend(options.pytest_args)

    return command


def run_tests(options: TestRunOptions) -> TestRunResult:
    """运行 pytest 并返回 JSON 报告数据。"""
    _ensure_report_dir(options.report_dir)

    raw_report_path = options.report_dir / RAW_REPORT_FILENAME
    command = _build_pytest_command(options, raw_report_path)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if not raw_report_path.exists():
        raise RuntimeError(
            "pytest 未生成 JSON 报告。"
            f"\n命令：{' '.join(command)}"
            f"\n返回码：{result.returncode}"
            f"\nstdout:\n{result.stdout[-2000:]}"
            f"\nstderr:\n{result.stderr[-2000:]}"
        )

    with raw_report_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return TestRunResult(
        data=data,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
        raw_report_path=raw_report_path,
    )


def cleanup_old_reports(report_dir: Path, keep: int) -> None:
    """
    删除旧的 Markdown 测试报告，只保留最近 keep 份。
    只处理 test_report_*.md，不删除 JSON latest 文件。
    """
    if keep <= 0:
        return

    reports = sorted(
        report_dir.glob("test_report_*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_report in reports[keep:]:
        try:
            old_report.unlink()
        except OSError:
            pass


def _extract_failure_text(test_item: dict[str, Any], max_chars: int = 1200) -> str:
    for phase in ("setup", "call", "teardown"):
        phase_data = test_item.get(phase, {})
        longrepr = phase_data.get("longrepr")
        if longrepr:
            text = str(longrepr)
            if len(text) > max_chars:
                return text[-max_chars:]
            return text

    return ""


def _status_label(outcome: str) -> str:
    if outcome == "passed":
        return "PASS"
    if outcome == "failed":
        return "FAIL"
    if outcome == "error":
        return "ERROR"
    if outcome == "skipped":
        return "SKIP"
    return outcome.upper() if outcome else "UNKNOWN"


def generate_report(test_result: TestRunResult) -> str:
    """将 pytest JSON 报告转换为 Markdown 格式。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = test_result.data
    summary = data.get("summary", {})
    tests = data.get("tests", [])
    environment = _read_environment_summary()

    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    error = summary.get("error", 0)
    skipped = summary.get("skipped", 0)
    duration = float(data.get("duration", 0) or 0)

    overall_status = "PASS" if failed == 0 and error == 0 and test_result.returncode == 0 else "FAIL"

    lines: list[str] = [
        "# HiveGreatSage-Verify 测试报告",
        "",
        "## 一、报告说明",
        "",
        "- 本报告由 `scripts/run_tests.py` 自动生成。",
        "- 本报告属于运行产物，不属于源码真相源。",
        "- 本报告不得作为旧字段、旧接口、旧边界继续保留的依据。",
        "- 测试通过不等于前端联调、三端联调、部署验收、安全验收全部完成。",
        "",
        "## 二、运行环境摘要",
        "",
        f"- 生成时间：{now}",
        f"- 总体状态：{overall_status}",
        f"- pytest 返回码：{test_result.returncode}",
        f"- ENVIRONMENT / APP_ENV：{environment['environment']}",
        f"- 数据库连接摘要：{environment['database']}",
        f"- Redis 连接摘要：{environment['redis']}",
        f"- Python：{environment['python']}",
        f"- 平台：{environment['platform']}",
        f"- 原始 JSON：`{test_result.raw_report_path.as_posix()}`",
        "",
        "## 三、概览",
        "",
        "| 总计 | 通过 | 失败 | 错误 | 跳过 | 耗时 |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {total} | {passed} | {failed} | {error} | {skipped} | {duration:.2f}s |",
        "",
    ]

    modules: dict[str, list[dict[str, Any]]] = {}
    for test_item in tests:
        node_id = test_item.get("nodeid", "")
        module = node_id.split("::")[0].replace("tests/", "").replace(".py", "")
        modules.setdefault(module, []).append(test_item)

    lines.extend(
        [
            "## 四、按模块结果",
            "",
        ]
    )

    for module_name in sorted(modules):
        module_tests = modules[module_name]
        module_passed = sum(
            1 for test_item in module_tests if test_item.get("outcome") == "passed"
        )
        module_failed = sum(
            1
            for test_item in module_tests
            if test_item.get("outcome") in ("failed", "error")
        )
        module_status = "PASS" if module_failed == 0 else "FAIL"

        lines.append(
            f"### {module_name} - {module_status} ({module_passed}/{len(module_tests)} 通过)"
        )
        lines.append("")
        lines.append("| 状态 | 用例 | 耗时 |")
        lines.append("|---|---|---:|")

        for test_item in module_tests:
            outcome = test_item.get("outcome", "unknown")
            duration_t = float(test_item.get("duration", 0) or 0)
            test_name = test_item.get("nodeid", "").split("::")[-1]
            lines.append(
                f"| {_status_label(outcome)} | `{test_name}` | {duration_t:.3f}s |"
            )

        lines.append("")

    failed_tests = [
        test_item
        for test_item in tests
        if test_item.get("outcome") in ("failed", "error")
    ]

    lines.extend(
        [
            "## 五、失败 / 错误明细",
            "",
        ]
    )

    if not failed_tests:
        lines.append("本次没有失败或错误用例。")
        lines.append("")
    else:
        for test_item in failed_tests:
            node_id = test_item.get("nodeid", "")
            outcome = _status_label(test_item.get("outcome", "unknown"))
            failure_text = _extract_failure_text(test_item)

            lines.append(f"### {node_id}")
            lines.append("")
            lines.append(f"- 状态：{outcome}")
            lines.append("")

            if failure_text:
                lines.append("```text")
                lines.append(failure_text)
                lines.append("```")
                lines.append("")
            else:
                lines.append("未获取到详细错误信息。")
                lines.append("")

    lines.extend(
        [
            "## 六、stdout / stderr 摘要",
            "",
            "### stdout 尾部",
            "",
            "```text",
            test_result.stdout[-2000:] if test_result.stdout else "",
            "```",
            "",
            "### stderr 尾部",
            "",
            "```text",
            test_result.stderr[-2000:] if test_result.stderr else "",
            "```",
            "",
            "---",
            "",
            "由 `scripts/run_tests.py` 自动生成。",
        ]
    )

    return "\n".join(lines)


def _parse_args() -> TestRunOptions:
    parser = argparse.ArgumentParser(
        description="运行 HiveGreatSage-Verify 自动化测试并生成 Markdown 报告。"
    )

    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help=f"测试报告输出目录。默认：{DEFAULT_REPORT_DIR.as_posix()}",
    )

    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP_REPORTS,
        help=f"保留最近 N 份 Markdown 测试报告。默认：{DEFAULT_KEEP_REPORTS}",
    )

    parser.add_argument(
        "--pytest-args",
        default="",
        help='附加 pytest 参数，例如：--pytest-args "-k test_auth -v"',
    )

    args = parser.parse_args()

    pytest_args = shlex.split(args.pytest_args) if args.pytest_args else []

    return TestRunOptions(
        report_dir=Path(args.report_dir),
        keep_reports=max(args.keep, 0),
        pytest_args=pytest_args,
    )


def main() -> None:
    options = _parse_args()

    print("=" * 60)
    print(" HiveGreatSage-Verify 自动化测试")
    print("=" * 60)
    print()
    print(f"报告目录：{options.report_dir.as_posix()}")
    print(f"保留报告数：{options.keep_reports}")
    print()

    try:
        test_result = run_tests(options)
        report = generate_report(test_result)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = options.report_dir / f"test_report_{timestamp}.md"
        report_path.write_text(report, encoding="utf-8")

        cleanup_old_reports(options.report_dir, keep=options.keep_reports)

        print(report)
        print()
        print(f"REPORT_PATH={report_path.as_posix()}")
        print(f"RAW_JSON_PATH={test_result.raw_report_path.as_posix()}")
        print()

        if test_result.returncode != 0:
            print("ERROR pytest 返回非 0。请查看报告中的失败 / 错误明细。")
            raise SystemExit(test_result.returncode)

        print("OK pytest 执行完成。")

    except SystemExit:
        raise
    except Exception as exc:
        print()
        print("ERROR 测试运行失败。")
        print(f"原因：{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()