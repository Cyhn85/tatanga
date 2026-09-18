"""
VIDEOCU v1 - Telegram Bot Test
Test bot initialization and basic functionality
"""

import sys
import logging
import os

# UTF-8 encoding for Windows
if sys.platform == 'win32':
    import locale
    if locale.getpreferredencoding() != 'UTF-8':
        sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

print("\n" + "="*70)
print("🤖 TELEGRAM BOT TEST")
print("="*70)

# Test 1: Import modules
print("\n📦 TEST 1: Importing modules...")
try:
    from telegram_bot import VideocuBot
    from modules.chef_ai import ChefAI
    from modules.skill_library import SkillLibrary
    from modules.agent_memory import AgentMemory
    print("   ✅ All imports successful")
except ImportError as e:
    print(f"   ❌ Import failed: {e}")
    print("\n   💡 Install missing dependency:")
    print("      pip install python-telegram-bot")
    sys.exit(1)

# Test 2: Initialize Chef AI system
print("\n🧪 TEST 2: Initializing Chef AI system...")
try:
    chef_ai = ChefAI(gemini_api_key="test_key")
    skill_library = SkillLibrary()
    agent_memory = AgentMemory()
    print("   ✅ Chef AI system initialized")
except Exception as e:
    print(f"   ❌ Initialization failed: {e}")
    sys.exit(1)

# Test 3: Check skill library
print("\n🧪 TEST 3: Checking skill library...")
try:
    from modules.skill_library import initialize_default_skills
    initialize_default_skills(skill_library)

    stats = skill_library.get_stats()
    print(f"   ✅ Skill Library loaded:")
    print(f"      • Total skills: {stats['total_skills']}")
    print(f"      • Categories: {stats['categories']}")
    for category, count in stats['category_breakdown'].items():
        print(f"        - {category}: {count} skills")
except Exception as e:
    print(f"   ❌ Skill library test failed: {e}")
    sys.exit(1)

# Test 4: Check agent memory
print("\n🧪 TEST 4: Checking agent memory...")
try:
    memory_stats = agent_memory.get_stats()
    print(f"   ✅ Agent Memory initialized:")
    print(f"      • Total tasks: {memory_stats['total_tasks']}")
    print(f"      • Completed: {memory_stats['completed_tasks']}")
    print(f"      • Metrics: {memory_stats['total_metrics']}")
except Exception as e:
    print(f"   ❌ Agent memory test failed: {e}")
    sys.exit(1)

# Test 5: Check Chef AI status
print("\n🧪 TEST 5: Checking Chef AI status...")
try:
    status = chef_ai.get_status()
    print(f"   ✅ Chef AI status:")
    print(f"      • AI enabled: {status['ai_enabled']}")
    print(f"      • Registered agents: {len(status['registered_agents'])}")
    print(f"      • Supported tasks: {len(status['supported_tasks'])}")
except Exception as e:
    print(f"   ❌ Status check failed: {e}")
    sys.exit(1)

# Test 6: Test prompt analysis (fallback mode)
print("\n🧪 TEST 6: Testing prompt analysis (fallback mode)...")
try:
    test_prompts = [
        "60 saniyelik Mars hakkında YouTube videosu yap",
        "TikTok için viral video oluştur",
        "Mırıldandığım melodiden müzik yap"
    ]

    for i, prompt in enumerate(test_prompts, 1):
        result = chef_ai.execute_order(prompt, user_id="test_user")
        print(f"   ✅ Test {i}: {result['analysis']['task_type']}")
        print(f"      Platform: {result['analysis'].get('platform', 'N/A')}")

except Exception as e:
    print(f"   ❌ Prompt analysis failed: {e}")
    sys.exit(1)

# Test 7: Check environment variables
print("\n🧪 TEST 7: Checking environment variables...")
env_vars = {
    'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
    'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY'),
    'PEXELS_API_KEY': os.getenv('PEXELS_API_KEY')
}

for var_name, var_value in env_vars.items():
    if var_value:
        masked_value = '*' * 10 + var_value[-4:] if len(var_value) > 4 else '****'
        print(f"   ✅ {var_name}: {masked_value}")
    else:
        print(f"   ⚠️ {var_name}: Not set")

# Summary
print("\n" + "="*70)
print("✅ TELEGRAM BOT TEST COMPLETE")
print("="*70)
print("\n📝 Next steps:")
print("   1. Set TELEGRAM_BOT_TOKEN in .env file")
print("   2. Run: python telegram_bot.py")
print("   3. Open Telegram and search for your bot")
print("   4. Send /start command")
print("\n💡 To create a Telegram bot:")
print("   1. Open Telegram and search for @BotFather")
print("   2. Send /newbot command")
print("   3. Follow instructions to get your bot token")
print("   4. Add token to .env file")
print("\n" + "="*70 + "\n")
