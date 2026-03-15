"""Tests for internal event bus."""

from __future__ import annotations

import pytest

from sentinel.events import EventBus, SentinelEvent


class TestEventBus:
    @pytest.mark.asyncio
    async def test_handler_receives_event(self):
        bus = EventBus()
        received = []
        bus.on("test", lambda e: received.append(e))
        await bus.emit(SentinelEvent(kind="test", detail="hello"))
        assert len(received) == 1
        assert received[0].detail == "hello"

    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        bus = EventBus()
        results = []
        bus.on("x", lambda e: results.append("a"))
        bus.on("x", lambda e: results.append("b"))
        await bus.emit(SentinelEvent(kind="x"))
        assert results == ["a", "b"]

    @pytest.mark.asyncio
    async def test_wildcard_handler(self):
        bus = EventBus()
        received = []
        bus.on("*", lambda e: received.append(e.kind))
        await bus.emit(SentinelEvent(kind="foo"))
        await bus.emit(SentinelEvent(kind="bar"))
        assert received == ["foo", "bar"]

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_propagate(self):
        bus = EventBus()

        def bad_handler(e):
            raise ValueError("boom")

        received = []
        bus.on("test", bad_handler)
        bus.on("test", lambda e: received.append("ok"))

        await bus.emit(SentinelEvent(kind="test"))
        assert received == ["ok"]

    @pytest.mark.asyncio
    async def test_async_handler(self):
        bus = EventBus()
        received = []

        async def handler(e):
            received.append(e.kind)

        bus.on("async_test", handler)
        await bus.emit(SentinelEvent(kind="async_test"))
        assert received == ["async_test"]

    @pytest.mark.asyncio
    async def test_unmatched_kind_no_handlers(self):
        bus = EventBus()
        bus.on("other", lambda e: None)
        # Should not raise
        await bus.emit(SentinelEvent(kind="nonexistent"))


class TestSentinelEvent:
    def test_defaults(self):
        e = SentinelEvent(kind="test")
        assert e.kind == "test"
        assert e.component_id == ""
        assert e.detail == ""
        assert e.timestamp != ""
