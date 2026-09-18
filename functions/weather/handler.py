"""
handler.py — Weather function logic.

Uses the free Open-Meteo API (no API key required) to fetch current
weather for a given city or lat/lon pair.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass


OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"


@dataclass
class WeatherResult:
    city: str
    country: str
    temperature: float
    windspeed: float
    weather_code: int
    description: str
    error: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


# WMO weather code → human description
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def _geocode(city: str) -> dict:
    params = urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
    url = f"{OPEN_METEO_GEO}?{params}"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    if not data.get("results"):
        return {}
    first = data["results"][0]
    return {
        "name": first.get("name", city),
        "country": first.get("country", ""),
        "latitude": first.get("latitude"),
        "longitude": first.get("longitude"),
    }


def _fetch_weather(lat: float, lon: float) -> dict:
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        "timezone": "auto",
    })
    url = f"{OPEN_METEO_FORECAST}?{params}"
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def get_weather(city: str) -> WeatherResult:
    try:
        geo = _geocode(city)
        if not geo:
            return WeatherResult(city, "", 0, 0, 0, "", error=f"City not found: {city}")
        wx = _fetch_weather(geo["latitude"], geo["longitude"])
        cur = wx.get("current", {})
        code = int(cur.get("weather_code", 0))
        return WeatherResult(
            city=geo["name"],
            country=geo["country"],
            temperature=cur.get("temperature_2m", 0),
            windspeed=cur.get("wind_speed_10m", 0),
            weather_code=code,
            description=_WMO.get(code, "Unknown"),
        )
    except Exception as e:
        return WeatherResult(city, "", 0, 0, 0, "", error=str(e))


if __name__ == "__main__":
    import sys
    city = " ".join(sys.argv[1:]) or "Riyadh"
    r = get_weather(city)
    print(json.dumps(r.to_dict(), indent=2))
