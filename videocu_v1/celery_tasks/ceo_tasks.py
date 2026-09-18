"""
VIDEOCU v1 - CEO Agent Celery Tasks
Background tasks for CEO orchestration
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Optional
from celery import shared_task

logger = logging.getLogger(__name__)


def get_ceo_agent():
    """Lazy load CEO Agent"""
    from modules.agents.ceo_agent import CEOAgent
    return CEOAgent(
        gemini_api_key=os.getenv('GEMINI_API_KEY'),
        telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
        admin_chat_id=os.getenv('ADMIN_TELEGRAM_CHAT_ID')
    )


def run_async(coro):
    """Helper to run async functions in sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    bind=True,
    name='ceo.process_order',
    queue='default',
    max_retries=2,
    default_retry_delay=60
)
def process_production_order(self, order: Dict) -> Dict:
    """
    Process a production order through CEO Agent

    Args:
        order: Production order dict with:
            - order_type: 'trend_based' | 'manual' | 'scheduled'
            - topic: Topic for manual orders
            - platforms: Target platforms
            - options: Additional options

    Returns:
        Processing result
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] CEO processing order: {order.get('order_type', 'unknown')}")

    try:
        self.update_state(state='PROCESSING', meta={
            'stage': 'initializing',
            'message': 'CEO Agent initializing...'
        })

        ceo = get_ceo_agent()

        self.update_state(state='PROCESSING', meta={
            'stage': 'executing',
            'message': 'Processing order...'
        })

        result = run_async(ceo.process_production_order(order))

        logger.info(f"[{task_id}] CEO order completed: {result.get('status', 'unknown')}")

        return {
            'celery_task_id': task_id,
            'timestamp': datetime.now().isoformat(),
            **result
        }

    except Exception as e:
        logger.error(f"[{task_id}] CEO order failed: {e}")
        return {
            'celery_task_id': task_id,
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


@shared_task(
    bind=True,
    name='ceo.daily_trend_cycle',
    queue='default'
)
def daily_trend_cycle(self) -> Dict:
    """
    Daily automated trend-based content cycle

    Scheduled to run at 8 AM daily via Celery Beat
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting CEO daily trend cycle")

    try:
        self.update_state(state='RUNNING', meta={
            'stage': 'trend_analysis',
            'message': 'Analyzing current trends...'
        })

        ceo = get_ceo_agent()
        result = run_async(ceo.run_daily_trend_cycle())

        logger.info(f"[{task_id}] Daily cycle complete: {result.get('successful', 0)} videos queued")

        return {
            'celery_task_id': task_id,
            'timestamp': datetime.now().isoformat(),
            **result
        }

    except Exception as e:
        logger.error(f"[{task_id}] Daily trend cycle failed: {e}")
        return {
            'celery_task_id': task_id,
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


@shared_task(
    bind=True,
    name='ceo.get_status',
    queue='default'
)
def get_ceo_status(self) -> Dict:
    """Get current CEO Agent status"""
    ceo = get_ceo_agent()
    return {
        'celery_task_id': self.request.id,
        'timestamp': datetime.now().isoformat(),
        **ceo.get_status()
    }


@shared_task(
    bind=True,
    name='ceo.get_daily_report',
    queue='default'
)
def get_daily_report(self) -> Dict:
    """Generate CEO daily performance report"""
    ceo = get_ceo_agent()
    return {
        'celery_task_id': self.request.id,
        'timestamp': datetime.now().isoformat(),
        **ceo.get_daily_report()
    }


@shared_task(
    bind=True,
    name='ceo.trigger_manual_production',
    queue='default'
)
def trigger_manual_production(self, topic: str, options: Optional[Dict] = None) -> Dict:
    """
    Trigger manual video production

    Args:
        topic: Video topic
        options: Production options (duration, style, etc.)

    Returns:
        Production result
    """
    order = {
        'order_type': 'manual',
        'topic': topic,
        'platforms': ['youtube'],
        'options': options or {
            'duration': 60,
            'style': 'informativ',
            'language': 'de'
        }
    }

    return process_production_order.apply(args=[order]).get()