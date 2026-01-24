#!/usr/bin/env python3
"""
Test script for Discord Bot <-> Eventos API Bridge
Run this to verify the integration is working correctly
"""

import sys
import time
from api_bridge import EventosAPIBridge

def print_separator():
    print("=" * 60)

def test_health_check(bridge):
    """Test 1: Health Check"""
    print("\n🏥 TEST 1: Health Check")
    print_separator()
    
    is_healthy = bridge.health_check()
    
    if is_healthy:
        print("✅ API is reachable and responding")
        return True
    else:
        print("❌ Cannot connect to API")
        print("   Make sure the backend is running:")
        print("   cd eventos-app/backend")
        print("   python -m uvicorn api.main:app --host 0.0.0.0 --port 7000")
        return False

def test_attack(bridge):
    """Test 2: Process Attack"""
    print("\n⚔️  TEST 2: Process Attack")
    print_separator()
    
    test_user = "test_user_123"
    attack_text = "I strike the enemy with a powerful lightning bolt!"
    
    print(f"User: {test_user}")
    print(f"Attack: {attack_text}")
    print()
    
    result = bridge.process_free_attack(test_user, attack_text)
    
    if result:
        print("✅ Attack processed successfully!")
        print(f"   Total Damage: {result.get('damage', 0)}")
        print(f"   Base Damage: {result.get('base_damage', 0)}")
        print(f"   Combo Multiplier: {result.get('combo_multiplier', 1.0)}x")
        print(f"   Combo Count: {result.get('combo_count', 0)}")
        print(f"   Quality Bonus: +{result.get('quality_bonus', 0)}")
        print(f"   Action Type: {result.get('action', 'unknown')}")
        print(f"   NLP Confidence: {result.get('nlp_confidence', 0):.2f}")
        return True
    else:
        print("❌ Attack failed")
        return False

def test_combo_system(bridge):
    """Test 3: Combo System"""
    print("\n🔥 TEST 3: Combo System (3 consecutive attacks)")
    print_separator()
    
    test_user = "combo_test_user"
    attacks = [
        "I slash with my sword!",
        "I follow up with a spin attack!",
        "I finish with an uppercut!"
    ]
    
    results = []
    for i, attack in enumerate(attacks, 1):
        print(f"\nAttack {i}: {attack}")
        result = bridge.process_free_attack(test_user, attack)
        
        if result:
            combo = result.get('combo_multiplier', 1.0)
            damage = result.get('damage', 0)
            print(f"   Damage: {damage} (x{combo} multiplier)")
            results.append(result)
        else:
            print(f"   ❌ Failed")
            return False
        
        time.sleep(0.5)  # Small delay between attacks
    
    if len(results) == 3:
        print("\n✅ Combo system working!")
        print(f"   Attack 1 multiplier: {results[0].get('combo_multiplier', 1.0)}x")
        print(f"   Attack 2 multiplier: {results[1].get('combo_multiplier', 1.0)}x")
        print(f"   Attack 3 multiplier: {results[2].get('combo_multiplier', 1.0)}x")
        return True
    
    return False

def test_boss_creation(bridge):
    """Test 4: Boss Creation"""
    print("\n👹 TEST 4: Boss Creation")
    print_separator()
    
    boss_name = "Test Dragon"
    boss_hp = 1000
    
    print(f"Creating boss: {boss_name} ({boss_hp} HP)")
    result = bridge.create_boss(boss_name, boss_hp)
    
    if result and result.get("success"):
        print("✅ Boss created successfully!")
        boss = result.get("boss", {})
        print(f"   Name: {boss.get('name', 'N/A')}")
        print(f"   HP: {boss.get('hp_current', 0)}/{boss.get('hp_max', 0)}")
        return True
    else:
        print("❌ Boss creation failed")
        return False

def test_player_stats(bridge):
    """Test 5: Player Stats"""
    print("\n📊 TEST 5: Player Stats")
    print_separator()
    
    test_user = "test_user_123"
    print(f"Fetching stats for: {test_user}")
    
    stats = bridge.get_player_stats(test_user)
    
    if stats:
        print("✅ Stats retrieved!")
        print(f"   Total Attempts: {stats.get('total_attempts', 0)}")
        print(f"   Successful: {stats.get('successful', 0)}")
        print(f"   Failed: {stats.get('failed', 0)}")
        print(f"   Best Time: {stats.get('best_time', 'N/A')}")
        print(f"   Black Flashes: {stats.get('black_flashes', 0)}")
        return True
    else:
        print("❌ Failed to get stats")
        return False

def main():
    print("\n" + "=" * 60)
    print("🧪 Discord Bot API Bridge Integration Test")
    print("=" * 60)
    
    # Initialize bridge
    print("\n🔌 Initializing API Bridge...")
    bridge = EventosAPIBridge("http://localhost:7000")
    
    # Run tests
    tests = [
        ("Health Check", lambda: test_health_check(bridge)),
        ("Attack Processing", lambda: test_attack(bridge)),
        ("Combo System", lambda: test_combo_system(bridge)),
        ("Boss Creation", lambda: test_boss_creation(bridge)),
        ("Player Stats", lambda: test_player_stats(bridge)),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ ERROR in {test_name}: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Integration is working correctly.")
        print("\n📝 Next steps:")
        print("   1. Update your Discord bot's .env file with EVENTOS_API_URL")
        print("   2. Add API bridge initialization to your bot")
        print("   3. Update NLP attack handler to use the API")
        print("   4. See DISCORD_API_INTEGRATION.md for details")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
