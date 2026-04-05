from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.workers.tasks import fetch_case_law, upload_pending

_settings = get_settings()


class WorkerSettings:
    functions = [fetch_case_law, upload_pending]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)

    cron_jobs = [
        cron(fetch_case_law, hour=3, minute=0),
        cron(upload_pending, hour=3, minute=30),
    ]
