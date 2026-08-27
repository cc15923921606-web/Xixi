from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .environment_context import WeatherAlert

logger = logging.getLogger("weather_alerts")


async def run_weather_alert_scheduler(
    cfg: "Config",
    brain: "Brain",
    owner_user_id: int,
    send_private: Callable[[int, str], Awaitable[None]],
    send_group: Callable[[int, WeatherAlert], Awaitable[None]] | None = None,
    runtime_enabled: Callable[[], bool] | None = None,
) -> None:
    logger.info(
        "extreme weather alert scheduler started, location=%s",
        cfg.weather_location,
    )
    previously_enabled: bool | None = None
    while True:
        enabled = bool(cfg.weather_enabled and cfg.weather_alert_enabled) and (
            runtime_enabled is None or runtime_enabled()
        )
        if not enabled:
            if previously_enabled is not False:
                logger.info("extreme weather alert scheduler paused")
            previously_enabled = False
            await asyncio.sleep(1.0)
            continue
        if previously_enabled is False:
            logger.info("extreme weather alert scheduler resumed")
        previously_enabled = True
        interval_seconds = max(60.0, cfg.weather_alert_check_minutes * 60.0)
        try:
            weather_available, alert = await asyncio.to_thread(
                brain.environment.alert_status
            )
            previous_private = brain.memory.get_state("weather_alert_fingerprint")
            previous_group = brain.memory.get_state("weather_alert_group_fingerprint")
            if weather_available and alert is None:
                if previous_private:
                    brain.memory.set_state("weather_alert_fingerprint", "")
                if previous_group:
                    brain.memory.set_state("weather_alert_group_fingerprint", "")
            elif alert:
                message = ""
                if alert.fingerprint != previous_private:
                    message = await asyncio.to_thread(brain.compose_weather_alert, alert)
                    if message:
                        await send_private(owner_user_id, message)
                        brain.remember_autonomous_reply(
                            f"private:{owner_user_id}",
                            message,
                f"你检测到{alert.location}出现{alert.title}并提醒了主人。",
                        )
                        brain.memory.set_state(
                            "weather_alert_fingerprint",
                            alert.fingerprint,
                        )
                        brain.memory.set_state(
                            "weather_alert_sent_at",
                            datetime.now(timezone.utc).isoformat(),
                        )
                        logger.warning(
                            "sent extreme weather alert to owner: %s",
                            alert.title,
                        )

                if (
                    cfg.weather_alert_group_enabled
                    and send_group
                    and cfg.autonomous_group_ids
                    and alert.fingerprint != previous_group
                ):
                    for group_id in sorted(cfg.autonomous_group_ids):
                        await send_group(group_id, alert)
                    brain.memory.set_state(
                        "weather_alert_group_fingerprint",
                        alert.fingerprint,
                    )
                    logger.warning(
                        "sent extreme weather alert to %s group(s): %s",
                        len(cfg.autonomous_group_ids),
                        alert.title,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("extreme weather alert cycle failed: %s", exc)

        remaining_sleep = interval_seconds
        while (
            remaining_sleep > 0
            and cfg.weather_enabled
            and cfg.weather_alert_enabled
            and (runtime_enabled is None or runtime_enabled())
        ):
            delay = min(1.0, remaining_sleep)
            await asyncio.sleep(delay)
            remaining_sleep -= delay


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .brain import Brain
    from .config import Config
