"""
VIDEOCU v1 - API Monitor Module
YouTube API quota tracking, alerts, and monitoring
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)


class APIMonitor:
    """YouTube API quota monitoring and tracking"""

    # YouTube Data API v3 Costs (per operation)
    QUOTA_COSTS = {
        'videos.list': 1,           # Get video details
        'search.list': 100,         # Search videos
        'channels.list': 1,         # Get channel details
        'videoCategories.list': 1,  # Get categories
        'playlistItems.list': 1,    # Get playlist items
    }

    DAILY_QUOTA_LIMIT = 10000  # Free tier limit
    WARNING_THRESHOLD = 8000   # 80% usage warning
    CRITICAL_THRESHOLD = 9500  # 95% usage critical

    def __init__(self, db_path: str = "api_usage.json"):
        self.db_path = db_path
        self.usage_data = self._load_usage_data()
        self._check_reset()

    def _load_usage_data(self) -> Dict:
        """Load usage data from JSON file"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load usage data: {e}")
                return self._create_default_data()
        return self._create_default_data()

    def _create_default_data(self) -> Dict:
        """Create default usage data structure"""
        return {
            'daily_usage': {},
            'total_usage': 0,
            'last_reset': datetime.now().strftime('%Y-%m-%d'),
            'operations': []
        }

    def _save_usage_data(self):
        """Save usage data to JSON file"""
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.usage_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save usage data: {e}")

    def _check_reset(self):
        """Check if daily quota should be reset (Pacific Time midnight)"""
        today = datetime.now().strftime('%Y-%m-%d')
        last_reset = self.usage_data.get('last_reset', '')

        if today != last_reset:
            logger.info(f"📅 Daily quota reset: {last_reset} → {today}")
            self.usage_data['daily_usage'] = {}
            self.usage_data['last_reset'] = today
            self._save_usage_data()

    def track_operation(self, operation: str, count: int = 1) -> Dict:
        """
        Track an API operation and update quota usage

        Args:
            operation: Operation name (e.g., 'videos.list', 'search.list')
            count: Number of times the operation was called

        Returns:
            Status dict with usage info and warnings
        """
        today = datetime.now().strftime('%Y-%m-%d')

        # Get quota cost for this operation
        cost_per_call = self.QUOTA_COSTS.get(operation, 1)
        total_cost = cost_per_call * count

        # Update daily usage
        if today not in self.usage_data['daily_usage']:
            self.usage_data['daily_usage'][today] = 0

        self.usage_data['daily_usage'][today] += total_cost
        self.usage_data['total_usage'] += total_cost

        # Log operation
        self.usage_data['operations'].append({
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'count': count,
            'cost': total_cost
        })

        # Keep only last 100 operations
        if len(self.usage_data['operations']) > 100:
            self.usage_data['operations'] = self.usage_data['operations'][-100:]

        self._save_usage_data()

        # Get current status
        current_usage = self.usage_data['daily_usage'][today]
        remaining = self.DAILY_QUOTA_LIMIT - current_usage
        percentage = (current_usage / self.DAILY_QUOTA_LIMIT) * 100

        # Determine status
        status = 'ok'
        message = ''

        if current_usage >= self.CRITICAL_THRESHOLD:
            status = 'critical'
            message = f'🚨 CRITICAL: {percentage:.1f}% quota used! Only {remaining} units remaining!'
            logger.critical(message)
        elif current_usage >= self.WARNING_THRESHOLD:
            status = 'warning'
            message = f'⚠️ WARNING: {percentage:.1f}% quota used. {remaining} units remaining.'
            logger.warning(message)
        else:
            status = 'ok'
            message = f'✅ OK: {percentage:.1f}% quota used. {remaining} units remaining.'
            logger.info(message)

        return {
            'status': status,
            'message': message,
            'current_usage': current_usage,
            'daily_limit': self.DAILY_QUOTA_LIMIT,
            'remaining': remaining,
            'percentage': percentage,
            'operation': operation,
            'cost': total_cost
        }

    def get_daily_usage(self, date: Optional[str] = None) -> int:
        """
        Get quota usage for a specific date

        Args:
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Quota units used
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        return self.usage_data['daily_usage'].get(date, 0)

    def get_usage_report(self) -> Dict:
        """
        Get comprehensive usage report

        Returns:
            Usage statistics and recommendations
        """
        today = datetime.now().strftime('%Y-%m-%d')
        current_usage = self.get_daily_usage(today)
        remaining = self.DAILY_QUOTA_LIMIT - current_usage
        percentage = (current_usage / self.DAILY_QUOTA_LIMIT) * 100

        # Calculate average daily usage (last 7 days)
        last_7_days = []
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            usage = self.usage_data['daily_usage'].get(date, 0)
            if usage > 0:
                last_7_days.append(usage)

        avg_daily_usage = sum(last_7_days) / len(last_7_days) if last_7_days else 0

        # Recommendations
        recommendations = []
        if percentage >= 80:
            recommendations.append("⚠️ Reduce API calls for today")
            recommendations.append("💡 Use cached data when possible")
            recommendations.append("💡 Batch multiple requests together")

        if avg_daily_usage > 8000:
            recommendations.append("⚠️ Consider upgrading to paid tier")
            recommendations.append("💡 Implement more aggressive caching")

        # Recent operations
        recent_ops = self.usage_data['operations'][-10:]

        return {
            'today': {
                'date': today,
                'usage': current_usage,
                'limit': self.DAILY_QUOTA_LIMIT,
                'remaining': remaining,
                'percentage': percentage
            },
            'statistics': {
                'total_lifetime_usage': self.usage_data['total_usage'],
                'avg_daily_usage_7d': int(avg_daily_usage),
                'days_tracked': len([d for d in self.usage_data['daily_usage'].values() if d > 0])
            },
            'recent_operations': recent_ops,
            'recommendations': recommendations
        }

    def can_make_request(self, operation: str, count: int = 1) -> bool:
        """
        Check if there's enough quota for a request

        Args:
            operation: Operation name
            count: Number of calls

        Returns:
            True if request is safe, False if quota would be exceeded
        """
        today = datetime.now().strftime('%Y-%m-%d')
        current_usage = self.get_daily_usage(today)

        cost_per_call = self.QUOTA_COSTS.get(operation, 1)
        total_cost = cost_per_call * count

        would_be_usage = current_usage + total_cost

        # Leave some buffer (don't use 100%)
        return would_be_usage <= (self.DAILY_QUOTA_LIMIT - 100)

    def reset_daily_usage(self):
        """Manually reset daily usage (for testing)"""
        today = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"🔄 Manually resetting daily usage for {today}")

        self.usage_data['daily_usage'][today] = 0
        self._save_usage_data()


# Test
if __name__ == "__main__":
    import sys

    # Set UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(level=logging.INFO)

    monitor = APIMonitor()

    print("\n" + "="*60)
    print("API USAGE MONITOR TEST")
    print("="*60)

    # Simulate some API calls
    print("\n1. Simulating videos.list call...")
    result = monitor.track_operation('videos.list', count=10)
    print(f"   {result['message']}")

    print("\n2. Simulating search.list call...")
    result = monitor.track_operation('search.list', count=5)
    print(f"   {result['message']}")

    print("\n3. Getting usage report...")
    report = monitor.get_usage_report()
    print(f"\n   📊 Today's Usage: {report['today']['usage']:,} / {report['today']['limit']:,}")
    print(f"   📈 Percentage: {report['today']['percentage']:.1f}%")
    print(f"   ⏳ Remaining: {report['today']['remaining']:,}")
    print(f"   📅 7-day Average: {report['statistics']['avg_daily_usage_7d']:,}")

    if report['recommendations']:
        print(f"\n   💡 Recommendations:")
        for rec in report['recommendations']:
            print(f"      {rec}")

    print("\n4. Recent Operations:")
    for op in report['recent_operations'][-5:]:
        print(f"   - {op['operation']} (cost: {op['cost']}) at {op['timestamp'][:19]}")

    print("\n5. Checking if we can make more requests...")
    can_search = monitor.can_make_request('search.list', count=80)
    print(f"   Can make 80 search calls? {'✅ Yes' if can_search else '❌ No (would exceed quota)'}")
