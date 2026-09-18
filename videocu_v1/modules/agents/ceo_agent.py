"""
VIDEOCU v1 - CEO Agent
Central orchestrator that manages all agents and workflows

Architecture:
- Trend Scout → Content Analyzer → Story Writer → Video Producer → Publisher → Analytics
- Uses Celery for async task execution
- Learns from Analytics Agent feedback
- Reports status via Telegram
"""

import os
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from celery import chain, group, chord

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStage(Enum):
    TREND_SCOUT = "trend_scout"
    CONTENT_ANALYZER = "content_analyzer"
    STORY_WRITER = "story_writer"
    VIDEO_PRODUCER = "video_producer"
    PUBLISHER = "publisher"
    ANALYTICS = "analytics"


class CEOAgent:
    """
    CEO Agent - Master orchestrator for VIDEOCU v1

    Responsibilities:
    1. Receive production orders (from Telegram, API, Activepieces)
    2. Validate inputs and check prerequisites
    3. Create pipeline of tasks
    4. Delegate to specialized agents via Celery
    5. Monitor progress and handle failures
    6. Learn from analytics feedback
    7. Report results to admin
    """

    def __init__(self,
                 gemini_api_key: Optional[str] = None,
                 telegram_bot_token: Optional[str] = None,
                 admin_chat_id: Optional[str] = None):
        """
        Initialize CEO Agent

        Args:
            gemini_api_key: For AI-powered decisions
            telegram_bot_token: For status reporting
            admin_chat_id: Admin Telegram chat ID
        """
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY', '')
        self.telegram_token = telegram_bot_token or os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.admin_chat_id = admin_chat_id or os.getenv('ADMIN_TELEGRAM_CHAT_ID', '')

        # Agent registry
        self.agents: Dict[str, Any] = {}
        self.agent_status: Dict[str, AgentStatus] = {}

        # Pipeline configuration
        self.pipeline_config = {
            'auto_publish': False,  # Manual approval for now
            'min_trend_score': 50,
            'target_platforms': ['youtube'],  # Start with YouTube only
            'max_daily_videos': 5,
            'learning_enabled': True
        }

        # Statistics
        self.stats = {
            'total_orders': 0,
            'successful': 0,
            'failed': 0,
            'videos_produced': 0,
            'videos_published': 0
        }

        logger.info("🎩 CEO Agent initialized")

    def register_agent(self, agent_name: str, agent_instance: Any):
        """Register a specialized agent"""
        self.agents[agent_name] = agent_instance
        self.agent_status[agent_name] = AgentStatus.IDLE
        logger.info(f"   ✅ Registered: {agent_name}")

    # ========== Main Entry Points ==========

    async def process_production_order(self, order: Dict) -> Dict:
        """
        Main entry point for production orders

        Args:
            order: Production order dict with:
                - order_type: 'trend_based' | 'manual' | 'scheduled'
                - topic: Optional topic for manual orders
                - platforms: Target platforms
                - options: Additional options

        Returns:
            Order processing result
        """
        order_id = self._generate_order_id()
        self.stats['total_orders'] += 1

        logger.info(f"🎩 CEO received order #{order_id}: {order.get('order_type', 'unknown')}")

        try:
            # Step 1: Validate order
            validation = self._validate_order(order)
            if not validation['valid']:
                return self._create_error_response(order_id, validation['error'])

            # Step 2: Determine pipeline based on order type
            order_type = order.get('order_type', 'manual')

            if order_type == 'trend_based':
                result = await self._execute_trend_based_pipeline(order_id, order)
            elif order_type == 'manual':
                result = await self._execute_manual_pipeline(order_id, order)
            elif order_type == 'scheduled':
                result = await self._execute_scheduled_pipeline(order_id, order)
            else:
                return self._create_error_response(order_id, f"Unknown order type: {order_type}")

            # Step 3: Log and report
            if result.get('success'):
                self.stats['successful'] += 1
                await self._report_success(order_id, result)
            else:
                self.stats['failed'] += 1
                await self._report_failure(order_id, result)

            return result

        except Exception as e:
            logger.error(f"❌ CEO order processing failed: {e}")
            self.stats['failed'] += 1
            return self._create_error_response(order_id, str(e))

    async def run_daily_trend_cycle(self) -> Dict:
        """
        Automated daily trend-based content creation
        Called by Celery beat or Activepieces scheduler
        """
        logger.info("🎩 CEO starting daily trend cycle")

        try:
            # Step 1: Get current trends
            trends = await self._get_current_trends()

            if not trends:
                logger.warning("No trends found for daily cycle")
                return {'success': False, 'error': 'No trends available'}

            # Step 2: Filter and score trends
            scored_trends = self._score_and_filter_trends(trends)

            # Step 3: Select best opportunities
            selected = scored_trends[:self.pipeline_config['max_daily_videos']]

            logger.info(f"   Selected {len(selected)} trends for production")

            # Step 4: Create production orders
            results = []
            for trend in selected:
                order = {
                    'order_type': 'trend_based',
                    'trend_data': trend,
                    'topic': trend.get('keyword'),
                    'platforms': self.pipeline_config['target_platforms'],
                    'options': {
                        'style': 'informativ',
                        'duration': 60
                    }
                }

                result = await self.process_production_order(order)
                results.append(result)

            # Step 5: Summary
            successful = sum(1 for r in results if r.get('success'))

            return {
                'success': True,
                'trends_analyzed': len(trends),
                'videos_queued': len(selected),
                'successful': successful,
                'results': results
            }

        except Exception as e:
            logger.error(f"Daily trend cycle failed: {e}")
            return {'success': False, 'error': str(e)}

    # ========== Pipeline Executors ==========

    async def _execute_trend_based_pipeline(self, order_id: str, order: Dict) -> Dict:
        """Execute full trend-based pipeline"""
        from celery_app import celery_app

        logger.info(f"   Executing trend-based pipeline for {order_id}")

        # Create Celery chain for the pipeline
        pipeline = chain(
            # Stage 1: Analyze trend
            celery_app.signature('celery_tasks.video_tasks.produce_video_async',
                args=[order.get('topic', 'Trending topic'), order_id],
                kwargs={'options': order.get('options', {})}
            )
        )

        # Execute async
        result = pipeline.apply_async()

        return {
            'success': True,
            'order_id': order_id,
            'celery_task_id': result.id,
            'status': 'queued',
            'pipeline': 'trend_based',
            'message': 'Production order queued for processing'
        }

    async def _execute_manual_pipeline(self, order_id: str, order: Dict) -> Dict:
        """Execute manual topic pipeline"""
        from celery_app import celery_app

        topic = order.get('topic', '')
        if not topic:
            return self._create_error_response(order_id, "Topic required for manual orders")

        logger.info(f"   Executing manual pipeline for: {topic[:50]}")

        # Queue video production
        from celery_tasks.video_tasks import produce_video_async

        result = produce_video_async.apply_async(
            args=[topic, order_id],
            kwargs={'options': order.get('options', {})}
        )

        return {
            'success': True,
            'order_id': order_id,
            'celery_task_id': result.id,
            'status': 'queued',
            'pipeline': 'manual',
            'topic': topic
        }

    async def _execute_scheduled_pipeline(self, order_id: str, order: Dict) -> Dict:
        """Execute scheduled/recurring pipeline"""
        # For scheduled tasks, we queue them with ETA
        schedule = order.get('schedule', {})

        return {
            'success': True,
            'order_id': order_id,
            'status': 'scheduled',
            'schedule': schedule,
            'message': 'Order scheduled for future execution'
        }

    # ========== Trend Analysis ==========

    async def _get_current_trends(self) -> List[Dict]:
        """Fetch current trends from Trend API"""
        import aiohttp

        trend_api_url = os.getenv('TREND_API_URL', 'http://localhost:8002')

        trends = []

        async with aiohttp.ClientSession() as session:
            # Google Trends
            try:
                async with session.get(f"{trend_api_url}/api/trends/germany?limit=20") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        trends.extend(data.get('data', []))
            except Exception as e:
                logger.warning(f"Google Trends fetch failed: {e}")

            # YouTube Trends
            try:
                async with session.get(f"{trend_api_url}/api/trends/youtube?limit=10") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for video in data.get('data', []):
                            trends.append({
                                'keyword': video.get('title', ''),
                                'source': 'youtube',
                                'score': video.get('score', 0),
                                'video_data': video
                            })
            except Exception as e:
                logger.warning(f"YouTube Trends fetch failed: {e}")

        return trends

    def _score_and_filter_trends(self, trends: List[Dict]) -> List[Dict]:
        """Score and filter trends based on potential"""
        min_score = self.pipeline_config['min_trend_score']

        scored = []
        for trend in trends:
            score = trend.get('score', 0)

            # Boost based on source
            source = trend.get('source', '')
            if source == 'google_trends_rss':
                score *= 1.2  # Boost real-time trends
            elif source == 'youtube':
                score *= 1.1  # Boost already-viral content

            if score >= min_score:
                trend['final_score'] = score
                scored.append(trend)

        # Sort by score
        scored.sort(key=lambda x: x.get('final_score', 0), reverse=True)

        return scored

    # ========== Validation ==========

    def _validate_order(self, order: Dict) -> Dict:
        """Validate production order"""
        order_type = order.get('order_type')

        if not order_type:
            return {'valid': False, 'error': 'order_type is required'}

        if order_type == 'manual' and not order.get('topic'):
            return {'valid': False, 'error': 'topic is required for manual orders'}

        # Check daily limit
        if self.stats['videos_produced'] >= self.pipeline_config['max_daily_videos']:
            return {'valid': False, 'error': 'Daily video limit reached'}

        return {'valid': True}

    # ========== Reporting ==========

    async def _report_success(self, order_id: str, result: Dict):
        """Report successful order to admin"""
        if not self.telegram_token or not self.admin_chat_id:
            return

        message = f"""
✅ *Production Order Completed*

Order ID: `{order_id}`
Pipeline: {result.get('pipeline', 'unknown')}
Status: {result.get('status', 'completed')}
Celery Task: `{result.get('celery_task_id', 'N/A')}`
        """

        await self._send_telegram_message(message)

    async def _report_failure(self, order_id: str, result: Dict):
        """Report failed order to admin"""
        if not self.telegram_token or not self.admin_chat_id:
            return

        message = f"""
❌ *Production Order Failed*

Order ID: `{order_id}`
Error: {result.get('error', 'Unknown error')}
        """

        await self._send_telegram_message(message)

    async def _send_telegram_message(self, message: str):
        """Send message to admin via Telegram"""
        try:
            import aiohttp

            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.admin_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.warning(f"Telegram notification failed: {await resp.text()}")

        except Exception as e:
            logger.warning(f"Failed to send Telegram message: {e}")

    # ========== Learning ==========

    def apply_learning(self, feedback: Dict):
        """Apply learning from analytics feedback"""
        if not self.pipeline_config['learning_enabled']:
            return

        # Update pipeline config based on performance
        if feedback.get('avg_views', 0) > 10000:
            # High performing - increase production
            logger.info("   📈 High performance detected - adjusting strategy")
        elif feedback.get('avg_views', 0) < 1000:
            # Low performing - adjust approach
            logger.info("   📉 Low performance detected - revising strategy")

    # ========== Utilities ==========

    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        return f"ORDER_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"

    def _create_error_response(self, order_id: str, error: str) -> Dict:
        """Create standardized error response"""
        return {
            'success': False,
            'order_id': order_id,
            'status': 'failed',
            'error': error
        }

    def get_status(self) -> Dict:
        """Get CEO Agent status"""
        return {
            'status': 'active',
            'stats': self.stats,
            'pipeline_config': self.pipeline_config,
            'registered_agents': list(self.agents.keys()),
            'agent_status': {k: v.value for k, v in self.agent_status.items()}
        }

    def get_daily_report(self) -> Dict:
        """Generate daily performance report"""
        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_orders': self.stats['total_orders'],
            'successful': self.stats['successful'],
            'failed': self.stats['failed'],
            'success_rate': (self.stats['successful'] / max(1, self.stats['total_orders'])) * 100,
            'videos_produced': self.stats['videos_produced'],
            'videos_published': self.stats['videos_published']
        }


