"""
VIDEOCU v1 - Analytics Collection Tasks
Scheduled tasks for collecting metrics and system monitoring
"""

import os
import logging
import shutil
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='celery_tasks.analytics_tasks.collect_all_analytics',
    queue='analytics'
)
def collect_all_analytics(self, min_age_hours: int = 24) -> Dict:
    """
    Collect analytics for all platforms (scheduled every 6 hours)

    Args:
        min_age_hours: Minimum video age before collecting analytics

    Returns:
        Collection results summary
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting analytics collection for all platforms")

    results = {
        'task_id': task_id,
        'timestamp': datetime.now().isoformat(),
        'platforms': {},
        'total_collected': 0,
        'total_errors': 0
    }

    platforms = ['youtube', 'tiktok', 'instagram']

    for platform in platforms:
        try:
            self.update_state(state='COLLECTING', meta={
                'platform': platform,
                'message': f'Collecting {platform} analytics...'
            })

            platform_result = collect_platform_analytics.apply(
                args=[platform, min_age_hours],
                throw=True
            ).get(timeout=300)  # 5 min timeout per platform

            results['platforms'][platform] = platform_result
            results['total_collected'] += platform_result.get('collected', 0)
            results['total_errors'] += platform_result.get('errors', 0)

        except Exception as e:
            logger.error(f"[{task_id}] {platform} analytics failed: {e}")
            results['platforms'][platform] = {
                'status': 'failed',
                'error': str(e)
            }
            results['total_errors'] += 1

    logger.info(f"[{task_id}] Analytics collection complete: {results['total_collected']} collected")
    return results


@shared_task(
    bind=True,
    name='celery_tasks.analytics_tasks.collect_platform_analytics',
    max_retries=2,
    default_retry_delay=60,
    queue='analytics'
)
def collect_platform_analytics(self, platform: str,
                                min_age_hours: int = 24) -> Dict:
    """
    Collect analytics for a specific platform

    Args:
        platform: Platform name (youtube, tiktok, instagram)
        min_age_hours: Minimum video age

    Returns:
        Platform-specific collection results
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Collecting {platform} analytics")

    try:
        from modules.agent_memory import AgentMemory
        from modules.performance_logger import PerformanceLogger

        memory = AgentMemory()
        perf_logger = PerformanceLogger(agent_memory=memory)

        # Get pending logs for this platform
        pending_logs = memory.get_performance_logs(
            platform=platform,
            status='AWAITING_ANALYTICS'
        )

        results = {
            'platform': platform,
            'status': 'success',
            'pending_count': len(pending_logs),
            'collected': 0,
            'skipped': 0,
            'errors': 0,
            'details': []
        }

        min_age_seconds = min_age_hours * 3600
        current_time = datetime.now().timestamp()

        for log in pending_logs:
            video_id = log.get('video_id')
            publish_time = log.get('publish_time', 0)

            # Skip if too recent
            if current_time - publish_time < min_age_seconds:
                results['skipped'] += 1
                continue

            try:
                # Fetch analytics based on platform
                analytics = _fetch_analytics(platform, video_id)

                if analytics:
                    # Update the log with analytics
                    memory.update_performance_log(
                        video_id=video_id,
                        platform=platform,
                        update_data={
                            'analytics': analytics,
                            'status': 'ANALYTICS_COLLECTED',
                            'last_updated': current_time
                        }
                    )
                    results['collected'] += 1
                    results['details'].append({
                        'video_id': video_id,
                        'views': analytics.get('views', 0)
                    })

            except Exception as e:
                logger.warning(f"Failed to collect analytics for {video_id}: {e}")
                results['errors'] += 1

        logger.info(f"[{task_id}] {platform}: collected {results['collected']}/{results['pending_count']}")
        return results

    except Exception as e:
        logger.error(f"[{task_id}] Platform analytics failed: {e}")
        return {
            'platform': platform,
            'status': 'failed',
            'error': str(e)
        }


def _fetch_analytics(platform: str, video_id: str) -> Optional[Dict]:
    """Fetch analytics from platform"""
    if platform == 'youtube':
        return _fetch_youtube_analytics(video_id)
    elif platform == 'tiktok':
        return _fetch_tiktok_analytics(video_id)
    elif platform == 'instagram':
        return _fetch_instagram_analytics(video_id)
    return None


def _fetch_youtube_analytics(video_id: str) -> Optional[Dict]:
    """Fetch YouTube video analytics"""
    try:
        from modules.performance_logger import YouTubeScraper

        scraper = YouTubeScraper()
        metrics = scraper.get_video_metrics(video_id)

        if metrics:
            return {
                'views': metrics.get('views', 0),
                'likes': metrics.get('likes', 0),
                'comments': metrics.get('comments', 0),
                'engagement_rate': metrics.get('engagement_rate', 0),
                'collected_at': datetime.now().isoformat()
            }
        return None

    except Exception as e:
        logger.warning(f"YouTube analytics fetch failed: {e}")
        return None


def _fetch_tiktok_analytics(video_id: str) -> Optional[Dict]:
    """Fetch TikTok video analytics (placeholder)"""
    logger.warning("TikTok analytics not yet implemented")
    return None


def _fetch_instagram_analytics(video_id: str) -> Optional[Dict]:
    """Fetch Instagram video analytics (placeholder)"""
    logger.warning("Instagram analytics not yet implemented")
    return None


