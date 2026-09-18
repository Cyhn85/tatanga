"""
VIDEOCU v1 - Skill Library
Modular capability catalog for AI agents

Purpose:
- Agents register their skills
- Chef AI queries available capabilities
- Expandable skill system
"""

import logging
from typing import Dict, List, Optional, Callable, Any
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillLibrary:
    """
    Centralized skill catalog for all agents

    Skills are organized by category:
    - video_production: create_reel, add_subtitles, etc.
    - music_creation: extract_melody, arrange_jazz, etc.
    - social_media: optimize_seo, schedule_post, etc.
    """

    def __init__(self, library_path: Optional[str] = None):
        """
        Initialize skill library

        Args:
            library_path: Optional path to load/save skill definitions
        """
        self.library_path = library_path or "output/skill_library.json"
        self.skills = {}  # {category: {skill_name: skill_def}}

        # Load existing skills if available
        self._load_skills()

        logger.info("📚 Skill Library initialized")

    def register_skill(self,
                      category: str,
                      skill_name: str,
                      description: str,
                      parameters: Dict,
                      implementation: Optional[Callable] = None) -> bool:
        """
        Register new skill

        Args:
            category: Skill category (video_production, music_creation, etc.)
            skill_name: Unique skill identifier
            description: Human-readable description
            parameters: Required parameters dict
            implementation: Optional callable implementation

        Returns:
            True if registered successfully
        """
        try:
            if category not in self.skills:
                self.skills[category] = {}

            skill_def = {
                'name': skill_name,
                'description': description,
                'parameters': parameters,
                'category': category,
                'has_implementation': implementation is not None
            }

            if implementation:
                skill_def['_implementation'] = implementation  # Non-serializable

            self.skills[category][skill_name] = skill_def

            logger.info(f"   ✅ Registered skill: {category}.{skill_name}")
            return True

        except Exception as e:
            logger.error(f"   ❌ Skill registration failed: {e}")
            return False

    def get_skill(self, category: str, skill_name: str) -> Optional[Dict]:
        """Get skill definition"""
        return self.skills.get(category, {}).get(skill_name)

    def list_skills(self, category: Optional[str] = None) -> Dict:
        """
        List available skills

        Args:
            category: Optional category filter

        Returns:
            Skills dict
        """
        if category:
            return {category: self.skills.get(category, {})}
        return self.skills

    def query_skills_by_keyword(self, keyword: str) -> List[Dict]:
        """
        Search skills by keyword

        Args:
            keyword: Search term

        Returns:
            List of matching skills
        """
        results = []
        keyword_lower = keyword.lower()

        for category, skills in self.skills.items():
            for skill_name, skill_def in skills.items():
                if (keyword_lower in skill_name.lower() or
                    keyword_lower in skill_def['description'].lower() or
                    keyword_lower in category.lower()):
                    results.append({
                        'category': category,
                        'skill': skill_name,
                        'description': skill_def['description']
                    })

        return results

    def execute_skill(self,
                     category: str,
                     skill_name: str,
                     parameters: Dict) -> Optional[Any]:
        """
        Execute skill if implementation available

        Args:
            category: Skill category
            skill_name: Skill name
            parameters: Execution parameters

        Returns:
            Execution result or None
        """
        skill = self.get_skill(category, skill_name)

        if not skill:
            logger.warning(f"⚠️ Skill not found: {category}.{skill_name}")
            return None

        if '_implementation' not in skill:
            logger.warning(f"⚠️ No implementation for: {category}.{skill_name}")
            return None

        try:
            implementation = skill['_implementation']
            result = implementation(**parameters)
            logger.info(f"✅ Executed skill: {category}.{skill_name}")
            return result

        except Exception as e:
            logger.error(f"❌ Skill execution failed: {e}")
            return None

    def _load_skills(self):
        """Load skills from disk"""
        try:
            library_file = Path(self.library_path)

            if library_file.exists():
                with open(library_file, 'r', encoding='utf-8') as f:
                    self.skills = json.load(f)
                logger.info(f"   ✅ Loaded {self._count_skills()} skills from disk")

        except Exception as e:
            logger.warning(f"   ⚠️ Failed to load skills: {e}")

    def save_skills(self) -> bool:
        """Save skills to disk"""
        try:
            library_file = Path(self.library_path)
            library_file.parent.mkdir(parents=True, exist_ok=True)

            # Create serializable version (without implementations)
            serializable_skills = {}
            for category, skills in self.skills.items():
                serializable_skills[category] = {}
                for skill_name, skill_def in skills.items():
                    # Copy without _implementation
                    clean_def = {k: v for k, v in skill_def.items()
                               if not k.startswith('_')}
                    serializable_skills[category][skill_name] = clean_def

            with open(library_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_skills, f, indent=2, ensure_ascii=False)

            logger.info(f"   ✅ Saved {self._count_skills()} skills to disk")
            return True

        except Exception as e:
            logger.error(f"   ❌ Failed to save skills: {e}")
            return False

    def _count_skills(self) -> int:
        """Count total skills"""
        return sum(len(skills) for skills in self.skills.values())

    def get_stats(self) -> Dict:
        """Get library statistics"""
        return {
            'total_skills': self._count_skills(),
            'categories': len(self.skills),
            'category_breakdown': {
                cat: len(skills) for cat, skills in self.skills.items()
            }
        }


