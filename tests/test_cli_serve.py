import asyncio
from pathlib import Path

from click.testing import CliRunner

from sentinel.cli import main


class _FakeAPI:
    instances = []

    def __init__(self, sentinel):
        self.sentinel = sentinel
        self.started = []
        self.stopped = False
        self.__class__.instances.append(self)

    async def start(self, host, port):
        self.started.append((host, port))

    async def stop(self):
        self.stopped = True


class _FakeSentinel:
    instances = []

    def __init__(self, config):
        self.config = config
        self.startup_calls = 0
        self.run_calls = 0
        self.__class__.instances.append(self)

    async def startup(self):
        self.startup_calls += 1

    async def run(self):
        self.run_calls += 1
        raise asyncio.CancelledError


async def _cancel_sleep(delay):
    raise asyncio.CancelledError


def _reset_fakes():
    _FakeAPI.instances.clear()
    _FakeSentinel.instances.clear()


def test_serve_api_only_runs_startup_and_stops_api(monkeypatch, tmp_path: Path):
    _reset_fakes()
    config_file = tmp_path / "sentinel.yaml"
    config_file.write_text(f"state_dir: '{tmp_path / '.sentinel'}'\nsources: []\n")

    monkeypatch.setattr("sentinel.api.SentinelAPI", _FakeAPI)
    monkeypatch.setattr("sentinel.sentinel.Sentinel", _FakeSentinel)
    monkeypatch.setattr("sentinel.cli.asyncio.sleep", _cancel_sleep)

    result = CliRunner().invoke(
        main,
        ["--config", str(config_file), "serve", "--host", "127.0.0.1", "--port", "9001"],
    )

    assert result.exit_code == 0
    assert _FakeSentinel.instances[0].startup_calls == 1
    assert _FakeSentinel.instances[0].run_calls == 0
    assert _FakeAPI.instances[0].started == [("127.0.0.1", 9001)]
    assert _FakeAPI.instances[0].stopped


def test_serve_with_sources_runs_watcher_loop(monkeypatch, tmp_path: Path):
    _reset_fakes()
    config_file = tmp_path / "sentinel.yaml"
    config_file.write_text(
        f"state_dir: '{tmp_path / '.sentinel'}'\n"
        "sources:\n"
        "  - type: file\n"
        "    path: app.log\n"
    )

    monkeypatch.setattr("sentinel.api.SentinelAPI", _FakeAPI)
    monkeypatch.setattr("sentinel.sentinel.Sentinel", _FakeSentinel)
    monkeypatch.setattr("sentinel.cli.asyncio.sleep", _cancel_sleep)

    result = CliRunner().invoke(
        main,
        ["--config", str(config_file), "serve", "--host", "127.0.0.1", "--port", "9002"],
    )

    assert result.exit_code == 0
    assert _FakeSentinel.instances[0].startup_calls == 0
    assert _FakeSentinel.instances[0].run_calls == 1
    assert _FakeAPI.instances[0].started == [("127.0.0.1", 9002)]
    assert _FakeAPI.instances[0].stopped
