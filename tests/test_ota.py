"""OTA discovery distinguishes transport timeout from a successful empty stream."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest

from polestar_api import grpc as grpc_call
from polestar_api.connection import GrpcConnection
from polestar_api.services import ota as ota_module
from polestar_api.services.ota import OtaServiceClient


class FakeConnection:
    def __init__(self) -> None:
        self.backend = SimpleNamespace(
            ota_discovery_svc="/ota_mobcache.OtaDiscoveryService",
            ota_scheduler_svc="/ota_mobcache.SchedulerService",
        )
        self.channel = object()

    async def get_metadata(self, vin: str) -> dict[str, str]:
        return {"authorization": "Bearer redacted", "vin": vin}


@pytest.mark.asyncio
async def test_software_info_timeout_propagates(monkeypatch) -> None:
    async def hanging_stream():
        await asyncio.sleep(1)
        if False:
            yield b""

    monkeypatch.setattr(grpc_call, "unary_stream", lambda *args, **kwargs: hanging_stream())
    monkeypatch.setattr(ota_module, "_STREAM_TIMEOUT", 0.001)
    client = OtaServiceClient(cast(GrpcConnection, FakeConnection()), "TARGET-VIN")

    with pytest.raises(TimeoutError):
        await client.get_software_info()


@pytest.mark.asyncio
async def test_software_info_completed_empty_stream_returns_none(monkeypatch) -> None:
    async def empty_stream():
        if False:
            yield b""

    monkeypatch.setattr(grpc_call, "unary_stream", lambda *args, **kwargs: empty_stream())
    client = OtaServiceClient(cast(GrpcConnection, FakeConnection()), "TARGET-VIN")

    assert await client.get_software_info() is None


@pytest.mark.asyncio
async def test_schedule_timeout_propagates(monkeypatch) -> None:
    async def hanging_stream():
        await asyncio.sleep(1)
        if False:
            yield b""

    monkeypatch.setattr(grpc_call, "unary_stream", lambda *args, **kwargs: hanging_stream())
    monkeypatch.setattr(ota_module, "_STREAM_TIMEOUT", 0.001)
    client = OtaServiceClient(cast(GrpcConnection, FakeConnection()), "TARGET-VIN")

    with pytest.raises(TimeoutError):
        await client.get_schedule()


@pytest.mark.asyncio
async def test_schedule_completed_empty_stream_returns_none(monkeypatch) -> None:
    async def empty_stream():
        if False:
            yield b""

    monkeypatch.setattr(grpc_call, "unary_stream", lambda *args, **kwargs: empty_stream())
    client = OtaServiceClient(cast(GrpcConnection, FakeConnection()), "TARGET-VIN")

    assert await client.get_schedule() is None
