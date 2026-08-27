from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.config import Config
from app.environment_context import EnvironmentContext, _detect_extreme_weather


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class EnvironmentContextTests(unittest.TestCase):
    def test_low_latency_render_does_not_block_on_weather_refresh(self) -> None:
        cfg = Config(weather_enabled=True, weather_location="重庆")
        http_get = Mock(side_effect=AssertionError("weather network should not run"))
        context = EnvironmentContext(cfg, http_get=http_get)

        rendered = context.render(refresh_weather=False)

        self.assertIn("缓存尚未刷新", rendered)
        http_get.assert_not_called()

    def test_city_change_invalidates_cached_coordinates_and_snapshot(self) -> None:
        cfg = Config(weather_enabled=True, weather_location="重庆")
        context = EnvironmentContext(cfg)
        context._coordinates = (29.5, 106.5, "重庆")
        context._snapshot = object()  # type: ignore[assignment]
        context._next_refresh_at = 999.0

        context.invalidate_weather()

        self.assertIsNone(context._coordinates)
        self.assertIsNone(context._snapshot)
        self.assertEqual(context._next_refresh_at, 0.0)

    def test_detects_thunderstorm_in_next_hours(self) -> None:
        alert = _detect_extreme_weather(
            "重庆",
            {"time": "2026-08-09T20:50"},
            {
                "time": ["2026-08-09T21:00"],
                "weather_code": [95],
                "temperature_2m": [30],
                "apparent_temperature": [35],
                "precipitation": [4],
                "precipitation_probability": [80],
                "snowfall": [0],
                "wind_gusts_10m": [40],
            },
        )

        self.assertIsNotNone(alert)
        self.assertEqual(alert.title, "雷暴风险")  # type: ignore[union-attr]
        self.assertEqual(alert.level, 4)  # type: ignore[union-attr]

    def test_renders_time_and_cached_weather(self) -> None:
        http_get = Mock(
            side_effect=[
                FakeResponse(
                    {
                        "results": [
                            {
                                "name": "重庆",
                                "admin1": "重庆市",
                                "latitude": 29.56,
                                "longitude": 106.56,
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "current": {
                            "time": "2026-08-09T20:50",
                            "temperature_2m": 28.2,
                            "apparent_temperature": 31.0,
                            "relative_humidity_2m": 68,
                            "weather_code": 2,
                            "wind_speed_10m": 7.4,
                            "precipitation": 0,
                        }
                    }
                ),
            ]
        )
        cfg = Config(
            weather_enabled=True,
            weather_location="重庆",
            weather_cache_minutes=10,
            weather_timeout_s=1,
        )
        now = datetime(2026, 8, 9, 20, 50, tzinfo=timezone(timedelta(hours=8)))
        context = EnvironmentContext(cfg, http_get=http_get, now=lambda: now)

        first = context.render()
        second = context.render()

        self.assertIn("2026-08-09 20:50 星期日", first)
        self.assertIn("重庆当前天气", first)
        self.assertIn("多云", first)
        self.assertIn("28.2°C", first)
        self.assertEqual(first, second)
        self.assertEqual(http_get.call_count, 2)

    def test_does_not_guess_when_weather_request_fails(self) -> None:
        http_get = Mock(side_effect=RuntimeError("network down"))
        cfg = Config(weather_enabled=True, weather_location="重庆")
        context = EnvironmentContext(
            cfg,
            http_get=http_get,
            now=lambda: datetime(2026, 8, 9, 20, 50, tzinfo=timezone.utc),
        )

        rendered = context.render()

        self.assertIn("当前本地时间", rendered)
        self.assertIn("暂时获取失败，不能猜测", rendered)


if __name__ == "__main__":
    unittest.main()
