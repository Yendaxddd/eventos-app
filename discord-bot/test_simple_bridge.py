#!/usr/bin/env python3
"""
Test the simplified Discord bot <-> Eventos App integration
No campaigns, no WebSocket - just pure damage calculation
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simple_api_bridge import SimpleEventosAPI
import time

def test_api_connection():
    """Test basic API connectivity"""
    print("=" * 60)
    print("Testing Simple API Bridge")
    print("=" * 60)
    
    # Initialize API connection
    api = SimpleEventosAPI("http://localhost:7001")
    
    # Test health check
    print("\n1. Testing health check...")
    if api.health_check():
        print("   ✓ API is healthy and responding")
    else:
        print("   ✗ API is not responding - make sure backend is running!")
        print("   Start with: cd eventos-app/backend && python api/main.py")
        return False
    
    return True

def test_damage_calculation():
    """Test damage calculation"""
    print("\n2. Testing damage calculation...")
    
    api = SimpleEventosAPI("http://localhost:7001")
    
    # Test attacks with different quality levels
    test_cases = [
        ("123456", "I slash with my sword"),
        ("123456", "I UNLEASH A DEVASTATING THUNDER STRIKE THAT SHAKES THE HEAVENS!"),
        ("123456", "punch"),
        ("789012", "I cast a powerful fireball spell that engulfs the enemy"),
    ]
    
    print("\n   Attack Tests:")
    print("   " + "-" * 56)
    
    for user_id, attack_text in test_cases:
        result = api.calculate_attack_damage(user_id, attack_text)
        
        if result:
            print(f"\n   User: {user_id}")
            print(f"   Attack: {attack_text[:40]}{'...' if len(attack_text) > 40 else ''}")
            print(f"   → Damage: {result['damage']}")
            print(f"   → Combo: x{result['combo_multiplier']} (count: {result['combo_count']})")
            print(f"   → Quality Bonus: +{result['quality_bonus']}")
            print(f"   → Action Type: {result['action']}")
        else:
            print(f"   ✗ Failed to calculate damage for: {attack_text}")
    
    print("\n   " + "-" * 56)

def main():
    """Run all tests"""
    print("\n🎮 Simple API Bridge Test Suite\n")
    
    # Test connection
    if not test_api_connection():
        return
    
    # Give API a moment
    time.sleep(0.5)
    
    # Test damage calculation
    test_damage_calculation()
    
    print("\n" + "=" * 60)
    print("✓ All tests completed!")
    print("\nNext steps:")
    print("1. Import SimpleEventosAPI in your Discord bot")
    print("2. Use calculate_attack_damage() when processing NLP attacks")
    print("3. The corrected damage formula is now being used!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
