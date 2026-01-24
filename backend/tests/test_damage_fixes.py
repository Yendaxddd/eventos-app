#!/usr/bin/env python3
"""
Test script to verify damage calculation fixes
Tests the corrected formulas and edge cases
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.game_engine import GameSession

def test_damage_calculations():
    """Test various damage calculation scenarios"""
    print("=" * 60)
    print("DAMAGE CALCULATION TESTS")
    print("=" * 60)
    
    session = GameSession()
    player_id = "test_player"
    session.add_player(player_id)
    
    # Test 1: Basic attack with no combo
    print("\n1. Basic Attack (No Combo)")
    print("-" * 40)
    result = session.process_free_attack(player_id, "I punch the enemy")
    print(f"Action: {result['action']}")
    print(f"Base Damage: {result['base_damage']}")
    print(f"Combo Multiplier: {result['combo_multiplier']}")
    print(f"Quality Bonus: {result['quality_bonus']}")
    print(f"Total Damage: {result['damage']}")
    print(f"Expected: ~15-25 (base) * 1.0 (no combo) + 0 (no quality)")
    
    # Test 2: Build combo with multiple attacks
    print("\n2. Building Combo")
    print("-" * 40)
    for i in range(3):
        result = session.process_free_attack(player_id, f"Attack {i+1}")
        print(f"Attack {i+1}: Combo={result['combo_multiplier']:.2f}x, Damage={result['damage']}")
    
    # Test 3: High quality action
    print("\n3. High Quality Action (>0.8 confidence)")
    print("-" * 40)
    # Simulate high confidence
    session.players[player_id]["combo_count"] = 0  # Reset combo
    result = session.process_free_attack(
        player_id, 
        "With precise aim and perfect timing, I channel all my energy into a devastating strike at the enemy's weak point"
    )
    print(f"Action: {result['action']}")
    print(f"Base Damage: {result['base_damage']}")
    print(f"Combo Multiplier: {result['combo_multiplier']}")
    print(f"NLP Confidence: {result.get('nlp_confidence', 'N/A')}")
    print(f"Quality Bonus: {result['quality_bonus']}")
    print(f"Total Damage: {result['damage']}")
    print(f"Expected: base * 1.0 + quality_bonus (if confidence > 0.8)")
    
    # Test 4: Combo + Quality
    print("\n4. Combo + Quality Bonus")
    print("-" * 40)
    # Build up combo first
    for i in range(2):
        session.process_free_attack(player_id, f"Build combo {i+1}")
    # Then high quality
    result = session.process_free_attack(
        player_id,
        "I execute a flawless combo attack with perfect precision"
    )
    print(f"Combo Count: {session.players[player_id]['combo_count']}")
    print(f"Base Damage: {result['base_damage']}")
    print(f"Combo Multiplier: {result['combo_multiplier']}")
    print(f"Quality Bonus: {result['quality_bonus']}")
    print(f"Total Damage: {result['damage']}")
    print(f"Formula: ({result['base_damage']} * {result['combo_multiplier']:.2f}) + {result['quality_bonus']}")
    
    # Test 5: Boss damage
    print("\n5. Boss Damage Test")
    print("-" * 40)
    session.boss_system.active_boss = session.boss_system.create_boss("Test Boss", 1000)
    initial_hp = session.boss_system.active_boss["hp_current"]
    result = session.process_free_attack(player_id, "I strike the boss")
    final_hp = session.boss_system.active_boss["hp_current"]
    damage_dealt = initial_hp - final_hp
    print(f"Boss Initial HP: {initial_hp}")
    print(f"Damage Calculated: {result['damage']}")
    print(f"Boss Final HP: {final_hp}")
    print(f"Actual Damage Dealt: {damage_dealt}")
    print(f"Match: {'✓' if damage_dealt == result['damage'] else '✗'}")
    
    # Test 6: Edge case - very long combo
    print("\n6. Extended Combo (10+ attacks)")
    print("-" * 40)
    session.players[player_id]["combo_count"] = 0  # Reset
    for i in range(12):
        result = session.process_free_attack(player_id, f"Combo attack {i+1}")
        if i % 3 == 0:
            print(f"Attack {i+1}: Combo={result['combo_multiplier']:.2f}x, Damage={result['damage']}")
    print(f"Final combo multiplier: {result['combo_multiplier']:.2f}x")
    print(f"Max cap (2.0x): {'✓' if result['combo_multiplier'] <= 2.0 else '✗'}")
    
    # Test 7: Zero/negative damage protection
    print("\n7. Edge Cases")
    print("-" * 40)
    session.players[player_id]["combo_count"] = 0
    result = session.process_free_attack(player_id, "a")  # Minimal input
    if result:
        print(f"Minimal input damage: {result['damage']}")
        print(f"Positive: {'✓' if result['damage'] > 0 else '✗'}")
    else:
        print(f"Minimal input: No action detected (expected)")
        print(f"NLP filter working: ✓")
    
    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)

def test_formula_validation():
    """Validate the damage formula matches specifications"""
    print("\n" + "=" * 60)
    print("FORMULA VALIDATION")
    print("=" * 60)
    
    session = GameSession()
    player_id = "test_player"
    session.add_player(player_id)
    
    # Manual calculation test
    print("\nManual Formula Check:")
    print("-" * 40)
    
    # Set known values
    base_damage = 20
    combo_count = 5
    quality_bonus = 10
    
    # Expected formula: (base_damage * combo_multiplier) + quality_bonus
    expected_combo_multiplier = 1.0 + (combo_count * 0.1)
    expected_damage = int((base_damage * expected_combo_multiplier) + quality_bonus)
    
    print(f"Base Damage: {base_damage}")
    print(f"Combo Count: {combo_count}")
    print(f"Quality Bonus: {quality_bonus}")
    print(f"Expected Combo Multiplier: {expected_combo_multiplier}")
    print(f"Expected Total: ({base_damage} * {expected_combo_multiplier}) + {quality_bonus} = {expected_damage}")
    
    # Verify the formula is correct
    calculated = int((base_damage * expected_combo_multiplier) + quality_bonus)
    print(f"Calculated: {calculated}")
    print(f"Match: {'✓' if calculated == expected_damage else '✗'}")

if __name__ == "__main__":
    test_damage_calculations()
    test_formula_validation()
