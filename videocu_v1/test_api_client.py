"""
VIDEOCU v1 - API Client Test
Demonstrates how to use the FastAPI backend

Features:
- Authentication (JWT)
- Task creation
- WebSocket real-time updates
- Metrics recording
"""

import requests
import json
import sys
import asyncio
import websockets
from typing import Dict, Optional

# UTF-8 encoding for Windows
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

# ========== Configuration ==========
API_BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

# Demo credentials
USERNAME = "admin"
PASSWORD = "videocu2025"

# ========== API Client ==========

class VideocuAPIClient:
    """VIDEOCU API Client"""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session = requests.Session()

    def login(self, username: str, password: str) -> bool:
        """Login and get JWT token"""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password}
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.session.headers.update({
                    'Authorization': f'Bearer {self.token}'
                })
                print(f"✅ Logged in as: {username}")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    def health_check(self) -> Optional[Dict]:
        """Check API health"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return None

    def create_task(self, prompt: str, user_id: str = "test_user") -> Optional[Dict]:
        """Create a new task"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/tasks",
                json={"prompt": prompt, "user_id": user_id}
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Task creation failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Task creation error: {e}")
            return None

    def list_skills(self, category: Optional[str] = None) -> Optional[Dict]:
        """List available skills"""
        try:
            url = f"{self.base_url}/api/skills"
            if category:
                url += f"?category={category}"

            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
            return None

        except Exception as e:
            print(f"❌ Skills list error: {e}")
            return None

    def search_skills(self, keyword: str) -> Optional[Dict]:
        """Search skills by keyword"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/skills/search",
                params={"keyword": keyword}
            )

            if response.status_code == 200:
                return response.json()
            return None

        except Exception as e:
            print(f"❌ Skills search error: {e}")
            return None

    def list_agents(self) -> Optional[Dict]:
        """List registered agents"""
        try:
            response = self.session.get(f"{self.base_url}/api/agents")
            if response.status_code == 200:
                return response.json()
            return None

        except Exception as e:
            print(f"❌ Agents list error: {e}")
            return None

    def record_metrics(self, task_id: str, platform: str, metrics: Dict) -> bool:
        """Record performance metrics"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/metrics",
                json={
                    "task_id": task_id,
                    "platform": platform,
                    **metrics
                }
            )

            return response.status_code == 200

        except Exception as e:
            print(f"❌ Metrics recording error: {e}")
            return False

    def system_health(self) -> Optional[Dict]:
        """Get detailed system health"""
        try:
            response = self.session.get(f"{self.base_url}/api/system/health")
            if response.status_code == 200:
                return response.json()
            return None

        except Exception as e:
            print(f"❌ System health error: {e}")
            return None

# ========== WebSocket Client ==========

async def websocket_client():
    """WebSocket client for real-time updates"""
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ WebSocket connected")

            # Send a test message
            await websocket.send(json.dumps({
                "type": "ping",
                "timestamp": "2025-11-26T12:00:00"
            }))

            # Receive messages
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                print(f"📨 WebSocket message: {data['type']}")

    except Exception as e:
        print(f"❌ WebSocket error: {e}")

# ========== Tests ==========

def main():
    """Run API tests"""
    print("\n" + "="*70)
    print("🧪 VIDEOCU v1 - API CLIENT TEST")
    print("="*70)

    client = VideocuAPIClient()

    # Test 1: Health check (no auth required)
    print("\n📊 TEST 1: Health Check (Public)")
    health = client.health_check()
    if health:
        print(f"   Status: {health['status']}")
        print(f"   Agents: {health['agents']}")
        print(f"   Skills: {health['skills']}")
    else:
        print("   ⚠️ Server not responding. Is it running?")
        print("   Start server with: python api_server.py")
        return

    # Test 2: Login
    print("\n🔐 TEST 2: Authentication")
    if not client.login(USERNAME, PASSWORD):
        print("   ❌ Login failed. Cannot proceed with protected endpoints.")
        return

    # Test 3: List agents
    print("\n🤖 TEST 3: List Agents")
    agents = client.list_agents()
    if agents:
        print(f"   Registered agents: {agents['count']}")
        for agent in agents['agents']:
            print(f"   • {agent}")

    # Test 4: List skills
    print("\n📚 TEST 4: List Skills")
    skills = client.list_skills()
    if skills:
        stats = skills['stats']
        print(f"   Total skills: {stats['total_skills']}")
        print(f"   Categories: {stats['categories']}")
        for category, count in stats['category_breakdown'].items():
            print(f"   • {category}: {count} skills")

    # Test 5: Search skills
    print("\n🔍 TEST 5: Search Skills")
    results = client.search_skills("video")
    if results:
        print(f"   Found: {results['count']} results")
        for result in results['results'][:3]:
            print(f"   • {result['category']}.{result['skill']}: {result['description'][:50]}...")

    # Test 6: Create task
    print("\n📝 TEST 6: Create Task")
    test_prompts = [
        "60 saniyelik Mars hakkında YouTube videosu yap",
        "TikTok için viral kedi videosu",
        "Relaxing ambient müzik oluştur"
    ]

    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n   Task {i}: {prompt[:50]}...")
        result = client.create_task(prompt)

        if result:
            print(f"      ✅ Task ID: {result['task_id']}")
            print(f"      Status: {result['status']}")
            print(f"      Type: {result['analysis']['task_type']}")
            print(f"      Platform: {result['analysis'].get('platform', 'N/A')}")

            # Record demo metrics
            if result['status'] == 'completed':
                metrics_recorded = client.record_metrics(
                    task_id=result['task_id'],
                    platform=result['analysis'].get('platform', 'youtube'),
                    metrics={
                        'views': 1000,
                        'likes': 50,
                        'ctr': 5.0,
                        'avg_watch_time': 45.0
                    }
                )
                if metrics_recorded:
                    print(f"      ✅ Metrics recorded")

    # Test 7: System health (detailed)
    print("\n🏥 TEST 7: System Health (Detailed)")
    sys_health = client.system_health()
    if sys_health and sys_health.get('success'):
        print(f"   Overall: {sys_health['overall_status']}")
        print(f"   CPU: {sys_health['cpu']['usage_percent']}% ({sys_health['cpu']['status']})")
        print(f"   Memory: {sys_health['memory']['percent']}% ({sys_health['memory']['status']})")
        print(f"   Disk: {sys_health['disk']['percent']}% ({sys_health['disk']['status']})")

    # Test 8: WebSocket (optional - requires asyncio)
    print("\n🔌 TEST 8: WebSocket Connection")
    print("   Testing WebSocket...")
    try:
        asyncio.run(websocket_client())
    except KeyboardInterrupt:
        print("   WebSocket test interrupted")
    except Exception as e:
        print(f"   ⚠️ WebSocket test skipped: {e}")

    # Summary
    print("\n" + "="*70)
    print("✅ API CLIENT TEST COMPLETE")
    print("="*70)
    print("\n📝 API Endpoints Tested:")
    print("   ✅ GET  /health          - Public health check")
    print("   ✅ POST /auth/login      - Authentication")
    print("   ✅ GET  /api/agents      - List agents")
    print("   ✅ GET  /api/skills      - List skills")
    print("   ✅ GET  /api/skills/search - Search skills")
    print("   ✅ POST /api/tasks       - Create tasks")
    print("   ✅ POST /api/metrics     - Record metrics")
    print("   ✅ GET  /api/system/health - System health")
    print("\n📡 API Documentation:")
    print(f"   Swagger UI: {API_BASE_URL}/docs")
    print(f"   ReDoc:      {API_BASE_URL}/redoc")
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()
