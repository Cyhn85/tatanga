"""
VIDEOCU v1 - Self-Improvement Engine
Autonomous learning system that analyzes performance data and improves Chef AI

This is the "brain" that learns from successes and failures, automatically
updating Chef AI's prompts and strategies for better content creation.

Phase 5 Core Component
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class SelfImprovementEngine:
    """
    Autonomous learning engine that continuously improves the system

    Learning Loop:
    1. Analyze performance metrics (from Performance Logger)
    2. Identify successful patterns and best practices
    3. Generate improved prompt templates
    4. Update Chef AI's master prompts
    5. Monitor results and iterate
    """

    def __init__(self, chef_ai, metrics_analyzer, agent_memory):
        """
        Initialize Self-Improvement Engine

        Args:
            chef_ai: ChefAI instance to update
            metrics_analyzer: MetricsAnalyzer for performance insights
            agent_memory: AgentMemory for historical data
        """
        self.chef_ai = chef_ai
        self.metrics_analyzer = metrics_analyzer
        self.agent_memory = agent_memory

        # Improvement tracking
        self.improvements_made = []
        self.learning_history = []

        # Configuration
        self.learning_rate = 0.3  # How aggressively to adopt new patterns (0-1)
        self.min_sample_size = 5  # Minimum videos before learning from pattern
        self.confidence_threshold = 0.7  # Minimum confidence for auto-updates

        # Paths
        self.prompts_dir = Path("modules/prompts")
        self.prompts_dir.mkdir(exist_ok=True)

        self.backup_dir = Path("output/prompt_backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info("🧠 Self-Improvement Engine initialized")
        logger.info(f"   Learning rate: {self.learning_rate}")
        logger.info(f"   Min sample size: {self.min_sample_size}")
        logger.info(f"   Confidence threshold: {self.confidence_threshold}")

    def run_learning_cycle(self, platforms: List[str] = None) -> Dict:
        """
        Execute one complete learning cycle

        Steps:
        1. Analyze performance across platforms
        2. Identify improvement opportunities
        3. Generate updated prompts
        4. Apply improvements (if confidence threshold met)
        5. Record learning history

        Args:
            platforms: List of platforms to analyze (None = all)

        Returns:
            Learning cycle results
        """
        logger.info("🧠 Starting learning cycle...")

        if platforms is None:
            platforms = ['youtube', 'tiktok', 'instagram']

        cycle_results = {
            'timestamp': datetime.now().isoformat(),
            'platforms_analyzed': platforms,
            'patterns_discovered': [],
            'improvements_applied': [],
            'recommendations_generated': [],
            'status': 'in_progress'
        }

        try:
            # Step 1: Analyze performance
            logger.info("   Step 1: Analyzing performance data...")
            performance_analysis = self._analyze_all_platforms(platforms)
            cycle_results['performance_analysis'] = performance_analysis

            # Step 2: Identify improvement opportunities
            logger.info("   Step 2: Identifying improvement opportunities...")
            opportunities = self._identify_opportunities(performance_analysis)
            cycle_results['opportunities'] = opportunities

            # Step 3: Generate improvements
            logger.info("   Step 3: Generating improvements...")
            improvements = self._generate_improvements(opportunities)
            cycle_results['improvements_generated'] = improvements

            # Step 4: Apply improvements (if confidence sufficient)
            logger.info("   Step 4: Applying high-confidence improvements...")
            applied = self._apply_improvements(improvements)
            cycle_results['improvements_applied'] = applied

            # Step 5: Record learning
            logger.info("   Step 5: Recording learning history...")
            self._record_learning_cycle(cycle_results)

            cycle_results['status'] = 'completed'

            logger.info(f"✅ Learning cycle complete:")
            logger.info(f"   Patterns discovered: {len(opportunities)}")
            logger.info(f"   Improvements generated: {len(improvements)}")
            logger.info(f"   Improvements applied: {len(applied)}")

            return cycle_results

        except Exception as e:
            logger.error(f"❌ Learning cycle failed: {e}")
            cycle_results['status'] = 'failed'
            cycle_results['error'] = str(e)
            return cycle_results

    def _analyze_all_platforms(self, platforms: List[str]) -> Dict:
        """Analyze performance across all platforms"""
        analysis = {}

        for platform in platforms:
            platform_analysis = self.metrics_analyzer.analyze_platform_performance(
                platform, days=30
            )

            if platform_analysis['status'] == 'success':
                analysis[platform] = platform_analysis

                # Also get patterns for this platform
                patterns = self.metrics_analyzer.identify_content_patterns(
                    platform=platform,
                    min_views=1000
                )
                analysis[platform]['patterns'] = patterns

                # Get recommendations
                recommendations = self.metrics_analyzer.generate_recommendations(platform)
                analysis[platform]['recommendations'] = recommendations

        return analysis

    def _identify_opportunities(self, performance_analysis: Dict) -> List[Dict]:
        """
        Identify specific improvement opportunities from analysis

        Opportunities are patterns or recommendations that meet criteria:
        - High confidence (>= confidence_threshold)
        - Sufficient sample size (>= min_sample_size)
        - Significant performance boost (>10%)
        """
        opportunities = []

        for platform, analysis in performance_analysis.items():
            # From content patterns
            if 'patterns' in analysis:
                for pattern in analysis['patterns']:
                    if (pattern['confidence'] >= self.confidence_threshold and
                        pattern['sample_size'] >= self.min_sample_size and
                        pattern['performance_boost'] > 0.1):  # >10% boost

                        opportunities.append({
                            'type': 'content_pattern',
                            'platform': platform,
                            'pattern': pattern['common_params'],
                            'performance_boost': pattern['performance_boost'],
                            'confidence': pattern['confidence'],
                            'sample_size': pattern['sample_size'],
                            'priority': 'high' if pattern['performance_boost'] > 0.2 else 'medium'
                        })

            # From recommendations
            if 'recommendations' in analysis:
                for rec in analysis['recommendations']:
                    if rec['priority'] == 'high':
                        opportunities.append({
                            'type': 'recommendation',
                            'platform': platform,
                            'title': rec['title'],
                            'description': rec['description'],
                            'action': rec['action'],
                            'expected_impact': rec['expected_impact'],
                            'priority': rec['priority']
                        })

            # From trend analysis
            if 'trend' in analysis:
                trend = analysis['trend']
                if trend['direction'] == 'declining':
                    opportunities.append({
                        'type': 'trend_alert',
                        'platform': platform,
                        'issue': f"Performance declining by {abs(trend['change_percent']):.1f}%",
                        'action': 'Experiment with new content styles',
                        'priority': 'high'
                    })

        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        opportunities.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 2))

        return opportunities

    def _generate_improvements(self, opportunities: List[Dict]) -> List[Dict]:
        """
        Generate concrete improvements from opportunities

        Improvements are actionable changes to:
        - Chef AI master prompts
        - Default parameters
        - Content generation strategies
        """
        improvements = []

        for opp in opportunities:
            if opp['type'] == 'content_pattern':
                # Update default parameters based on successful pattern
                improvement = {
                    'type': 'parameter_update',
                    'platform': opp['platform'],
                    'changes': opp['pattern'],
                    'reason': f"Pattern shows +{opp['performance_boost']:.0%} performance",
                    'confidence': opp['confidence'],
                    'priority': opp['priority']
                }
                improvements.append(improvement)

                # Generate updated prompt template
                prompt_improvement = self._generate_prompt_update(opp)
                if prompt_improvement:
                    improvements.append(prompt_improvement)

            elif opp['type'] == 'trend_alert':
                # Suggest strategy change
                improvement = {
                    'type': 'strategy_change',
                    'platform': opp['platform'],
                    'issue': opp['issue'],
                    'suggestion': opp['action'],
                    'priority': opp['priority']
                }
                improvements.append(improvement)

            elif opp['type'] == 'recommendation':
                # Convert recommendation to actionable improvement
                improvement = {
                    'type': 'recommendation_action',
                    'platform': opp['platform'],
                    'action': opp['action'],
                    'expected_impact': opp['expected_impact'],
                    'priority': opp['priority']
                }
                improvements.append(improvement)

        return improvements

    def _generate_prompt_update(self, pattern_opportunity: Dict) -> Optional[Dict]:
        """
        Generate an updated prompt template based on successful pattern

        Args:
            pattern_opportunity: Opportunity dict with pattern details

        Returns:
            Prompt update improvement dict or None
        """
        pattern = pattern_opportunity['pattern']
        platform = pattern_opportunity['platform']

        # Build enhanced prompt based on successful parameters
        prompt_enhancements = []

        if 'duration' in pattern:
            duration = pattern['duration']
            prompt_enhancements.append(f"Duration: {duration} seconds (proven optimal)")

        if 'style' in pattern:
            style = pattern['style']
            prompt_enhancements.append(f"Style: {style} (high engagement)")

        if 'language' in pattern:
            language = pattern['language']
            prompt_enhancements.append(f"Language: {language} (target audience)")

        if not prompt_enhancements:
            return None

        return {
            'type': 'prompt_update',
            'platform': platform,
            'enhancements': prompt_enhancements,
            'pattern': pattern,
            'confidence': pattern_opportunity['confidence'],
            'priority': pattern_opportunity['priority']
        }

    def _apply_improvements(self, improvements: List[Dict]) -> List[Dict]:
        """
        Apply improvements that meet confidence threshold

        Only auto-applies improvements with high confidence.
        Others are logged for manual review.

        Args:
            improvements: List of improvement dicts

        Returns:
            List of applied improvements
        """
        applied = []

        for improvement in improvements:
            confidence = improvement.get('confidence', 0.5)

            # Auto-apply only high-confidence improvements
            if confidence >= self.confidence_threshold:
                try:
                    if improvement['type'] == 'parameter_update':
                        self._apply_parameter_update(improvement)
                        applied.append(improvement)
                        logger.info(f"   ✅ Applied: {improvement['type']} for {improvement['platform']}")

                    elif improvement['type'] == 'prompt_update':
                        self._apply_prompt_update(improvement)
                        applied.append(improvement)
                        logger.info(f"   ✅ Applied: {improvement['type']} for {improvement['platform']}")

                    # Strategy changes and recommendations are logged but not auto-applied
                    elif improvement['type'] in ['strategy_change', 'recommendation_action']:
                        logger.info(f"   📝 Logged: {improvement['type']} - {improvement.get('action', improvement.get('suggestion', 'N/A'))}")

                except Exception as e:
                    logger.error(f"   ❌ Failed to apply improvement: {e}")
            else:
                logger.info(f"   ⚠️ Low confidence ({confidence:.0%}), skipping auto-apply: {improvement['type']}")

        # Record applied improvements
        self.improvements_made.extend(applied)

        return applied

    def _apply_parameter_update(self, improvement: Dict):
        """Update Chef AI's default parameters"""
        platform = improvement['platform']
        changes = improvement['changes']

        # Store updated defaults (in production, this would update Chef AI config)
        defaults_file = self.prompts_dir / f"{platform}_defaults.json"

        # Load existing defaults or create new
        if defaults_file.exists():
            with open(defaults_file, 'r', encoding='utf-8') as f:
                defaults = json.load(f)
        else:
            defaults = {}

        # Update with new parameters
        defaults.update(changes)
        defaults['last_updated'] = datetime.now().isoformat()
        defaults['reason'] = improvement['reason']

        # Save updated defaults
        with open(defaults_file, 'w', encoding='utf-8') as f:
            json.dump(defaults, f, indent=2, ensure_ascii=False)

        logger.info(f"      Updated defaults for {platform}: {changes}")

    def _apply_prompt_update(self, improvement: Dict):
        """Update Chef AI's prompt templates"""
        platform = improvement['platform']
        enhancements = improvement['enhancements']

        # Create enhanced prompt template
        prompt_file = self.prompts_dir / f"{platform}_prompt_template.txt"

        # Backup existing prompt
        if prompt_file.exists():
            backup_file = self.backup_dir / f"{platform}_prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(prompt_file, 'r', encoding='utf-8') as f:
                with open(backup_file, 'w', encoding='utf-8') as bf:
                    bf.write(f.read())

        # Create new enhanced prompt
        enhanced_prompt = self._build_enhanced_prompt(platform, enhancements, improvement['pattern'])

        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(enhanced_prompt)

        logger.info(f"      Updated prompt template for {platform}")

    def _build_enhanced_prompt(self, platform: str, enhancements: List[str], pattern: Dict) -> str:
        """Build an enhanced prompt template"""
        prompt = f"""# {platform.upper()} Video Creation Prompt (Auto-Optimized)

## Successful Pattern Detected
{chr(10).join(f'- {enhancement}' for enhancement in enhancements)}

## Recommended Parameters
Duration: {pattern.get('duration', 60)} seconds
Style: {pattern.get('style', 'informative')}
Language: {pattern.get('language', 'de')}

## Instructions
Create engaging video content following the proven successful pattern above.
Focus on {pattern.get('style', 'informative')} delivery in {pattern.get('language', 'de')} language.

This template was automatically generated by the Self-Improvement Engine based on
performance analysis of {pattern.get('sample_size', 'multiple')} successful videos.

Last updated: {datetime.now().isoformat()}
"""
        return prompt

    def _record_learning_cycle(self, cycle_results: Dict):
        """Record learning cycle in history"""
        self.learning_history.append(cycle_results)

        # Also save to file for persistence
        history_file = self.backup_dir / "learning_history.json"

        if history_file.exists():
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []

        history.append(cycle_results)

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    def get_improvement_stats(self) -> Dict:
        """Get statistics about improvements made"""
        return {
            'total_cycles': len(self.learning_history),
            'total_improvements': len(self.improvements_made),
            'last_cycle': self.learning_history[-1] if self.learning_history else None,
            'improvement_by_type': self._count_by_type(self.improvements_made),
            'improvement_by_platform': self._count_by_platform(self.improvements_made)
        }

    def _count_by_type(self, improvements: List[Dict]) -> Dict:
        """Count improvements by type"""
        counts = {}
        for imp in improvements:
            imp_type = imp.get('type', 'unknown')
            counts[imp_type] = counts.get(imp_type, 0) + 1
        return counts

    def _count_by_platform(self, improvements: List[Dict]) -> Dict:
        """Count improvements by platform"""
        counts = {}
        for imp in improvements:
            platform = imp.get('platform', 'unknown')
            counts[platform] = counts.get(platform, 0) + 1
        return counts

    def get_current_configuration(self, platform: str = None) -> Dict:
        """
        Get current learned configuration

        Args:
            platform: Specific platform or None for all

        Returns:
            Current defaults and prompts
        """
        if platform:
            platforms = [platform]
        else:
            platforms = ['youtube', 'tiktok', 'instagram']

        config = {}

        for plt in platforms:
            defaults_file = self.prompts_dir / f"{plt}_defaults.json"
            prompt_file = self.prompts_dir / f"{plt}_prompt_template.txt"

            plt_config = {}

            if defaults_file.exists():
                with open(defaults_file, 'r', encoding='utf-8') as f:
                    plt_config['defaults'] = json.load(f)

            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    plt_config['prompt_template'] = f.read()

            config[plt] = plt_config

        return config

    def manual_override(self, platform: str, parameter: str, value: any):
        """
        Manually override a learned parameter

        Args:
            platform: Target platform
            parameter: Parameter name
            value: New value
        """
        defaults_file = self.prompts_dir / f"{platform}_defaults.json"

        if defaults_file.exists():
            with open(defaults_file, 'r', encoding='utf-8') as f:
                defaults = json.load(f)
        else:
            defaults = {}

        defaults[parameter] = value
        defaults['last_manual_override'] = datetime.now().isoformat()

        with open(defaults_file, 'w', encoding='utf-8') as f:
            json.dump(defaults, f, indent=2, ensure_ascii=False)

        logger.info(f"✏️ Manual override: {platform}.{parameter} = {value}")


if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*70)
    print("🧠 SELF-IMPROVEMENT ENGINE")
    print("="*70)
    print("\nThis module enables autonomous learning from performance data.")
    print("\nUsage:")
    print("  engine = SelfImprovementEngine(chef_ai, metrics_analyzer, agent_memory)")
    print("  results = engine.run_learning_cycle()")
    print("\n" + "="*70 + "\n")
