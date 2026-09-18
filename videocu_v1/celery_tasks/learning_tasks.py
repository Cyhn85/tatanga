"""
VIDEOCU v1 - Learning Cycle Tasks
Scheduled self-improvement and optimization tasks
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, List
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='celery_tasks.learning_tasks.run_learning_cycle',
    queue='learning'
)
def run_learning_cycle(self, platforms: Optional[List[str]] = None) -> Dict:
    """
    Run complete learning cycle (scheduled daily at 3 AM)

    This task:
    1. Analyzes performance data from all platforms
    2. Identifies patterns and opportunities
    3. Generates improvement suggestions
    4. Applies high-confidence improvements automatically

    Args:
        platforms: Specific platforms to analyze (None = all)

    Returns:
        Learning cycle results
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting autonomous learning cycle")

    try:
        from modules.self_improvement import SelfImprovementEngine
        from modules.agent_memory import AgentMemory
        from modules.metrics_analyzer import MetricsAnalyzer
        from modules.chef_ai import ChefAI

        # Initialize components
        memory = AgentMemory()
        analyzer = MetricsAnalyzer(memory)
        chef_ai = ChefAI(gemini_api_key=os.getenv('GEMINI_API_KEY', ''))

        engine = SelfImprovementEngine(
            agent_memory=memory,
            metrics_analyzer=analyzer,
            chef_ai=chef_ai
        )

        self.update_state(state='LEARNING', meta={
            'stage': 'analyzing',
            'message': 'Analyzing performance data...'
        })

        # Run the learning cycle
        result = engine.run_learning_cycle()

        # Build detailed report
        report = {
            'task_id': task_id,
            'timestamp': datetime.now().isoformat(),
            'status': result.get('status', 'unknown'),
            'platforms_analyzed': result.get('platforms_analyzed', []),
            'patterns_discovered': result.get('patterns_discovered', 0),
            'opportunities_found': result.get('opportunities_found', 0),
            'improvements_generated': result.get('improvements_generated', 0),
            'improvements_applied': result.get('improvements_applied', 0),
            'details': result.get('details', {})
        }

        # Log significant findings
        if report['improvements_applied'] > 0:
            logger.info(f"[{task_id}] Applied {report['improvements_applied']} improvements automatically")

        if report['patterns_discovered'] > 0:
            logger.info(f"[{task_id}] Discovered {report['patterns_discovered']} new patterns")

        return report

    except Exception as e:
        logger.error(f"[{task_id}] Learning cycle failed: {e}")
        return {
            'task_id': task_id,
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


@shared_task(
    bind=True,
    name='celery_tasks.learning_tasks.analyze_performance',
    queue='learning'
)
def analyze_performance(self, platform: str, days: int = 30) -> Dict:
    """
    Analyze performance for a specific platform

    Args:
        platform: Platform to analyze
        days: Analysis period

    Returns:
        Performance analysis results
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Analyzing {platform} performance ({days} days)")

    try:
        from modules.agent_memory import AgentMemory
        from modules.metrics_analyzer import MetricsAnalyzer

        memory = AgentMemory()
        analyzer = MetricsAnalyzer(memory)

        # Run analysis
        analysis = analyzer.analyze_platform_performance(
            platform=platform,
            days=days
        )

        # Identify patterns
        patterns = analyzer.identify_content_patterns(
            platform=platform,
            min_views=1000
        )

        # Get recommendations
        recommendations = analyzer.generate_recommendations(platform=platform)

        return {
            'task_id': task_id,
            'platform': platform,
            'period_days': days,
            'timestamp': datetime.now().isoformat(),
            'analysis': analysis,
            'patterns': patterns,
            'recommendations': recommendations[:5],  # Top 5
            'status': 'success'
        }

    except Exception as e:
        logger.error(f"[{task_id}] Performance analysis failed: {e}")
        return {
            'task_id': task_id,
            'platform': platform,
            'status': 'failed',
            'error': str(e)
        }


@shared_task(
    bind=True,
    name='celery_tasks.learning_tasks.apply_improvements',
    queue='learning'
)
def apply_improvements(self, improvements: List[Dict],
                        auto_apply: bool = False) -> Dict:
    """
    Apply suggested improvements to system configuration

    Args:
        improvements: List of improvement suggestions
        auto_apply: If True, apply without confirmation

    Returns:
        Application results
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Applying {len(improvements)} improvements (auto={auto_apply})")

    results = {
        'task_id': task_id,
        'timestamp': datetime.now().isoformat(),
        'total': len(improvements),
        'applied': 0,
        'skipped': 0,
        'failed': 0,
        'details': []
    }

    try:
        from modules.self_improvement import SelfImprovementEngine
        from modules.agent_memory import AgentMemory
        from modules.metrics_analyzer import MetricsAnalyzer
        from modules.chef_ai import ChefAI

        memory = AgentMemory()
        analyzer = MetricsAnalyzer(memory)
        chef_ai = ChefAI(gemini_api_key=os.getenv('GEMINI_API_KEY', ''))

        engine = SelfImprovementEngine(
            agent_memory=memory,
            metrics_analyzer=analyzer,
            chef_ai=chef_ai
        )

        for improvement in improvements:
            try:
                imp_type = improvement.get('type', 'unknown')
                confidence = improvement.get('confidence', 0)
                platform = improvement.get('platform', 'all')

                # Skip low confidence unless forced
                if not auto_apply and confidence < 0.7:
                    results['skipped'] += 1
                    results['details'].append({
                        'type': imp_type,
                        'status': 'skipped',
                        'reason': f'Low confidence: {confidence}'
                    })
                    continue

                # Apply the improvement
                if imp_type == 'parameter_update':
                    success = engine._apply_parameter_update(
                        platform=platform,
                        parameters=improvement.get('parameters', {})
                    )
                elif imp_type == 'prompt_update':
                    success = engine._apply_prompt_update(
                        platform=platform,
                        template=improvement.get('template', '')
                    )
                else:
                    success = False

                if success:
                    results['applied'] += 1
                    results['details'].append({
                        'type': imp_type,
                        'platform': platform,
                        'status': 'applied'
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'type': imp_type,
                        'status': 'failed'
                    })

            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'type': improvement.get('type'),
                    'status': 'error',
                    'error': str(e)
                })

        logger.info(f"[{task_id}] Improvements applied: {results['applied']}/{results['total']}")
        return results

    except Exception as e:
        logger.error(f"[{task_id}] Apply improvements failed: {e}")
        return {
            'task_id': task_id,
            'status': 'failed',
            'error': str(e)
        }


