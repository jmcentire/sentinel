"""Tests for git operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from sentinel.git_ops import GitOps


class TestGitOps:
    @pytest.fixture
    def git_repo(self, tmp_path: Path):
        """Create a real git repo in tmp_path."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        # Initial commit
        (tmp_path / "README").write_text("init")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        return tmp_path

    def test_is_git_repo(self, git_repo: Path):
        ops = GitOps(git_repo)
        assert ops.is_git_repo is True

    def test_not_git_repo(self, tmp_path: Path):
        ops = GitOps(tmp_path)
        assert ops.is_git_repo is False

    @pytest.mark.asyncio
    async def test_current_hash(self, git_repo: Path):
        ops = GitOps(git_repo)
        h = await ops.current_hash()
        assert h is not None
        assert len(h) == 40

    @pytest.mark.asyncio
    async def test_current_hash_not_git(self, tmp_path: Path):
        ops = GitOps(tmp_path)
        assert await ops.current_hash() is None

    @pytest.mark.asyncio
    async def test_snapshot(self, git_repo: Path):
        (git_repo / "file.txt").write_text("content")
        ops = GitOps(git_repo)
        h = await ops.snapshot("test snapshot")
        assert h is not None

    @pytest.mark.asyncio
    async def test_snapshot_not_git(self, tmp_path: Path):
        ops = GitOps(tmp_path)
        assert await ops.snapshot("test") is None

    @pytest.mark.asyncio
    async def test_commit_fix(self, git_repo: Path):
        f = git_repo / "fix.py"
        f.write_text("fixed")
        ops = GitOps(git_repo)
        h = await ops.commit_fix("fix commit", [f])
        assert h is not None

    @pytest.mark.asyncio
    async def test_revert_to(self, git_repo: Path):
        ops = GitOps(git_repo)
        h1 = await ops.current_hash()
        (git_repo / "new.txt").write_text("new")
        await ops.snapshot("add new")
        (git_repo / "another.txt").write_text("another")
        await ops.snapshot("add another")

        success = await ops.revert_to(h1)
        assert success is True
        assert not (git_repo / "new.txt").exists()

    @pytest.mark.asyncio
    async def test_revert_not_git(self, tmp_path: Path):
        ops = GitOps(tmp_path)
        assert await ops.revert_to("abc123") is False
