"""
VIDEOCU v1 - Video Production Tasks
Async video creation and upload tasks for Celery
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional
from celery import shared_task, chain, group
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)


def get_chef_ai():
    """Lazy load Chef AI to avoid circular imports"""
    from modules.chef_ai import ChefAI
    from modules.skill_library import SkillLibrary, initialize_default_skills
    from modules.agent_memory import AgentMemory
    from modules.agents import VideoProducerAgent, SocialMediaManagerAgent
    from modules.orchestrator import VideoProducer

    gemini_key = os.getenv('GEMINI_API_KEY', '')
    chef = ChefAI(gemini_api_key=gemini_key)

    skill_library = SkillLibrary()
    initialize_default_skills(skill_library)

    video_producer = VideoProducer()
    video_agent = VideoProducerAgent(
        orchestrator=video_producer,
        skill_library=skill_library
    )
    social_agent = SocialMediaManagerAgent(
        youtube_uploader=None,
        skill_library=skill_library
    )

    chef.register_agent('video_producer', video_agent)
    chef.register_agent('social_media_manager', social_agent)

    return chef, AgentMemory()


@shared_task(
    bind=True,
    name='celery_tasks.video_tasks.produce_video_async',
    max_retries=3,
    default_retry_delay=60,
    queue='video'
)
def produce_video_async(self, prompt: str, user_id: str = 'celery',
                        options: Optional[Dict] = None) -> Dict:
    """
    Async video production task

    Args:
        prompt: Natural language video request
        user_id: User identifier
        options: Additional production options

    Returns:
        Production result dictionary
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting video production: {prompt[:50]}...")

    try:
        # Update task state
        self.update_state(state='PROCESSING', meta={
            'stage': 'initializing',
            'progress': 0,
            'message': 'Initializing Chef AI...'
        })

        chef_ai, agent_memory = get_chef_ai()

        # Update state
        self.update_state(state='PROCESSING', meta={
            'stage': 'analyzing',
            'progress': 10,
            'message': 'Analyzing request...'
        })

        # Execute through Chef AI
        result = chef_ai.execute_order(
            raw_prompt=prompt,
            user_id=user_id
        )

        # Record in memory
        agent_memory.record_task(result)

        # Update state
        self.update_state(state='PROCESSING', meta={
            'stage': 'completed',
            'progress': 100,
            'message': 'Production complete'
        })

        logger.info(f"[{task_id}] Video production completed: {result['status']}")

        return {
            'task_id': result['task_id'],
            'celery_task_id': task_id,
            'status': result['status'],
            'analysis': result.get('analysis', {}),
            'result': result.get('result', {}),
            'completed_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"[{task_id}] Video production failed: {e}")

        try:
            # Retry on failure
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            return {
                'task_id': task_id,
                'status': 'failed',
                'error': str(e),
                'failed_at': datetime.now().isoformat()
            }


@shared_task(
    bind=True,
    name='celery_tasks.video_tasks.produce_video_batch',
    queue='video'
)
def produce_video_batch(self, prompts: list, user_id: str = 'celery') -> Dict:
    """
    Batch video production - creates multiple videos

    Args:
        prompts: List of video prompts
        user_id: User identifier

    Returns:
        Batch results dictionary
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting batch production: {len(prompts)} videos")

    results = {
        'batch_id': task_id,
        'total': len(prompts),
        'completed': 0,
        'failed': 0,
        'results': []
    }

    for i, prompt in enumerate(prompts):
        self.update_state(state='PROCESSING', meta={
            'stage': f'video_{i+1}_of_{len(prompts)}',
            'progress': int((i / len(prompts)) * 100),
            'message': f'Processing video {i+1}/{len(prompts)}'
        })

        try:
            # Call single video task synchronously within batch
            result = produce_video_async.apply(
                args=[prompt, user_id],
                throw=True
            ).get(timeout=600)  # 10 min timeout per video

            results['results'].append(result)
            results['completed'] += 1

        except Exception as e:
            logger.error(f"[{task_id}] Batch item {i+1} failed: {e}")
            results['results'].append({
                'prompt': prompt[:50],
                'status': 'failed',
                'error': str(e)
            })
            results['failed'] += 1

    logger.info(f"[{task_id}] Batch complete: {results['completed']}/{results['total']}")
    return results


@shared_task(
    bind=True,
    name='celery_tasks.video_tasks.upload_video_async',
    max_retries=3,
    default_retry_delay=120,
    queue='video'
)
def upload_video_async(self, video_path: str, platform: str,
                       metadata: Dict) -> Dict:
    """
    Async video upload task

    Args:
        video_path: Path to video file
        platform: Target platform (youtube, tiktok, instagram)
        metadata: Upload metadata (title, description, tags)

    Returns:
        Upload result dictionary
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting upload to {platform}: {video_path}")

    try:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        self.update_state(state='UPLOADING', meta={
            'platform': platform,
            'progress': 0,
            'message': 'Preparing upload...'
        })

        # Platform-specific upload
        if platform == 'youtube':
            result = _upload_to_youtube(video_path, metadata, self)
        elif platform == 'tiktok':
            result = _upload_to_tiktok(video_path, metadata, self)
        elif platform == 'instagram':
            result = _upload_to_instagram(video_path, metadata, self)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        # Log to performance tracker
        if result.get('success') and result.get('video_id'):
            _log_publication(result, platform, metadata)

        logger.info(f"[{task_id}] Upload completed: {result.get('video_id', 'N/A')}")
        return result

    except Exception as e:
        logger.error(f"[{task_id}] Upload failed: {e}")
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            return {
                'status': 'failed',
                'platform': platform,
                'error': str(e)
            }


def _upload_to_youtube(video_path: str, metadata: Dict, task) -> Dict:
    """Upload video to YouTube"""
    try:
        from modules.youtube_uploader import YouTubeUploader

        uploader = YouTubeUploader()

        task.update_state(state='UPLOADING', meta={
            'platform': 'youtube',
            'progress': 50,
            'message': 'Uploading to YouTube...'
        })

        result = uploader.upload_video(
            video_path=video_path,
            title=metadata.get('title', 'Untitled Video'),
            description=metadata.get('description', ''),
            tags=metadata.get('tags', []),
            category_id=metadata.get('category_id', '22'),
            privacy_status=metadata.get('privacy_status', 'public')
        )

        return {
            'success': True,
            'platform': 'youtube',
            'video_id': result.get('id'),
            'url': f"https://youtube.com/watch?v={result.get('id')}"
        }

    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        return {'success': False, 'platform': 'youtube', 'error': str(e)}


def _upload_to_tiktok(video_path: str, metadata: Dict, task) -> Dict:
    """Upload video to TikTok (placeholder)"""
    # TikTok API implementation would go here
    logger.warning("TikTok upload not yet implemented")
    return {
        'success': False,
        'platform': 'tiktok',
        'error': 'TikTok upload not implemented'
    }


def _upload_to_instagram(video_path: str, metadata: Dict, task) -> Dict:
    """Upload video to Instagram (placeholder)"""
    # Instagram API implementation would go here
    logger.warning("Instagram upload not yet implemented")
    return {
        'success': False,
        'platform': 'instagram',
        'error': 'Instagram upload not implemented'
    }


def _log_publication(result: Dict, platform: str, metadata: Dict):
    """Log publication for performance tracking"""
    try:
        from modules.agent_memory import AgentMemory

        memory = AgentMemory()
        memory.add_performance_log({
            'video_id': result.get('video_id'),
            'platform': platform,
            'topic': metadata.get('title', ''),
            'status': 'AWAITING_ANALYTICS',
            'publish_time': datetime.now().timestamp(),
            'initial_data': {
                'title': metadata.get('title'),
                'tags': metadata.get('tags', []),
                'url': result.get('url')
            }
        })
        logger.info(f"Publication logged for analytics: {result.get('video_id')}")

    except Exception as e:
        logger.warning(f"Failed to log publication: {e}")


# ========== Task Chains ==========

def create_and_upload_chain(prompt: str, platform: str, user_id: str = 'celery'):
    """
    Create a chain: produce video -> upload to platform

    Usage:
        chain_result = create_and_upload_chain(
            "60 second AI video",
            "youtube"
        ).apply_async()
    """
    return chain(
        produce_video_async.s(prompt, user_id),
        upload_video_async.s(platform)  # Gets video_path from previous result
    )


def create_multi_platform_group(prompt: str, platforms: list, user_id: str = 'celery'):
    """
    Create video and upload to multiple platforms in parallel

    Usage:
        group_result = create_multi_platform_group(
            "viral video",
            ["youtube", "tiktok", "instagram"]
        ).apply_async()
    """
    # First produce the video
    video_task = produce_video_async.s(prompt, user_id)

    # Then upload to all platforms in parallel
    upload_group = group([
        upload_video_async.s(platform) for platform in platforms
    ])

    return chain(video_task, upload_group)
