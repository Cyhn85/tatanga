"""
VIDEOCU v1 - Celery Tasks Package
Background task definitions for async processing
"""

from celery_tasks.video_tasks import (
    produce_video_async,
    produce_video_batch,
    upload_video_async
)

from celery_tasks.analytics_tasks import (
    collect_all_analytics,
    collect_platform_analytics,
    system_health_check,
    cleanup_old_files
)

from celery_tasks.learning_tasks import (
    run_learning_cycle,
    analyze_performance,
    apply_improvements
)

from celery_tasks.ceo_tasks import (
    process_production_order,
    daily_trend_cycle,
    get_ceo_status,
    get_daily_report,
    trigger_manual_production
)

__all__ = [
    # CEO Tasks
    'process_production_order',
    'daily_trend_cycle',
    'get_ceo_status',
    'get_daily_report',
    'trigger_manual_production',
    # Video Tasks
    'produce_video_async',
    'produce_video_batch',
    'upload_video_async',
    # Analytics Tasks
    'collect_all_analytics',
    'collect_platform_analytics',
    'system_health_check',
    'cleanup_old_files',
    # Learning Tasks
    'run_learning_cycle',
    'analyze_performance',
    'apply_improvements'
]