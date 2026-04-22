from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.workers.tasks import fetch_case_law, heartbeat, heartbeat_alert_only, upload_pending

_settings = get_settings()


class WorkerSettings:
    functions = [fetch_case_law, upload_pending, heartbeat, heartbeat_alert_only]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)

    cron_jobs = [
        # Case law pipeline
        cron(fetch_case_law, hour=3, minute=0),
        cron(upload_pending, hour=3, minute=30),
        # Full heartbeat every 6h (always sends to Telegram, keeps FST alive)
        cron(heartbeat, hour={0, 6, 12, 18}, minute=0),
        # Hourly health check (only sends Telegram alert on failure)
        cron(heartbeat_alert_only, minute=0),
    ]
