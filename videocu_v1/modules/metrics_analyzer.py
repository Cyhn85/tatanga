"""
VIDEOCU v1 - Metrics Analyzer
Analyzes performance data to identify successful patterns and generate insights

Features:
- Trend analysis (views, CTR, engagement)
- Content pattern recognition
- Best practices identification
- Performance prediction
- Anomaly detection
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


class MetricsAnalyzer:
    """Analyzes performance metrics to generate actionable insights"""

    def __init__(self, agent_memory):
        """
        Initialize Metrics Analyzer

        Args:
            agent_memory: AgentMemory instance for data access
        """
        self.agent_memory = agent_memory
        logger.info("📊 Metrics Analyzer initialized")

    def analyze_platform_performance(self, platform: str, days: int = 30) -> Dict:
        """
        Analyze overall performance for a specific platform

        Args:
            platform: Platform name (youtube, tiktok, instagram)
            days: Number of days to analyze

        Returns:
            Performance analysis dictionary
        """
        logger.info(f"   Analyzing {platform} performance (last {days} days)")

        # Get metrics from agent memory
        metrics = self._get_recent_metrics(platform, days)

        if not metrics:
            logger.warning(f"   ⚠️ No metrics found for {platform}")
            return {
                'platform': platform,
                'status': 'no_data',
                'message': f'No metrics available for {platform}'
            }

        # Calculate aggregate statistics
        total_views = sum(m['views'] for m in metrics)
        avg_views = statistics.mean(m['views'] for m in metrics)
        median_views = statistics.median(m['views'] for m in metrics)

        avg_ctr = statistics.mean(m.get('ctr', 0) for m in metrics)
        avg_engagement = statistics.mean(m.get('engagement_rate', 0) for m in metrics)

        # Identify trends
        trend = self._calculate_trend(metrics, 'views')

        # Best and worst performing content
        best_video = max(metrics, key=lambda x: x['views'])
        worst_video = min(metrics, key=lambda x: x['views'])

        analysis = {
            'platform': platform,
            'period_days': days,
            'total_videos': len(metrics),
            'aggregate_stats': {
                'total_views': total_views,
                'avg_views': round(avg_views, 2),
                'median_views': median_views,
                'avg_ctr': round(avg_ctr, 2),
                'avg_engagement_rate': round(avg_engagement, 2)
            },
            'trend': trend,
            'best_performing': {
                'task_id': best_video['task_id'],
                'views': best_video['views'],
                'ctr': best_video.get('ctr', 0),
                'engagement_rate': best_video.get('engagement_rate', 0)
            },
            'worst_performing': {
                'task_id': worst_video['task_id'],
                'views': worst_video['views']
            },
            'status': 'success'
        }

        logger.info(f"   ✅ Analysis complete: {len(metrics)} videos, {total_views:,} total views")

        return analysis

    def identify_content_patterns(self, platform: str = None, min_views: int = 1000) -> List[Dict]:
        """
        Identify successful content patterns across tasks

        Args:
            platform: Optional platform filter
            min_views: Minimum views threshold for "successful" content

        Returns:
            List of identified patterns
        """
        logger.info(f"   Identifying content patterns (min_views={min_views})")

        # Get high-performing tasks
        high_performers = self._get_high_performing_tasks(platform, min_views)

        if not high_performers:
            logger.warning("   ⚠️ No high-performing tasks found")
            return []

        # Group by common parameters
        patterns = self._extract_patterns(high_performers)

        logger.info(f"   ✅ Found {len(patterns)} content patterns")

        return patterns

    def predict_performance(self, task_parameters: Dict) -> Dict:
        """
        Predict performance for a task based on historical data

        Args:
            task_parameters: Task parameters (topic, duration, platform, etc.)

        Returns:
            Performance prediction
        """
        logger.info(f"   Predicting performance for: {task_parameters.get('topic', 'Unknown')}")

        platform = task_parameters.get('platform', 'youtube')
        duration = task_parameters.get('duration', 60)

        # Find similar past tasks
        similar_tasks = self._find_similar_tasks(task_parameters)

        if not similar_tasks:
            logger.warning("   ⚠️ No similar tasks found, using platform averages")
            return self._predict_from_platform_average(platform)

        # Calculate prediction from similar tasks
        avg_views = statistics.mean(t['views'] for t in similar_tasks)
        avg_ctr = statistics.mean(t.get('ctr', 0) for t in similar_tasks)
        avg_engagement = statistics.mean(t.get('engagement_rate', 0) for t in similar_tasks)

        # Confidence based on sample size
        confidence = min(len(similar_tasks) / 10, 1.0)  # Max confidence at 10+ similar tasks

        prediction = {
            'predicted_views': round(avg_views),
            'predicted_ctr': round(avg_ctr, 2),
            'predicted_engagement_rate': round(avg_engagement, 2),
            'confidence': round(confidence, 2),
            'similar_tasks_count': len(similar_tasks),
            'status': 'success'
        }

        logger.info(f"   ✅ Prediction: {prediction['predicted_views']:,} views (confidence: {confidence:.0%})")

        return prediction

    def generate_recommendations(self, platform: str = None) -> List[Dict]:
        """
        Generate actionable recommendations based on analysis

        Args:
            platform: Optional platform filter

        Returns:
            List of recommendations
        """
        logger.info(f"   Generating recommendations for: {platform or 'all platforms'}")

        recommendations = []

        # Analyze content patterns
        patterns = self.identify_content_patterns(platform)

        for pattern in patterns[:5]:  # Top 5 patterns
            recommendations.append({
                'type': 'content_pattern',
                'priority': 'high',
                'title': f"High-performing pattern identified",
                'description': f"Videos with {pattern['common_params']} achieved {pattern['avg_views']:,} avg views",
                'action': f"Create more content with similar parameters",
                'expected_impact': f"+{pattern['performance_boost']:.0%} views"
            })

        # Identify underperforming areas
        if platform:
            analysis = self.analyze_platform_performance(platform)

            if analysis['status'] == 'success':
                trend = analysis['trend']

                if trend['direction'] == 'declining':
                    recommendations.append({
                        'type': 'trend_alert',
                        'priority': 'high',
                        'title': 'Performance declining',
                        'description': f"{platform} views declining by {abs(trend['change_percent']):.1f}% recently",
                        'action': 'Experiment with new content styles or topics',
                        'expected_impact': 'Stabilize or reverse trend'
                    })

        # Best practices from top performers
        best_practices = self.agent_memory.query_best_practices(
            task_type='video_creation',
            platform=platform
        )

        for practice in best_practices[:3]:
            recommendations.append({
                'type': 'best_practice',
                'priority': 'medium',
                'title': 'Proven successful approach',
                'description': f"Parameters: {practice['parameters']}",
                'action': f"Apply these settings to future videos",
                'expected_impact': f"Avg {practice['avg_views']:,} views based on {practice['sample_size']} videos"
            })

        logger.info(f"   ✅ Generated {len(recommendations)} recommendations")

        return recommendations

    def detect_anomalies(self, platform: str = None, threshold: float = 2.0) -> List[Dict]:
        """
        Detect anomalous performance (outliers)

        Args:
            platform: Optional platform filter
            threshold: Standard deviations from mean to consider anomaly

        Returns:
            List of anomalies
        """
        logger.info(f"   Detecting anomalies (threshold={threshold} std dev)")

        metrics = self._get_recent_metrics(platform, days=30)

        if len(metrics) < 5:
            logger.warning("   ⚠️ Not enough data for anomaly detection")
            return []

        # Calculate statistics
        views = [m['views'] for m in metrics]
        mean_views = statistics.mean(views)
        std_dev = statistics.stdev(views) if len(views) > 1 else 0

        if std_dev == 0:
            logger.warning("   ⚠️ No variance in data")
            return []

        # Identify outliers
        anomalies = []

        for metric in metrics:
            z_score = (metric['views'] - mean_views) / std_dev

            if abs(z_score) >= threshold:
                anomaly_type = 'exceptional' if z_score > 0 else 'underperforming'

                anomalies.append({
                    'task_id': metric['task_id'],
                    'platform': metric.get('platform', 'unknown'),
                    'views': metric['views'],
                    'z_score': round(z_score, 2),
                    'type': anomaly_type,
                    'deviation_percent': round(((metric['views'] - mean_views) / mean_views) * 100, 1),
                    'collected_at': metric.get('collected_at', 'unknown')
                })

        anomalies.sort(key=lambda x: abs(x['z_score']), reverse=True)

        logger.info(f"   ✅ Found {len(anomalies)} anomalies")

        return anomalies

    def get_performance_summary(self, days: int = 30) -> Dict:
        """
        Get comprehensive performance summary

        Args:
            days: Number of days to analyze

        Returns:
            Performance summary across all platforms
        """
        logger.info(f"   Generating performance summary (last {days} days)")

        platforms = ['youtube', 'tiktok', 'instagram']
        summary = {
            'period_days': days,
            'generated_at': datetime.now().isoformat(),
            'platforms': {},
            'overall': {
                'total_videos': 0,
                'total_views': 0,
                'avg_engagement': 0
            }
        }

        total_videos = 0
        total_views = 0
        engagement_rates = []

        for platform in platforms:
            analysis = self.analyze_platform_performance(platform, days)

            if analysis['status'] == 'success':
                summary['platforms'][platform] = analysis

                total_videos += analysis['total_videos']
                total_views += analysis['aggregate_stats']['total_views']
                engagement_rates.append(analysis['aggregate_stats']['avg_engagement_rate'])

        summary['overall']['total_videos'] = total_videos
        summary['overall']['total_views'] = total_views
        summary['overall']['avg_engagement'] = round(
            statistics.mean(engagement_rates) if engagement_rates else 0,
            2
        )

        logger.info(f"   ✅ Summary: {total_videos} videos, {total_views:,} total views")

        return summary

    # ========== Helper Methods ==========

    def _get_recent_metrics(self, platform: Optional[str], days: int) -> List[Dict]:
        """Get metrics from recent tasks"""
        # Query agent memory for recent metrics
        cutoff_date = datetime.now() - timedelta(days=days)

        cursor = self.agent_memory.conn.cursor()

        if platform:
            query = """
                SELECT m.task_id, m.platform, m.views, m.likes, m.ctr,
                       m.engagement_rate, m.collected_at
                FROM metrics m
                JOIN tasks t ON m.task_id = t.task_id
                WHERE m.platform = ? AND datetime(m.collected_at) >= datetime(?)
                ORDER BY m.collected_at DESC
            """
            cursor.execute(query, (platform, cutoff_date.isoformat()))
        else:
            query = """
                SELECT m.task_id, m.platform, m.views, m.likes, m.ctr,
                       m.engagement_rate, m.collected_at
                FROM metrics m
                JOIN tasks t ON m.task_id = t.task_id
                WHERE datetime(m.collected_at) >= datetime(?)
                ORDER BY m.collected_at DESC
            """
            cursor.execute(query, (cutoff_date.isoformat(),))

        rows = cursor.fetchall()

        metrics = []
        for row in rows:
            metrics.append({
                'task_id': row[0],
                'platform': row[1],
                'views': row[2],
                'likes': row[3],
                'ctr': row[4],
                'engagement_rate': row[5],
                'collected_at': row[6]
            })

        return metrics

    def _calculate_trend(self, metrics: List[Dict], field: str) -> Dict:
        """Calculate trend direction and magnitude"""
        if len(metrics) < 2:
            return {'direction': 'stable', 'change_percent': 0}

        # Sort by date
        sorted_metrics = sorted(metrics, key=lambda x: x.get('collected_at', ''))

        # Split into two halves
        mid = len(sorted_metrics) // 2
        first_half = sorted_metrics[:mid]
        second_half = sorted_metrics[mid:]

        avg_first = statistics.mean(m[field] for m in first_half)
        avg_second = statistics.mean(m[field] for m in second_half)

        if avg_first == 0:
            change_percent = 0
        else:
            change_percent = ((avg_second - avg_first) / avg_first) * 100

        if change_percent > 5:
            direction = 'improving'
        elif change_percent < -5:
            direction = 'declining'
        else:
            direction = 'stable'

        return {
            'direction': direction,
            'change_percent': round(change_percent, 2),
            'first_half_avg': round(avg_first, 2),
            'second_half_avg': round(avg_second, 2)
        }

    def _get_high_performing_tasks(self, platform: Optional[str], min_views: int) -> List[Dict]:
        """Get tasks that exceeded view threshold"""
        cursor = self.agent_memory.conn.cursor()

        if platform:
            query = """
                SELECT t.task_id, t.parameters, m.views, m.ctr, m.engagement_rate, m.platform
                FROM tasks t
                JOIN metrics m ON t.task_id = m.task_id
                WHERE m.platform = ? AND m.views >= ?
            """
            cursor.execute(query, (platform, min_views))
        else:
            query = """
                SELECT t.task_id, t.parameters, m.views, m.ctr, m.engagement_rate, m.platform
                FROM tasks t
                JOIN metrics m ON t.task_id = m.task_id
                WHERE m.views >= ?
            """
            cursor.execute(query, (min_views,))

        rows = cursor.fetchall()

        tasks = []
        for row in rows:
            import json
            tasks.append({
                'task_id': row[0],
                'parameters': json.loads(row[1]) if row[1] else {},
                'views': row[2],
                'ctr': row[3],
                'engagement_rate': row[4],
                'platform': row[5]
            })

        return tasks

    def _extract_patterns(self, tasks: List[Dict]) -> List[Dict]:
        """Extract common patterns from successful tasks"""
        # Group tasks by common parameter combinations
        patterns = defaultdict(list)

        for task in tasks:
            params = task['parameters']

            # Create pattern key from important parameters
            pattern_key = (
                params.get('duration', 'unknown'),
                params.get('style', 'unknown'),
                params.get('language', 'unknown')
            )

            patterns[pattern_key].append(task)

        # Calculate statistics for each pattern
        result = []

        for pattern_key, pattern_tasks in patterns.items():
            if len(pattern_tasks) >= 2:  # At least 2 examples
                avg_views = statistics.mean(t['views'] for t in pattern_tasks)

                # Compare to overall average
                all_views = [t['views'] for t in tasks]
                overall_avg = statistics.mean(all_views)

                performance_boost = (avg_views - overall_avg) / overall_avg if overall_avg > 0 else 0

                result.append({
                    'common_params': {
                        'duration': pattern_key[0],
                        'style': pattern_key[1],
                        'language': pattern_key[2]
                    },
                    'sample_size': len(pattern_tasks),
                    'avg_views': round(avg_views),
                    'performance_boost': performance_boost,
                    'confidence': min(len(pattern_tasks) / 5, 1.0)
                })

        # Sort by performance boost
        result.sort(key=lambda x: x['performance_boost'], reverse=True)

        return result

    def _find_similar_tasks(self, task_parameters: Dict) -> List[Dict]:
        """Find tasks with similar parameters"""
        platform = task_parameters.get('platform', 'youtube')
        duration = task_parameters.get('duration', 60)

        # Get all tasks for platform
        cursor = self.agent_memory.conn.cursor()
        query = """
            SELECT t.task_id, t.parameters, m.views, m.ctr, m.engagement_rate
            FROM tasks t
            JOIN metrics m ON t.task_id = m.task_id
            WHERE m.platform = ?
        """
        cursor.execute(query, (platform,))
        rows = cursor.fetchall()

        similar = []
        import json

        for row in rows:
            params = json.loads(row[1]) if row[1] else {}

            # Check similarity (duration within 20 seconds)
            if abs(params.get('duration', 60) - duration) <= 20:
                similar.append({
                    'task_id': row[0],
                    'views': row[2],
                    'ctr': row[3],
                    'engagement_rate': row[4]
                })

        return similar

    def _predict_from_platform_average(self, platform: str) -> Dict:
        """Fallback prediction using platform averages"""
        analysis = self.analyze_platform_performance(platform, days=90)

        if analysis['status'] == 'success':
            return {
                'predicted_views': round(analysis['aggregate_stats']['avg_views']),
                'predicted_ctr': analysis['aggregate_stats']['avg_ctr'],
                'predicted_engagement_rate': analysis['aggregate_stats']['avg_engagement_rate'],
                'confidence': 0.3,  # Low confidence for generic prediction
                'similar_tasks_count': 0,
                'status': 'platform_average'
            }

        return {
            'predicted_views': 0,
            'predicted_ctr': 0,
            'predicted_engagement_rate': 0,
            'confidence': 0,
            'similar_tasks_count': 0,
            'status': 'no_data'
        }


if __name__ == "__main__":
    import sys

    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(level=logging.INFO)

    # Test with mock agent memory
    from agent_memory import AgentMemory

    print("\n" + "="*70)
    print("🧪 METRICS ANALYZER TEST")
    print("="*70)

    memory = AgentMemory()
    analyzer = MetricsAnalyzer(memory)

    print("\n✅ Metrics Analyzer initialized successfully")
    print("\nNote: Full functionality requires task and metrics data in agent_memory.db")
    print("="*70 + "\n")
