# Special Objects Loader & Manager
# INVENTORY-BASED SYSTEM: Objects are given to players by GM
# Players have limited object slots

import json
import os
import pathlib
import shutil
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import logging

log = logging.getLogger("SpecialObjects")

class SpecialObjectsManager:
    """
    Manages special objects with INVENTORY SYSTEM:
    - Objects are standalone items with name, image, rarity
    - GM gives objects to players via commands
    - Players have limited object slots
    - Objects can be tradeable/unique
    """
    
    # Default inventory slot limit per player
    DEFAULT_MAX_SLOTS = 5
    
    def __init__(self, base_path: str = "data/special_objects"):
        self.base_path = pathlib.Path(base_path)
        self.templates_path = self.base_path / "templates"
        self.pending_path = self.base_path / "pending"
        self.approved_path = self.base_path / "approved"
        self.archive_path = self.base_path / "archive"
        
        # Ensure directories exist
        for path in [self.templates_path, self.pending_path, self.approved_path, self.archive_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        # Loaded object definitions: {object_id: object_data}
        self.objects: Dict[str, dict] = {}
        
        # ========== INVENTORY SYSTEM ==========
        # Player inventories: {user_id: [object_ids]}
        self.player_inventory: Dict[int, List[str]] = {}
        
        # Player max slots (can be customized): {user_id: max_slots}
        self.player_max_slots: Dict[int, int] = {}
        
        # Object ownership tracking (for unique objects): {object_id: user_id}
        # If an object is unique, only one player can have it
        self.unique_object_owners: Dict[str, int] = {}
        
        # Tracking data: {user_id: {object_id: {tracking_key: value}}}
        self.tracking_data: Dict[int, Dict[str, Dict[str, Any]]] = {}
        
        # Pending files cache for notifications
        self._last_pending_check: List[str] = []
        
        # Valid effect patterns for validation
        self.valid_effects = [
            r"damage_reduction(\.[\w]+)?:[+-]?\d+",
            r"heal:\d+",
            r"heal_percent:\d+",
            r"charge_ultimate:\d+",
            r"charge_ultimate_full",
            r"stun_enemy:[\d.]+",
            r"damage_boss:\d+",
            r"boss_damage_percent:\d+",
            r"guaranteed_hit",
            r"guaranteed_counter",
            r"black_flash",
            r"invoke_qte:(easy|medium|hard|impossible)",
            r"cooldown_reduce:\d+",
            r"copy_attack",
            r"counter_for_enemy",
            r"remove_timing_requirement",
            r"auto_evade:(easy|medium|hard|impossible)",
            r"on_evade:[\w_]+:\d+",
            r"on_hard_evade:[\w_]+:\d+",
            r"on_boss_stunned:[\w_]+",
            r"on_boss_stunned:[\w_]+:\d+",
            r"damage_boost:[+-]?\d+",
            r"bf_chance:[+-]?\d+",
        ]
    
    def load_all(self) -> Tuple[int, List[str]]:
        """Load all approved objects. Returns (count, errors)"""
        self.objects.clear()
        
        errors = []
        count = 0
        
        for filepath in self.approved_path.glob("*.json"):
            success, error = self._load_object(filepath)
            if success:
                count += 1
            else:
                errors.append(f"{filepath.name}: {error}")
        
        # Load inventory data
        self.load_inventory()
        
        log.info(f"Loaded {count} special objects, {len(errors)} errors")
        return count, errors
    
    def _load_object(self, filepath: pathlib.Path) -> Tuple[bool, Optional[str]]:
        """Load a single object definition from file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate required fields (new schema - no assignment required!)
            required = ['id', 'name', 'type']
            for field in required:
                if field not in data:
                    return False, f"Missing required field: {field}"
            
            obj_id = data['id']
            
            # Set defaults for inventory fields if not present
            data.setdefault('image_url', None)
            data.setdefault('rarity', 'common')
            data.setdefault('slots_required', 1)
            data.setdefault('tradeable', True)
            data.setdefault('unique', False)
            data.setdefault('lore', '')
            
            # Store object
            self.objects[obj_id] = data
            
            log.info(f"Loaded special object: {obj_id} ({data['name']})")
            return True, None
            
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, str(e)
    
    def validate_object(self, filepath: pathlib.Path) -> Tuple[bool, List[str]]:
        """Validate an object file without loading it. Returns (valid, errors)"""
        errors = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON syntax: {e}"]
        except Exception as e:
            return False, [f"Cannot read file: {e}"]
        
        # Check required fields (NEW: no assignment required)
        required = ['id', 'name', 'type']
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: '{field}'")
        
        if errors:
            return False, errors
        
        # Validate ID format
        if not re.match(r'^[a-z0-9_]+$', data['id']):
            errors.append("ID must be lowercase alphanumeric with underscores only")
        
        # Validate type
        valid_types = ['adaptation', 'passive', 'triggered', 'consumable']
        if data['type'] not in valid_types:
            errors.append(f"Invalid type '{data['type']}'. Must be one of: {valid_types}")
        
        # Validate rarity if present
        valid_rarities = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic']
        if data.get('rarity') and data['rarity'] not in valid_rarities:
            errors.append(f"Invalid rarity '{data['rarity']}'. Must be one of: {valid_rarities}")
        
        # Validate slots_required if present
        if data.get('slots_required'):
            if not isinstance(data['slots_required'], int) or data['slots_required'] < 1:
                errors.append("slots_required must be a positive integer")
        
        # Validate trigger if present
        trigger = data.get('trigger', {})
        if trigger:
            valid_windows = ['parry', 'counter', 'evade', 'any', 'passive']
            if trigger.get('window') and trigger['window'] not in valid_windows:
                errors.append(f"Invalid trigger window '{trigger['window']}'. Must be one of: {valid_windows}")
        
        # Validate effects in thresholds
        for difficulty, thresholds in data.get('thresholds', {}).items():
            for i, threshold in enumerate(thresholds):
                if 'spins' not in threshold:
                    errors.append(f"thresholds.{difficulty}[{i}] missing 'spins'")
                if 'effects' not in threshold:
                    errors.append(f"thresholds.{difficulty}[{i}] missing 'effects'")
                else:
                    for effect in threshold['effects']:
                        if not self._validate_effect(effect):
                            errors.append(f"Invalid effect syntax: '{effect}'")
        
        # Validate conditionals
        for i, cond in enumerate(data.get('conditionals', [])):
            if 'if' not in cond:
                errors.append(f"conditionals[{i}] missing 'if'")
            if 'then' not in cond:
                errors.append(f"conditionals[{i}] missing 'then'")
            else:
                for effect in cond['then']:
                    if not self._validate_effect(effect):
                        errors.append(f"Invalid effect in conditional: '{effect}'")
        
        return len(errors) == 0, errors
    
    def _validate_effect(self, effect: str) -> bool:
        """Check if an effect string matches valid patterns"""
        for pattern in self.valid_effects:
            if re.match(f"^{pattern}$", effect):
                return True
        return False
    
    def test_object(self, filepath: pathlib.Path) -> Tuple[bool, List[str], List[str]]:
        """
        Dry-run test an object: validate + simulate effects.
        Returns (valid, errors, warnings)
        """
        valid, errors = self.validate_object(filepath)
        warnings = []
        
        if not valid:
            return False, errors, warnings
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check for potential issues
            
            # Warn about high damage values
            for diff, thresholds in data.get('thresholds', {}).items():
                for t in thresholds:
                    for effect in t.get('effects', []):
                        if 'damage_reduction:100' in effect:
                            warnings.append(f"100% damage reduction in {diff} - damage will be completely negated")
                        if 'boss_damage_percent' in effect:
                            match = re.search(r':(\d+)', effect)
                            if match and int(match.group(1)) > 50:
                                warnings.append(f"High boss damage percent ({match.group(1)}%) in effects")
            
            # Warn about no thresholds for adaptation type
            if data['type'] == 'adaptation' and not data.get('thresholds'):
                warnings.append("Adaptation type but no thresholds defined")
            
            # Warn about duplicate character assignments
            chars = data.get('assignment', {}).get('characters', [])
            if len(chars) != len(set(c.lower() for c in chars)):
                warnings.append("Duplicate characters in assignment (case-insensitive)")
            
            return True, errors, warnings
            
        except Exception as e:
            return False, [f"Test error: {e}"], warnings
    
    def approve_object(self, filename: str) -> Tuple[bool, str]:
        """Move object from pending to approved"""
        source = self.pending_path / filename
        if not source.exists():
            return False, f"File not found: {filename}"
        
        # Validate first
        valid, errors = self.validate_object(source)
        if not valid:
            return False, f"Validation failed: {'; '.join(errors)}"
        
        # Archive existing if same ID
        try:
            with open(source, 'r', encoding='utf-8') as f:
                data = json.load(f)
            obj_id = data['id']
            
            # Check if already exists in approved
            for existing in self.approved_path.glob("*.json"):
                with open(existing, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                if existing_data.get('id') == obj_id:
                    # Archive the old version
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    archive_name = f"{existing.stem}_{timestamp}.json"
                    shutil.move(str(existing), str(self.archive_path / archive_name))
                    log.info(f"Archived old version: {archive_name}")
                    break
        except Exception as e:
            log.warning(f"Error checking for existing object: {e}")
        
        # Move to approved
        dest = self.approved_path / filename
        shutil.move(str(source), str(dest))
        
        # Reload this object
        success, error = self._load_object(dest)
        if not success:
            return False, f"Load failed after approval: {error}"
        
        return True, f"Approved and loaded: {filename}"
    
    def reject_object(self, filename: str, reason: str = "") -> Tuple[bool, str]:
        """Move object from pending to archive with rejection marker"""
        source = self.pending_path / filename
        if not source.exists():
            return False, f"File not found: {filename}"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"REJECTED_{filename.replace('.json', '')}_{timestamp}.json"
        
        # Add rejection reason to file
        try:
            with open(source, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['_rejected'] = {
                'timestamp': timestamp,
                'reason': reason
            }
            with open(source, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except:
            pass
        
        shutil.move(str(source), str(self.archive_path / archive_name))
        return True, f"Rejected: {filename}"
    
    def archive_object(self, obj_id: str) -> Tuple[bool, str]:
        """Archive (deactivate) an approved object"""
        for filepath in self.approved_path.glob("*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('id') == obj_id:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    archive_name = f"{filepath.stem}_{timestamp}.json"
                    shutil.move(str(filepath), str(self.archive_path / archive_name))
                    
                    # Remove from loaded objects
                    if obj_id in self.objects:
                        del self.objects[obj_id]
                    
                    return True, f"Archived: {obj_id}"
            except:
                continue
        
        return False, f"Object not found: {obj_id}"
    
    def check_pending(self) -> List[str]:
        """Check for new files in pending folder. Returns list of new files."""
        current = [f.name for f in self.pending_path.glob("*.json")]
        new_files = [f for f in current if f not in self._last_pending_check]
        self._last_pending_check = current
        return new_files
    
    # ========== INVENTORY SYSTEM ==========
    
    def get_player_max_slots(self, user_id: int) -> int:
        """Get max inventory slots for a player"""
        return self.player_max_slots.get(user_id, self.DEFAULT_MAX_SLOTS)
    
    def set_player_max_slots(self, user_id: int, max_slots: int):
        """Set max inventory slots for a player"""
        self.player_max_slots[user_id] = max_slots
        self.save_inventory()
    
    def get_used_slots(self, user_id: int) -> int:
        """Get how many slots a player has used"""
        total = 0
        for obj_id in self.player_inventory.get(user_id, []):
            obj = self.objects.get(obj_id)
            if obj:
                total += obj.get('slots_required', 1)
        return total
    
    def get_available_slots(self, user_id: int) -> int:
        """Get how many slots a player has available"""
        return self.get_player_max_slots(user_id) - self.get_used_slots(user_id)
    
    def give_object(self, user_id: int, object_id: str) -> Tuple[bool, str]:
        """Give an object to a player. Returns (success, message)"""
        # Check object exists
        obj = self.objects.get(object_id)
        if not obj:
            return False, f"Object '{object_id}' not found"
        
        # Check if unique and already owned
        if obj.get('unique', False):
            if object_id in self.unique_object_owners:
                current_owner = self.unique_object_owners[object_id]
                if current_owner != user_id:
                    return False, f"This unique object is already owned by <@{current_owner}>"
        
        # Check if player already has it
        if object_id in self.player_inventory.get(user_id, []):
            return False, f"Player already has '{obj['name']}'"
        
        # Check slot availability
        slots_needed = obj.get('slots_required', 1)
        available = self.get_available_slots(user_id)
        if slots_needed > available:
            return False, f"Not enough slots! Needs {slots_needed}, has {available} available"
        
        # Give the object
        if user_id not in self.player_inventory:
            self.player_inventory[user_id] = []
        self.player_inventory[user_id].append(object_id)
        
        # Track unique ownership
        if obj.get('unique', False):
            self.unique_object_owners[object_id] = user_id
        
        self.save_inventory()
        return True, f"Gave **{obj['name']}** to player"
    
    def take_object(self, user_id: int, object_id: str) -> Tuple[bool, str]:
        """Remove an object from a player. Returns (success, message)"""
        obj = self.objects.get(object_id)
        if not obj:
            return False, f"Object '{object_id}' not found"
        
        if user_id not in self.player_inventory:
            return False, "Player has no objects"
        
        if object_id not in self.player_inventory[user_id]:
            return False, f"Player doesn't have '{obj['name']}'"
        
        self.player_inventory[user_id].remove(object_id)
        
        # Remove unique ownership
        if obj.get('unique', False) and self.unique_object_owners.get(object_id) == user_id:
            del self.unique_object_owners[object_id]
        
        self.save_inventory()
        return True, f"Removed **{obj['name']}** from player"
    
    def transfer_object(self, from_user: int, to_user: int, object_id: str) -> Tuple[bool, str]:
        """Transfer an object between players. Returns (success, message)"""
        obj = self.objects.get(object_id)
        if not obj:
            return False, f"Object '{object_id}' not found"
        
        # Check if tradeable
        if not obj.get('tradeable', True):
            return False, f"**{obj['name']}** is not tradeable"
        
        # Check source has it
        if object_id not in self.player_inventory.get(from_user, []):
            return False, "Source player doesn't have this object"
        
        # Check destination slots
        slots_needed = obj.get('slots_required', 1)
        available = self.get_available_slots(to_user)
        if slots_needed > available:
            return False, f"Destination player doesn't have enough slots ({slots_needed} needed, {available} available)"
        
        # Do the transfer
        self.player_inventory[from_user].remove(object_id)
        if to_user not in self.player_inventory:
            self.player_inventory[to_user] = []
        self.player_inventory[to_user].append(object_id)
        
        # Update unique ownership
        if obj.get('unique', False):
            self.unique_object_owners[object_id] = to_user
        
        self.save_inventory()
        return True, f"Transferred **{obj['name']}** to new owner"
    
    def get_player_inventory(self, user_id: int) -> List[dict]:
        """Get all objects in a player's inventory with full data"""
        result = []
        for obj_id in self.player_inventory.get(user_id, []):
            if obj_id in self.objects:
                result.append(self.objects[obj_id])
        return result
    
    def get_objects_for_user(self, user_id: int, character_names: Optional[List[str]] = None) -> List[dict]:
        """Get all special objects that apply to a user (from their INVENTORY)"""
        # NEW: Just return inventory contents
        return self.get_player_inventory(user_id)
    
    def get_objects_by_trigger(self, command: str, window: str) -> List[dict]:
        """Get all objects that can be triggered by a command in a window"""
        result = []
        for obj in self.objects.values():
            trigger = obj.get('trigger', {})
            if trigger.get('command') == command:
                obj_window = trigger.get('window', 'any')
                if obj_window == 'any' or obj_window == window:
                    result.append(obj)
        return result
    
    # ========== TRACKING DATA ==========
    
    def get_tracking(self, user_id: int, obj_id: str, key: str) -> Any:
        """Get tracking value for user's object"""
        return self.tracking_data.get(user_id, {}).get(obj_id, {}).get(key, 0)
    
    def set_tracking(self, user_id: int, obj_id: str, key: str, value: Any):
        """Set tracking value for user's object"""
        if user_id not in self.tracking_data:
            self.tracking_data[user_id] = {}
        if obj_id not in self.tracking_data[user_id]:
            self.tracking_data[user_id][obj_id] = {}
        self.tracking_data[user_id][obj_id][key] = value
    
    def increment_tracking(self, user_id: int, obj_id: str, key: str, amount: int = 1) -> int:
        """Increment tracking value and return new value"""
        current = self.get_tracking(user_id, obj_id, key)
        new_value = current + amount
        self.set_tracking(user_id, obj_id, key, new_value)
        return new_value
    
    def get_all_tracking(self, user_id: int, obj_id: str) -> Dict[str, Any]:
        """Get all tracking data for user's object"""
        return self.tracking_data.get(user_id, {}).get(obj_id, {})
    
    def save_tracking(self, filepath: str = "data/special_objects/tracking_data.json"):
        """Save tracking data to file"""
        try:
            # Convert int keys to strings for JSON
            save_data = {}
            for user_id, obj_data in self.tracking_data.items():
                save_data[str(user_id)] = obj_data
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            log.error(f"Error saving tracking data: {e}")
    
    def load_tracking(self, filepath: str = "data/special_objects/tracking_data.json"):
        """Load tracking data from file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Convert string keys back to int
            self.tracking_data = {int(k): v for k, v in data.items()}
        except FileNotFoundError:
            self.tracking_data = {}
        except Exception as e:
            log.error(f"Error loading tracking data: {e}")
            self.tracking_data = {}
    
    # ========== INVENTORY PERSISTENCE ==========
    
    def save_inventory(self, filepath: str = "data/special_objects/player_inventory.json"):
        """Save player inventory data to file"""
        try:
            save_data = {
                'inventories': {str(k): v for k, v in self.player_inventory.items()},
                'max_slots': {str(k): v for k, v in self.player_max_slots.items()},
                'unique_owners': self.unique_object_owners
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2)
            log.info(f"Saved inventory data for {len(self.player_inventory)} players")
        except Exception as e:
            log.error(f"Error saving inventory data: {e}")
    
    def load_inventory(self, filepath: str = "data/special_objects/player_inventory.json"):
        """Load player inventory data from file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load inventories
            self.player_inventory = {int(k): v for k, v in data.get('inventories', {}).items()}
            
            # Load max slots
            self.player_max_slots = {int(k): v for k, v in data.get('max_slots', {}).items()}
            
            # Load unique owners
            self.unique_object_owners = data.get('unique_owners', {})
            
            log.info(f"Loaded inventory data for {len(self.player_inventory)} players")
        except FileNotFoundError:
            self.player_inventory = {}
            self.player_max_slots = {}
            self.unique_object_owners = {}
            log.info("No inventory file found, starting fresh")
        except Exception as e:
            log.error(f"Error loading inventory data: {e}")
            self.player_inventory = {}
            self.player_max_slots = {}
            self.unique_object_owners = {}
    
    # ========== EFFECT INTERPRETATION ==========
    
    def get_current_threshold(self, user_id: int, obj_id: str, difficulty: str) -> Optional[dict]:
        """Get the current active threshold for a user's object at a difficulty"""
        obj = self.objects.get(obj_id)
        if not obj:
            return None
        
        # Handle both tracking types
        tracking_config = obj.get('tracking', {})
        tracking_type = tracking_config.get('type', 'per_difficulty')
        
        thresholds_config = obj.get('thresholds', {})
        
        # Get thresholds based on tracking type
        if tracking_type == 'total':
            # New format: flat list
            if isinstance(thresholds_config, list):
                thresholds = thresholds_config
                tracking_key = 'total'
            else:
                # Malformed, treat as empty
                return None
        else:
            # Old format: per-difficulty dict
            if isinstance(thresholds_config, dict):
                thresholds = thresholds_config.get(difficulty, [])
            else:
                # New format but used for per-difficulty, treat as flat list
                thresholds = thresholds_config if isinstance(thresholds_config, list) else []
            tracking_key = difficulty
        
        if not thresholds:
            return None
        
        spins = self.get_tracking(user_id, obj_id, tracking_key)
        
        # Find highest threshold met
        active_threshold = None
        for t in thresholds:
            if spins >= t['spins']:
                active_threshold = t
        
        return active_threshold
    
    def get_damage_reduction(self, user_id: int, character_names: List[str], difficulty: str) -> float:
        """Calculate total damage reduction % for a user at a difficulty"""
        total_reduction = 0.0
        
        for obj in self.get_objects_for_user(user_id, character_names):
            obj_id = obj['id']
            
            # Check threshold effects
            threshold = self.get_current_threshold(user_id, obj_id, difficulty)
            if threshold:
                for effect in threshold.get('effects', []):
                    if effect.startswith('damage_reduction'):
                        match = re.search(r':([+-]?\d+)', effect)
                        if match:
                            value = int(match.group(1))
                            if effect.startswith('damage_reduction:+'):
                                total_reduction += value
                            elif effect.startswith('damage_reduction:'):
                                total_reduction = max(total_reduction, value)
            
            # Check conditionals
            for cond in obj.get('conditionals', []):
                if self._evaluate_condition(cond['if'], user_id, obj_id, difficulty):
                    for effect in cond['then']:
                        # Check if effect applies to this difficulty
                        if f'damage_reduction.{difficulty}' in effect:
                            match = re.search(r':([+-]?\d+)', effect)
                            if match:
                                value = int(match.group(1))
                                if '+' in effect:
                                    total_reduction += value
                                else:
                                    total_reduction = max(total_reduction, value)
                        elif effect.startswith('damage_reduction:') and '.' not in effect:
                            match = re.search(r':([+-]?\d+)', effect)
                            if match:
                                value = int(match.group(1))
                                total_reduction = max(total_reduction, value)
        
        return min(100.0, total_reduction)  # Cap at 100%
    
    def _evaluate_condition(self, condition: str, user_id: int, obj_id: str, current_difficulty: Optional[str] = None) -> bool:
        """Evaluate a condition string"""
        try:
            # Parse condition
            # Examples: "spins.impossible >= 12", "hp.percent <= 20", "enemy.stunned"
            
            # spins.DIFFICULTY >= VALUE
            match = re.match(r'spins\.(\w+)\s*(>=|<=|>|<|==|!=)\s*(\d+)', condition)
            if match:
                difficulty, op, value = match.groups()
                spins = self.get_tracking(user_id, obj_id, difficulty)
                value = int(value)
                return self._compare(spins, op, value)
            
            # Simple boolean checks
            if condition == 'enemy.stunned':
                # This would need to be passed in from the bot context
                return False  # Placeholder
            
            if condition == 'boss.active':
                return False  # Placeholder
            
            if condition == 'cooldown.ready':
                return True  # Placeholder
            
            # difficulty.current == "VALUE"
            match = re.match(r'difficulty\.current\s*==\s*["\']?(\w+)["\']?', condition)
            if match:
                return current_difficulty == match.group(1)
            
            return False
            
        except Exception as e:
            log.error(f"Error evaluating condition '{condition}': {e}")
            return False
    
    def _compare(self, a, op: str, b) -> bool:
        """Compare two values with an operator"""
        if op == '>=': return a >= b
        if op == '<=': return a <= b
        if op == '>': return a > b
        if op == '<': return a < b
        if op == '==': return a == b
        if op == '!=': return a != b
        return False
    
    def get_active_effects(self, user_id: int, difficulty: str = None) -> Dict[str, Any]:
        """Get all currently active effects for a user based on their objects and thresholds.
        
        Returns a dict with all active effects:
        {
            'auto_evade': 'easy' | 'medium' | None,
            'guaranteed_counter': bool,
            'on_hard_evade_heal': int (HP amount),
            'invoke_qte': 'easy' | 'medium' | 'hard' | None,
            'on_boss_stunned': {'black_flash': bool, 'boss_damage_percent': int},
            'total_spins': int,  # For display
        }
        """
        result = {
            'auto_evade': None,
            'guaranteed_counter': False,
            'on_hard_evade_heal': 0,
            'invoke_qte': None,
            'on_boss_stunned': {'black_flash': False, 'boss_damage_percent': 0},
            'total_spins': 0,
        }
        
        for obj in self.get_objects_for_user(user_id, []):
            obj_id = obj['id']
            
            # Get tracking type and spins
            tracking_config = obj.get('tracking', {})
            tracking_type = tracking_config.get('type', 'per_difficulty')
            
            if tracking_type == 'total':
                spins = self.get_tracking(user_id, obj_id, 'total')
                result['total_spins'] = max(result['total_spins'], spins)
                
                # Get active threshold from flat list
                thresholds = obj.get('thresholds', [])
                if isinstance(thresholds, list):
                    for t in thresholds:
                        if spins >= t.get('spins', 0):
                            for effect in t.get('effects', []):
                                self._apply_effect_to_result(effect, result)
            else:
                # Per-difficulty tracking
                if difficulty:
                    spins = self.get_tracking(user_id, obj_id, difficulty)
                    result['total_spins'] = max(result['total_spins'], spins)
                    
                    thresholds_config = obj.get('thresholds', {})
                    if isinstance(thresholds_config, dict):
                        thresholds = thresholds_config.get(difficulty, [])
                        for t in thresholds:
                            if spins >= t.get('spins', 0):
                                for effect in t.get('effects', []):
                                    self._apply_effect_to_result(effect, result)
        
        return result
    
    def _apply_effect_to_result(self, effect: str, result: Dict[str, Any]):
        """Parse an effect string and apply it to the result dict"""
        if effect.startswith('auto_evade:'):
            result['auto_evade'] = effect.split(':')[1]
        elif effect == 'guaranteed_counter':
            result['guaranteed_counter'] = True
        elif effect.startswith('on_hard_evade:heal:'):
            result['on_hard_evade_heal'] = int(effect.split(':')[2])
        elif effect.startswith('invoke_qte:'):
            result['invoke_qte'] = effect.split(':')[1]
        elif effect == 'on_boss_stunned:black_flash':
            result['on_boss_stunned']['black_flash'] = True
        elif effect.startswith('on_boss_stunned:boss_damage_percent:'):
            result['on_boss_stunned']['boss_damage_percent'] = int(effect.split(':')[2])
    
    def parse_effects(self, effects: List[str]) -> Dict[str, Any]:
        """Parse effect strings into a structured dict"""
        result = {
            'damage_reduction': {},
            'heal': 0,
            'heal_percent': 0,
            'charge_ultimate': 0,
            'charge_ultimate_full': False,
            'stun_enemy': 0,
            'damage_boss': 0,
            'boss_damage_percent': 0,
            'guaranteed_hit': False,
            'guaranteed_counter': False,
            'auto_evade': None,
            'black_flash': False,
            'invoke_qte': None,
            'cooldown_reduce': 0,
            'copy_attack': False,
            'counter_for_enemy': False,
            'remove_timing_requirement': False,
            'on_evade': {},
            'on_hard_evade': {},
            'on_boss_stunned': {},
            'damage_boost': 0,
            'bf_chance': 0,
        }
        
        for effect in effects:
            try:
                if effect.startswith('damage_reduction'):
                    # damage_reduction:50 or damage_reduction.easy:50 or damage_reduction:+20
                    match = re.match(r'damage_reduction(?:\.(\w+))?:([+-]?\d+)', effect)
                    if match:
                        difficulty = match.group(1) or 'all'
                        value = int(match.group(2))
                        result['damage_reduction'][difficulty] = value
                
                elif effect.startswith('heal_percent:'):
                    result['heal_percent'] = int(effect.split(':')[1])
                
                elif effect.startswith('heal:'):
                    result['heal'] = int(effect.split(':')[1])
                
                elif effect == 'charge_ultimate_full':
                    result['charge_ultimate_full'] = True
                
                elif effect.startswith('charge_ultimate:'):
                    result['charge_ultimate'] = int(effect.split(':')[1])
                
                elif effect.startswith('stun_enemy:'):
                    result['stun_enemy'] = float(effect.split(':')[1])
                
                elif effect.startswith('damage_boss:'):
                    result['damage_boss'] = int(effect.split(':')[1])
                
                elif effect.startswith('boss_damage_percent:'):
                    result['boss_damage_percent'] = int(effect.split(':')[1])
                
                elif effect == 'guaranteed_hit':
                    result['guaranteed_hit'] = True
                
                elif effect == 'guaranteed_counter':
                    result['guaranteed_counter'] = True
                
                elif effect.startswith('auto_evade:'):
                    result['auto_evade'] = effect.split(':')[1]
                
                elif effect == 'black_flash':
                    result['black_flash'] = True
                
                elif effect.startswith('invoke_qte:'):
                    result['invoke_qte'] = effect.split(':')[1]
                
                elif effect.startswith('cooldown_reduce:'):
                    result['cooldown_reduce'] = int(effect.split(':')[1])
                
                elif effect == 'copy_attack':
                    result['copy_attack'] = True
                
                elif effect == 'counter_for_enemy':
                    result['counter_for_enemy'] = True
                
                elif effect == 'remove_timing_requirement':
                    result['remove_timing_requirement'] = True
                
                elif effect.startswith('on_hard_evade:'):
                    parts = effect.split(':')
                    if len(parts) >= 3:
                        result['on_hard_evade'][parts[1]] = int(parts[2])
                
                elif effect.startswith('on_boss_stunned:'):
                    parts = effect.split(':')
                    if len(parts) >= 2:
                        if len(parts) >= 3:
                            result['on_boss_stunned'][parts[1]] = int(parts[2])
                        else:
                            result['on_boss_stunned'][parts[1]] = True
                
                elif effect.startswith('on_evade:'):
                    parts = effect.split(':')
                    if len(parts) >= 3:
                        result['on_evade'][parts[1]] = int(parts[2])
                
                elif effect.startswith('damage_boost:'):
                    result['damage_boost'] = int(effect.split(':')[1].replace('+', ''))
                
                elif effect.startswith('bf_chance:'):
                    result['bf_chance'] = int(effect.split(':')[1].replace('+', ''))
                    
            except Exception as e:
                log.warning(f"Error parsing effect '{effect}': {e}")
        
        return result


# Singleton instance for easy import
_manager_instance: Optional[SpecialObjectsManager] = None

def get_manager() -> SpecialObjectsManager:
    """Get the singleton SpecialObjectsManager instance"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SpecialObjectsManager()
    return _manager_instance
