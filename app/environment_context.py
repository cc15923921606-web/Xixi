from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable

import httpx

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger("environment_context")

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
_WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


@dataclass(frozen=True)
class WeatherAlert:
    fingerprint: str
    location: str
    level: int
    title: str
    detail: str
    advice: str


@dataclass(frozen=True)
class WeatherSnapshot:
    location: str
    observed_at: str
    condition: str
    temperature_c: float
    apparent_temperature_c: float
    humidity_percent: float
    wind_speed_kmh: float
    precipitation_mm: float
    alert: WeatherAlert | None = None


class EnvironmentContext:
    """Provide fresh local time and a short cached current-weather summary."""

    def __init__(
        self,
        cfg: Config,
        *,
        http_get: Callable[..., Any] = httpx.get,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cfg = cfg
        self.http_get = http_get
        self.now = now or (lambda: datetime.now().astimezone())
        self.monotonic = monotonic
        self._lock = threading.Lock()
        self._coordinates: tuple[float, float, str] | None = None
        self._snapshot: WeatherSnapshot | None = None
        self._next_refresh_at = 0.0

    def invalidate_weather(self) -> None:
        """Discard location-specific data after the configured city changes."""
        with self._lock:
            self._coordinates = None
            self._snapshot = None
            self._next_refresh_at = 0.0

    def render(self, *, refresh_weather: bool = True) -> str:
        local_now = self.now()
        offset = local_now.strftime("%z")
        formatted_offset = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        lines = [
            "实时环境信息（由程序提供的可信数据）：",
            (
                f"- 当前本地时间：{local_now:%Y-%m-%d %H:%M} "
                f"{_WEEKDAYS[local_now.weekday()]}（UTC{formatted_offset}）"
            ),
        ]

        if self.cfg.weather_enabled:
            if refresh_weather:
                snapshot = self._current_weather()
            else:
                with self._lock:
                    snapshot = self._snapshot
            if snapshot:
                lines.append(
                    f"- {snapshot.location}当前天气（数据时间 {snapshot.observed_at}）："
                    f"{snapshot.condition}，{snapshot.temperature_c:.1f}°C，"
                    f"体感 {snapshot.apparent_temperature_c:.1f}°C，"
                    f"湿度 {snapshot.humidity_percent:.0f}%，"
                    f"风速 {snapshot.wind_speed_kmh:.1f} km/h，"
                    f"当前降水 {snapshot.precipitation_mm:.1f} mm"
                )
                if snapshot.alert:
                    lines.append(
                        f"- 极端天气风险：{snapshot.alert.title}。"
                        f"{snapshot.alert.detail}"
                    )
            else:
                location = self.cfg.weather_location or "本地"
                status = "暂时获取失败" if refresh_weather else "缓存尚未刷新"
                lines.append(f"- {location}当前天气：{status}，不能猜测天气情况。")

        lines.append("回答时间或天气问题时以这里为准；未被问及时不必主动复述这些数据。")
        return "\n".join(lines)

    def _current_weather(self) -> WeatherSnapshot | None:
        if not self.cfg.weather_location.strip():
            return None

        with self._lock:
            now = self.monotonic()
            if now < self._next_refresh_at:
                return self._snapshot

            try:
                latitude, longitude, location = self._resolve_location()
                response = self.http_get(
                    _WEATHER_URL,
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current": (
                            "temperature_2m,apparent_temperature,relative_humidity_2m,"
                            "weather_code,wind_speed_10m,precipitation"
                        ),
                        "hourly": (
                            "weather_code,temperature_2m,apparent_temperature,precipitation,"
                            "precipitation_probability,snowfall,wind_gusts_10m"
                        ),
                        "timezone": "auto",
                        "forecast_days": 2,
                    },
                    timeout=self.cfg.weather_timeout_s,
                )
                response.raise_for_status()
                payload = response.json()
                current = payload.get("current")
                if not isinstance(current, dict):
                    raise ValueError("weather response did not contain current conditions")

                snapshot = WeatherSnapshot(
                    location=location,
                    observed_at=str(current.get("time") or "刚刚"),
                    condition=_weather_condition(int(current.get("weather_code", -1))),
                    temperature_c=_as_float(current.get("temperature_2m")),
                    apparent_temperature_c=_as_float(current.get("apparent_temperature")),
                    humidity_percent=_as_float(current.get("relative_humidity_2m")),
                    wind_speed_kmh=_as_float(current.get("wind_speed_10m")),
                    precipitation_mm=_as_float(current.get("precipitation")),
                    alert=_detect_extreme_weather(
                        location,
                        current,
                        payload.get("hourly"),
                    ),
                )
                self._snapshot = snapshot
                self._next_refresh_at = now + max(
                    60.0,
                    self.cfg.weather_cache_minutes * 60.0,
                )
                logger.info("weather refreshed for %s", location)
            except Exception as exc:
                self._next_refresh_at = now + 60.0
                logger.warning("weather refresh failed: %s", exc)

            return self._snapshot

    def current_alert(self) -> WeatherAlert | None:
        snapshot = self._current_weather()
        return snapshot.alert if snapshot else None

    def alert_status(self) -> tuple[bool, WeatherAlert | None]:
        snapshot = self._current_weather()
        return snapshot is not None, snapshot.alert if snapshot else None

    def _resolve_location(self) -> tuple[float, float, str]:
        if self._coordinates:
            return self._coordinates

        response = self.http_get(
            _GEOCODING_URL,
            params={
                "name": self.cfg.weather_location.strip(),
                "count": 1,
                "language": "zh",
                "format": "json",
            },
            timeout=self.cfg.weather_timeout_s,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError(f"could not resolve weather location: {self.cfg.weather_location}")

        result = results[0]
        if not isinstance(result, dict):
            raise ValueError("invalid geocoding response")
        latitude = _as_float(result.get("latitude"))
        longitude = _as_float(result.get("longitude"))
        name = str(result.get("name") or self.cfg.weather_location).strip()
        admin1 = str(result.get("admin1") or "").strip()
        location = name if name in admin1 or not admin1 else f"{admin1}{name}"
        self._coordinates = (latitude, longitude, location)
        return self._coordinates


def _as_float(value: object) -> float:
    if value is None:
        raise ValueError("weather response contained a missing number")
    return float(value)


def _weather_condition(code: int) -> str:
    if code == 0:
        return "晴"
    if code == 1:
        return "大致晴朗"
    if code == 2:
        return "多云"
    if code == 3:
        return "阴"
    if code in {45, 48}:
        return "有雾"
    if code in {51, 53, 55}:
        return "毛毛雨"
    if code in {56, 57}:
        return "冻毛毛雨"
    if code in {61, 63, 65}:
        return "有雨"
    if code in {66, 67}:
        return "冻雨"
    if code in {71, 73, 75, 77}:
        return "有雪"
    if code in {80, 81, 82}:
        return "阵雨"
    if code in {85, 86}:
        return "阵雪"
    if code in {95, 96, 99}:
        return "雷暴"
    return "天气状况未知"


def _detect_extreme_weather(
    location: str,
    current: dict[str, object],
    hourly: object,
) -> WeatherAlert | None:
    if not isinstance(hourly, dict):
        return None

    times = hourly.get("time")
    if not isinstance(times, list):
        return None
    current_time = _parse_weather_time(current.get("time"))
    entries: list[tuple[datetime, dict[str, object]]] = []
    fields = (
        "weather_code",
        "temperature_2m",
        "apparent_temperature",
        "precipitation",
        "precipitation_probability",
        "snowfall",
        "wind_gusts_10m",
    )
    for index, value in enumerate(times):
        timestamp = _parse_weather_time(value)
        if timestamp is None or (current_time and timestamp < current_time):
            continue
        if current_time and timestamp > current_time + timedelta(hours=12):
            continue
        entry = {
            field: _item_at(hourly.get(field), index)
            for field in fields
        }
        entries.append((timestamp, entry))

    if not entries:
        return None

    candidates: list[tuple[int, datetime, str, str, str]] = []
    for timestamp, entry in entries:
        code = _as_int(entry.get("weather_code"))
        temperature = _optional_float(entry.get("temperature_2m"))
        apparent = _optional_float(entry.get("apparent_temperature"))
        precipitation = _optional_float(entry.get("precipitation"))
        snowfall = _optional_float(entry.get("snowfall"))
        gust = _optional_float(entry.get("wind_gusts_10m"))
        when = timestamp.strftime("%H:%M")

        if code in {95, 96, 99}:
            candidates.append(
                (
                    4,
                    timestamp,
                    "雷暴风险",
                    f"未来约12小时内预计在{when}前后出现雷暴",
                    "尽量待在室内，远离窗边和高处，打雷时不要在户外逗留。",
                )
            )
        if code in {65, 82} or (precipitation is not None and precipitation >= 20):
            candidates.append(
                (
                    4,
                    timestamp,
                    "暴雨风险",
                    f"未来约12小时内{when}前后可能有短时强降雨",
                    "出门前确认路况，避开低洼积水和河道，非必要先别出门。",
                )
            )
        elif code in {63, 81} or (precipitation is not None and precipitation >= 10):
            candidates.append(
                (
                    3,
                    timestamp,
                    "强降雨风险",
                    f"未来约12小时内{when}前后可能有较强降雨",
                    "外出带好雨具并留意积水、滑坡和道路拥堵情况。",
                )
            )
        if gust is not None and gust >= 90:
            candidates.append(
                (
                    4,
                    timestamp,
                    "强风风险",
                    f"预计{when}前后阵风可能达到{gust:.0f} km/h",
                    "收好阳台物品，远离广告牌、树木和临时搭建物。",
                )
            )
        elif gust is not None and gust >= 75:
            candidates.append(
                (
                    3,
                    timestamp,
                    "大风风险",
                    f"预计{when}前后阵风可能达到{gust:.0f} km/h",
                    "外出注意高空坠物，尽量避开树木和临时建筑。",
                )
            )
        if temperature is not None and (temperature >= 40 or (apparent or temperature) >= 45):
            candidates.append(
                (
                    4,
                    timestamp,
                    "极端高温风险",
                    f"{when}前后气温或体感温度可能达到危险高温",
                    "减少正午外出，及时补水，身体不适时立即到阴凉处休息。",
                )
            )
        elif temperature is not None and (temperature >= 38 or (apparent or temperature) >= 42):
            candidates.append(
                (
                    3,
                    timestamp,
                    "高温风险",
                    f"{when}前后气温可能达到{temperature:.1f}°C",
                    "尽量避开高温时段，补水并注意防晒。",
                )
            )
        if temperature is not None and (temperature <= -10 or (apparent or temperature) <= -15):
            candidates.append(
                (
                    4,
                    timestamp,
                    "极端低温风险",
                    f"{when}前后可能出现危险低温",
                    "做好保暖，减少不必要的外出，注意防滑和用电安全。",
                )
            )
        elif temperature is not None and (temperature <= -5 or (apparent or temperature) <= -10):
            candidates.append(
                (
                    3,
                    timestamp,
                    "低温风险",
                    f"{when}前后气温可能降到{temperature:.1f}°C",
                    "注意保暖和路面结冰情况。",
                )
            )
        if snowfall is not None and snowfall >= 5:
            candidates.append(
                (
                    4,
                    timestamp,
                    "大雪风险",
                    f"{when}前后预计有较强降雪",
                    "非必要不要出门，出行注意积雪、结冰和交通延误。",
                )
            )

    if not candidates:
        return None
    level, timestamp, title, detail, advice = max(
        candidates,
        key=lambda item: (item[0], -item[1].timestamp()),
    )
    day = timestamp.strftime("%Y-%m-%d")
    kind = title.split("风险", 1)[0]
    return WeatherAlert(
        fingerprint=f"{location}:{day}:{kind}:{level}",
        location=location,
        level=level,
        title=title,
        detail=detail,
        advice=advice,
    )


def _parse_weather_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _item_at(values: object, index: int) -> object:
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
