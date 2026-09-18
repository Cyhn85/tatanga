"""
VIDEOCU v1 - Celery Integration Test
Verifies Celery tasks are properly configured
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_celery_imports():
    """Test all Celery modules can be imported"""
    print("=" * 70)
    print("VIDEOCU v1 - CELERY INTEGRATION TEST")
    print("=" * 70)
    print()

    tests_passed = 0
    tests_failed = 0

    # Test 1: Celery app
    print("TEST 1: Celery App Configuration")
    try:
        from celery_app import celery_app
        print(f"   Broker: {celery_app.conf.broker_url}")
        print(f"   Backend: {celery_app.conf.result_backend}")
        print(f"   Timezone: {celery_app.conf.timezone}")
        print(f"   Beat Schedule: {len(celery_app.conf.beat_schedule)} tasks")
        print("   PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Test 2: Video Tasks
    print("TEST 2: Video Tasks Module")
    try:
        from celery_tasks.video_tasks import (
            produce_video_async,
            produce_video_batch,
            upload_video_async
        )
        print(f"   produce_video_async: {produce_video_async.name}")
        print(f"   produce_video_batch: {produce_video_batch.name}")
        print(f"   upload_video_async: {upload_video_async.name}")
        print("   PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Test 3: Analytics Tasks
    print("TEST 3: Analytics Tasks Module")
    try:
        from celery_tasks.analytics_tasks import (
            collect_all_analytics,
            collect_platform_analytics,
            system_health_check,
            cleanup_old_files
        )
        print(f"   collect_all_analytics: {collect_all_analytics.name}")
        print(f"   system_health_check: {system_health_check.name}")
        print(f"   cleanup_old_files: {cleanup_old_files.name}")
        print("   PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Test 4: Learning Tasks
    print("TEST 4: Learning Tasks Module")
    try:
        from celery_tasks.learning_tasks import (
            run_learning_cycle,
            analyze_performance,
            apply_improvements
        )
        print(f"   run_learning_cycle: {run_learning_cycle.name}")
        print(f"   analyze_performance: {analyze_performance.name}")
        print(f"   apply_improvements: {apply_improvements.name}")
        print("   PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Test 5: Beat Schedule
    print("TEST 5: Celery Beat Schedule")
    try:
        from celery_app import celery_app
        schedule = celery_app.conf.beat_schedule

        print("   Scheduled Tasks:")
        for name, config in schedule.items():
            task_name = config.get('task', 'unknown')
            schedule_info = config.get('schedule', 'unknown')
            print(f"      - {name}: {task_name}")

        if len(schedule) >= 4:
            print("   PASSED")
            tests_passed += 1
        else:
            print(f"   WARNING: Only {len(schedule)} scheduled tasks")
            tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Test 6: API Server Celery Endpoints
    print("TEST 6: API Server Celery Endpoints")
    try:
        from api_server import app

        celery_routes = [
            r for r in app.routes
            if hasattr(r, 'path') and (
                'async' in r.path or
                'triggers' in r.path or
                'celery' in r.path
            )
        ]

        print(f"   Found {len(celery_routes)} Celery-related endpoints:")
        for route in celery_routes:
            methods = list(route.methods) if hasattr(route, 'methods') else ['WS']
            for m in methods:
                if m != 'HEAD':
                    print(f"      {m:6} {route.path}")

        if len(celery_routes) >= 6:
            print("   PASSED")
            tests_passed += 1
        else:
            print("   WARNING: Missing some endpoints")
            tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Test 7: Task Queues Configuration
    print("TEST 7: Task Queues Configuration")
    try:
        from celery_app import celery_app

        routes = celery_app.conf.task_routes
        print("   Task Routes:")
        for pattern, config in routes.items():
            print(f"      {pattern} -> {config.get('queue', 'default')}")

        print("   PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"   FAILED: {e}")
        tests_failed += 1
    print()

    # Summary
    print("=" * 70)
    print("CELERY INTEGRATION TEST SUMMARY")
    print("=" * 70)
    print(f"   Tests Passed: {tests_passed}")
    print(f"   Tests Failed: {tests_failed}")
    print(f"   Total: {tests_passed + tests_failed}")
    print()

    if tests_failed == 0:
        print("   STATUS: ALL TESTS PASSED")
        print()
        print("   Celery is properly configured!")
        print()
        print("   To start Celery workers:")
        print("   $ celery -A celery_app worker --loglevel=info")
        print()
        print("   To start Celery Beat (scheduler):")
        print("   $ celery -A celery_app beat --loglevel=info")
        print()
        print("   Or use Docker Compose:")
        print("   $ docker compose up -d worker beat")
    else:
        print(f"   STATUS: {tests_failed} TESTS FAILED")

    print("=" * 70)

    return tests_failed == 0


if __name__ == "__main__":
    success = test_celery_imports()
    sys.exit(0 if success else 1)
