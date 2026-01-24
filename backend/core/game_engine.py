"""
Core Game Engine - Extracted from Discord Bot
Handles QTE mechanics, damage calculation, and game logic
"""

import time
import random
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from .nlp_detector import ActionDetector

class QTEEngine:
    """Core QTE mechanics engine"""
    
    def __init__(self):
        self.nlp_detector = ActionDetector()
        # Latency compensation
        self.latency_offset = 0.25
        
        # Combo multiplier
        self.combo_multiplier = 1.0
        
        # QTE timing configurations (from Discord bot)
        self.qte_times = {
            'easy': {
                'evade_window': 6.0,
                'parry_window': (4.0, 7.0),
                'perfect_parry': 5.5
            },
            'medium': {
                'evade_window': 4.5,
                'parry_window': (3.0, 5.0),
                'perfect_parry': 4.0
            },
            'hard': {
                'evade_window': 4.0,
                'parry_window': (2.5, 4.5),
                'perfect_parry': 3.5
            },
            'impossible': {
                'evade_window': 1.5,
                'parry_window': (0.8, 1.7),
                'perfect_parry': 1.25
            }
        }
        
        # Damage ranges per difficulty
        self.damage_ranges = {
            'easy': (1, 3),
            'medium': (1, 5),
            'hard': (1, 10),
            'impossible': (15, 15)
        }
        
        # Black Flash configuration
        self.black_flash_base_chance = 0.02
        self.black_flash_increment = 0.01
        self.black_flash_cap = 0.20
        
        # REVENGE mode configuration
        self.revenge_threshold = 0.20
        self.revenge_parry_shift = -0.3
        self.revenge_parry_tightness = 0.7
        self.revenge_damage_multiplier = 1.5
        self.revenge_bf_bonus = 0.10
        
        # Counter mechanic
        self.counter_window = 2.0
        self.counter_damage = 20
        
    def check_qte_response(self, action: str, response_time: float, difficulty: str, 
                          user_hp_data: Dict = None) -> Dict:
        """
        Check if QTE response was successful
        Returns: {success: bool, damage: int, special: str or None}
        """
        # Compensate for latency
        response_time -= self.latency_offset
        
        timing = self.qte_times[difficulty]
        result = {
            "success": False,
            "damage": 0,
            "special": None,
            "response_time": response_time
        }
        
        if action == "evade":
            if response_time <= timing['evade_window']:
                result["success"] = True
                # Check for counter window
                if response_time < self.counter_window:
                    result["special"] = "counter_enabled"
            else:
                result["damage"] = self.calculate_damage(difficulty)
                
        elif action == "parry":
            parry_min, parry_max = self.get_adjusted_parry_window(difficulty, user_hp_data)
            
            if parry_min <= response_time <= parry_max:
                result["success"] = True
                # Check for Black Flash
                if self.check_black_flash(response_time, difficulty, user_hp_data):
                    result["special"] = "black_flash"
            else:
                result["damage"] = self.calculate_damage(difficulty)
                
        elif action == "save":
            if response_time <= timing['evade_window']:
                result["success"] = True
            else:
                result["damage"] = self.calculate_damage(difficulty)
        
        elif action == "fail":
            result["damage"] = self.calculate_damage(difficulty)
            
        return result
    
    def calculate_damage(self, difficulty: str, combo_multiplier: float = 1.0, quality_bonus: int = 0) -> int:
        """Calculate variable damage based on difficulty, combo, and quality"""
        min_dmg, max_dmg = self.damage_ranges.get(difficulty, (5, 15))
        base_damage = random.randint(min_dmg, max_dmg)
        
        # Apply combo multiplier and quality bonus
        total_damage = int((base_damage + quality_bonus) * combo_multiplier)
        
        return total_damage
    
    def calculate_attack_damage(self, action: str, text: str, combo_multiplier: float = 1.0) -> int:
        """
        Calculate damage for free-form attacks based on action type and text quality.
        Maps action types to appropriate difficulty ranges.
        """
        # Map actions to damage ranges
        action_damage_ranges = {
            'evade': (3, 8),      # Defensive action, lower damage
            'parry': (5, 12),     # Counter action, moderate damage
            'attack': (8, 20),    # Direct attack, high damage
            'save': (3, 8),       # Protective action, lower damage
            'heal': (0, 0),       # No damage
            'power1': (15, 30),   # Ultimate ability
            'power2': (20, 35),   # Ultimate ability
        }
        
        # Get damage range for this action
        min_dmg, max_dmg = action_damage_ranges.get(action, (5, 15))
        
        # Base damage with randomization
        base_damage = random.randint(min_dmg, max_dmg)
        
        # Quality bonus based on text length (words)
        word_count = len(text.split())
        quality_bonus = word_count // 3  # 1 bonus damage per 3 words
        
        # Apply combo multiplier
        total_damage = int((base_damage + quality_bonus) * combo_multiplier)
        
        return max(1, total_damage)  # Minimum 1 damage
    
    def get_adjusted_parry_window(self, difficulty: str, user_hp_data: Optional[Dict] = None) -> Tuple[float, float]:
        """Get parry window adjusted for REVENGE mode"""
        parry_min, parry_max = self.qte_times[difficulty]['parry_window']
        
        # Check if player is in REVENGE mode
        if user_hp_data and user_hp_data.get("revenge_mode", False):
            # Shift window earlier
            parry_min += self.revenge_parry_shift
            parry_max += self.revenge_parry_shift
            
            # Make window tighter
            center = (parry_min + parry_max) / 2
            width = (parry_max - parry_min) * self.revenge_parry_tightness
            parry_min = center - width / 2
            parry_max = center + width / 2
            
        return parry_min, parry_max
    
    def check_black_flash(self, response_time: float, difficulty: str, 
                          user_hp_data: Dict = None) -> bool:
        """Check if a black flash occurred"""
        if difficulty not in ['medium', 'hard', 'impossible']:
            return False
        
        perfect_timing = self.qte_times[difficulty]['perfect_parry']
        timing_deviation = abs(response_time - perfect_timing)
        
        if timing_deviation > 0.1:
            return False
        
        # Base chance + REVENGE bonus if active
        chance = self.black_flash_base_chance
        if user_hp_data and user_hp_data.get("revenge_mode", False):
            chance += self.revenge_bf_bonus
        
        return random.random() < chance


