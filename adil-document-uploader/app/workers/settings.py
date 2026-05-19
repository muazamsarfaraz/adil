from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.workers.tasks import (
    fast_probe,
    fetch_acts,
    fetch_case_law,
    heartbeat,
    heartbeat_alert_only,
    rate_limit_cleanup,
    scrape_solicitors,
    upload_pending,
)

_settings = get_settings()


class WorkerSettings:
    functions = [
        fetch_case_law,
        fetch_acts,
        upload_pending,
        heartbeat,
        heartbeat_alert_only,
        fast_probe,
        rate_limit_cleanup,
        scrape_solicitors,
    ]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)

    cron_jobs = [
        # Case law pipeline
        cron(fetch_case_law, hour=3, minute=0),
        cron(upload_pending, hour=3, minute=30),
        # Full heartbeat every 6h (always sends to Telegram, keeps FST alive)
        cron(heartbeat, hour={0, 6, 12, 18}, minute=0),
        # Hourly health check (only sends Telegram alert on failure)
        cron(heartbeat_alert_only, minute=0),
        # Fast synthetic prober every 2 min (alerts on 2nd consecutive failure,
        # and again on recovery). Covers adil-rag-api and adil-frontend-next.
        cron(
            fast_probe,
            minute={
                0,
                2,
                4,
                6,
                8,
                10,
                12,
                14,
                16,
                18,
                20,
                22,
                24,
                26,
                28,
                30,
                32,
                34,
                36,
                38,
                40,
                42,
                44,
                46,
                48,
                50,
                52,
                54,
                56,
                58,
            },
        ),
        # Hourly cleanup of rate-limit counters (>48h) and expired uploads
        cron(rate_limit_cleanup, minute=15),
        # Monthly SRA register scrape — refreshes solicitor_firms table
        # Runs 1st of each month at 04:00 UTC (arq uses 'day' for day-of-month)
        cron(scrape_solicitors, day=1, hour=4, minute=0),
        # Monthly Acts fetch — refreshes UK statutes from legislation.gov.uk.
        # Runs 1st of each month at 05:00 UTC (after the SRA scrape).
        cron(fetch_acts, day=1, hour=5, minute=0),
    ]
