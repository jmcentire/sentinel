"""Tests for the sentinel triage CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from sentinel.cli import main


class TestTriageCLIPactKey:
    """Test triage command with PACT key extraction (no LLM needed)."""

    def _setup_manifest(self, tmp_path: Path) -> Path:
        """Create a state dir with a manifest containing test components."""
        state_dir = tmp_path / ".sentinel"
        state_dir.mkdir()
        manifest = {
            "components": {
                "auth_module": {
                    "component_id": "auth_module",
                    "contract_path": "",
                    "test_path": "",
                    "source_path": "",
                    "language": "python",
                    "last_registered": "2026-01-01T00:00:00",
                    "pact_project": "",
                },
                "payment_processor": {
                    "component_id": "payment_processor",
                    "contract_path": "",
                    "test_path": "",
                    "source_path": "",
                    "language": "python",
                    "last_registered": "2026-01-01T00:00:00",
                    "pact_project": "",
                },
            }
        }
        (state_dir / "manifest.json").write_text(json.dumps(manifest))
        return state_dir

    def test_triage_with_pact_key_registered(self, tmp_path: Path):
        """When error contains a PACT key for a registered component, report it directly."""
        state_dir = self._setup_manifest(tmp_path)
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(f"state_dir: '{state_dir}'\n")

        runner = CliRunner()
        result = runner.invoke(main, [
            "--config", str(config_file),
            "triage",
            "[PACT:auth_module:validate_token] Token signature invalid",
        ])

        assert result.exit_code == 0
        assert "component_id: auth_module" in result.output
        assert "confidence:   1.0" in result.output
        assert "PACT key" in result.output

    def test_triage_with_pact_key_unregistered(self, tmp_path: Path):
        """When PACT key found but component not in manifest, report partial match."""
        state_dir = self._setup_manifest(tmp_path)
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(f"state_dir: '{state_dir}'\n")

        runner = CliRunner()
        result = runner.invoke(main, [
            "--config", str(config_file),
            "triage",
            "[PACT:unknown_component:some_method] Something broke",
        ])

        assert result.exit_code == 0
        assert "component_id: unknown" in result.output
        assert "confidence:   0.5" in result.output
        assert "not registered" in result.output

    def test_triage_no_pact_key_no_llm(self, tmp_path: Path):
        """When no PACT key and LLM unavailable, report gracefully."""
        state_dir = self._setup_manifest(tmp_path)
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(f"state_dir: '{state_dir}'\n")

        runner = CliRunner()
        # Patch LLMClient to raise ImportError
        with patch("sentinel.cli.asyncio.run", side_effect=RuntimeError("No LLM")):
            # The import of LLMClient should work, but the LLM call will fail
            result = runner.invoke(main, [
                "--config", str(config_file),
                "triage",
                "Some random error with no key",
            ])

        assert result.exit_code == 0
        assert "component_id: unknown" in result.output
        assert "confidence:   0.0" in result.output

    def test_triage_no_components(self, tmp_path: Path):
        """When no components registered, exit with error."""
        state_dir = tmp_path / ".sentinel"
        state_dir.mkdir()
        (state_dir / "manifest.json").write_text('{"components": {}}')
        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(f"state_dir: '{state_dir}'\n")

        runner = CliRunner()
        result = runner.invoke(main, [
            "--config", str(config_file),
            "triage",
            "Some error",
        ])

        assert result.exit_code != 0
        assert "No components registered" in result.output

    def test_triage_manifest_override(self, tmp_path: Path):
        """The --manifest option overrides the manifest directory."""
        # Create manifest in a non-default location
        custom_dir = tmp_path / "custom_state"
        custom_dir.mkdir()
        manifest = {
            "components": {
                "custom_comp": {
                    "component_id": "custom_comp",
                    "contract_path": "",
                    "test_path": "",
                    "source_path": "",
                    "language": "python",
                    "last_registered": "2026-01-01T00:00:00",
                    "pact_project": "",
                },
            }
        }
        (custom_dir / "manifest.json").write_text(json.dumps(manifest))

        config_file = tmp_path / "sentinel.yaml"
        config_file.write_text(f"state_dir: '{tmp_path / '.sentinel'}'\n")

        runner = CliRunner()
        result = runner.invoke(main, [
            "--config", str(config_file),
            "triage",
            "--manifest", str(custom_dir),
            "[PACT:custom_comp:do_thing] Error happened",
        ])

        assert result.exit_code == 0
        assert "component_id: custom_comp" in result.output
        assert "confidence:   1.0" in result.output
