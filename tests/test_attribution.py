"""Tests for PACT key extraction and attribution."""

from __future__ import annotations

from pathlib import Path

from sentinel.attribution import AttributionEngine
from sentinel.manifest import ManifestManager
from sentinel.schemas import ManifestEntry, Signal


def _make_engine(tmp_path: Path, components: list[str] | None = None) -> AttributionEngine:
    mgr = ManifestManager(tmp_path)
    for comp_id in (components or []):
        mgr.register(ManifestEntry(component_id=comp_id))
    return AttributionEngine(mgr)


class TestExtractKey:
    def test_canonical_format(self, tmp_path: Path):
        engine = _make_engine(tmp_path)
        key = engine.extract_key("ERROR [PACT:auth_module:validate_token] Token invalid")
        assert key is not None
        assert key.component_id == "auth_module"
        assert key.method_name == "validate_token"
        assert key.raw == "PACT:auth_module:validate_token"

    def test_no_key(self, tmp_path: Path):
        engine = _make_engine(tmp_path)
        assert engine.extract_key("ERROR: something went wrong") is None

    def test_partial_key(self, tmp_path: Path):
        engine = _make_engine(tmp_path)
        assert engine.extract_key("PACT:abc123") is None

    def test_empty_string(self, tmp_path: Path):
        engine = _make_engine(tmp_path)
        assert engine.extract_key("") is None

    def test_key_with_underscores(self, tmp_path: Path):
        engine = _make_engine(tmp_path)
        key = engine.extract_key("PACT:my_component:my_method")
        assert key is not None
        assert key.component_id == "my_component"
        assert key.method_name == "my_method"


class TestAttribute:
    def test_registered_component(self, tmp_path: Path):
        engine = _make_engine(tmp_path, ["auth_module"])
        attr = engine.attribute("ERROR [PACT:auth_module:validate_token] Token invalid")
        assert attr.status == "registered"
        assert attr.component_id == "auth_module"
        assert attr.method_name == "validate_token"
        assert attr.manifest_entry is not None

    def test_unregistered_component(self, tmp_path: Path):
        engine = _make_engine(tmp_path)  # no components registered
        attr = engine.attribute("ERROR [PACT:auth_module:validate_token] Token invalid")
        assert attr.status == "unregistered"
        assert attr.component_id == "auth_module"

    def test_unattributed(self, tmp_path: Path):
        engine = _make_engine(tmp_path, ["auth"])
        attr = engine.attribute("ERROR: generic failure with no PACT key")
        assert attr.status == "unattributed"
        assert attr.pact_key == ""

    def test_secondary_format_fallback(self, tmp_path: Path):
        # Register "pricing" — secondary format has it as second segment
        engine = _make_engine(tmp_path, ["pricing"])
        attr = engine.attribute("ERROR [PACT:abc123:pricing] Price is None")
        # First tries abc123 (not found), then tries pricing (found)
        assert attr.status == "registered"
        assert attr.component_id == "pricing"


class TestAttributeSignal:
    def test_uses_log_key_first(self, tmp_path: Path):
        engine = _make_engine(tmp_path, ["auth"])
        signal = Signal(
            source="log_file",
            raw_text="ERROR: something",
            timestamp="2024-01-01",
            log_key="PACT:auth:validate",
        )
        attr = engine.attribute_signal(signal)
        assert attr.status == "registered"
        assert attr.component_id == "auth"

    def test_falls_back_to_raw_text(self, tmp_path: Path):
        engine = _make_engine(tmp_path, ["auth"])
        signal = Signal(
            source="log_file",
            raw_text="ERROR [PACT:auth:check] failed",
            timestamp="2024-01-01",
        )
        attr = engine.attribute_signal(signal)
        assert attr.status == "registered"
        assert attr.component_id == "auth"
