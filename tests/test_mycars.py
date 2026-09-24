"""Contract tests for the C3 MyCars installed-software-version path."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from polestar_api import grpc as grpc_call
from polestar_api.codec import decode, encode_message
from polestar_api.connection import GrpcConnection
from polestar_api.models.mycars import CarDetails, MyCarEntry
from polestar_api.services.mycars import MyCarsServiceClient


class FakeConnection:
    def __init__(self) -> None:
        self.backend = SimpleNamespace(mycars_svc="/car_information.CarInformation")
        self.channel = object()

    async def get_metadata(self, vin: str) -> dict[str, str]:
        return {"authorization": "Bearer redacted", "vin": vin}


def _entry(vin: str, version: str) -> bytes:
    return MyCarEntry(
        details=CarDetails(
            vin=vin,
            model_name="Polestar 4",
            model_year="2026",
            installed_software_version=version,
            market="GB",
        )
    ).to_bytes()


@pytest.mark.asyncio
async def test_get_mycars_selects_matching_vin_and_builds_expected_request(monkeypatch) -> None:
    connection = FakeConnection()
    response = encode_message(1, _entry("OTHER-VIN", "P4.2.10")) + encode_message(
        1, _entry("TARGET-VIN", "P4.2.11")
    )
    call = AsyncMock(return_value=response)
    monkeypatch.setattr(grpc_call, "unary_unary", call)
    monkeypatch.setattr(
        "polestar_api.services.mycars.uuid.uuid4",
        lambda: UUID("00000000-0000-0000-0000-000000000001"),
    )

    result = await MyCarsServiceClient(
        cast(GrpcConnection, connection), "TARGET-VIN"
    ).get_mycars()

    assert result is not None
    assert result.details is not None
    assert result.details.vin == "TARGET-VIN"
    assert result.details.installed_software_version == "P4.2.11"

    await_args = call.await_args
    assert await_args is not None
    channel, method, request = await_args.args
    assert channel is connection.channel
    assert method == "/car_information.CarInformation/GetMyCars"
    assert decode(request, {1: ("id", "string"), 2: ("vin", "string")}) == {
        "id": "00000000-0000-0000-0000-000000000001",
        "vin": "TARGET-VIN",
    }
    assert await_args.kwargs["metadata"]["vin"] == "TARGET-VIN"


@pytest.mark.asyncio
async def test_get_mycars_single_entry_fallback_and_empty_response(monkeypatch) -> None:
    connection = FakeConnection()
    call = AsyncMock(return_value=encode_message(1, _entry("", "P4.2.11")))
    monkeypatch.setattr(grpc_call, "unary_unary", call)

    result = await MyCarsServiceClient(
        cast(GrpcConnection, connection), "TARGET-VIN"
    ).get_mycars()
    assert result is not None
    assert result.details is not None
    assert result.details.installed_software_version == "P4.2.11"

    call.return_value = b""
    assert (
        await MyCarsServiceClient(
            cast(GrpcConnection, connection), "TARGET-VIN"
        ).get_mycars()
        is None
    )

    call.return_value = encode_message(1, _entry("DIFFERENT-VIN", "P4.9.9"))
    assert (
        await MyCarsServiceClient(
            cast(GrpcConnection, connection), "TARGET-VIN"
        ).get_mycars()
        is None
    )
