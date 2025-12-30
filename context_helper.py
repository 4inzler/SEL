"""
Context helper for SEL Desktop
Provides current time, weather, and other contextual information
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx

# Configuration from environment
TIMEZONE = os.environ.get("SEL_TIMEZONE", "America/Los_Angeles")
LATITUDE = float(os.environ.get("WEATHER_LATITUDE", "45.5152"))
LONGITUDE = float(os.environ.get("WEATHER_LONGITUDE", "-122.6784"))
CITY_NAME = os.environ.get("WEATHER_CITY", "Portland, OR")

def get_current_time() -> str:
    """
    Get current date and time in configured timezone

    Returns:
        Formatted time string
    """
    try:
        tz = ZoneInfo(TIMEZONE)
        now = datetime.now(tz)

        # Format: "Wednesday, December 27, 2023 at 3:45 PM PST"
        formatted = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")

        return formatted
    except Exception as e:
        return f"Current time unavailable: {e}"

def get_weather_summary() -> str:
    """
    Get brief current weather summary

    Returns:
        Brief weather description
    """
    try:
        # Use Open-Meteo API (free, no key needed)
        params = {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "current": [
                "temperature_2m",
                "weather_code",
                "wind_speed_10m",
            ],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": TIMEZONE,
        }

        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params
            )
            response.raise_for_status()
            data = response.json()

        current = data.get("current", {})
        temp = current.get("temperature_2m", 0)
        weather_code = current.get("weather_code", 0)
        wind = current.get("wind_speed_10m", 0)

        # Convert weather code to description
        condition = _weather_code_to_description(weather_code)
        emoji = _weather_code_to_emoji(weather_code)

        return f"{emoji} {temp:.0f}°F, {condition.lower()}, {wind:.0f} mph winds in {CITY_NAME}"

    except Exception as e:
        return f"Weather unavailable: {e}"

def _weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to description"""
    codes = {
        0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Foggy", 51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
        61: "Light rain", 63: "Rain", 65: "Heavy rain",
        71: "Light snow", 73: "Snow", 75: "Heavy snow",
        80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
        95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"
    }
    return codes.get(code, "Unknown")

def _weather_code_to_emoji(code: int) -> str:
    """Convert weather code to emoji"""
    if code == 0: return "☀️"
    elif code in (1, 2): return "⛅"
    elif code == 3: return "☁️"
    elif code in (45, 48): return "🌫️"
    elif code in range(51, 68): return "🌧️"
    elif code in range(71, 78): return "🌨️"
    elif code in (80, 81, 82): return "🌧️"
    elif code in (85, 86): return "🌨️"
    elif code in (95, 96, 99): return "⛈️"
    return "🌡️"

def get_full_context() -> str:
    """
    Get complete context (time + weather)

    Returns:
        Formatted context string
    """
    time_str = get_current_time()
    weather_str = get_weather_summary()

    return f"📅 {time_str}\n🌤️ {weather_str}"

def get_context_for_prompt() -> str:
    """
    Get context formatted for inclusion in LLM prompts

    Returns:
        Context string suitable for system prompt
    """
    time_str = get_current_time()
    weather_str = get_weather_summary()

    return f"""CURRENT CONTEXT:
Time: {time_str}
Weather: {weather_str}

"""
