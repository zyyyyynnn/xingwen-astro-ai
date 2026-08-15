"""Bounded spectrum and light-curve analysis built on trusted numeric libraries."""

from __future__ import annotations

from math import isfinite
from statistics import median

import numpy as np

from .parameters import (
    optional_number,
    optional_string,
    reject_unknown,
    require_rows,
    require_string,
)
from .types import ScientificSkillRequest


def analyze_spectrum(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "wavelength_field",
            "flux_field",
            "uncertainty_field",
            "object_name",
            "wavelength_unit",
            "flux_unit",
            "rest_wavelength",
            "line_sigma",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    wavelength_field = require_string(request.parameters, "wavelength_field")
    flux_field = require_string(request.parameters, "flux_field")
    uncertainty_field = optional_string(request.parameters, "uncertainty_field")
    samples = sorted(
        (
            _number(row.get(wavelength_field), wavelength_field),
            _number(row.get(flux_field), flux_field),
            (
                _positive_number(row.get(uncertainty_field), uncertainty_field)
                if uncertainty_field is not None and row.get(uncertainty_field) is not None
                else None
            ),
        )
        for row in rows
    )
    if len(samples) < 8:
        raise ValueError("spectrum analysis requires at least 8 finite samples")
    wavelengths = np.asarray([item[0] for item in samples], dtype=np.float64)
    flux = np.asarray([item[1] for item in samples], dtype=np.float64)
    if np.any(wavelengths <= 0) or np.any(np.diff(wavelengths) <= 0):
        raise ValueError("spectrum wavelengths must be unique and positive")

    continuum = _continuum(wavelengths, flux)
    normalized = flux / continuum
    residual = normalized - 1.0
    noise = _robust_scale(np.diff(normalized)) / np.sqrt(2.0)
    if noise <= 0:
        noise = max(float(np.std(residual)), 1e-12)
    line_sigma = optional_number(request.parameters, "line_sigma", default=4.0)
    if not 2 <= line_sigma <= 20:
        raise ValueError("line_sigma must be between 2 and 20")
    lines = _spectral_lines(wavelengths, normalized, residual, noise, line_sigma)
    strongest = lines[0] if lines else None
    rest_wavelength = (
        optional_number(request.parameters, "rest_wavelength", default=0.0)
        if "rest_wavelength" in request.parameters
        else None
    )
    if rest_wavelength is not None and rest_wavelength <= 0:
        raise ValueError("rest_wavelength must be positive")
    radial_velocity = (
        299_792.458
        * (float(strongest["observed_wavelength"]) / rest_wavelength - 1.0)
        if strongest is not None and rest_wavelength is not None
        else None
    )
    selected = _sample_indices(len(samples), request.budget.max_output_rows)
    points = [
        {
            "wavelength": float(wavelengths[index]),
            "flux": float(flux[index]),
            "continuum": float(continuum[index]),
            "normalized_flux": float(normalized[index]),
            "uncertainty": samples[index][2],
        }
        for index in selected
    ]
    return {
        "object_name": optional_string(
            request.parameters, "object_name", default="Observed target"
        ),
        "wavelength_unit": optional_string(
            request.parameters, "wavelength_unit", default="angstrom"
        ),
        "flux_unit": optional_string(
            request.parameters, "flux_unit", default="relative_flux"
        ),
        "sample_count": len(samples),
        "display_sample_count": len(points),
        "wavelength_min": float(wavelengths[0]),
        "wavelength_max": float(wavelengths[-1]),
        "signal_to_noise": min(1e12, 1.0 / noise),
        "radial_velocity_km_s": radial_velocity,
        "rest_wavelength": rest_wavelength,
        "detected_lines": lines,
        "points": points,
    }


def analyze_light_curve(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "time_field",
            "value_field",
            "uncertainty_field",
            "object_name",
            "time_scale",
            "time_unit",
            "value_unit",
            "value_kind",
            "sigma_clip",
            "minimum_period",
            "maximum_period",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    time_field = require_string(request.parameters, "time_field")
    value_field = require_string(request.parameters, "value_field")
    uncertainty_field = optional_string(request.parameters, "uncertainty_field")
    samples = sorted(
        (
            _number(row.get(time_field), time_field),
            _number(row.get(value_field), value_field),
            (
                _positive_number(row.get(uncertainty_field), uncertainty_field)
                if uncertainty_field is not None and row.get(uncertainty_field) is not None
                else None
            ),
        )
        for row in rows
    )
    if len(samples) < 8:
        raise ValueError("light-curve analysis requires at least 8 finite samples")
    times = np.asarray([item[0] for item in samples], dtype=np.float64)
    values = np.asarray([item[1] for item in samples], dtype=np.float64)
    if np.any(np.diff(times) <= 0):
        raise ValueError("light-curve times must be unique")
    value_kind = optional_string(
        request.parameters, "value_kind", default="relative_flux"
    )
    if value_kind not in {"relative_flux", "flux", "magnitude"}:
        raise ValueError("value_kind must be relative_flux, flux, or magnitude")
    center = float(np.median(values))
    if value_kind in {"relative_flux", "flux"}:
        if center == 0:
            raise ValueError("light-curve median flux must be non-zero")
        normalized = values / center
        normalization = "median_division"
    else:
        normalized = values - center
        normalization = "median_subtraction"
    sigma_clip = optional_number(request.parameters, "sigma_clip", default=5.0)
    if not 2 <= sigma_clip <= 20:
        raise ValueError("sigma_clip must be between 2 and 20")
    scale = _robust_scale(normalized)
    good = (
        np.ones(len(samples), dtype=bool)
        if scale <= 0
        else np.abs(normalized - np.median(normalized)) <= sigma_clip * scale
    )
    if int(np.sum(good)) < 5:
        raise ValueError("light curve has fewer than 5 samples after quality filtering")
    good_times = times[good]
    good_values = normalized[good]
    duration = float(good_times[-1] - good_times[0])
    if duration <= 0:
        raise ValueError("light-curve duration must be positive")
    cadence = float(median(np.diff(good_times).tolist()))
    minimum_period = optional_number(
        request.parameters,
        "minimum_period",
        default=max(2.0 * cadence, duration / 10_000.0),
    )
    maximum_period = optional_number(
        request.parameters, "maximum_period", default=duration / 2.0
    )
    if minimum_period <= 0 or maximum_period <= minimum_period:
        raise ValueError("light-curve period bounds are invalid")
    periodogram = _periodogram(
        good_times,
        good_values,
        minimum_period=minimum_period,
        maximum_period=maximum_period,
    )
    selected = _sample_indices(len(samples), request.budget.max_output_rows)
    best_period = float(periodogram["best_period"])
    points = [
        {
            "time": float(times[index]),
            "value": float(values[index]),
            "normalized_value": float(normalized[index]),
            "uncertainty": samples[index][2],
            "quality": "good" if good[index] else "rejected",
            "phase": float(((times[index] - good_times[0]) / best_period) % 1.0),
        }
        for index in selected
    ]
    return {
        "object_name": optional_string(
            request.parameters, "object_name", default="Observed target"
        ),
        "time_scale": optional_string(request.parameters, "time_scale", default="tdb"),
        "time_unit": optional_string(request.parameters, "time_unit", default="day"),
        "value_unit": optional_string(
            request.parameters, "value_unit", default=str(value_kind)
        ),
        "value_kind": value_kind,
        "normalization": normalization,
        "sample_count": len(samples),
        "accepted_sample_count": int(np.sum(good)),
        "rejected_sample_count": int(np.sum(~good)),
        "duration": duration,
        "median_cadence": cadence,
        **periodogram,
        "points": points,
    }


def _continuum(wavelengths: np.ndarray, flux: np.ndarray) -> np.ndarray:
    scaled = 2.0 * (wavelengths - wavelengths[0]) / (
        wavelengths[-1] - wavelengths[0]
    ) - 1.0
    mask = np.ones(len(flux), dtype=bool)
    degree = min(3, len(flux) - 1)
    fit = np.full(len(flux), float(np.median(flux)))
    for _ in range(4):
        if int(np.sum(mask)) <= degree:
            break
        coefficients = np.polyfit(scaled[mask], flux[mask], degree)
        fit = np.polyval(coefficients, scaled)
        residual = flux - fit
        scale = _robust_scale(residual[mask])
        if scale <= 0:
            break
        mask = np.abs(residual) <= 3.0 * scale
    if np.any(~np.isfinite(fit)) or np.any(np.abs(fit) < 1e-15):
        raise ValueError("spectrum continuum could not be estimated safely")
    return fit


def _spectral_lines(
    wavelengths: np.ndarray,
    normalized: np.ndarray,
    residual: np.ndarray,
    noise: float,
    line_sigma: float,
) -> list[dict[str, object]]:
    candidates = [
        index
        for index in range(1, len(residual) - 1)
        if abs(float(residual[index])) >= line_sigma * noise
        and abs(float(residual[index])) >= abs(float(residual[index - 1]))
        and abs(float(residual[index])) > abs(float(residual[index + 1]))
    ]
    candidates.sort(key=lambda index: abs(float(residual[index])), reverse=True)
    lines = []
    for rank, index in enumerate(candidates[:32], start=1):
        left = max(0, index - 2)
        right = min(len(residual), index + 3)
        equivalent_width = float(
            np.trapezoid(1.0 - normalized[left:right], wavelengths[left:right])
        )
        lines.append(
            {
                "line_id": f"line.{rank}",
                "kind": "emission" if residual[index] > 0 else "absorption",
                "observed_wavelength": float(wavelengths[index]),
                "normalized_flux": float(normalized[index]),
                "significance_sigma": abs(float(residual[index])) / noise,
                "equivalent_width": equivalent_width,
            }
        )
    return lines


def _periodogram(
    times: np.ndarray,
    values: np.ndarray,
    *,
    minimum_period: float,
    maximum_period: float,
) -> dict[str, object]:
    from astropy.timeseries import LombScargle

    model = LombScargle(times, values, normalization="standard")
    frequency, power = model.autopower(
        minimum_frequency=1.0 / maximum_period,
        maximum_frequency=1.0 / minimum_period,
        samples_per_peak=5,
    )
    if not len(power) or np.any(~np.isfinite(power)):
        raise ValueError("light-curve periodogram did not produce finite power")
    best_index = int(np.argmax(power))
    peaks = [
        index
        for index in range(1, len(power) - 1)
        if power[index] >= power[index - 1] and power[index] > power[index + 1]
    ]
    if best_index not in peaks:
        peaks.append(best_index)
    peaks.sort(key=lambda index: float(power[index]), reverse=True)
    best_power = float(power[best_index])
    try:
        false_alarm_probability = float(model.false_alarm_probability(best_power))
    except (ValueError, RuntimeError):
        false_alarm_probability = None
    return {
        "best_period": float(1.0 / frequency[best_index]),
        "best_power": best_power,
        "false_alarm_probability": false_alarm_probability,
        "period_peaks": [
            {"period": float(1.0 / frequency[index]), "power": float(power[index])}
            for index in peaks[:10]
        ],
    }


def _sample_indices(length: int, limit: int) -> list[int]:
    if length <= limit:
        return list(range(length))
    return sorted({int(index) for index in np.linspace(0, length - 1, limit)})


def _robust_scale(values: np.ndarray) -> float:
    center = float(np.median(values))
    return 1.4826 * float(np.median(np.abs(values - center)))


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must contain only finite numeric values")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field} must contain only finite numeric values")
    return normalized


def _positive_number(value: object, field: str) -> float:
    normalized = _number(value, field)
    if normalized <= 0:
        raise ValueError(f"{field} must contain positive uncertainties")
    return normalized


__all__ = ["analyze_light_curve", "analyze_spectrum"]
