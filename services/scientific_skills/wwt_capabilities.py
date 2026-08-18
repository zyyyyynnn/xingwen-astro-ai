"""Auditable capability boundary for declarative WorldWide Telescope scenes."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Literal, TypedDict


CapabilityStatus = Literal["supported", "unsupported"]


class WwtCapabilityDisposition(TypedDict):
    contract: CapabilityStatus
    engine: CapabilityStatus
    renderer: CapabilityStatus


def _disposition(
    *,
    contract: CapabilityStatus,
    engine: CapabilityStatus,
    renderer: CapabilityStatus,
) -> WwtCapabilityDisposition:
    return {"contract": contract, "engine": engine, "renderer": renderer}


WWT_CAPABILITY_MATRIX: Final = MappingProxyType(
    {
        "annotation_circle": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "annotation_label": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "annotation_line": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "annotation_point": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "annotation_style": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "arbitrary_websocket_command": _disposition(
            contract="unsupported", engine="unsupported", renderer="unsupported"
        ),
        "automatic_screenshot_upload": _disposition(
            contract="unsupported", engine="unsupported", renderer="unsupported"
        ),
        "background": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "camera_roll": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "center_on_coordinates": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "constellation_overlays": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "coordinate_grid_labels": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "current_time_readback": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "fits_display_settings": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "fits_layer": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "fixed_time": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "foreground": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "local_horizon_mode": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "multiple_coordinate_grids": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "observer_location": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "precession_chart": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "screenshot_polling": _disposition(
            contract="unsupported", engine="supported", renderer="unsupported"
        ),
        "single_coordinate_grid": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "solar_system_overlays": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "system_clock": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "table_layer": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "text_alternative": _disposition(
            contract="supported", engine="unsupported", renderer="supported"
        ),
        "time_pause": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "time_playback": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "tour_steps": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "track_object": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
        "unbounded_remote_layer_url": _disposition(
            contract="unsupported", engine="supported", renderer="unsupported"
        ),
        "view_readback": _disposition(
            contract="supported", engine="supported", renderer="supported"
        ),
    }
)


__all__ = ["WWT_CAPABILITY_MATRIX", "WwtCapabilityDisposition"]
