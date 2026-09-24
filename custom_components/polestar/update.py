"""Update platform for Polestar OTA state."""

from __future__ import annotations

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from polestar_api.models.ota import SoftwareState

from .const import DOMAIN
from .coordinator import PolestarCoordinator
from .entity import PolestarEntity
from .software import advertised_software_version, installed_software_version
from .utils import enum_name, timestamp_to_iso

_IN_PROGRESS_STATES = {
    SoftwareState.DOWNLOAD_STARTED,
    SoftwareState.DOWNLOAD_COMPLETED,
    SoftwareState.INSTALLATION_INITIATED,
    SoftwareState.INSTALLATION_STARTED,
    SoftwareState.INSTALLATION_SCHEDULED,
    SoftwareState.INSTALLATION_SCHEDULE_TRIGGERED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Polestar update entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    entities = [
        PolestarOtaUpdate(coordinator)
        for coordinator in data["coordinators"].values()
    ]
    async_add_entities(entities)


class PolestarOtaUpdate(PolestarEntity, UpdateEntity, RestoreEntity):
    """OTA update entity backed by the Polestar software info API."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_name = "Software update"
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(self, coordinator: PolestarCoordinator) -> None:
        super().__init__(coordinator)
        self.entity_description = UpdateEntityDescription(key="software_update")
        self._attr_unique_id = f"{self._vehicle.vin}_software_update"

    async def async_added_to_hass(self) -> None:
        """Restore the last known installed version across restarts."""
        await super().async_added_to_hass()
        if self.coordinator.installed_version_cache:
            return
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        installed_version = last_state.attributes.get("installed_version")
        if isinstance(installed_version, str) and installed_version:
            self.coordinator.restore_installed_version_cache(installed_version)

    @property
    def available(self) -> bool:
        if not super().available or self.coordinator.data is None:
            return False
        data = self.coordinator.data
        return data.software_fetch_succeeded and (
            data.software is not None or data.mycars is not None
        )

    @property
    def installed_version(self) -> str | None:
        data = self.coordinator.data
        version = (
            installed_software_version(data.software, data.mycars)
            if data
            else None
        )
        return version or self.coordinator.installed_version_cache

    @property
    def latest_version(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        return advertised_software_version(
            software_fetch_succeeded=data.software_fetch_succeeded,
            software=data.software,
            mycars=data.mycars,
        )

    @property
    def in_progress(self) -> bool | int:
        data = self.coordinator.data
        if data and data.software_fetch_succeeded and data.software:
            return data.software.state in _IN_PROGRESS_STATES
        return False

    @property
    def release_summary(self) -> str | None:
        data = self.coordinator.data
        software = data.software if data and data.software_fetch_succeeded else None
        if software is None or software.description is None:
            return None
        parts = [part for part in (software.description.short_desc, software.description.long_desc) if part]
        if not parts:
            return None
        return "\n\n".join(parts)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        data = self.coordinator.data
        software = data.software if data and data.software_fetch_succeeded else None
        schedule = data.ota_schedule if data else None
        return {
            "software_id": software.software_id if software else None,
            "software_state": enum_name(software.state) if software else None,
            "software_state_timestamp": timestamp_to_iso(software.state_timestamp) if software else None,
            "scheduled_for": timestamp_to_iso(software.schedule_info.scheduled_at) if software and software.schedule_info else None,
            "scheduler_status": enum_name(schedule.status) if schedule else None,
            "scheduler_scheduled_time": timestamp_to_iso(schedule.scheduled_time) if schedule else None,
            "scheduler_set_by": enum_name(schedule.set_by) if schedule else None,
        }

    async def async_install(
        self,
        version: str | None,
        backup: bool,
        **kwargs,
    ) -> None:
        """Install the currently available OTA update immediately."""
        if version is not None and version != self.latest_version:
            raise HomeAssistantError(f"Version {version} is not the advertised OTA version")
        await self.coordinator.async_install_ota_now()
