"""
Attack Validator for Skill Builder System
Validates boss attack JSON files for safety and correctness
"""

import json
import re
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import logging

log = logging.getLogger("AttackValidator")


class AttackValidator:
    """Validates attack JSON files before approval"""
    
    # Required fields for all attacks
    REQUIRED_FIELDS = [
        'attack_id', 'name', 'description', 'type', 'category',
        'damage', 'effects'
    ]
    
    # Valid attack types
    VALID_TYPES = ['special_attack', 'ultimate', 'counter_attack', 'passive']
    
    # Valid categories
    VALID_CATEGORIES = ['destructive', 'control', 'defensive', 'utility', 'mixed']
    
    # Valid target types
    VALID_TARGETS = [
        'all_players', 'selected_player', 'random_player', 
        'self', 'all_enemies', 'all_active'
    ]
    
    # Valid damage scaling types
    VALID_SCALING = ['fixed', 'combo_based', 'hp_based', 'charge_based']
    
    # Safety limits
    MAX_DAMAGE_PER_HIT = 500
    MAX_TOTAL_DAMAGE = 2000
    MAX_DOT_PER_TICK = 50
    MAX_STUN_DURATION = 5.0
    MAX_DEBUFF_DURATION = 60
    MAX_INVULN_DURATION = 5.0
    MAX_MINIONS = 3
    MAX_ANIMATION_STEPS = 10
    MAX_EFFECTS = 8
    MIN_COOLDOWN_SPECIAL = 30
    MIN_COOLDOWN_ULTIMATE = 120
    MIN_COOLDOWN_COUNTER = 15
    
    # Valid effect types with their required parameters
    EFFECT_SCHEMAS = {
        'damage': ['type', 'target', 'value', 'can_be_mitigated'],
        'multi_hit_damage': ['type', 'hits', 'damage_per_hit', 'target', 'can_be_mitigated'],
        'damage_over_time': ['type', 'target', 'damage_per_tick', 'ticks', 'tick_interval', 'debuff_name'],
        'percent_damage': ['type', 'target', 'percent', 'can_be_mitigated'],
        'stun_target': ['type', 'target', 'duration'],
        'apply_debuff': ['type', 'target', 'debuff', 'duration', 'effect'],
        'apply_buff': ['type', 'target', 'buff', 'duration', 'effect'],
        'heal_self': ['type'],  # value or percent required
        'heal_allies': ['type'],
        'summon_minion': ['type', 'minion_type', 'hp', 'damage', 'count'],
        'teleport': ['type', 'message', 'invulnerable_duration'],
        'trigger_player_qte': ['type', 'difficulty', 'timeout', 'damage_on_fail', 'target'],
        'cancel_player_qte': ['type', 'target'],
        'reverse_qte': ['type', 'target', 'duration'],
        'steal_buff': ['type', 'target', 'buff_types'],
        'reflect_next_attack': ['type', 'duration', 'reflect_percent'],
        'consume_resource': ['type', 'target', 'resource', 'amount'],
        'remove_buff': ['type', 'target'],
    }
    
    # Valid debuff/buff effect patterns
    VALID_STAT_EFFECTS = [
        r'damage_reduction:[+-]?\d+',
        r'defense_reduction:[+-]?\d+',
        r'speed_reduction:[+-]?\d+',
        r'accuracy_reduction:[+-]?\d+',
        r'damage_boost:[+-]?\d+',
        r'defense_boost:[+-]?\d+',
        r'damage_over_time:\d+',
    ]
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def validate(self, attack_data: dict, filepath: Optional[Path] = None) -> Tuple[bool, List[str], List[str]]:
        """
        Validate an attack JSON.
        Returns (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []
        
        # Basic structure validation
        self._validate_required_fields(attack_data)
        self._validate_attack_id(attack_data.get('attack_id'))
        self._validate_type_and_category(attack_data)
        
        # Damage validation
        self._validate_damage(attack_data.get('damage', {}))
        
        # Requirements validation
        self._validate_requirements(attack_data.get('requirements', {}), attack_data.get('type'))
        
        # Effects validation (most important)
        self._validate_effects(attack_data.get('effects', []))
        
        # Animation sequence validation
        if 'animation_sequence' in attack_data:
            self._validate_animation_sequence(attack_data['animation_sequence'])
        
        # Visuals validation (optional but recommended)
        if 'visuals' in attack_data:
            self._validate_visuals(attack_data['visuals'])
        
        # Overall balance check
        self._validate_balance(attack_data)
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings
    
    def _validate_required_fields(self, data: dict):
        """Check all required fields are present"""
        for field in self.REQUIRED_FIELDS:
            if field not in data:
                self.errors.append(f"Missing required field: '{field}'")
    
    def _validate_attack_id(self, attack_id: Optional[str]):
        """Validate attack_id format"""
        if not attack_id:
            return
        
        # Check format: lowercase, underscores, alphanumeric
        if not re.match(r'^[a-z0-9_]+$', attack_id):
            self.errors.append(
                f"Invalid attack_id '{attack_id}': must be lowercase alphanumeric with underscores only"
            )
        
        # Check length
        if len(attack_id) < 3:
            self.errors.append(f"attack_id '{attack_id}' too short (min 3 characters)")
        if len(attack_id) > 50:
            self.errors.append(f"attack_id '{attack_id}' too long (max 50 characters)")
    
    def _validate_type_and_category(self, data: dict):
        """Validate attack type and category"""
        attack_type = data.get('type')
        if attack_type not in self.VALID_TYPES:
            self.errors.append(
                f"Invalid type '{attack_type}'. Must be one of: {', '.join(self.VALID_TYPES)}"
            )
        
        category = data.get('category')
        if category not in self.VALID_CATEGORIES:
            self.errors.append(
                f"Invalid category '{category}'. Must be one of: {', '.join(self.VALID_CATEGORIES)}"
            )
    
    def _validate_damage(self, damage: dict):
        """Validate damage configuration"""
        if not damage:
            self.errors.append("Missing 'damage' field")
            return
        
        # Check base damage
        base = damage.get('base', 0)
        if base < 0:
            self.errors.append(f"Negative base damage: {base}")
        elif base > self.MAX_DAMAGE_PER_HIT:
            self.errors.append(
                f"Base damage {base} exceeds maximum {self.MAX_DAMAGE_PER_HIT}"
            )
        
        # Check scaling
        scaling = damage.get('scaling', 'fixed')
        if scaling not in self.VALID_SCALING:
            self.errors.append(
                f"Invalid scaling '{scaling}'. Must be one of: {', '.join(self.VALID_SCALING)}"
            )
        
        # Check variance
        variance = damage.get('variance', 0)
        if variance < 0 or variance > 0.5:
            self.errors.append(f"Variance {variance} out of range (0.0-0.5)")
        
        # Check multi-hit total damage
        hits = damage.get('hits', 1)
        total_damage = base * hits
        if total_damage > self.MAX_TOTAL_DAMAGE:
            self.errors.append(
                f"Total damage {total_damage} (base {base} × {hits} hits) exceeds maximum {self.MAX_TOTAL_DAMAGE}"
            )
    
    def _validate_requirements(self, requirements: dict, attack_type: Optional[str]):
        """Validate cooldown and usage requirements"""
        if not requirements:
            self.warnings.append("No requirements specified - attack will have default cooldown")
            return
        
        # Validate cooldown based on type
        cooldown = requirements.get('cooldown_seconds')
        if cooldown is not None:
            if attack_type == 'special_attack' and cooldown < self.MIN_COOLDOWN_SPECIAL:
                self.errors.append(
                    f"Special attack cooldown {cooldown}s too short (min {self.MIN_COOLDOWN_SPECIAL}s)"
                )
            elif attack_type == 'ultimate' and cooldown < self.MIN_COOLDOWN_ULTIMATE:
                self.errors.append(
                    f"Ultimate cooldown {cooldown}s too short (min {self.MIN_COOLDOWN_ULTIMATE}s)"
                )
            elif attack_type == 'counter_attack' and cooldown < self.MIN_COOLDOWN_COUNTER:
                self.errors.append(
                    f"Counter attack cooldown {cooldown}s too short (min {self.MIN_COOLDOWN_COUNTER}s)"
                )
        
        # Validate HP threshold
        min_hp = requirements.get('min_boss_hp')
        if min_hp is not None and (min_hp < 0 or min_hp > 100):
            self.errors.append(f"min_boss_hp {min_hp} out of range (0-100)")
        
        # Validate max uses
        max_uses = requirements.get('max_uses_per_battle')
        if max_uses is not None and max_uses < -1:
            self.errors.append(f"max_uses_per_battle {max_uses} invalid (use -1 for unlimited)")
    
    def _validate_effects(self, effects: List[dict]):
        """Validate all effects in the attack"""
        if not effects:
            self.errors.append("No effects defined - attack does nothing!")
            return
        
        if len(effects) > self.MAX_EFFECTS:
            self.errors.append(f"Too many effects ({len(effects)}) - maximum is {self.MAX_EFFECTS}")
        
        for i, effect in enumerate(effects):
            self._validate_single_effect(effect, i)
    
    def _validate_single_effect(self, effect: dict, index: int):
        """Validate a single effect"""
        effect_type = effect.get('type')
        
        if not effect_type:
            self.errors.append(f"Effect {index}: missing 'type' field")
            return
        
        if effect_type not in self.EFFECT_SCHEMAS:
            self.errors.append(
                f"Effect {index}: unknown effect type '{effect_type}'"
            )
            return
        
        # Check required parameters for this effect type
        required_params = self.EFFECT_SCHEMAS[effect_type]
        for param in required_params:
            if param not in effect and param != 'type':
                # Special cases where one of multiple params is required
                if effect_type == 'heal_self' and ('value' in effect or 'percent' in effect):
                    continue
                self.errors.append(
                    f"Effect {index} ({effect_type}): missing required parameter '{param}'"
                )
        
        # Validate target
        target = effect.get('target')
        if target and target not in self.VALID_TARGETS:
            self.errors.append(
                f"Effect {index}: invalid target '{target}'. Must be one of: {', '.join(self.VALID_TARGETS)}"
            )
        
        # Type-specific validation
        if effect_type == 'damage':
            value = effect.get('value', 0)
            if value > self.MAX_DAMAGE_PER_HIT:
                self.errors.append(
                    f"Effect {index}: damage {value} exceeds maximum {self.MAX_DAMAGE_PER_HIT}"
                )
        
        elif effect_type == 'multi_hit_damage':
            damage_per_hit = effect.get('damage_per_hit', 0)
            hits = effect.get('hits', 1)
            if damage_per_hit > self.MAX_DAMAGE_PER_HIT:
                self.errors.append(
                    f"Effect {index}: damage_per_hit {damage_per_hit} exceeds maximum {self.MAX_DAMAGE_PER_HIT}"
                )
            if hits < 1 or hits > 20:
                self.errors.append(f"Effect {index}: hits {hits} out of range (1-20)")
        
        elif effect_type == 'damage_over_time':
            damage_per_tick = effect.get('damage_per_tick', 0)
            if damage_per_tick > self.MAX_DOT_PER_TICK:
                self.errors.append(
                    f"Effect {index}: damage_per_tick {damage_per_tick} exceeds maximum {self.MAX_DOT_PER_TICK}"
                )
            ticks = effect.get('ticks', 0)
            if ticks < 1 or ticks > 20:
                self.errors.append(f"Effect {index}: ticks {ticks} out of range (1-20)")
        
        elif effect_type == 'stun_target':
            duration = effect.get('duration', 0)
            if duration > self.MAX_STUN_DURATION:
                self.errors.append(
                    f"Effect {index}: stun duration {duration}s exceeds maximum {self.MAX_STUN_DURATION}s"
                )
        
        elif effect_type in ['apply_debuff', 'apply_buff']:
            duration = effect.get('duration', 0)
            if duration > self.MAX_DEBUFF_DURATION:
                self.errors.append(
                    f"Effect {index}: debuff/buff duration {duration}s exceeds maximum {self.MAX_DEBUFF_DURATION}s"
                )
            
            # Validate effect pattern
            stat_effect = effect.get('effect', '')
            if not any(re.match(pattern, stat_effect) for pattern in self.VALID_STAT_EFFECTS):
                self.errors.append(
                    f"Effect {index}: invalid stat effect '{stat_effect}'. " +
                    f"Must match pattern like 'damage_reduction:±X'"
                )
        
        elif effect_type == 'summon_minion':
            count = effect.get('count', 1)
            if count > self.MAX_MINIONS:
                self.errors.append(
                    f"Effect {index}: summon count {count} exceeds maximum {self.MAX_MINIONS}"
                )
        
        elif effect_type == 'teleport':
            invuln = effect.get('invulnerable_duration', 0)
            if invuln > self.MAX_INVULN_DURATION:
                self.errors.append(
                    f"Effect {index}: invulnerability {invuln}s exceeds maximum {self.MAX_INVULN_DURATION}s"
                )
        
        elif effect_type == 'trigger_player_qte':
            difficulty = effect.get('difficulty')
            if difficulty not in ['easy', 'medium', 'hard', 'impossible']:
                self.errors.append(
                    f"Effect {index}: invalid QTE difficulty '{difficulty}'"
                )
            timeout = effect.get('timeout', 0)
            if timeout < 1 or timeout > 10:
                self.warnings.append(
                    f"Effect {index}: QTE timeout {timeout}s may be too short/long (recommended 3-7s)"
                )
    
    def _validate_animation_sequence(self, sequence: List[dict]):
        """Validate animation sequence"""
        if len(sequence) > self.MAX_ANIMATION_STEPS:
            self.errors.append(
                f"Animation sequence has {len(sequence)} steps (max {self.MAX_ANIMATION_STEPS})"
            )
        
        total_duration = 0
        for i, step in enumerate(sequence):
            delay = step.get('delay', 0)
            if delay < 0:
                self.errors.append(f"Animation step {i}: negative delay {delay}")
            
            total_duration = max(total_duration, delay + 2)  # Assume 2s per step
        
        if total_duration > 20:
            self.warnings.append(
                f"Animation sequence may be too long ({total_duration}s) - consider shortening"
            )
    
    def _validate_visuals(self, visuals: dict):
        """Validate visual configuration"""
        # Check GIF URLs if present
        gif_url = visuals.get('gif_url')
        if gif_url and not gif_url.startswith(('http://', 'https://')):
            self.errors.append(f"Invalid gif_url: must start with http:// or https://")
        
        # Check color format
        color = visuals.get('color')
        if color and not re.match(r'^#[0-9a-fA-F]{6}$', color):
            self.errors.append(f"Invalid color '{color}': must be hex format like #e74c3c")
    
    def _validate_balance(self, attack_data: dict):
        """Overall balance check"""
        # Calculate total potential damage
        damage_config = attack_data.get('damage', {})
        effects = attack_data.get('effects', [])
        
        base_damage = damage_config.get('base', 0)
        hits = damage_config.get('hits', 1)
        direct_damage = base_damage * hits
        
        # Add DoT damage
        dot_damage = 0
        for effect in effects:
            if effect.get('type') == 'damage_over_time':
                tick_damage = effect.get('damage_per_tick', 0)
                ticks = effect.get('ticks', 0)
                dot_damage += tick_damage * ticks
        
        total_damage = direct_damage + dot_damage
        
        # Check if damage is reasonable for attack type
        attack_type = attack_data.get('type')
        cooldown = attack_data.get('requirements', {}).get('cooldown_seconds', 60)
        
        if attack_type == 'special_attack' and total_damage > 500:
            dps = total_damage / cooldown
            if dps > 10:
                self.warnings.append(
                    f"High DPS ({dps:.1f}) for special attack - may be overpowered"
                )
        
        elif attack_type == 'ultimate' and total_damage > 1500:
            self.warnings.append(
                f"Very high total damage ({total_damage}) for ultimate - ensure balanced"
            )


def validate_attack_file(filepath: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Validate an attack JSON file.
    Returns (is_valid, errors, warnings)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            attack_data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"JSON syntax error: {e}"], []
    except Exception as e:
        return False, [f"Error reading file: {e}"], []
    
    validator = AttackValidator()
    return validator.validate(attack_data, filepath)


# For testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python attack_validator.py <attack_file.json>")
        sys.exit(1)
    
    filepath = Path(sys.argv[1])
    is_valid, errors, warnings = validate_attack_file(filepath)
    
    if errors:
        print("❌ ERRORS:")
        for error in errors:
            print(f"  - {error}")
    
    if warnings:
        print("\n⚠️  WARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if is_valid:
        print("\n✅ Attack is valid!")
    else:
        print(f"\n❌ Attack failed validation with {len(errors)} error(s)")
        sys.exit(1)
