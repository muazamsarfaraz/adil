from arq.cron import cron

from app.workers.tasks import fetch_case_law, upload_pending
from app.config import get_settings


class WorkerSettings:
    functions = [fetch_case_law, upload_pending]

    cron_jobs = [
        cron(fetch_case_law, hour=3, minute=0),
        cron(upload_pending, hour=3, minute=30),
    ]

    @staticmethod
    def redis_settings():
        from arq.connections import RedisSettings

        settings = get_settings()
        return RedisSettings.from_dsn(settings.redis_url)
