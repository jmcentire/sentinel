"""Test runner — executes tests via subprocess and parses results."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TestFailureDetail:
    """Details of a single test failure."""
    test_id: str = ""
    error_message: str = ""
    stdout: str = ""
    stderr: str = ""


@dataclass
class TestResults:
    """Aggregated test run results."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failure_details: list[TestFailureDetail] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0


async def run_tests(
    test_path: Path,
    source_dir: Path,
    language: str = "python",
    timeout: int = 120,
    temp_dir: Path | None = None,
) -> TestResults:
    """Run tests via subprocess. Copies to temp_dir if provided for isolation."""
    if temp_dir:
        return await _run_in_temp(test_path, source_dir, language, timeout, temp_dir)
    return await _run_direct(test_path, source_dir, language, timeout)


async def _run_in_temp(
    test_path: Path,
    source_dir: Path,
    language: str,
    timeout: int,
    temp_dir: Path,
) -> TestResults:
    """Copy source and tests to temp dir, run there."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_src = temp_dir / "src"
    temp_test = temp_dir / "tests"

    if source_dir.exists():
        shutil.copytree(source_dir, temp_src, dirs_exist_ok=True)
    if test_path.is_dir():
        shutil.copytree(test_path, temp_test, dirs_exist_ok=True)
    else:
        temp_test.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_path, temp_test / test_path.name)
        test_path = temp_test / test_path.name

    return await _run_direct(test_path, temp_src, language, timeout, cwd=temp_dir)


async def _run_direct(
    test_path: Path,
    source_dir: Path,
    language: str,
    timeout: int,
    cwd: Path | None = None,
) -> TestResults:
    """Execute tests directly."""
    if language == "python":
        return await _run_pytest(test_path, source_dir, timeout, cwd)
    return TestResults()


async def _run_pytest(
    test_path: Path,
    source_dir: Path,
    timeout: int,
    cwd: Path | None = None,
) -> TestResults:
    """Run pytest and parse results."""
    report_file = Path(tempfile.mktemp(suffix=".json"))

    cmd = [
        "python", "-m", "pytest",
        str(test_path),
        f"--json-report-file={report_file}",
        "--json-report",
        "-q",
        "--tb=short",
        "--no-header",
    ]

    env_cwd = cwd or (test_path.parent if test_path.is_file() else test_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(env_cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PYTHONPATH": str(source_dir), "PYTHONUNBUFFERED": "1"},
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()  # type: ignore[union-attr]
        return TestResults(errors=1, failure_details=[
            TestFailureDetail(test_id="<timeout>", error_message=f"Tests timed out after {timeout}s"),
        ])
    except FileNotFoundError:
        return TestResults(errors=1, failure_details=[
            TestFailureDetail(test_id="<missing>", error_message="pytest not found"),
        ])

    # Try JSON report first, fall back to exit code parsing
    if report_file.exists():
        try:
            return _parse_json_report(report_file)
        except Exception:
            pass
        finally:
            report_file.unlink(missing_ok=True)

    return _parse_exit_code(proc.returncode or 0, stdout.decode(), stderr.decode())


def _parse_json_report(report_file: Path) -> TestResults:
    """Parse pytest-json-report output."""
    data = json.loads(report_file.read_text())
    summary = data.get("summary", {})
    tests = data.get("tests", [])

    failures = []
    for test in tests:
        if test.get("outcome") in ("failed", "error"):
            call = test.get("call", {})
            failures.append(TestFailureDetail(
                test_id=test.get("nodeid", ""),
                error_message=call.get("longrepr", "")[:500],
            ))

    return TestResults(
        total=summary.get("total", len(tests)),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        errors=summary.get("error", 0),
        failure_details=failures,
    )


def _parse_exit_code(rc: int, stdout: str, stderr: str) -> TestResults:
    """Fallback: infer results from exit code."""
    if rc == 0:
        return TestResults(total=1, passed=1)
    return TestResults(
        total=1,
        failed=1,
        failure_details=[TestFailureDetail(
            test_id="<unknown>",
            error_message=stderr[:500] or stdout[:500],
        )],
    )
