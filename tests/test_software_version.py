"""Regression tests for installed-vs-advertised software-version arbitration."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from polestar_api.models.mycars import CarDetails, MyCarEntry
from polestar_api.models.ota import CarSoftwareInfo, SoftwareState


def _load_module(name: str, relative_path: str):
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(name, root / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stub_module(monkeypatch, name: str, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class FakeDataUpdateCoordinator:
    @classmethod
    def __class_getitem__(cls, item):
        return cls


class FakeCoordinatorEntity:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator


class FakeConfigEntryAuthFailed(Exception):
    pass


class FakeHomeAssistantError(Exception):
    pass


class FakeUpdateFailed(Exception):
    pass


def _load_coordinator_module(monkeypatch):
    _stub_module(monkeypatch, "homeassistant")
    _stub_module(
        monkeypatch,
        "homeassistant.exceptions",
        ConfigEntryAuthFailed=FakeConfigEntryAuthFailed,
        HomeAssistantError=FakeHomeAssistantError,
    )
    _stub_module(monkeypatch, "homeassistant.helpers")
    _stub_module(
        monkeypatch,
        "homeassistant.helpers.device_registry",
        DeviceInfo=lambda **kwargs: kwargs,
    )
    _stub_module(
        monkeypatch,
        "homeassistant.helpers.update_coordinator",
        CoordinatorEntity=FakeCoordinatorEntity,
        DataUpdateCoordinator=FakeDataUpdateCoordinator,
        UpdateFailed=FakeUpdateFailed,
    )
    _stub_module(monkeypatch, "homeassistant.util")
    _stub_module(
        monkeypatch,
        "homeassistant.util.dt",
        UTC=UTC,
        now=lambda: datetime.now(UTC),
    )

    package_name = "_polestar_coordinator_under_test"
    component_dir = Path(__file__).parents[1] / "custom_components" / "polestar"
    package = types.ModuleType(package_name)
    package.__path__ = [str(component_dir)]
    monkeypatch.setitem(sys.modules, package_name, package)

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.coordinator",
        component_dir / "coordinator.py",
        submodule_search_locations=[str(component_dir)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f"{package_name}.coordinator", module)
    spec.loader.exec_module(module)
    return module


def _load_entity_module(monkeypatch):
    coordinator_module = _load_coordinator_module(monkeypatch)
    package_name = "_polestar_coordinator_under_test"
    component_dir = Path(__file__).parents[1] / "custom_components" / "polestar"
    spec = importlib.util.spec_from_file_location(
        f"{package_name}.entity",
        component_dir / "entity.py",
        submodule_search_locations=[str(component_dir)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f"{package_name}.entity", module)
    spec.loader.exec_module(module)
    return coordinator_module, module


software_helpers = _load_module(
    "polestar_software_under_test",
    "custom_components/polestar/software.py",
)


def _mycars(version: str = "P4.2.11") -> MyCarEntry:
    return MyCarEntry(
        details=CarDetails(
            vin="TARGET-VIN",
            model_name="Polestar 4",
            model_year="2026",
            installed_software_version=version,
            market="GB",
        )
    )


def test_pending_target_is_not_reported_as_installed() -> None:
    pending = CarSoftwareInfo(
        software_id="pending-1",
        new_sw_version="P4.2.13",
        state=SoftwareState.DOWNLOAD_READY,
    )

    assert software_helpers.installed_software_version(pending, _mycars()) == "P4.2.11"
    assert (
        software_helpers.advertised_software_version(
            software_fetch_succeeded=True,
            software=pending,
            mycars=_mycars(),
        )
        == "P4.2.13"
    )


def test_empty_ota_success_and_ota_failure_are_distinct() -> None:
    assert (
        software_helpers.advertised_software_version(
            software_fetch_succeeded=True,
            software=None,
            mycars=_mycars(),
        )
        == "P4.2.11"
    )
    assert (
        software_helpers.advertised_software_version(
            software_fetch_succeeded=False,
            software=None,
            mycars=_mycars(),
        )
        is None
    )


def test_completed_ota_is_a_fallback_when_mycars_is_missing() -> None:
    completed = CarSoftwareInfo(
        software_id="completed-1",
        new_sw_version="P4.2.10",
        state=SoftwareState.INSTALLATION_COMPLETED,
    )
    assert software_helpers.installed_software_version(completed, None) == "P4.2.10"


def test_unknown_ota_state_is_not_proof_of_installation() -> None:
    unknown = CarSoftwareInfo(
        software_id="ambiguous-1",
        new_sw_version="P4.9.9",
        state=SoftwareState.UNKNOWN,
    )
    assert software_helpers.installed_software_version(unknown, None) is None


def test_software_state_distinguishes_failure_empty_and_value() -> None:
    assert (
        software_helpers.software_state_value(
            software_fetch_succeeded=False,
            software=CarSoftwareInfo(state=SoftwareState.DOWNLOAD_READY),
        )
        is None
    )
    assert (
        software_helpers.software_state_value(
            software_fetch_succeeded=True,
            software=None,
        )
        == "no_update_available"
    )
    assert (
        software_helpers.software_state_value(
            software_fetch_succeeded=True,
            software=CarSoftwareInfo(state=SoftwareState.DOWNLOAD_READY),
        )
        == "download_ready"
    )


@pytest.mark.asyncio
async def test_demo_vehicle_exposes_mycars() -> None:
    demo_module = _load_module(
        "polestar_demo_under_test",
        "custom_components/polestar/demo.py",
    )
    vehicle = demo_module.DemoVehicle()

    info = await vehicle.get_mycars()

    assert info.details is not None
    assert info.details.vin == vehicle.vin
    assert info.details.installed_software_version == "P2.8.1"


def test_device_registry_never_uses_unknown_ota_target_as_installed(monkeypatch) -> None:
    coordinator_module, entity_module = _load_entity_module(monkeypatch)
    vehicle = SimpleNamespace(
        vin="TARGET-VIN",
        model_name="Polestar 4",
        registration_no="AB12 CDE",
    )
    coordinator = SimpleNamespace(
        vehicle=vehicle,
        data=coordinator_module.PolestarVehicleData(
            software=CarSoftwareInfo(
                software_id="ambiguous-1",
                new_sw_version="P4.9.9",
                state=SoftwareState.UNKNOWN,
            ),
            software_fetch_succeeded=True,
        ),
        installed_version_cache=None,
    )

    entity = entity_module.PolestarEntity(coordinator)

    assert entity.device_info["sw_version"] is None


@pytest.mark.asyncio
async def test_coordinator_distinguishes_empty_ota_success_from_failure(monkeypatch) -> None:
    coordinator_module = _load_coordinator_module(monkeypatch)
    previous_software = CarSoftwareInfo(
        software_id="stale-update",
        new_sw_version="P4.2.13",
        state=SoftwareState.DOWNLOAD_READY,
    )
    previous = coordinator_module.PolestarVehicleData(
        software=previous_software,
        software_fetch_succeeded=True,
    )

    class Vehicle:
        vin = "TARGET-VIN"

        async def get_software_info(self):
            return None

    coordinator = object.__new__(coordinator_module.PolestarCoordinator)
    coordinator.vehicle = Vehicle()

    values, successes = await coordinator._async_fetch_values(["software"], previous)
    assert successes == 1
    assert values["software"] is None
    assert values["software_fetch_succeeded"] is True

    async def fail():
        raise RuntimeError("temporary OTA failure")

    coordinator.vehicle.get_software_info = fail
    values, successes = await coordinator._async_fetch_values(["software"], previous)
    assert successes == 0
    assert values["software"] is previous_software
    assert values["software_fetch_succeeded"] is False

    captured = []
    coordinator.data = previous

    def capture(data):
        captured.append(data)
        coordinator.data = data

    coordinator.async_set_updated_data = capture
    await coordinator.async_request_attrs_refresh("software")

    assert captured
    assert captured[-1].software_fetch_succeeded is False
    with pytest.raises(FakeHomeAssistantError):
        coordinator._require_software_id()
