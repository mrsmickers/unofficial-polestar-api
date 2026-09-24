"""Pure software-version arbitration shared by Polestar entities."""

from __future__ import annotations

from polestar_api.models.mycars import MyCarEntry
from polestar_api.models.ota import CarSoftwareInfo, SoftwareState

_INSTALLED_OTA_STATES = {
    SoftwareState.UNKNOWN,
    SoftwareState.INSTALLATION_COMPLETED,
    SoftwareState.INSTALLATION_UNKNOWN,
}


def installed_software_version(
    software: CarSoftwareInfo | None,
    mycars: MyCarEntry | None,
) -> str | None:
    """Return the installed version, preferring MyCars over OTA target data."""
    if mycars is not None and mycars.details and mycars.details.installed_software_version:
        return mycars.details.installed_software_version
    if (
        software is not None
        and software.new_sw_version
        and software.state in _INSTALLED_OTA_STATES
    ):
        return software.new_sw_version
    return None


def advertised_software_version(
    *,
    software_fetch_succeeded: bool,
    software: CarSoftwareInfo | None,
    mycars: MyCarEntry | None,
) -> str | None:
    """Return the pending target, or installed version after a successful empty fetch."""
    if not software_fetch_succeeded:
        return None
    if software is not None and software.new_sw_version:
        return software.new_sw_version
    return installed_software_version(software, mycars)