# Initialize default skills
def initialize_default_skills(library: SkillLibrary):
    """
    Register default skills for VIDEOCU v1

    Args:
        library: SkillLibrary instance
    """

    # VIDEO PRODUCTION SKILLS
    library.register_skill(
        category="video_production",
        skill_name="create_standard_video",
        description="Create standard YouTube video (60s, 16:9)",
        parameters={
            'topic': 'string',
            'duration': 'int (seconds)',
            'language': 'string (de/en/tr)'
        }
    )

    library.register_skill(
        category="video_production",
        skill_name="create_short_video",
        description="Create short-form video (TikTok/Reels, 9:16)",
        parameters={
            'topic': 'string',
            'duration': 'int (15-90s)',
            'platform': 'string (tiktok/instagram)'
        }
    )

    library.register_skill(
        category="video_production",
        skill_name="create_long_form_video",
        description="Create long-form video with segmentation (15+ min)",
        parameters={
            'topic': 'string',
            'target_duration': 'int (seconds)',
            'language': 'string'
        }
    )

    library.register_skill(
        category="video_production",
        skill_name="create_photo_video",
        description="Create video from user photos with Ken Burns effects",
        parameters={
            'photo_paths': 'list[string]',
            'title': 'string',
            'duration_per_photo': 'float'
        }
    )

    # MUSIC CREATION SKILLS
    library.register_skill(
        category="music_creation",
        skill_name="extract_melody_from_voice",
        description="Extract MIDI from hummed/sung melody",
        parameters={
            'audio_file': 'string (path)',
            'output_midi': 'string (path)'
        }
    )

    library.register_skill(
        category="music_creation",
        skill_name="arrange_music",
        description="Arrange MIDI into full music (jazz/pop/club/classical)",
        parameters={
            'midi_file': 'string (path)',
            'style': 'string (jazz/pop/club/classical)',
            'output_audio': 'string (path)'
        }
    )

    # SOCIAL MEDIA SKILLS
    library.register_skill(
        category="social_media",
        skill_name="optimize_seo",
        description="Generate SEO-optimized title, description, tags",
        parameters={
            'content_topic': 'string',
            'platform': 'string (youtube/tiktok/instagram)',
            'language': 'string'
        }
    )

    library.register_skill(
        category="social_media",
        skill_name="publish_to_platform",
        description="Publish content to social media platform",
        parameters={
            'content_path': 'string',
            'platform': 'string',
            'metadata': 'dict (title, description, tags)'
        }
    )

    logger.info(f"✅ Initialized {library._count_skills()} default skills")


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
    print("📚 SKILL LIBRARY TEST")
    print("="*70)

    library = SkillLibrary()

    # Initialize default skills
    print("\n📝 Initializing default skills...")
    initialize_default_skills(library)

    # Show stats
    print(f"\n📊 Library Stats:")
    stats = library.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Query skills
    print(f"\n🔍 Video Production Skills:")
    video_skills = library.list_skills("video_production")
    for skill_name, skill_def in video_skills.get("video_production", {}).items():
        print(f"   • {skill_name}: {skill_def['description']}")

    # Search
    print(f"\n🔎 Search 'short':")
    results = library.query_skills_by_keyword("short")
    for result in results:
        print(f"   • {result['category']}.{result['skill']}: {result['description']}")

    # Save
    print(f"\n💾 Saving skills...")
    library.save_skills()

    print("\n" + "="*70)
    print("✅ SKILL LIBRARY TEST COMPLETE")
    print("="*70)
