"""Signal ingestion — tail logs, watch processes, receive webhooks.

Async generators that yield Signal objects from various sources.
Fingerprinting deduplicates identical errors within a configurable window.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime

from sentinel.config import SourceConfig
from sentinel.schemas import Signal, SignalFingerprint

logger = logging.getLogger(__name__)

# Patterns stripped during fingerprint normalization
_NORMALIZE_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"),  # timestamps
    re.compile(r"0x[0-9a-fA-F]+"),  # memory addresses
    re.compile(r":\d+"),  # line numbers
    re.compile(r"\b\d{5,}\b"),  # large numbers (PIDs, etc.)
]


def fingerprint_signal(signal: Signal) -> str:
    """Normalize error text and produce a stable SHA256 hash.

    Strips timestamps, memory addresses, line numbers, and large
    numbers so that the same logical error produces the same hash.
    """
    text = signal.raw_text
    for pattern in _NORMALIZE_PATTERNS:
        text = pattern.sub("", text)
    text = " ".join(text.split())
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class LogTailer:
    """Async generator that tails log files using tail -F.

    FA-S-024: Handles log source unavailability with retry and exponential backoff.
    """

    MAX_BACKOFF = 60  # seconds

    def __init__(self, path: str, error_patterns: list[str] | None = None) -> None:
        self.path = path
        self._patterns = [re.compile(p) for p in (error_patterns or ["ERROR", "CRITICAL", "Traceback"])]
        self._process: asyncio.subprocess.Process | None = None
        self._stopped = False

    async def start(self) -> None:
        """Start the tail -F subprocess. Retries on failure."""
        await self._start_process()

    async def _start_process(self) -> None:
        """Launch tail -F. Handles missing files gracefully."""
        try:
            self._process = await asyncio.create_subprocess_exec(
                "tail", "-F", self.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            logger.warning("Failed to start tail for %s: %s", self.path, e)
            self._process = None

    async def lines(self):
        """Yield matching log lines with automatic reconnection on failure."""
        backoff = 1
        while not self._stopped:
            if not self._process or not self._process.stdout:
                # FA-S-024: Retry with exponential backoff
                logger.debug("Log source %s unavailable, retrying in %ds", self.path, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.MAX_BACKOFF)
                await self._start_process()
                continue

            try:
                line_bytes = await self._process.stdout.readline()
                if not line_bytes:
                    # Process died — restart with backoff
                    self._process = None
                    continue
                backoff = 1  # Reset backoff on successful read
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if any(p.search(line) for p in self._patterns):
                    yield line
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("LogTailer read error for %s: %s", self.path, e)
                self._process = None

    def stop(self) -> None:
        self._stopped = True
        if self._process:
            self._process.terminate()


class ProcessWatcher:
    """Periodically checks for crashed processes matching patterns."""

    def __init__(self, patterns: list[str], poll_interval: float = 10.0) -> None:
        self.patterns = patterns
        self.poll_interval = poll_interval
        self._known_pids: set[str] = set()

    async def watch(self):
        while True:
            for pattern in self.patterns:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "pgrep", "-f", pattern,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout, _ = await proc.communicate()
                    current_pids = set(stdout.decode().strip().split("\n")) - {""}
                    lost = self._known_pids - current_pids
                    if self._known_pids and lost:
                        yield Signal(
                            source="process",
                            raw_text=f"Process matching '{pattern}' disappeared (PIDs: {', '.join(lost)})",
                            timestamp=datetime.now().isoformat(),
                            process_name=pattern,
                        )
                    self._known_pids = current_pids
                except Exception:
                    pass
            await asyncio.sleep(self.poll_interval)


class WebhookReceiver:
    """Minimal HTTP server accepting POST error reports."""

    def __init__(self, port: int) -> None:
        self.port = port
        self._queue: asyncio.Queue[Signal] = asyncio.Queue()
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_connection, "127.0.0.1", self.port,
        )

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            await reader.readline()  # request line
            headers: dict[str, str] = {}
            while True:
                header_line = await reader.readline()
                if header_line in (b"\r\n", b"\n", b""):
                    break
                if b":" in header_line:
                    key, val = header_line.decode().split(":", 1)
                    headers[key.strip().lower()] = val.strip()

            content_length = int(headers.get("content-length", "0"))
            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            try:
                data = json.loads(body.decode())
                signal = Signal(
                    source="webhook",
                    raw_text=data.get("error", data.get("message", str(data))),
                    timestamp=datetime.now().isoformat(),
                    log_key=data.get("log_key", ""),
                )
                await self._queue.put(signal)
                response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
            except (json.JSONDecodeError, KeyError):
                response = b"HTTP/1.1 400 Bad Request\r\nContent-Length: 11\r\n\r\nBad Request"

            writer.write(response)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def signals(self):
        while True:
            signal = await self._queue.get()
            yield signal

    def stop(self) -> None:
        if self._server:
            self._server.close()


class StdoutWatcher:
    """Watches stdout of a subprocess for error patterns."""

    def __init__(self, error_patterns: list[str] | None = None) -> None:
        self._patterns = [re.compile(p) for p in (error_patterns or ["ERROR", "CRITICAL", "Traceback"])]

    async def watch_process(self, proc: asyncio.subprocess.Process):
        """Yield signals from a process's stdout."""
        if not proc.stdout:
            return
        while True:
            try:
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if any(p.search(line) for p in self._patterns):
                    yield Signal(
                        source="log_file",
                        raw_text=line,
                        timestamp=datetime.now().isoformat(),
                    )
            except asyncio.CancelledError:
                break


