"""
VIDEOCU v1 - Chef AI Core
CEO-level orchestrator: Analyzes prompts → Delegates to specialized agents

Architecture:
- Raw prompt analysis (Gemini AI)
- Intent classification (video/music/social)
- Task delegation to agents
- Result aggregation & reporting
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
import google.generativeai as genai

logger = logging.getLogger(__name__)


class ChefAI:
    """
    CEO of VIDEOCU v1 - Strategic decision maker

    Responsibilities:
    - Understand user intent from raw prompts
    - Classify task type (video, music, social media, server)
    - Create structured task specifications
    - Delegate to appropriate specialized agents
    - Aggregate results and report back
    """

    # Supported task types
    TASK_VIDEO_CREATION = "video_creation"
    TASK_MUSIC_CREATION = "music_creation"
    TASK_SOCIAL_MEDIA = "social_media_management"
    TASK_SERVER_ADMIN = "server_administration"
    TASK_MULTI_AGENT = "multi_agent"  # Requires multiple agents

    # Platform types
    PLATFORMS = {
        'youtube': {'format': '16:9', 'max_duration': 3600, 'min_duration': 10},
        'tiktok': {'format': '9:16', 'max_duration': 180, 'min_duration': 15},
        'instagram': {'format': '9:16', 'max_duration': 90, 'min_duration': 15},
        'twitter': {'format': '16:9', 'max_duration': 140, 'min_duration': 5},
    }

    def __init__(self, gemini_api_key: Optional[str] = None):
        """
        Initialize Chef AI

        Args:
            gemini_api_key: Gemini API key for prompt analysis
        """
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY', '')

        if not self.gemini_api_key:
            logger.warning("⚠️ Gemini API key not provided. Chef AI intelligence limited.")
            self.ai_enabled = False
        else:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.ai_enabled = True

        # Agent registry (will be populated by agent initialization)
        self.agents = {}

        logger.info("👨‍🍳 Chef AI initialized (CEO mode)")

    def register_agent(self, agent_type: str, agent_instance: Any):
        """
        Register specialized agent

        Args:
            agent_type: Agent type (video_producer, music_composer, etc.)
            agent_instance: Agent instance
        """
        self.agents[agent_type] = agent_instance
        logger.info(f"   ✅ Registered agent: {agent_type}")

    def execute_order(self, raw_prompt: str, user_id: str = "anonymous") -> Dict:
        """
        Main entry point: Analyze prompt and execute

        Args:
            raw_prompt: User's natural language request
            user_id: User identifier

        Returns:
            Execution result dict
        """
        try:
            logger.info(f"👨‍🍳 Chef AI received order: '{raw_prompt[:80]}...'")

            # Generate task ID
            task_id = self._generate_task_id()

            # Analyze prompt to understand intent
            logger.info("   🧠 Analyzing intent...")
            analysis = self._analyze_prompt(raw_prompt)

            if 'error' in analysis:
                return {
                    'task_id': task_id,
                    'status': 'failed',
                    'error': analysis['error']
                }

            # Create structured task
            task = {
                'task_id': task_id,
                'user_id': user_id,
                'raw_prompt': raw_prompt,
                'analysis': analysis,
                'created_at': datetime.now().isoformat(),
                'status': 'in_progress'
            }

            logger.info(f"   📋 Task classified: {analysis['task_type']}")
            logger.info(f"   🎯 Platform: {analysis.get('platform', 'N/A')}")

            # Delegate to appropriate agent(s)
            logger.info("   🎯 Delegating to agents...")
            result = self._delegate_task(task)

            # Update task status
            task['status'] = 'completed' if result.get('success') else 'failed'
            task['result'] = result
            task['completed_at'] = datetime.now().isoformat()

            logger.info(f"   ✅ Task {task_id} completed")
            return task

        except Exception as e:
            logger.error(f"   ❌ Chef AI execution failed: {e}")
            return {
                'task_id': task_id if 'task_id' in locals() else 'unknown',
                'status': 'failed',
                'error': str(e)
            }

    def _analyze_prompt(self, prompt: str) -> Dict:
        """
        Analyze raw prompt to extract intent and parameters

        Args:
            prompt: User's raw prompt

        Returns:
            Analysis dict with task_type, platform, parameters
        """
        if not self.ai_enabled:
            # Fallback: simple keyword matching
            return self._simple_intent_detection(prompt)

        try:
            # Use Gemini AI for intelligent analysis
            analysis_prompt = f"""
You are Chef AI, a strategic task analyzer for VIDEOCU v1 content creation system.

User's request: "{prompt}"

Analyze this request and respond with a JSON object containing:
{{
    "task_type": "video_creation|music_creation|social_media_management|multi_agent",
    "intent_description": "Brief description of what user wants",
    "platform": "youtube|tiktok|instagram|twitter|all|null",
    "parameters": {{
        "topic": "extracted topic",
        "duration": estimated_duration_seconds,
        "style": "informativ|unterhaltsam|dramatisch|humorvoll|viral|professional",
        "format": "16:9|9:16|1:1|null",
        "language": "de|en|tr",
        "requires_music": true|false,
        "requires_photos": true|false,
        "is_long_form": true|false
    }},
    "assigned_agents": ["video_producer", "social_media_manager", ...]
}}

