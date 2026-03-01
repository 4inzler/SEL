"""
Context provider for SEL Discord bot
Provides current time and weather information with hormone effects
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
from typing import Optional, Dict
from dataclasses import dataclass
import time as time_module

# Configuration from environment
TIMEZONE = os.environ.get("SEL_TIMEZONE", "America/Los_Angeles")
LATITUDE = float(os.environ.get("WEATHER_LATITUDE", "45.5152"))
LONGITUDE = float(os.environ.get("WEATHER_LONGITUDE", "-122.6784"))
CITY_NAME = os.environ.get("WEATHER_CITY", "Portland, OR")

# Cache weather data to avoid excessive API calls
_weather_cache: Dict = {}
_weather_cache_time: float = 0
WEATHER_CACHE_TTL = 300  # 5 minutes


@dataclass
class WeatherData:
    """Structured weather data with hormone effects"""
    temperature: float  # Fahrenheit
    weather_code: int
    condition: str
    emoji: str
    wind_speed: float
    humidity: Optional[float] = None
    cloud_cover: Optional[float] = None
    is_rainy: bool = False
    is_sunny: bool = False
    is_cloudy: bool = False
    is_stormy: bool = False
    is_snowy: bool = False
    is_foggy: bool = False

    def get_hormone_effects(self) -> Dict[str, float]:
        """
        Calculate hormone adjustments based on weather conditions.

        Weather affects mood through various mechanisms:
        - Sunny: Boosts serotonin, dopamine, reduces melatonin
        - Rainy: Can increase melatonin (cozy/sleepy), mild cortisol
        - Stormy: Increases adrenaline, cortisol, anxiety
        - Cold: Increases alertness (mild cortisol)
        - Hot: Can cause irritability (cortisol)
        - Cloudy: Mild serotonin reduction
        """
        effects = {}

        # Sunlight effects
        if self.is_sunny:
            effects["serotonin"] = 0.08
            effects["dopamine"] = 0.05
            effects["melatonin"] = -0.06
            effects["contentment"] = 0.05
            effects["excitement"] = 0.03

        # Cloudy/overcast
        if self.is_cloudy and not self.is_rainy:
            effects["serotonin"] = -0.03
            effects["melatonin"] = 0.02
            effects["contentment"] = -0.02

        # Rain effects (cozy but can be gloomy)
        if self.is_rainy:
            effects["melatonin"] = 0.08  # Cozy/sleepy
            effects["contentment"] = 0.03  # Rain can be cozy
            effects["serotonin"] = -0.02
            effects["excitement"] = -0.03
            effects["loneliness"] = 0.02

        # Storm effects
        if self.is_stormy:
            effects["adrenaline"] = 0.10
            effects["cortisol"] = 0.08
            effects["anxiety"] = 0.06
            effects["excitement"] = 0.05  # Can be exciting too
            effects["melatonin"] = -0.03

        # Snow effects
        if self.is_snowy:
            effects["excitement"] = 0.06
            effects["dopamine"] = 0.04
            effects["melatonin"] = 0.03
            effects["contentment"] = 0.04

        # Fog effects
        if self.is_foggy:
            effects["melatonin"] = 0.05
            effects["confusion"] = 0.03
            effects["anxiety"] = 0.02
            effects["excitement"] = -0.02

        # Temperature effects
        if self.temperature < 40:  # Cold
            effects["cortisol"] = effects.get("cortisol", 0) + 0.03
            effects["adrenaline"] = effects.get("adrenaline", 0) + 0.02
        elif self.temperature > 85:  # Hot
            effects["cortisol"] = effects.get("cortisol", 0) + 0.04
            effects["frustration"] = effects.get("frustration", 0) + 0.03
            effects["patience"] = effects.get("patience", 0) - 0.03
        elif 65 <= self.temperature <= 75:  # Perfect weather
            effects["serotonin"] = effects.get("serotonin", 0) + 0.03
            effects["contentment"] = effects.get("contentment", 0) + 0.02

        # Wind effects
        if self.wind_speed > 20:
            effects["adrenaline"] = effects.get("adrenaline", 0) + 0.02
            effects["excitement"] = effects.get("excitement", 0) + 0.02

        return effects

def get_local_datetime() -> datetime:
    """Get current datetime in configured timezone"""
    try:
        tz = ZoneInfo(TIMEZONE)
        return datetime.now(tz)
    except Exception:
        return datetime.now()


def get_current_time() -> str:
    """
    Get current date and time in configured timezone

    Returns:
        Formatted time string
    """
    try:
        now = get_local_datetime()
        # Format: "Wednesday, December 27, 2023 at 3:45 PM PST"
        formatted = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
        return formatted
    except Exception as e:
        return f"Current time unavailable: {e}"


def get_time_of_day() -> str:
    """
    Get natural language time of day.

    Returns:
        One of: 'early morning', 'morning', 'late morning', 'afternoon',
                'late afternoon', 'evening', 'night', 'late night'
    """
    now = get_local_datetime()
    hour = now.hour

    if 5 <= hour < 7:
        return "early morning"
    elif 7 <= hour < 10:
        return "morning"
    elif 10 <= hour < 12:
        return "late morning"
    elif 12 <= hour < 15:
        return "afternoon"
    elif 15 <= hour < 17:
        return "late afternoon"
    elif 17 <= hour < 20:
        return "evening"
    elif 20 <= hour < 23:
        return "night"
    else:  # 23-5
        return "late night"


def get_sleepiness_level() -> tuple[str, float]:
    """
    Get natural sleepiness description and melatonin modifier.

    Returns:
        Tuple of (description, melatonin_modifier)
    """
    now = get_local_datetime()
    hour = now.hour

    # Peak alertness: 9am-11am, 3pm-5pm
    # Natural dips: 1pm-3pm (post-lunch), 2am-4am (circadian low)
    # Sleepy: 10pm-6am

    if 2 <= hour < 5:
        return "very sleepy, it's the middle of the night", 0.35
    elif 5 <= hour < 7:
        return "a bit groggy, just waking up", 0.15
    elif 7 <= hour < 9:
        return "waking up, getting alert", 0.05
    elif 9 <= hour < 11:
        return "alert and awake", -0.05
    elif 11 <= hour < 13:
        return "awake", 0.0
    elif 13 <= hour < 15:
        return "a little drowsy (afternoon slump)", 0.08
    elif 15 <= hour < 17:
        return "alert again", -0.03
    elif 17 <= hour < 20:
        return "winding down a bit", 0.05
    elif 20 <= hour < 22:
        return "getting sleepy", 0.12
    elif 22 <= hour < 24:
        return "pretty tired, it's late", 0.22
    else:  # 0-2
        return "really sleepy, should be asleep", 0.30


def get_time_hormone_effects() -> Dict[str, float]:
    """
    Get hormone effects based on time of day.

    This supplements the circadian rhythm in hormones.py with
    more nuanced time-based adjustments.

    Returns:
        Dictionary of hormone adjustments
    """
    now = get_local_datetime()
    hour = now.hour
    effects = {}

    _, melatonin_mod = get_sleepiness_level()
    effects["melatonin"] = melatonin_mod

    # Morning cortisol spike (helps wake up)
    if 6 <= hour < 9:
        effects["cortisol"] = 0.08
        effects["adrenaline"] = 0.03

    # Post-lunch dip
    if 13 <= hour < 15:
        effects["contentment"] = 0.03
        effects["patience"] = -0.02

    # Late night loneliness/introspection
    if 23 <= hour or hour < 4:
        effects["loneliness"] = 0.05
        effects["anxiety"] = 0.03
        effects["confusion"] = 0.02

    # Evening relaxation
    if 19 <= hour < 22:
        effects["contentment"] = 0.04
        effects["anxiety"] = -0.03
        effects["patience"] = 0.02

    return effects


def get_enhanced_time_context() -> str:
    """
    Get enhanced time context for prompts including time of day feeling.

    Returns:
        Formatted context string
    """
    now = get_local_datetime()
    time_str = now.strftime("%I:%M %p")
    day_str = now.strftime("%A")
    date_str = now.strftime("%B %d")
    time_of_day = get_time_of_day()
    sleepiness, _ = get_sleepiness_level()

    return f"It's {time_str} on {day_str}, {date_str} ({time_of_day}). You're feeling {sleepiness}."

def get_weather_data() -> Optional[WeatherData]:
    """
    Get structured weather data with caching.

    Returns:
        WeatherData object or None if unavailable
    """
    global _weather_cache, _weather_cache_time

    # Check cache
    now = time_module.time()
    if _weather_cache and (now - _weather_cache_time) < WEATHER_CACHE_TTL:
        return _weather_cache.get("data")

    try:
        # Use Open-Meteo API (free, no key needed)
        params = {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "current": [
                "temperature_2m",
                "weather_code",
                "wind_speed_10m",
                "relative_humidity_2m",
                "cloud_cover",
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
        humidity = current.get("relative_humidity_2m")
        cloud_cover = current.get("cloud_cover")

        condition = _weather_code_to_description(weather_code)
        emoji = _weather_code_to_emoji(weather_code)

        # Determine weather flags
        is_rainy = weather_code in (51, 53, 55, 61, 63, 65, 80, 81, 82)
        is_sunny = weather_code == 0
        is_cloudy = weather_code in (2, 3) or (cloud_cover and cloud_cover > 60)
        is_stormy = weather_code in (95, 96, 99)
        is_snowy = weather_code in (71, 73, 75, 85, 86)
        is_foggy = weather_code in (45, 48)

        weather_data = WeatherData(
            temperature=temp,
            weather_code=weather_code,
            condition=condition,
            emoji=emoji,
            wind_speed=wind,
            humidity=humidity,
            cloud_cover=cloud_cover,
            is_rainy=is_rainy,
            is_sunny=is_sunny,
            is_cloudy=is_cloudy,
            is_stormy=is_stormy,
            is_snowy=is_snowy,
            is_foggy=is_foggy,
        )

        # Update cache
        _weather_cache = {"data": weather_data}
        _weather_cache_time = now

        return weather_data

    except Exception:
        return None  # Silently fail - weather is optional


def get_weather_summary() -> Optional[str]:
    """
    Get brief current weather summary

    Returns:
        Brief weather description or None if unavailable
    """
    weather = get_weather_data()
    if weather:
        return f"{weather.emoji} {weather.temperature:.0f}°F, {weather.condition.lower()}, {weather.wind_speed:.0f} mph winds in {CITY_NAME}"
    return None


def get_weather_hormone_effects() -> Dict[str, float]:
    """
    Get hormone effects based on current weather.

    Returns:
        Dictionary of hormone adjustments
    """
    weather = get_weather_data()
    if weather:
        return weather.get_hormone_effects()
    return {}

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

def get_context_for_prompt() -> str:
    """
    Get context formatted for inclusion in LLM prompts

    Returns:
        Context string suitable for system prompt (may be empty)
    """
    time_str = get_current_time()
    weather_str = get_weather_summary()

    parts = []
    if time_str:
        parts.append(f"Current time: {time_str}")
    if weather_str:
        parts.append(f"Weather: {weather_str}")

    if parts:
        return "\n".join(parts) + "\n\n"
    return ""
