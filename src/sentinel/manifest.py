"""Component manifest — maps component IDs to their filesystem artifacts."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from sentinel.schemas import ManifestEntry

logger = logging.getLogger(__name__)

_PACT_KEY_RE = re.compile(r"PACT:([a-zA-Z0-9_]+):([a-zA-Z0-9_]+)")


class ManifestManager:
    """Manages .sentinel/manifest.json — the component registry."""

    def __init__(self, sentinel_dir: Path) -> None:
        self._sentinel_dir = sentinel_dir
        self._manifest_path = sentinel_dir / "manifest.json"
        self._entries: dict[str, ManifestEntry] = {}
        self.load()

    def register(self, entry: ManifestEntry) -> None:
        """Register or update a component."""
        entry.last_registered = datetime.now().isoformat()
        self._entries[entry.component_id] = entry
        self.save()

    def unregister(self, component_id: str) -> bool:
        """Remove a component. Returns True if it existed."""
        if component_id in self._entries:
            del self._entries[component_id]
            self.save()
            return True
        return False

    def lookup(self, component_id: str) -> ManifestEntry | None:
        """Look up a component by ID."""
        return self._entries.get(component_id)

    def lookup_by_key(self, pact_key: str) -> ManifestEntry | None:
        """Look up by full PACT key string (PACT:<component_id>:<method>)."""
        m = _PACT_KEY_RE.search(pact_key)
        if not m:
            return None
        component_id = m.group(1)
        entry = self._entries.get(component_id)
        if entry:
            return entry
        # Try second segment as component_id (secondary format)
        return self._entries.get(m.group(2))

    def all_entries(self) -> dict[str, ManifestEntry]:
        """Return all registered components."""
        return dict(self._entries)

    def save(self) -> None:
        """Persist manifest to disk."""
        self._sentinel_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "components": {
                k: v.model_dump() for k, v in self._entries.items()
            }
        }
        self._manifest_path.write_text(json.dumps(data, indent=2, default=str))

    def load(self) -> None:
        """Load manifest from disk. No-op if file doesn't exist."""
        if not self._manifest_path.exists():
            return
        try:
            data = json.loads(self._manifest_path.read_text())
            self._entries = {
                k: ManifestEntry.model_validate(v)
                for k, v in data.get("components", {}).items()
            }
        except Exception as e:
            logger.warning("Failed to load manifest: %s", e)

    @staticmethod
    def scan_directory(project_dir: Path) -> list[ManifestEntry]:
        """Auto-discover components by scanning a Pact project directory.

        Looks for:
        - contracts/<component_id>/interface.json
        - tests/<component_id>/
        - src/<component_id>/
        """
        entries = []
        contracts_dir = project_dir / "contracts"
        if not contracts_dir.exists():
            return entries

        for contract_dir in sorted(contracts_dir.iterdir()):
            if not contract_dir.is_dir():
                continue
            component_id = contract_dir.name

            interface = contract_dir / "interface.json"
            if not interface.exists():
                continue

            test_dir = project_dir / "tests" / component_id
            src_dir = project_dir / "src" / component_id

            # Detect language
            language = "python"
            if any(src_dir.glob("*.ts")) if src_dir.exists() else False:
                language = "typescript"

            entries.append(ManifestEntry(
                component_id=component_id,
                contract_path=str(interface),
                test_path=str(test_dir) if test_dir.exists() else "",
                source_path=str(src_dir) if src_dir.exists() else "",
                language=language,
                pact_project=str(project_dir),
            ))

        return entries
