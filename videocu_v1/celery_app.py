
"""
VIDEOCU v1 - Celery Application Configuration
Background task queue for async video production and scheduled jobs

Features:
- Async video production tasks
- Scheduled analytics collection (every 6 hours)
- Scheduled learning cycles (daily)
- Task monitoring and retry logic
"""

import os
import logging
from datetime import timedelta
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ========== Celery Configuration ==========

# Redis broker URL (from environment or default)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

# Create Celery app
celery_app = Celery(
    'videocu',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        'celery_tasks.ceo_tasks',
        'celery_tasks.video_tasks',
        'celery_tasks.analytics_tasks',
        'celery_tasks.learning_tasks',
        'celery_tasks.music_tasks'
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Berlin',
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker

    # Result settings
    result_expires=3600,  # Results expire after 1 hour

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Logging
    worker_hijack_root_logger=False,

    # Beat scheduler (for periodic tasks)
    beat_schedule={
        # CEO: Daily trend-based content cycle at 8 AM
        'ceo-daily-trend-cycle': {
            'task': 'ceo.daily_trend_cycle',
            'schedule': crontab(hour=8, minute=0),
            'options': {'queue': 'default'}
        },

        # Collect analytics every 6 hours
        'collect-analytics-every-6-hours': {
            'task': 'celery_tasks.analytics_tasks.collect_all_analytics',
            'schedule': timedelta(hours=6),
            'options': {'queue': 'analytics'}
        },

        # Run learning cycle daily at 3 AM
        'daily-learning-cycle': {
            'task': 'celery_tasks.learning_tasks.run_learning_cycle',
            'schedule': crontab(hour=3, minute=0),
            'options': {'queue': 'learning'}
        },

        # System health check every 30 minutes
        'health-check-every-30-min': {
            'task': 'celery_tasks.analytics_tasks.system_health_check',
            'schedule': timedelta(minutes=30),
            'options': {'queue': 'default'}
        },

        # Clean old files weekly (Sunday 4 AM)
        'weekly-cleanup': {
            'task': 'celery_tasks.analytics_tasks.cleanup_old_files',
            'schedule': crontab(hour=4, minute=0, day_of_week=0),
            'options': {'queue': 'maintenance'}
        }
    },

    # Task routing
    task_routes={
        'celery_tasks.video_tasks.*': {'queue': 'video'},
        'celery_tasks.analytics_tasks.*': {'queue': 'analytics'},
        'celery_tasks.learning_tasks.*': {'queue': 'learning'},
        'celery_tasks.music_tasks.*': {'queue': 'music'},
        'music.*': {'queue': 'music'},
    },

    # Queue definitions
    task_queues={
        'default': {},
        'video': {'routing_key': 'video.#'},
        'analytics': {'routing_key': 'analytics.#'},
        'learning': {'routing_key': 'learning.#'},
        'maintenance': {'routing_key': 'maintenance.#'},
        'music': {'routing_key': 'music.#'},
    }
)

# ========== Celery Signals ==========

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Additional periodic task setup"""
    logger.info("Celery Beat periodic tasks configured")

@celery_app.task(bind=True)
def debug_task(self):
    """Debug task to verify Celery is working"""
    return f'Request: {self.request!r}'


if __name__ == '__main__':
    celery_app.start()