class HPSystem:
    """HP and damage management system"""
    
    def __init__(self):
        self.max_hp = 100
        self.regen_amount = 30
        
    def initialize_player(self) -> Dict:
        """Initialize HP for a new player"""
        return {
            "current": self.max_hp,
            "max": self.max_hp,
            "alive": True,
            "revenge_mode": False
        }
    
    def apply_damage(self, hp_data: Dict, damage: int) -> Dict:
        """Apply damage to player and check for REVENGE mode"""
        old_hp = hp_data["current"]
        hp_data["current"] = max(0, hp_data["current"] - damage)
        actual_damage = old_hp - hp_data["current"]
        
        # Check if REVENGE mode should activate
        hp_percent = hp_data["current"] / hp_data["max"]
        if hp_percent <= 0.20 and not hp_data["revenge_mode"] and hp_data["alive"]:
            hp_data["revenge_mode"] = True
        
        # Check if player died
        if hp_data["current"] == 0:
            hp_data["alive"] = False
        
        return hp_data
    
    def heal_player(self, hp_data: Dict, amount: int) -> Dict:
        """Heal a player"""
        if not hp_data["alive"]:
            return hp_data
        
        old_hp = hp_data["current"]
        hp_data["current"] = min(hp_data["max"], hp_data["current"] + amount)
        
        return hp_data


class PowerSystem:
    """Power charge and ultimate system"""
    
    def __init__(self):
        self.charge_per_damage_dealt = 1.0  # 1% per 10 damage
        self.charge_per_damage_taken = 2.0  # 2% per 5 damage
        self.ultimate_cost = 100.0
        
    def initialize_player(self) -> Dict:
        """Initialize power charges for a player"""
        return {
            "power1": 0.0,
            "power2": 0.0
        }
    
    def add_charge_from_damage_dealt(self, charges: Dict, damage: int) -> Dict:
        """Add charge when player deals damage"""
        charge_gain = (damage / 10.0) * self.charge_per_damage_dealt
        
        for power_key in ["power1", "power2"]:
            charges[power_key] = min(100.0, charges[power_key] + charge_gain)
        
        return charges
    
    def add_charge_from_damage_taken(self, charges: Dict, damage: int) -> Dict:
        """Add charge when player takes damage"""
        charge_gain = (damage / 5.0) * self.charge_per_damage_taken
        
        for power_key in ["power1", "power2"]:
            charges[power_key] = min(100.0, charges[power_key] + charge_gain)
        
        return charges
    
    def can_use_ultimate(self, charges: Dict, power_slot: int) -> bool:
        """Check if player has enough charge for ultimate"""
        power_key = f"power{power_slot}"
        return charges.get(power_key, 0.0) >= self.ultimate_cost
    
    def consume_ultimate(self, charges: Dict, power_slot: int) -> bool:
        """Consume ultimate charge when power is used"""
        power_key = f"power{power_slot}"
        if charges.get(power_key, 0.0) >= self.ultimate_cost:
            charges[power_key] = 0.0
            return True
        return False


class BossSystem:
    """Boss battle management"""
    
    def __init__(self):
        self.active_boss: Optional[Dict[str, any]] = None
        
    def create_boss(self, name: str, hp: int, gif_url: str = None) -> Dict:
        """Create a new boss"""
        return {
            'name': name,
            'hp_current': hp,
            'hp_max': hp,
            'gif_url': gif_url,
            'participants': [],
            'phase': 1
        }
    
    def damage_boss(self, boss: Dict, damage: int) -> Dict:
        """Deal damage to boss"""
        old_hp = boss['hp_current']
        boss['hp_current'] = max(0, boss['hp_current'] - damage)
        
        # Check for phase transitions
        hp_percent = boss['hp_current'] / boss['hp_max']
        if hp_percent <= 0.5 and boss['phase'] == 1:
            boss['phase'] = 2
        elif hp_percent <= 0.25 and boss['phase'] == 2:
            boss['phase'] = 3
        
        return boss
    
    def is_boss_defeated(self, boss: Dict) -> bool:
        """Check if boss is defeated"""
        return boss['hp_current'] == 0


