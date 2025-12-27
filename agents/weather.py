"""
Weather Agent for SEL

Fetches current weather and forecast using the free Open-Meteo API.
No API key required. Location configurable via environment variables.

Environment variables:
- WEATHER_LATITUDE: Latitude (default: 45.5152 for Portland)
- WEATHER_LONGITUDE: Longitude (default: -122.6784 for Portland)
- WEATHER_CITY: City name for display (default: "Portland, OR")
- SEL_TIMEZONE: Timezone (default: "America/Los_Angeles")

Usage examples:
- "What's the weather?"
- "Weather forecast"
- "Current temperature"
- "Is it going to rain?"
"""

import os
from typing import Optional

import httpx

DESCRIPTION = "Get current weather and forecast (no API key needed)."

# Configurable location via environment
LATITUDE = float(os.environ.get("WEATHER_LATITUDE", "45.5152"))
LONGITUDE = float(os.environ.get("WEATHER_LONGITUDE", "-122.6784"))
CITY_NAME = os.environ.get("WEATHER_CITY", "Portland, OR")
TIMEZONE = os.environ.get("SEL_TIMEZONE", "America/Los_Angeles")

# Open-Meteo API (free, no key required)
BASE_URL = "https://api.open-meteo.com/v1/forecast"


def _weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, f"Unknown ({code})")


def _weather_code_to_emoji(code: int) -> str:
    """Convert WMO weather code to emoji."""
    if code == 0:
        return "☀️"
    elif code in (1, 2):
        return "⛅"
    elif code == 3:
        return "☁️"
    elif code in (45, 48):
        return "🌫️"
    elif code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "🌧️"
    elif code in (71, 73, 75, 77, 85, 86):
        return "🌨️"
    elif code in (95, 96, 99):
        return "⛈️"
    return "🌡️"


def _celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (c * 9/5) + 32


def _fetch_weather() -> dict:
    """Fetch current weather and forecast from Open-Meteo."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation",
        ],
        "hourly": [
            "temperature_2m",
            "precipitation_probability",
            "weather_code",
        ],
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
        ],
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": TIMEZONE,
        "forecast_days": 3,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(BASE_URL, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.text}"}
    except Exception as exc:
        return {"error": str(exc)}


def _format_current(data: dict) -> str:
    """Format current weather conditions."""
    current = data.get("current", {})

    temp = current.get("temperature_2m", 0)
    feels_like = current.get("apparent_temperature", 0)
    humidity = current.get("relative_humidity_2m", 0)
    weather_code = current.get("weather_code", 0)
    wind_speed = current.get("wind_speed_10m", 0)
    wind_gusts = current.get("wind_gusts_10m", 0)
    precip = current.get("precipitation", 0)

    emoji = _weather_code_to_emoji(weather_code)
    condition = _weather_code_to_description(weather_code)

    lines = [
        f"{emoji} **{CITY_NAME} Weather**",
        f"",
        f"**Currently:** {condition}",
        f"**Temperature:** {temp:.0f}°F (feels like {feels_like:.0f}°F)",
        f"**Humidity:** {humidity:.0f}%",
        f"**Wind:** {wind_speed:.0f} mph (gusts to {wind_gusts:.0f} mph)",
    ]

    if precip > 0:
        lines.append(f"**Precipitation:** {precip:.2f} in")

    return "\n".join(lines)


def _format_forecast(data: dict) -> str:
    """Format daily forecast."""
    daily = data.get("daily", {})

    times = daily.get("time", [])
    weather_codes = daily.get("weather_code", [])
    temp_maxs = daily.get("temperature_2m_max", [])
    temp_mins = daily.get("temperature_2m_min", [])
    precip_probs = daily.get("precipitation_probability_max", [])

    lines = ["\n**3-Day Forecast:**"]

    day_names = ["Today", "Tomorrow"]

    for i, time in enumerate(times[:3]):
        if i < len(day_names):
            day = day_names[i]
        else:
            from datetime import datetime
            dt = datetime.fromisoformat(time)
            day = dt.strftime("%A")

        code = weather_codes[i] if i < len(weather_codes) else 0
        high = temp_maxs[i] if i < len(temp_maxs) else 0
        low = temp_mins[i] if i < len(temp_mins) else 0
        rain_chance = precip_probs[i] if i < len(precip_probs) else 0

        emoji = _weather_code_to_emoji(code)
        condition = _weather_code_to_description(code)

        lines.append(f"{emoji} **{day}:** {condition}, {high:.0f}°/{low:.0f}°F")
        if rain_chance > 20:
            lines.append(f"   🌧️ {rain_chance}% chance of precipitation")

    return "\n".join(lines)


def _check_rain_today(data: dict) -> str:
    """Check if rain is expected today."""
    hourly = data.get("hourly", {})

    times = hourly.get("time", [])
    precip_probs = hourly.get("precipitation_probability", [])
    weather_codes = hourly.get("weather_code", [])

    # Check next 12 hours
    rain_hours = []
    for i in range(min(12, len(times))):
        prob = precip_probs[i] if i < len(precip_probs) else 0
        code = weather_codes[i] if i < len(weather_codes) else 0

        # Rain codes: 51-67, 80-82
        is_rainy = code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82)

        if prob > 40 or is_rainy:
            from datetime import datetime
            dt = datetime.fromisoformat(times[i])
            rain_hours.append((dt.strftime("%I%p").lstrip("0"), prob))

    if rain_hours:
        hours_str = ", ".join([f"{h} ({p}%)" for h, p in rain_hours[:4]])
        return f"🌧️ Rain expected: {hours_str}"
    else:
        return "☀️ No significant rain expected in the next 12 hours."


def run(query: str, **kwargs) -> str:
    """
    Get weather for Portland, OR.

    Examples:
        "weather" -> Current conditions + forecast
        "forecast" -> 3-day forecast
        "is it raining" -> Check precipitation
        "temperature" -> Just the current temp
    """
    query = query.strip().lower()

    data = _fetch_weather()

    if "error" in data:
        return f"❌ Weather error: {data['error']}"

    # Specific queries
    if any(word in query for word in ["rain", "raining", "precipitation", "umbrella"]):
        current = _format_current(data)
        rain_check = _check_rain_today(data)
        return f"{current}\n\n{rain_check}"

    if "forecast" in query:
        current = _format_current(data)
        forecast = _format_forecast(data)
        return f"{current}\n{forecast}"

    if any(word in query for word in ["temp", "temperature", "hot", "cold"]):
        current = data.get("current", {})
        temp = current.get("temperature_2m", 0)
        feels = current.get("apparent_temperature", 0)
        return f"🌡️ {CITY_NAME}: {temp:.0f}°F (feels like {feels:.0f}°F)"

    # Default: current + forecast
    current = _format_current(data)
    forecast = _format_forecast(data)
    return f"{current}\n{forecast}"
