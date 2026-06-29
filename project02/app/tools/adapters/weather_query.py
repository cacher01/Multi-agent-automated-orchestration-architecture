from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.tools.adapters.base import AdapterResult, ToolAdapterError


class WeatherQueryAdapter:
    name = "weather_query"

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        location = str(tool_input.get("location") or "").strip()
        if not location:
            raise ToolAdapterError("invalid_input", "Weather location is required.")
        try:
            geocode = httpx.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1, "language": "en", "format": "json"},
                timeout=self.timeout_seconds,
            )
            geocode.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolAdapterError("external_request_failed", "Weather geocoding request failed.") from exc
        results = geocode.json().get("results") or []
        if not results:
            raise ToolAdapterError("location_not_found", f"Location was not found: {location}")
        place = results[0]
        try:
            forecast = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                },
                timeout=self.timeout_seconds,
            )
            forecast.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolAdapterError("external_request_failed", "Weather forecast request failed.") from exc
        payload = forecast.json()
        current = payload.get("current") or {}
        units = payload.get("current_units") or {}
        temp_unit = units.get("temperature_2m", "")
        wind_unit = units.get("wind_speed_10m", "")
        output = {
            "location": place.get("name", location),
            "date": str(current.get("time") or ""),
            "summary": f"Temperature {current.get('temperature_2m')} {temp_unit}, wind {current.get('wind_speed_10m')} {wind_unit}.",
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind": f"{current.get('wind_speed_10m')} {wind_unit}",
            "source": "Open-Meteo",
        }
        return AdapterResult(output=output, message="Weather query completed.")