class GameSession:
    """Main game session manager"""
    
    def __init__(self):
        self.qte_engine = QTEEngine()
        self.hp_system = HPSystem()
        self.power_system = PowerSystem()
        self.boss_system = BossSystem()
        
        # Session data
        self.players = {}
        self.active_qtes = {}
        self.qte_counter = 0
        
    def add_player(self, user_id: str) -> Dict:
        """Add a player to the session"""
        if user_id not in self.players:
            self.players[user_id] = {
                "id": user_id,
                "hp": self.hp_system.initialize_player(),
                "power": self.power_system.initialize_player(),
                "stats": {
                    "total_attempts": 0,
                    "successful": 0,
                    "failed": 0,
                    "best_time": float('inf'),
                    "black_flashes": 0
                }
            }
        return self.players[user_id]
    
    def trigger_qte(self, difficulty: str, target_user: str = None, mode: str = "single") -> Dict:
        """Trigger a QTE event"""
        qte_id = f"qte_{self.qte_counter}"
        self.qte_counter += 1
        
        qte_data = {
            "id": qte_id,
            "difficulty": difficulty,
            "mode": mode,
            "target": target_user,
            "start_time": time.time(),
            "window": self.qte_engine.qte_times[difficulty]['evade_window'],
            "responses": {}
        }
        
        self.active_qtes[qte_id] = qte_data
        return qte_data
    
    def process_qte_response(self, user_id: str, qte_id: str, action: str, 
                            response_time: float) -> Dict:
        """Process a player's QTE response"""
        if qte_id not in self.active_qtes:
            return {"error": "QTE not found"}
        
        qte = self.active_qtes[qte_id]
        player = self.players.get(user_id)
        
        if not player:
            return {"error": "Player not found"}
        
        # Check response
        result = self.qte_engine.check_qte_response(
            action, response_time, qte['difficulty'], player['hp']
        )
        
        # Apply damage if failed
        if not result['success'] and result['damage'] > 0:
            self.hp_system.apply_damage(player['hp'], result['damage'])
            self.power_system.add_charge_from_damage_taken(
                player['power'], result['damage']
            )
            player['stats']['failed'] += 1
            self.qte_engine.combo_multiplier = 1.0
        else:
            player['stats']['successful'] += 1
            if response_time < player['stats']['best_time']:
                player['stats']['best_time'] = response_time
            self.qte_engine.combo_multiplier += 0.25
        
        # Update stats
        player['stats']['total_attempts'] += 1
        
        # Store response
        qte['responses'][user_id] = result
        
        return result

    def process_free_attack(self, user_id: str, text: str) -> Optional[Dict]:
        """Process a free-form attack from a player."""
        player = self.players.get(user_id)
        if not player:
            return None
            
        action, confidence = self.qte_engine.nlp_detector.detect(text)
        
        if action:
            # Get combo info
            if "combo_count" not in player:
                player["combo_count"] = 0
            
            combo_count = player["combo_count"]
            combo_multiplier = 1.0 + (combo_count * 0.1)
            combo_multiplier = min(2.0, combo_multiplier)  # Cap at 2.0x
            
            # Map actions to damage ranges
            action_damage_ranges = {
                'evade': (3, 8),
                'parry': (5, 12),
                'attack': (8, 20),
                'save': (3, 8),
                'heal': (0, 0),
                'power1': (15, 30),
                'power2': (20, 35),
            }
            
            min_dmg, max_dmg = action_damage_ranges.get(action, (5, 15))
            base_damage = random.randint(min_dmg, max_dmg)
            
            # Calculate quality bonus
            word_count = len(text.split())
            quality_bonus = 0
            if confidence > 0.8:
                quality_bonus = word_count // 3
            
            # CORRECTED FORMULA: (base_damage * combo_multiplier) + quality_bonus
            damage = int((base_damage * combo_multiplier) + quality_bonus)
            damage = max(1, damage)  # Minimum 1 damage
            
            # Apply damage to boss
            if self.boss_system.active_boss:
                self.boss_system.damage_boss(self.boss_system.active_boss, damage)
            
            # Increment combo count
            player["combo_count"] = combo_count + 1
            
            # Add charge from damage dealt
            self.power_system.add_charge_from_damage_dealt(player["power"], damage)
            
            return {
                "damage": damage,
                "base_damage": base_damage,
                "combo_count": combo_count,
                "combo_multiplier": combo_multiplier,
                "quality_bonus": quality_bonus,
                "action": action,
                "confidence": confidence,
                "word_count": word_count,
                "nlp_confidence": confidence
            }
        
        return None


# Export main components
__all__ = ['QTEEngine', 'HPSystem', 'PowerSystem', 'BossSystem', 'GameSession']