Be intelligent and extract as much context as possible.
Respond ONLY with valid JSON, no additional text.
"""

            response = self.model.generate_content(analysis_prompt)
            response_text = response.text.strip()

            # Extract JSON (handle markdown code blocks)
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()

            analysis = json.loads(response_text)

            logger.info(f"   ✅ AI Analysis complete: {analysis['task_type']}")
            return analysis

        except Exception as e:
            logger.warning(f"   ⚠️ AI analysis failed: {e}. Using fallback.")
            return self._simple_intent_detection(prompt)

    def _simple_intent_detection(self, prompt: str) -> Dict:
        """
        Fallback: Simple keyword-based intent detection

        Args:
            prompt: User prompt

        Returns:
            Basic analysis dict
        """
        prompt_lower = prompt.lower()

        # Detect task type
        if any(word in prompt_lower for word in ['video', 'film', 'clip', 'reel', 'short']):
            task_type = self.TASK_VIDEO_CREATION
        elif any(word in prompt_lower for word in ['müzik', 'music', 'şarkı', 'song', 'beste', 'melody']):
            task_type = self.TASK_MUSIC_CREATION
        elif any(word in prompt_lower for word in ['yayınla', 'publish', 'upload', 'paylaş', 'share']):
            task_type = self.TASK_SOCIAL_MEDIA
        else:
            task_type = self.TASK_VIDEO_CREATION  # Default

        # Detect platform
        platform = None
        for p in ['youtube', 'tiktok', 'instagram', 'twitter']:
            if p in prompt_lower:
                platform = p
                break

        # Estimate duration
        duration = 60  # Default
        if 'reel' in prompt_lower or 'short' in prompt_lower:
            duration = 30
        elif 'tiktok' in prompt_lower:
            duration = 45
        elif 'long' in prompt_lower or 'uzun' in prompt_lower:
            duration = 300

        return {
            'task_type': task_type,
            'intent_description': f"Detected: {task_type}",
            'platform': platform,
            'parameters': {
                'topic': prompt[:100],
                'duration': duration,
                'style': 'informativ',
                'language': 'de'
            },
            'assigned_agents': self._get_default_agents(task_type)
        }

    def _get_default_agents(self, task_type: str) -> List[str]:
        """Get default agents for task type"""
        if task_type == self.TASK_VIDEO_CREATION:
            return ['video_producer']
        elif task_type == self.TASK_MUSIC_CREATION:
            return ['music_composer']
        elif task_type == self.TASK_SOCIAL_MEDIA:
            return ['social_media_manager']
        else:
            return ['video_producer', 'social_media_manager']

    def _delegate_task(self, task: Dict) -> Dict:
        """
        Delegate task to appropriate agent(s)

        Args:
            task: Task specification

        Returns:
            Aggregated result from agents
        """
        analysis = task['analysis']
        task_type = analysis['task_type']
        assigned_agents = analysis.get('assigned_agents', [])

        results = {}

        # Delegate to each assigned agent
        for agent_name in assigned_agents:
            if agent_name not in self.agents:
                logger.warning(f"   ⚠️ Agent '{agent_name}' not registered, skipping")
                continue

            logger.info(f"   → Delegating to {agent_name}...")
            agent = self.agents[agent_name]

            try:
                # Call agent's execute method
                if hasattr(agent, 'execute_task'):
                    result = agent.execute_task(task)
                    results[agent_name] = result
                else:
                    logger.warning(f"   ⚠️ Agent '{agent_name}' has no execute_task method")

            except Exception as e:
                logger.error(f"   ❌ Agent '{agent_name}' failed: {e}")
                results[agent_name] = {'success': False, 'error': str(e)}

        # Aggregate results
        all_success = all(r.get('success', False) for r in results.values())

        return {
            'success': all_success,
            'agent_results': results,
            'task_type': task_type
        }

    def _generate_task_id(self) -> str:
        """Generate unique task ID"""
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"

    def get_status(self) -> Dict:
        """Get Chef AI status"""
        return {
            'ai_enabled': self.ai_enabled,
            'registered_agents': list(self.agents.keys()),
            'supported_tasks': [
                self.TASK_VIDEO_CREATION,
                self.TASK_MUSIC_CREATION,
                self.TASK_SOCIAL_MEDIA,
                self.TASK_SERVER_ADMIN
            ]
        }


# Test
if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*70)
    print("👨‍🍳 CHEF AI TEST")
    print("="*70)

    chef = ChefAI()

    print(f"\nStatus: {chef.get_status()}")

    # Test prompt analysis
    test_prompts = [
        "Mars kolonizasyonu hakkında 60 saniyelik YouTube videosu yap",
        "Çok aranan şarkı sözlerinden 45 saniyelik viral TikTok videosu",
        "Mırıldandığım melodiden jazz tarzı bir beste yap"
    ]

    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n📝 TEST {i}: {prompt}")
        result = chef.execute_order(prompt)
        print(f"   Task ID: {result['task_id']}")
        print(f"   Status: {result['status']}")
        if 'analysis' in result:
            print(f"   Type: {result['analysis']['task_type']}")
            print(f"   Platform: {result['analysis'].get('platform', 'N/A')}")

    print("\n" + "="*70)
    print("✅ CHEF AI TEST COMPLETE")
    print("="*70)