@shared_task(
    bind=True,
    name='celery_tasks.analytics_tasks.system_health_check',
    queue='default'
)
def system_health_check(self) -> Dict:
    """
    Periodic system health check (every 30 minutes)

    Returns:
        System health status
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Running system health check")

    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        health = {
            'task_id': task_id,
            'timestamp': datetime.now().isoformat(),
            'status': 'healthy',
            'metrics': {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'disk_percent': disk.percent,
                'disk_free_gb': round(disk.free / (1024**3), 2)
            },
            'warnings': []
        }

        # Check thresholds
        if cpu_percent > 80:
            health['warnings'].append(f'High CPU usage: {cpu_percent}%')
            health['status'] = 'warning'

        if memory.percent > 85:
            health['warnings'].append(f'High memory usage: {memory.percent}%')
            health['status'] = 'warning'

        if disk.percent > 90:
            health['warnings'].append(f'Low disk space: {disk.percent}% used')
            health['status'] = 'critical'

        # Check output directory size
        output_dir = Path('output')
        if output_dir.exists():
            total_size = sum(f.stat().st_size for f in output_dir.rglob('*') if f.is_file())
            health['metrics']['output_size_gb'] = round(total_size / (1024**3), 2)

            if total_size > 10 * 1024**3:  # More than 10GB
                health['warnings'].append('Output directory exceeds 10GB')

        if health['warnings']:
            logger.warning(f"[{task_id}] Health warnings: {health['warnings']}")
        else:
            logger.info(f"[{task_id}] System healthy")

        return health

    except Exception as e:
        logger.error(f"[{task_id}] Health check failed: {e}")
        return {
            'task_id': task_id,
            'status': 'error',
            'error': str(e)
        }


@shared_task(
    bind=True,
    name='celery_tasks.analytics_tasks.cleanup_old_files',
    queue='maintenance'
)
def cleanup_old_files(self, max_age_days: int = 7,
                       dry_run: bool = False) -> Dict:
    """
    Clean up old output files (weekly maintenance)

    Args:
        max_age_days: Delete files older than this
        dry_run: If True, only report what would be deleted

    Returns:
        Cleanup results
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting file cleanup (max_age={max_age_days} days, dry_run={dry_run})")

    results = {
        'task_id': task_id,
        'timestamp': datetime.now().isoformat(),
        'dry_run': dry_run,
        'files_checked': 0,
        'files_deleted': 0,
        'space_freed_mb': 0,
        'errors': []
    }

    output_dir = Path('output')
    if not output_dir.exists():
        return results

    cutoff_time = datetime.now() - timedelta(days=max_age_days)
    cutoff_timestamp = cutoff_time.timestamp()

    # Patterns to clean
    cleanup_patterns = ['*.mp4', '*.mp3', '*.wav', '*.jpg', '*.png']

    for pattern in cleanup_patterns:
        for file_path in output_dir.rglob(pattern):
            results['files_checked'] += 1

            try:
                # Check file age
                file_mtime = file_path.stat().st_mtime
                if file_mtime < cutoff_timestamp:
                    file_size = file_path.stat().st_size

                    if not dry_run:
                        file_path.unlink()
                        logger.info(f"Deleted: {file_path}")

                    results['files_deleted'] += 1
                    results['space_freed_mb'] += file_size / (1024 * 1024)

            except Exception as e:
                results['errors'].append(f"{file_path}: {str(e)}")

    results['space_freed_mb'] = round(results['space_freed_mb'], 2)

    logger.info(f"[{task_id}] Cleanup complete: {results['files_deleted']} files, "
                f"{results['space_freed_mb']} MB freed")

    return results


@shared_task(
    bind=True,
    name='celery_tasks.analytics_tasks.export_analytics_report',
    queue='analytics'
)
def export_analytics_report(self, days: int = 30,
                             format: str = 'json') -> Dict:
    """
    Export analytics report for the specified period

    Args:
        days: Report period in days
        format: Output format (json, csv)

    Returns:
        Report file path and summary
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Generating analytics report ({days} days)")

    try:
        from modules.agent_memory import AgentMemory
        from modules.metrics_analyzer import MetricsAnalyzer
        import json

        memory = AgentMemory()
        analyzer = MetricsAnalyzer(memory)

        # Generate summary
        summary = analyzer.generate_performance_summary(days=days)

        # Create report
        report = {
            'generated_at': datetime.now().isoformat(),
            'period_days': days,
            'summary': summary
        }

        # Save report
        output_dir = Path('output/reports')
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"analytics_report_{timestamp}.{format}"
        filepath = output_dir / filename

        if format == 'json':
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        elif format == 'csv':
            # Convert to CSV format
            _export_to_csv(report, filepath)

        logger.info(f"[{task_id}] Report exported: {filepath}")

        return {
            'task_id': task_id,
            'status': 'success',
            'filepath': str(filepath),
            'summary': {
                'total_videos': summary.get('overall', {}).get('total_videos', 0),
                'total_views': summary.get('overall', {}).get('total_views', 0)
            }
        }

    except Exception as e:
        logger.error(f"[{task_id}] Report generation failed: {e}")
        return {
            'task_id': task_id,
            'status': 'failed',
            'error': str(e)
        }


def _export_to_csv(report: Dict, filepath: Path):
    """Convert report to CSV format"""
    import csv

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow(['Metric', 'Value'])

        # Overall stats
        overall = report.get('summary', {}).get('overall', {})
        for key, value in overall.items():
            writer.writerow([key, value])

        # Platform breakdown
        platforms = report.get('summary', {}).get('platforms', {})
        for platform, stats in platforms.items():
            writer.writerow([f'{platform}_videos', stats.get('video_count', 0)])
            writer.writerow([f'{platform}_views', stats.get('total_views', 0)])
