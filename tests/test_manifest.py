"""Tests for component manifest."""

from __future__ import annotations

from pathlib import Path

from sentinel.manifest import ManifestManager
from sentinel.schemas import ManifestEntry


class TestManifestManager:
    def test_register_and_lookup(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        entry = ManifestEntry(component_id="auth", contract_path="/c/auth.json")
        mgr.register(entry)
        assert mgr.lookup("auth") is not None
        assert mgr.lookup("auth").contract_path == "/c/auth.json"

    def test_unregister(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        mgr.register(ManifestEntry(component_id="auth"))
        assert mgr.unregister("auth") is True
        assert mgr.lookup("auth") is None
        assert mgr.unregister("auth") is False

    def test_lookup_by_key_canonical(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        mgr.register(ManifestEntry(component_id="auth"))
        entry = mgr.lookup_by_key("PACT:auth:validate_token")
        assert entry is not None
        assert entry.component_id == "auth"

    def test_lookup_by_key_secondary_format(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        mgr.register(ManifestEntry(component_id="pricing"))
        # Secondary format: PACT:<project_hash>:<component_id>
        entry = mgr.lookup_by_key("PACT:abc123:pricing")
        assert entry is not None
        assert entry.component_id == "pricing"

    def test_lookup_by_key_not_found(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        assert mgr.lookup_by_key("PACT:unknown:method") is None

    def test_lookup_by_key_invalid(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        assert mgr.lookup_by_key("not a key") is None

    def test_all_entries(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        mgr.register(ManifestEntry(component_id="a"))
        mgr.register(ManifestEntry(component_id="b"))
        assert len(mgr.all_entries()) == 2

    def test_persistence(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        mgr.register(ManifestEntry(component_id="auth", test_path="/tests/auth"))
        mgr.save()

        mgr2 = ManifestManager(tmp_path)
        entry = mgr2.lookup("auth")
        assert entry is not None
        assert entry.test_path == "/tests/auth"

    def test_scan_directory(self, tmp_path: Path):
        # Set up fake Pact project structure
        contracts = tmp_path / "contracts" / "pricing"
        contracts.mkdir(parents=True)
        (contracts / "interface.json").write_text('{"functions": [], "types": []}')
        (tmp_path / "src" / "pricing").mkdir(parents=True)
        (tmp_path / "tests" / "pricing").mkdir(parents=True)

        entries = ManifestManager.scan_directory(tmp_path)
        assert len(entries) == 1
        assert entries[0].component_id == "pricing"
        assert entries[0].pact_project == str(tmp_path)

    def test_scan_empty_directory(self, tmp_path: Path):
        entries = ManifestManager.scan_directory(tmp_path)
        assert entries == []

    def test_register_updates_last_registered(self, tmp_path: Path):
        mgr = ManifestManager(tmp_path)
        entry = ManifestEntry(component_id="auth")
        mgr.register(entry)
        loaded = mgr.lookup("auth")
        assert loaded.last_registered != ""
