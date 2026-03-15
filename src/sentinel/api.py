"""HTTP API — status, manifest, fixes, manual triggers."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from aiohttp import web

from sentinel.schemas import ManifestEntry

logger = logging.getLogger(__name__)


class SentinelAPI:
    """HTTP API server for Sentinel."""

    def __init__(self, sentinel) -> None:
        """Accept a Sentinel instance (avoid circular import with TYPE_CHECKING)."""
        self._sentinel = sentinel
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._start_time = datetime.now().isoformat()
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_get("/status", self._handle_status)
        self._app.router.add_get("/manifest", self._handle_manifest)
        self._app.router.add_get("/fixes", self._handle_fixes)
        self._app.router.add_get("/fixes/{fix_id}", self._handle_fix_detail)
        self._app.router.add_post("/fix", self._handle_manual_fix)
        self._app.router.add_post("/register", self._handle_register)
        self._app.router.add_get("/metrics", self._handle_metrics)

    async def start(self, host: str = "0.0.0.0", port: int = 8484) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port)
        await site.start()
        logger.info("Sentinel API listening on %s:%d", host, port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle_status(self, request: web.Request) -> web.Response:
        s = self._sentinel
        data = {
            "version": "0.1.0",
            "started_at": self._start_time,
            "sources": len(s._config.sources),
            "components": len(s.manifest.all_entries()),
            "active_incidents": len(s.incident_mgr.get_active_incidents()),
            "total_fixes": len(s.fixes),
            "arbiter_configured": s._arbiter.is_configured(),
            "stigmergy_configured": s._stigmergy.is_configured(),
            "ledger_configured": s._ledger.is_configured(),
            "pact_configured": s._contracts.pact_configured,
        }
        return web.json_response(data)

    async def _handle_manifest(self, request: web.Request) -> web.Response:
        entries = self._sentinel.manifest.all_entries()
        data = {k: v.model_dump() for k, v in entries.items()}
        return web.json_response({"components": data})

    async def _handle_fixes(self, request: web.Request) -> web.Response:
        fixes = self._sentinel.fixes[-50:]  # last 50
        data = [f.model_dump() for f in reversed(fixes)]
        return web.json_response(data)

    async def _handle_fix_detail(self, request: web.Request) -> web.Response:
        fix_id = request.match_info["fix_id"]
        for fix in self._sentinel.fixes:
            if fix.id == fix_id:
                return web.json_response(fix.model_dump())
        return web.json_response({"error": "Fix not found"}, status=404)

    async def _handle_manual_fix(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        pact_key = body.get("pact_key", "")
        error = body.get("error", "")
        if not pact_key or not error:
            return web.json_response(
                {"error": "pact_key and error required"}, status=400,
            )

        result = await self._sentinel.handle_manual_fix(pact_key, error)
        return web.json_response(result.model_dump())

    async def _handle_register(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        component_id = body.get("component_id", "")
        if not component_id:
            return web.json_response(
                {"error": "component_id required"}, status=400,
            )

        entry = ManifestEntry(
            component_id=component_id,
            contract_path=body.get("contract_path", ""),
            test_path=body.get("test_path", ""),
            source_path=body.get("source_path", ""),
            language=body.get("language", "python"),
            pact_project=body.get("pact_project", ""),
        )
        self._sentinel.manifest.register(entry)
        return web.json_response({"status": "registered", "component_id": component_id})

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        s = self._sentinel
        total_fixes = len(s.fixes)
        successful = sum(1 for f in s.fixes if f.status == "success")
        failed = sum(1 for f in s.fixes if f.status == "failure")
        total_spend = sum(f.spend_usd for f in s.fixes)

        incidents = s.incident_mgr.get_recent_incidents(1000)
        data = {
            "total_incidents": len(incidents),
            "active_incidents": len(s.incident_mgr.get_active_incidents()),
            "total_fixes_attempted": total_fixes,
            "fixes_succeeded": successful,
            "fixes_failed": failed,
            "total_spend_usd": round(total_spend, 2),
            "components_registered": len(s.manifest.all_entries()),
        }
        return web.json_response(data)
