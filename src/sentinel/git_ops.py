"""Git operations — snapshot, commit, revert. Silent no-op outside git repos."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GitOps:
    """Manages git snapshots and commits for fix application."""

    def __init__(self, repo_dir: Path) -> None:
        self._repo_dir = repo_dir
        self._is_git: bool | None = None

    @property
    def is_git_repo(self) -> bool:
        """Check if repo_dir is inside a git repository."""
        if self._is_git is None:
            self._is_git = (self._repo_dir / ".git").exists() or any(
                (p / ".git").exists() for p in self._repo_dir.parents
            )
        return self._is_git

    async def _run(self, *args: str) -> tuple[int, str, str]:
        """Run a git command, return (returncode, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self._repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace").strip(),
            stderr.decode("utf-8", errors="replace").strip(),
        )

    async def current_hash(self) -> str | None:
        """Get current HEAD commit hash. None if not a git repo."""
        if not self.is_git_repo:
            return None
        rc, stdout, _ = await self._run("rev-parse", "HEAD")
        return stdout if rc == 0 else None

    async def snapshot(self, message: str) -> str | None:
        """Commit all current changes as a snapshot. Returns commit hash or None."""
        if not self.is_git_repo:
            return None
        try:
            await self._run("add", "-A")
            rc, _, stderr = await self._run("commit", "-m", message, "--allow-empty")
            if rc != 0:
                logger.debug("Git snapshot commit failed: %s", stderr)
                return None
            return await self.current_hash()
        except Exception as e:
            logger.debug("Git snapshot failed: %s", e)
            return None

    async def commit_fix(self, message: str, files: list[Path]) -> str | None:
        """Stage specific files and commit. Returns commit hash or None."""
        if not self.is_git_repo:
            return None
        try:
            for f in files:
                await self._run("add", str(f))
            rc, _, stderr = await self._run("commit", "-m", message)
            if rc != 0:
                logger.debug("Git commit failed: %s", stderr)
                return None
            return await self.current_hash()
        except Exception as e:
            logger.debug("Git commit failed: %s", e)
            return None

    async def revert_to(self, commit_hash: str) -> bool:
        """Hard reset to a previous commit. Returns success."""
        if not self.is_git_repo:
            return False
        try:
            rc, _, stderr = await self._run("reset", "--hard", commit_hash)
            if rc != 0:
                logger.debug("Git revert failed: %s", stderr)
                return False
            return True
        except Exception as e:
            logger.debug("Git revert failed: %s", e)
            return False
