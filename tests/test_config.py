"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from sentinel.config import (
    SentinelConfig,
    SourceConfig,
    LLMConfig,
    load_config,
)


class TestSentinelConfig:
    def test_defaults(self):
        c = SentinelConfig()
        assert c.version == "1.0"
        assert c.sources == []
        assert c.auto_remediate is False
        assert c.state_dir == ".sentinel"
        assert c.llm.model == "claude-sonnet-4-20250514"

    def test_custom_values(self):
        c = SentinelConfig(
            auto_remediate=True,
            state_dir="/tmp/sentinel",
            llm=LLMConfig(model="claude-opus-4-20250514", budget_per_fix=5.0),
        )
        assert c.auto_remediate is True
        assert c.llm.budget_per_fix == 5.0

    def test_source_config(self):
        s = SourceConfig(type="file", path="/var/log/app.log")
        assert s.type == "file"
        assert "ERROR" in s.error_patterns

    def test_serialization_roundtrip(self):
        c = SentinelConfig(
            sources=[SourceConfig(type="file", path="/tmp/test.log")],
            auto_remediate=True,
        )
        data = c.model_dump()
        c2 = SentinelConfig.model_validate(data)
        assert c2.auto_remediate is True
        assert len(c2.sources) == 1


class TestLoadConfig:
    def test_loads_from_file(self, tmp_path: Path):
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(yaml.dump({
            "auto_remediate": True,
            "state_dir": str(tmp_path / ".sentinel"),
        }))
        c = load_config(config_file)
        assert c.auto_remediate is True

    def test_returns_defaults_when_missing(self, tmp_path: Path):
        c = load_config(tmp_path / "nonexistent.yaml")
        assert c.auto_remediate is False
        assert c.sources == []

    def test_handles_empty_yaml(self, tmp_path: Path):
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text("")
        c = load_config(config_file)
        assert c.version == "1.0"
