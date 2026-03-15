"""Tests for the fixer agent."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sentinel.fixer import (
    FixerAgent,
    _extract_section,
    build_narrative_debrief,
)
from sentinel.llm import LLMClient
from sentinel.schemas import Incident, ManifestEntry, Signal
from sentinel.test_runner import TestResults, TestFailureDetail


class TestExtractSection:
    def test_extracts_section(self):
        response = """### REPRODUCER_TEST
def test_repro():
    assert False

### FIXED_SOURCE
def main():
    return 42

### CONTRACT_CHANGE
none"""
        assert "def test_repro" in _extract_section(response, "REPRODUCER_TEST")
        assert "def main" in _extract_section(response, "FIXED_SOURCE")
        assert "none" == _extract_section(response, "CONTRACT_CHANGE")

    def test_missing_section(self):
        assert _extract_section("no sections here", "REPRODUCER_TEST") == ""

    def test_strips_code_fences(self):
        response = """### FIXED_SOURCE
```python
def main():
    return 42
```"""
        result = _extract_section(response, "FIXED_SOURCE")
        assert "def main" in result
        assert "```" not in result


class TestBuildNarrativeDebrief:
    def test_first_attempt_empty(self):
        assert build_narrative_debrief(1, [], None) == ""

    def test_includes_failures(self):
        result = build_narrative_debrief(
            2,
            ["Test 'test_a': assertion error"],
            None,
        )
        assert "test_a" in result
        assert "FRESH APPROACH" in result

    def test_includes_test_details(self):
        results = TestResults(
            total=2, passed=1, failed=1,
            failure_details=[TestFailureDetail(test_id="test_x", error_message="boom")],
        )
        result = build_narrative_debrief(2, [], results)
        assert "test_x" in result
        assert "boom" in result

    def test_caps_failures_at_10(self):
        failures = [f"Test 'test_{i}': fail" for i in range(20)]
        result = build_narrative_debrief(2, failures, None)
        assert "10 more failures" in result


class TestFixerAgent:
    def _make_incident(self) -> Incident:
        return Incident(
            id="inc_001",
            component_id="pricing",
            pact_key="PACT:pricing:calculate",
            signals=[Signal(
                source="log_file",
                raw_text="TypeError: NoneType has no attribute 'price'",
                timestamp=datetime.now().isoformat(),
            )],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

    def _make_entry(self, tmp_path: Path) -> ManifestEntry:
        # Set up files
        contract = tmp_path / "contract.json"
        contract.write_text('{"functions": [{"name": "calculate_price"}]}')
        source = tmp_path / "pricing.py"
        source.write_text("def calculate_price(): return None")
        tests = tmp_path / "test_pricing.py"
        tests.write_text("def test_basic(): assert True")

        return ManifestEntry(
            component_id="pricing",
            contract_path=str(contract),
            test_path=str(tests),
            source_path=str(source),
            language="python",
            pact_project=str(tmp_path),
        )

    @pytest.mark.asyncio
    async def test_no_contract_fails(self, tmp_path: Path):
        llm = MagicMock(spec=LLMClient)
        fixer = FixerAgent(llm=llm)
        entry = ManifestEntry(component_id="x", contract_path="/nonexistent")
        incident = self._make_incident()

        result = await fixer.fix(incident, entry)
        assert result.status == "failure"
        assert "No contract" in result.error

    @pytest.mark.asyncio
    async def test_successful_fix(self, tmp_path: Path):
        entry = self._make_entry(tmp_path)
        incident = self._make_incident()

        llm = MagicMock(spec=LLMClient)
        llm.generate = AsyncMock(return_value="""### REPRODUCER_TEST
def test_repro():
    assert True

### FIXED_SOURCE
def calculate_price():
    return 42.0

### CONTRACT_CHANGE
none""")
        llm.spend = 0.50
        llm.is_budget_exceeded = MagicMock(return_value=False)

        async def mock_tests(**kwargs):
            return TestResults(total=2, passed=2)

        fixer = FixerAgent(llm=llm, test_runner_fn=mock_tests)
        result = await fixer.fix(incident, entry)
        assert result.status == "success"
        assert result.reproducer_test != ""

    @pytest.mark.asyncio
    async def test_fix_failure_after_retries(self, tmp_path: Path):
        entry = self._make_entry(tmp_path)
        incident = self._make_incident()

        llm = MagicMock(spec=LLMClient)
        llm.generate = AsyncMock(return_value="""### REPRODUCER_TEST
def test_repro():
    assert True

### FIXED_SOURCE
def calculate_price():
    return None  # still buggy

### CONTRACT_CHANGE
none""")
        llm.spend = 1.00
        llm.is_budget_exceeded = MagicMock(return_value=False)

        async def mock_tests(**kwargs):
            return TestResults(total=2, passed=1, failed=1, failure_details=[
                TestFailureDetail(test_id="test_repro", error_message="assertion error"),
            ])

        fixer = FixerAgent(llm=llm, test_runner_fn=mock_tests)
        result = await fixer.fix(incident, entry, max_attempts=2)
        assert result.status == "failure"

    @pytest.mark.asyncio
    async def test_no_reproducer_retries(self, tmp_path: Path):
        entry = self._make_entry(tmp_path)
        incident = self._make_incident()

        call_count = 0

        async def mock_generate(prompt, system, max_tokens=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "No sections here"
            return """### REPRODUCER_TEST
def test_repro(): assert True

### FIXED_SOURCE
def calculate_price(): return 42.0

### CONTRACT_CHANGE
none"""

        llm = MagicMock(spec=LLMClient)
        llm.generate = mock_generate
        llm.spend = 0.10
        llm.is_budget_exceeded = MagicMock(return_value=False)

        async def mock_tests(**kwargs):
            return TestResults(total=2, passed=2)

        fixer = FixerAgent(llm=llm, test_runner_fn=mock_tests)
        result = await fixer.fix(incident, entry, max_attempts=2)
        assert result.status == "success"
        assert call_count == 2