@shared_task(
    bind=True,
    name='celery_tasks.learning_tasks.generate_content_strategy',
    queue='learning'
)
def generate_content_strategy(self, platform: str,
                               target_views: int = 10000) -> Dict:
    """
    Generate optimized content strategy based on learned patterns

    Args:
        platform: Target platform
        target_views: Target view count

    Returns:
        Content strategy recommendations
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Generating content strategy for {platform}")

    try:
        from modules.self_improvement import SelfImprovementEngine
        from modules.agent_memory import AgentMemory
        from modules.metrics_analyzer import MetricsAnalyzer
        from modules.chef_ai import ChefAI

        memory = AgentMemory()
        analyzer = MetricsAnalyzer(memory)

        # Get learned configuration
        config = memory.get_learned_config(platform) or {}

        # Get best performing patterns
        patterns = analyzer.identify_content_patterns(
            platform=platform,
            min_views=target_views // 2
        )

        # Get performance predictions
        chef_ai = ChefAI(gemini_api_key=os.getenv('GEMINI_API_KEY', ''))

        strategy = {
            'task_id': task_id,
            'platform': platform,
            'target_views': target_views,
            'timestamp': datetime.now().isoformat(),
            'status': 'success',
            'recommendations': {
                'optimal_duration': config.get('defaults', {}).get('duration', 60),
                'optimal_style': config.get('defaults', {}).get('style', 'informative'),
                'optimal_language': config.get('defaults', {}).get('language', 'de'),
                'best_performing_patterns': patterns[:3] if patterns else [],
                'suggested_topics': _get_trending_topics(platform),
                'posting_schedule': _get_optimal_schedule(platform)
            }
        }

        # Generate AI-powered suggestions if available
        if chef_ai.ai_enabled:
            try:
                ai_suggestions = _generate_ai_suggestions(chef_ai, platform, patterns)
                strategy['recommendations']['ai_suggestions'] = ai_suggestions
            except Exception as e:
                logger.warning(f"AI suggestions failed: {e}")

        return strategy

    except Exception as e:
        logger.error(f"[{task_id}] Strategy generation failed: {e}")
        return {
            'task_id': task_id,
            'platform': platform,
            'status': 'failed',
            'error': str(e)
        }


def _get_trending_topics(platform: str) -> List[str]:
    """Get trending topics for platform (placeholder)"""
    # In production, this would use trend analysis
    default_topics = {
        'youtube': ['AI Technology', 'Tutorial', 'News Analysis', 'Product Review'],
        'tiktok': ['Viral Challenge', 'Life Hack', 'Quick Tips', 'Behind the Scenes'],
        'instagram': ['Lifestyle', 'Travel', 'Food', 'Fashion']
    }
    return default_topics.get(platform, ['General Content'])


def _get_optimal_schedule(platform: str) -> Dict:
    """Get optimal posting schedule (placeholder)"""
    # In production, this would be based on analytics
    schedules = {
        'youtube': {
            'best_days': ['Tuesday', 'Thursday', 'Saturday'],
            'best_hours': ['14:00', '18:00', '20:00'],
            'frequency': 'Every 2-3 days'
        },
        'tiktok': {
            'best_days': ['Monday', 'Wednesday', 'Friday'],
            'best_hours': ['12:00', '19:00', '21:00'],
            'frequency': 'Daily'
        },
        'instagram': {
            'best_days': ['Tuesday', 'Wednesday', 'Friday'],
            'best_hours': ['11:00', '14:00', '19:00'],
            'frequency': 'Every 1-2 days'
        }
    }
    return schedules.get(platform, {'frequency': '2-3 times per week'})


def _generate_ai_suggestions(chef_ai, platform: str, patterns: List) -> List[str]:
    """Generate AI-powered content suggestions"""
    prompt = f"""
    Based on these high-performing content patterns for {platform}:
    {patterns[:3]}

    Suggest 3 specific video ideas that would likely perform well.
    Format: Simple list, one idea per line.
    """

    try:
        response = chef_ai.gemini_model.generate_content(prompt)
        suggestions = response.text.strip().split('\n')
        return [s.strip('- ').strip() for s in suggestions if s.strip()][:3]
    except:
        return []


@shared_task(
    bind=True,
    name='celery_tasks.learning_tasks.rollback_improvement',
    queue='learning'
)
def rollback_improvement(self, improvement_id: str) -> Dict:
    """
    Rollback a previously applied improvement

    Args:
        improvement_id: ID of the improvement to rollback

    Returns:
        Rollback result
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Rolling back improvement: {improvement_id}")

    try:
        from modules.agent_memory import AgentMemory

        memory = AgentMemory()

        # Get improvement history
        history = memory.get_learning_history()

        # Find the improvement
        improvement = None
        for entry in history:
            if entry.get('id') == improvement_id:
                improvement = entry
                break

        if not improvement:
            return {
                'task_id': task_id,
                'status': 'not_found',
                'error': f'Improvement {improvement_id} not found'
            }

        # Get previous state and restore
        previous_state = improvement.get('previous_state', {})
        platform = improvement.get('platform')

        if previous_state and platform:
            memory.update_learned_config(platform, previous_state)
            logger.info(f"[{task_id}] Rolled back {platform} to previous state")

            return {
                'task_id': task_id,
                'status': 'success',
                'improvement_id': improvement_id,
                'platform': platform,
                'restored_state': previous_state
            }
        else:
            return {
                'task_id': task_id,
                'status': 'failed',
                'error': 'No previous state available for rollback'
            }

    except Exception as e:
        logger.error(f"[{task_id}] Rollback failed: {e}")
        return {
            'task_id': task_id,
            'status': 'failed',
            'error': str(e)
        }