class SignalIngester:
    """Orchestrates all signal sources with deduplication.

    Driven by SourceConfig from sentinel.yaml instead of MonitoringTarget.
    """

    def __init__(
        self,
        sources: list[SourceConfig],
        dedup_window_seconds: float = 300.0,
    ) -> None:
        self._sources = sources
        self._dedup_window = dedup_window_seconds
        self._fingerprints: dict[str, SignalFingerprint] = {}
        self._signal_queue: asyncio.Queue[Signal] = asyncio.Queue()
        self._tailers: list[LogTailer] = []
        self._webhooks: list[WebhookReceiver] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all configured signal sources."""
        for source in self._sources:
            if source.type == "file" and source.path:
                tailer = LogTailer(source.path, source.error_patterns)
                self._tailers.append(tailer)
                await tailer.start()
                self._tasks.append(
                    asyncio.create_task(self._consume_tailer(tailer))
                )

    async def _consume_tailer(self, tailer: LogTailer) -> None:
        try:
            async for line in tailer.lines():
                signal = Signal(
                    source="log_file",
                    raw_text=line,
                    timestamp=datetime.now().isoformat(),
                    file_path=tailer.path,
                    log_key=_extract_key_str(line),
                )
                if self._deduplicate(signal):
                    await self._signal_queue.put(signal)
        except asyncio.CancelledError:
            pass

    def _deduplicate(self, signal: Signal) -> bool:
        """Returns True if signal is new (should be emitted)."""
        fp_hash = fingerprint_signal(signal)
        now = datetime.now()

        if fp_hash in self._fingerprints:
            existing = self._fingerprints[fp_hash]
            last_seen = datetime.fromisoformat(existing.last_seen)
            if (now - last_seen).total_seconds() < self._dedup_window:
                existing.count += 1
                existing.last_seen = now.isoformat()
                return False

        self._fingerprints[fp_hash] = SignalFingerprint(
            hash=fp_hash,
            first_seen=now.isoformat(),
            last_seen=now.isoformat(),
            count=1,
            representative=signal,
        )
        return True

    async def watch(self):
        """Async generator yielding Signal objects."""
        while True:
            signal = await self._signal_queue.get()
            yield signal

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for tailer in self._tailers:
            tailer.stop()
        for webhook in self._webhooks:
            webhook.stop()


# Default pattern for extracting PACT key strings from lines
_KEY_PATTERN = re.compile(r"PACT:[a-zA-Z0-9_]+:[a-zA-Z0-9_]+")


def _extract_key_str(line: str) -> str:
    """Extract PACT:xxx:yyy from a line, returning the full key string or empty."""
    m = _KEY_PATTERN.search(line)
    return m.group(0) if m else ""
