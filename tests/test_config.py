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


class TestCloudWatchSourceConfig:
    """Validate CloudWatch source config parsing."""

    def test_cloudwatch_source_defaults(self):
        s = SourceConfig(type="cloudwatch", log_group="/aws/lambda/test")
        assert s.type == "cloudwatch"
        assert s.log_group == "/aws/lambda/test"
        assert s.filter_pattern == ""
        assert s.region == ""
        assert s.poll_interval == 30
        assert "ERROR" in s.error_patterns

    def test_cloudwatch_source_full(self):
        s = SourceConfig(
            type="cloudwatch",
            log_group="/aws/ecs/service",
            filter_pattern="ERROR",
            region="us-east-1",
            poll_interval=60,
            error_patterns=["FATAL"],
        )
        assert s.type == "cloudwatch"
        assert s.filter_pattern == "ERROR"
        assert s.region == "us-east-1"
        assert s.poll_interval == 60
        assert s.error_patterns == ["FATAL"]

    def test_cloudwatch_in_config_yaml(self, tmp_path: Path):
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(
            "sources:\n"
            '  - type: cloudwatch\n'
            '    log_group: "/aws/lambda/my-function"\n'
            '    filter_pattern: "ERROR"\n'
            '    region: "us-west-2"\n'
            '    poll_interval: 15\n'
        )
        c = load_config(config_file)
        assert len(c.sources) == 1
        assert c.sources[0].type == "cloudwatch"
        assert c.sources[0].log_group == "/aws/lambda/my-function"
        assert c.sources[0].filter_pattern == "ERROR"
        assert c.sources[0].region == "us-west-2"
        assert c.sources[0].poll_interval == 15

    def test_mixed_sources_in_config(self, tmp_path: Path):
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(
            "sources:\n"
            '  - type: file\n'
            '    path: "/var/log/app.log"\n'
            '  - type: cloudwatch\n'
            '    log_group: "/aws/lambda/test"\n'
            '    filter_pattern: "ERROR"\n'
            '  - type: webhook\n'
            '    port: 9090\n'
        )
        c = load_config(config_file)
        assert len(c.sources) == 3
        assert c.sources[0].type == "file"
        assert c.sources[1].type == "cloudwatch"
        assert c.sources[2].type == "webhook"
        assert c.sources[2].port == 9090

    def test_webhook_source_config(self):
        s = SourceConfig(type="webhook", port=8080)
        assert s.type == "webhook"
        assert s.port == 8080

    def test_source_config_serialization_roundtrip(self):
        s = SourceConfig(
            type="cloudwatch",
            log_group="/aws/test",
            filter_pattern="ERROR",
            region="eu-west-1",
            poll_interval=45,
        )
        data = s.model_dump()
        s2 = SourceConfig.model_validate(data)
        assert s2.type == "cloudwatch"
        assert s2.log_group == "/aws/test"
        assert s2.filter_pattern == "ERROR"
        assert s2.region == "eu-west-1"
        assert s2.poll_interval == 45
