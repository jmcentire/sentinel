"""Fixer agent — LLM-driven production error repair with reproducer tests.

Spawned per attributed error. Reads contract/tests/source from manifest paths,
generates reproducer test + fix via LLM, validates in temp dir, applies via git.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from sentinel.config import LLMConfig
from sentinel.git_ops import GitOps
from sentinel.llm import LLMClient
from sentinel.schemas import (
    ContractProposal,
    FixResult,
    Incident,
    ManifestEntry,
    Signal,
)
from sentinel.test_runner import TestResults, run_tests

logger = logging.getLogger(__name__)

FIXER_SYSTEM = """You are fixing a production error in a verified software component.

You MUST respond with exactly three sections, each starting with the section header on its own line:

### REPRODUCER_TEST
A test function that reproduces this exact error. It must FAIL on the current source and PASS after your fix.

### FIXED_SOURCE
The complete fixed source file.

### CONTRACT_CHANGE
The tightened contract YAML, or "none" if no change needed."""


class FixerAgent:
    """Orchestrates the full fix cycle for a single incident."""

    def __init__(
        self,
        llm: LLMClient,
        git: GitOps | None = None,
        test_runner_fn: Callable[..., TestResults] | None = None,
    ) -> None:
        self._llm = llm
        self._git = git
        self._test_fn = test_runner_fn or run_tests

    async def fix(
        self,
        incident: Incident,
        manifest_entry: ManifestEntry,
        max_attempts: int = 2,
    ) -> FixResult:
        """Full fix cycle: reproducer -> fix -> test -> git commit.

        Returns FixResult with status "success" or "failure".
        """
        fix_id = uuid.uuid4().hex[:12]
        result = FixResult(
            id=fix_id,
            incident_id=incident.id,
            component_id=manifest_entry.component_id,
            status="running",
            started_at=datetime.now().isoformat(),
        )

        # Read component artifacts
        contract_text = _read_file(manifest_entry.contract_path)
        test_text = _read_file(manifest_entry.test_path)
        source_text = _read_file(manifest_entry.source_path)

        if not contract_text:
            result.status = "failure"
            result.error = f"No contract found at {manifest_entry.contract_path}"
            result.completed_at = datetime.now().isoformat()
            return result

        signal = incident.signals[0] if incident.signals else Signal(
            source="manual", raw_text="Unknown error", timestamp=datetime.now().isoformat(),
        )

        prior_failures: list[str] = []
        last_test_results: TestResults | None = None

        for attempt in range(1, max_attempts + 1):
            incident.remediation_attempts = attempt

            prompt = _build_fixer_prompt(
                manifest_entry.component_id,
                contract_text,
                test_text,
                source_text,
                signal,
                attempt,
                prior_failures,
                last_test_results,
            )

            try:
                response = await self._llm.generate(
                    prompt=prompt,
                    system=FIXER_SYSTEM,
                    max_tokens=8192,
                )
            except Exception as e:
                result.error = f"LLM call failed: {e}"
                prior_failures.append(f"Attempt {attempt}: LLM error — {e}")
                continue

            # Parse response sections
            reproducer = _extract_section(response, "REPRODUCER_TEST")
            fixed_source = _extract_section(response, "FIXED_SOURCE")
            contract_change = _extract_section(response, "CONTRACT_CHANGE")

            if not reproducer:
                # FA-S-009: retry once if no reproducer
                prior_failures.append(f"Attempt {attempt}: no reproducer test in response")
                continue

            result.reproducer_test = reproducer
            result.contract_change = contract_change or ""

            # Test in temp dir (FA-S-011)
            test_results = await self._test_in_temp(
                manifest_entry, test_text, reproducer, fixed_source,
            )
            last_test_results = test_results

            if test_results.all_passed:
                # Apply fix
                applied = await self._apply_fix(
                    manifest_entry, fixed_source, test_text, reproducer, incident,
                )
                if applied:
                    result.status = "success"
                    result.fixed_source = {"source": fixed_source}
                    if contract_change and contract_change.strip() != "none":
                        result.contract_change = contract_change
                else:
                    result.status = "failure"
                    result.error = "Fix application failed (git revert)"

                result.completed_at = datetime.now().isoformat()
                result.spend_usd = self._llm.spend
                return result

            # Collect failures for retry
            for fd in test_results.failure_details:
                prior_failures.append(f"Test '{fd.test_id}': {fd.error_message}")

        result.status = "failure"
        result.error = f"Failed after {max_attempts} attempts"
        result.completed_at = datetime.now().isoformat()
        result.spend_usd = self._llm.spend
        return result

    async def _test_in_temp(
        self,
        entry: ManifestEntry,
        existing_tests: str,
        reproducer: str,
        fixed_source: str,
    ) -> TestResults:
        """Run all tests (existing + reproducer) against fixed source in a temp dir."""
        temp_dir = Path(tempfile.mkdtemp(prefix="sentinel_fix_"))
        try:
            # Write fixed source
            src_dir = temp_dir / "src"
            src_dir.mkdir()
            source_path = Path(entry.source_path)
            if source_path.is_dir():
                # Copy entire source directory, then overwrite main file
                shutil.copytree(source_path, src_dir, dirs_exist_ok=True)
            # Write the fixed source as the main module
            main_file = src_dir / (entry.component_id + ".py")
            main_file.write_text(fixed_source)

            # Write tests
            test_dir = temp_dir / "tests"
            test_dir.mkdir()
            combined_tests = existing_tests + "\n\n" + reproducer if existing_tests else reproducer
            test_file = test_dir / f"test_{entry.component_id}.py"
            test_file.write_text(combined_tests)

            return await self._test_fn(
                test_path=test_file,
                source_dir=src_dir,
                language=entry.language,
                timeout=120,
            )
        except Exception as e:
            logger.debug("Temp dir test failed: %s", e)
            return TestResults(errors=1, failure_details=[])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _apply_fix(
        self,
        entry: ManifestEntry,
        fixed_source: str,
        existing_tests: str,
        reproducer: str,
        incident: Incident,
    ) -> bool:
        """Apply fix to actual files with git snapshot/commit. Returns success."""
        source_path = Path(entry.source_path)
        test_path = Path(entry.test_path)

        # FA-S-012: Pre-fix git snapshot
        snapshot_ref = None
        if self._git:
            snapshot_ref = await self._git.snapshot(
                f"sentinel: pre-fix snapshot for {incident.pact_key or entry.component_id}"
            )

        try:
            # Write fixed source
            if source_path.is_file():
                source_path.write_text(fixed_source)
            elif source_path.is_dir():
                main_file = source_path / (entry.component_id + ".py")
                main_file.write_text(fixed_source)

            # Write updated tests with reproducer (FA-S-010)
            if test_path.is_file():
                current = test_path.read_text()
                test_path.write_text(current + "\n\n" + reproducer)
            elif test_path.is_dir():
                test_file = test_path / f"test_{entry.component_id}.py"
                if test_file.exists():
                    current = test_file.read_text()
                    test_file.write_text(current + "\n\n" + reproducer)
                else:
                    test_file.write_text(reproducer)

            # Run full test suite from actual files
            actual_results = await self._test_fn(
                test_path=test_path,
                source_dir=source_path if source_path.is_dir() else source_path.parent,
                language=entry.language,
                timeout=120,
            )

            if actual_results.all_passed:
                # FA-S-013: Post-fix git commit
                if self._git:
                    files = [source_path, test_path]
                    error_summary = incident.signals[0].raw_text[:80] if incident.signals else "unknown"
                    await self._git.commit_fix(
                        f"sentinel: fix {incident.pact_key or entry.component_id} - {error_summary}",
                        files,
                    )
                return True

            # FA-S-014: Revert on failure
            if self._git and snapshot_ref:
                await self._git.revert_to(snapshot_ref)
            return False

        except Exception as e:
            logger.debug("Fix application failed: %s", e)
            if self._git and snapshot_ref:
                await self._git.revert_to(snapshot_ref)
            return False


def build_narrative_debrief(
    attempt: int,
    prior_failures: list[str],
    last_test_results: TestResults | None,
) -> str:
    """Build enriched context for retry attempts."""
    if attempt <= 1:
        return ""

    sections = []
    sections.append(f"## ATTEMPT {attempt - 1} DEBRIEF")

    if prior_failures:
        capped = prior_failures[:10]
        for f in capped:
            truncated = f[:200] if len(f) > 200 else f
            sections.append(f"- {truncated}")
        if len(prior_failures) > 10:
            sections.append(f"... and {len(prior_failures) - 10} more failures")

    sections.append("")
    sections.append("## WHAT WENT WRONG")
    if last_test_results and last_test_results.failure_details:
        for fd in last_test_results.failure_details[:10]:
            sections.append(f"- {fd.test_id}: {fd.error_message}")
    elif prior_failures:
        sections.append("See failure list above.")
    else:
        sections.append("Previous attempt did not produce passing tests.")

    sections.append("")
    sections.append("## FRESH APPROACH REQUIRED")
    sections.append(
        "You are a senior engineer brought in specifically because the previous "
        "approach failed. Take a fundamentally different approach."
    )

    return "\n".join(sections)


def _build_fixer_prompt(
    component_id: str,
    contract_text: str,
    test_text: str,
    source_text: str,
    signal: Signal,
    attempt: int,
    prior_failures: list[str],
    last_test_results: TestResults | None,
) -> str:
    """Build the full fixer prompt with all context."""
    parts = [
        f"## Component: {component_id}",
        "",
        "## Contract",
        contract_text,
        "",
        "## Current Tests",
        test_text or "(no existing tests)",
        "",
        "## Current Source",
        source_text or "(no existing source)",
        "",
        "## Production Error",
        f"Source: {signal.source}",
        f"Error: {signal.raw_text}",
        "",
        "## Instructions",
        "1. Add a reproducer test that fails on the current source and passes after your fix",
        "2. Fix the source to make all tests pass",
        "3. If the fix requires a contract change, propose tightened contract YAML",
        "",
        "## Constraints",
        "- Do not remove existing tests",
        "- Do not change the public interface without changing the contract",
        "- The reproducer test must be a single function appended to existing tests",
    ]

    debrief = build_narrative_debrief(attempt, prior_failures, last_test_results)
    if debrief:
        parts.append("")
        parts.append(debrief)

    return "\n".join(parts)


def _extract_section(response: str, section_name: str) -> str:
    """Extract content between ### SECTION_NAME and the next ### or end of text."""
    marker = f"### {section_name}"
    idx = response.find(marker)
    if idx == -1:
        return ""

    start = idx + len(marker)
    # Skip any trailing whitespace/newlines after the header
    while start < len(response) and response[start] in (" ", "\t", "\n", "\r"):
        start += 1

    # Find next ### section header
    next_header = response.find("\n###", start)
    if next_header == -1:
        content = response[start:]
    else:
        content = response[start:next_header]

    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline + 1:]
    if content.endswith("```"):
        content = content[:-3]

    return content.strip()


def _read_file(path: str) -> str:
    """Read a file or directory's main content. Returns empty string on failure."""
    if not path:
        return ""
    p = Path(path)
    if p.is_file():
        try:
            return p.read_text()
        except Exception:
            return ""
    if p.is_dir():
        # Try common entry points
        for name in [f"{p.name}.py", "main.py", "__init__.py", "index.ts", "index.js"]:
            candidate = p / name
            if candidate.exists():
                try:
                    return candidate.read_text()
                except Exception:
                    pass
        # Read all .py files concatenated
        texts = []
        for py_file in sorted(p.glob("*.py")):
            try:
                texts.append(f"# --- {py_file.name} ---\n{py_file.read_text()}")
            except Exception:
                pass
        return "\n\n".join(texts)
    return ""