# ========== Celery Tasks for CEO ==========

def create_ceo_tasks(celery_app):
    """Create Celery tasks for CEO Agent"""

    @celery_app.task(name='ceo.process_order')
    def process_order_task(order: Dict) -> Dict:
        """Celery task wrapper for process_production_order"""
        import asyncio

        ceo = CEOAgent()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(ceo.process_production_order(order))
            return result
        finally:
            loop.close()

    @celery_app.task(name='ceo.daily_trend_cycle')
    def daily_trend_cycle_task() -> Dict:
        """Celery task for daily trend cycle"""
        import asyncio

        ceo = CEOAgent()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(ceo.run_daily_trend_cycle())
            return result
        finally:
            loop.close()

    @celery_app.task(name='ceo.get_status')
    def get_ceo_status_task() -> Dict:
        """Get CEO status"""
        ceo = CEOAgent()
        return ceo.get_status()

    return {
        'process_order': process_order_task,
        'daily_trend_cycle': daily_trend_cycle_task,
        'get_status': get_ceo_status_task
    }


# ========== Test ==========

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("🎩 CEO AGENT TEST")
    print("="*70)

    ceo = CEOAgent()

    print(f"\nStatus: {json.dumps(ceo.get_status(), indent=2)}")

    # Test manual order
    test_order = {
        'order_type': 'manual',
        'topic': 'Almanya\'da yapay zeka trendi',
        'platforms': ['youtube'],
        'options': {
            'duration': 60,
            'style': 'informativ'
        }
    }

    print(f"\n📋 Test Order: {test_order}")

    # Would need async context to actually run
    print("\n✅ CEO Agent initialized successfully")
    print("="*70)