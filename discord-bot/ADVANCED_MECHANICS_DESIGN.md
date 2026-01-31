# 🎮 ADVANCED MECHANICS DESIGN DOCUMENT
**Phase 3 Implementation Plan**

---

## 📋 OVERVIEW

This document outlines the design for 4 major new systems:

1. **Block Mechanic** - Third defensive option (evade/parry/block)
2. **Boss QTE System** - Bosses respond to player attacks
3. **GM Boss Creation** - Convert Tupper characters into playable bosses
4. **Skill Builder System** - JSON-based external attack/skill creator

---

## 🛡️ 1. BLOCK MECHANIC

### Concept
A third defensive option that sits between evade and parry:
- **Evade**: Avoids damage completely, enables counter (0-2s window)
- **Parry**: Reflects damage, Black Flash eligible (2-4s window)
- **Block**: Reduces damage, builds "Guard" meter (anywhere in window)

### How It Works

#### Timing
```
QTE Window: [--EVADE--|--PARRY--|--BLOCK--]
            0s       2s        4s        6s
```

- **Block Window**: From 4s until timeout (or 0-6s with reduced effectiveness)
- **No Perfect Timing Required**: Block always works, but timing affects reduction
- **Can't Fail**: Block never misses, but late blocks reduce less damage

#### Damage Reduction Tiers
```python
BLOCK_TIERS = {
    'early_block': {     # 0-2s (evade window but using *block*)
        'reduction': 90,  # 90% reduction
        'guard_gain': 15, # +15 Guard meter
        'message': '🛡️ PERFECT BLOCK!'
    },
    'mid_block': {       # 2-4s (parry window but using *block*)
        'reduction': 75,  # 75% reduction
        'guard_gain': 10,
        'message': '🛡️ SOLID BLOCK!'
    },
    'late_block': {      # 4s+ (normal block window)
        'reduction': 50,  # 50% reduction
        'guard_gain': 5,
        'message': '🛡️ Block!'
    }
}
```

### Guard Meter System

**Guard Meter**: 0-100 resource that builds from blocking
- **Gain**: +5 to +15 per block (based on timing)
- **Decay**: -2 per second when not blocking
- **Uses**:
  - **50 Guard**: "Shield Bash" - Stun enemy for 1s
  - **100 Guard**: "Fortress" - Immune to next attack

### Commands
```
*block* - Attempt to block incoming attack
*shieldbash* - Spend 50 Guard to stun enemy (must have 50+ Guard)
*fortress* - Spend 100 Guard for immunity (must have 100 Guard)
```

### Integration Points

#### File: `advanced_qte_hp_system_debug.py`
```python
# Add to __init__ (around line 280)
self.guard_meter = {}  # {user_id: guard_amount}
self.guard_max = 100
self.guard_decay_rate = 2  # per second
self.fortress_active = {}  # {user_id: expiry_timestamp}

# Add to handle_qte_response (around line 4450)
elif '*block*' in content.lower():
    await self.handle_block_response(qte_id, qte_data, message, ...)

# New function
async def handle_block_response(self, qte_id, qte_data, message, user_id, response_time):
    """Handle *block* command"""
    # Determine block tier based on response_time
    # Calculate damage reduction
    # Add Guard meter
    # Update HP
    # Send feedback
```

### Data Structure
```json
// data/player_guard.json
{
    "user_id": {
        "guard": 45,
        "last_update": 1738000000,
        "fortress_active": false
    }
}
```

---

## 🎯 2. BOSS QTE SYSTEM

### Concept
Bosses can **respond to player attacks** by receiving QTEs. If the boss (controlled by GM or Tupper) fails the QTE, they take damage. If they succeed, they counter or mitigate.

### How It Works

#### Trigger Flow
```
1. Player uses offensive ability (e.g., Raiden's *adapt*)
2. System generates QTE for boss
3. Boss (GM/Tupper) must respond within window
4. Success = Boss counters/evades
5. Failure = Boss takes full damage
```

#### Boss Response Options
```python
BOSS_RESPONSES = {
    'evade': 'Boss dodges attack completely (0 damage)',
    'parry': 'Boss reflects 50% damage back to attacker',
    'block': 'Boss reduces damage by 75%',
    'counter': 'Boss cancels attack and stuns attacker'
}
```

### Commands

#### For GM/Admin
```
/createbossqte <@boss_user> <difficulty> <damage> [timeout]
# Manually throw a QTE at a boss character

Example:
/createbossqte @BossName hard 150 6.0
```

#### Automatic Triggers
- **Raiden's Adaptation**: When used on boss, creates hard QTE
- **Ultimate Abilities**: High-damage powers create boss QTEs
- **Special Attacks**: Any attack with `boss_qte:true` flag

### Integration Points

```python
# File: advanced_qte_hp_system_debug.py

# Add to __init__
self.boss_characters = {}  # {user_id: boss_data}
self.boss_active_qtes = {}  # {qte_id: boss_qte_data}

# New function
async def trigger_boss_qte(self, boss_id: int, attacker_id: int, 
                           damage: int, difficulty: str):
    """Create a QTE that the boss must respond to"""
    # Generate QTE ID
    # Calculate windows based on difficulty
    # Send QTE message to boss
    # Wait for response
    # Handle success/failure
    
# Modify adaptation system (around line 4520+)
async def process_adaptation(self, user_id, difficulty, objects, message):
    # Check if target is a boss
    if target_user_id in self.boss_characters:
        # Trigger boss QTE instead of direct damage
        await self.trigger_boss_qte(target_user_id, user_id, ...)
```

### Boss QTE Message Format
```
🎯 INCOMING ATTACK! 🎯
Attacker: PlayerName used **Raiden's Adaptation**
Damage: 150 HP

React within 6.0s:
🏃 *evade* - Dodge completely
⚔️ *parry* - Reflect 50% back
🛡️ *block* - Reduce by 75%
💥 *counter* - Cancel & stun attacker

[Difficulty: HARD]
```

---

## 👾 3. GM BOSS CREATION SYSTEM

### Concept
Convert any Tupper character (or regular user) into a **boss entity** with:
- Custom HP pool
- Special attack registry
- QTE response capabilities
- Ultimate abilities
- Death/victory conditions

### Commands

#### `/createboss`
```python
/createboss <character_name> <max_hp> [difficulty_tier]

Parameters:
- character_name: Tupper character name or @user
- max_hp: Boss health pool (100-10000)
- difficulty_tier: easy, medium, hard, nightmare (affects QTE windows)

Example:
/createboss "Dark Seth" 5000 nightmare
```

#### `/registerbossattack`
```python
/registerbossattack <boss_name> <attack_file>

Parameters:
- boss_name: The boss to register attack for
- attack_file: JSON filename in data/boss_attacks/

Example:
/registerbossattack "Dark Seth" void_annihilation.json
```

#### `/bossstatus`
```python
/bossstatus <boss_name>

Shows:
- Current HP
- Active attacks
- Difficulty tier
- Stats (evades, parries, damage dealt)
```

#### `/removeboss`
```python
/removeboss <boss_name>

Removes boss designation from character
```

### Boss Data Structure
```json
// data/boss_registry.json
{
    "Dark Seth": {
        "user_id": 123456789,
        "tupper_name": "🌑┋𝐒𝐞𝐭𝐡",
        "max_hp": 5000,
        "current_hp": 5000,
        "difficulty_tier": "nightmare",
        "registered_attacks": [
            "void_annihilation",
            "matter_collapse"
        ],
        "stats": {
            "qtes_received": 15,
            "evades": 8,
            "parries": 4,
            "blocks": 2,
            "failures": 1,
            "damage_dealt": 1200,
            "damage_taken": 800
        },
        "active": true,
        "created_at": "2026-01-24T12:00:00Z"
    }
}
```

### Integration Points

```python
# File: advanced_qte_hp_system_debug.py

# Add to __init__
self.boss_registry = load_data("boss_registry", {})
self.boss_attacks = {}  # Loaded from data/boss_attacks/

# Add slash command
@self.bot.tree.command(name="createboss")
async def create_boss(interaction, character_name: str, max_hp: int, 
                      difficulty_tier: str = "medium"):
    """[ADMIN] Convert character into a boss"""
    # Validate permissions
    # Resolve character to user_id
    # Create boss entry
    # Save to registry
    # Send confirmation
```

---

## ⚔️ 4. SKILL BUILDER SYSTEM (JSON-Based)

### Concept
**External JSON files** define attacks/skills with:
- Damage values
- Effect chains
- Animations/visuals
- Cooldowns
- Requirements
- Boss QTE triggers

Users create JSON files → GM approves → Bot loads them

### Directory Structure
```
data/
  boss_attacks/
    templates/
      ATTACK_TEMPLATE.json
      ULTIMATE_TEMPLATE.json
    pending/
      user_submitted_attack.json
    approved/
      void_annihilation.json
      matter_collapse.json
      black_flash_storm.json
    archive/
      old_version_attacks.json
```

### JSON Schema

#### Basic Attack Example
```json
{
  "attack_id": "void_annihilation",
  "name": "Void Annihilation",
  "description": "Seth collapses matter and antimatter, releasing devastating gamma radiation",
  "type": "special_attack",
  "category": "destructive",
  
  "damage": {
    "base": 200,
    "scaling": "fixed",
    "variance": 0.1
  },
  
  "requirements": {
    "min_boss_hp": 0,
    "max_uses_per_battle": 3,
    "cooldown_seconds": 60
  },
  
  "effects": [
    {
      "type": "damage",
      "target": "all_players",
      "value": 200,
      "can_be_mitigated": true
    },
    {
      "type": "apply_debuff",
      "target": "all_players",
      "debuff": "radiation_sickness",
      "duration": 30,
      "effect": "damage_over_time:5"
    }
  ],
  
  "visuals": {
    "gif_url": "https://media.tenor.com/...",
    "color": "#9b59b6",
    "icon": "☢️"
  },
  
  "triggers_boss_qte": false,
  
  "animation_sequence": [
    {
      "delay": 0,
      "message": "⚫ **VOID ANNIHILATION** ⚫",
      "description": "Seth begins channeling antimatter..."
    },
    {
      "delay": 2,
      "message": "The air crackles with gamma radiation!",
      "trigger_player_qte": {
        "difficulty": "hard",
        "timeout": 5.0,
        "damage_on_fail": 200
      }
    },
    {
      "delay": 4,
      "message": "💥 ANNIHILATION WAVE! 💥",
      "apply_effects": true
    }
  ],
  
  "metadata": {
    "author": "PlayerName",
    "created_at": "2026-01-24",
    "approved_by": "GM_Username",
    "version": "1.0"
  }
}
```

#### Ultimate Attack Example
```json
{
  "attack_id": "black_flash_storm",
  "name": "Black Flash Storm",
  "description": "Unleash a barrage of Black Flash strikes",
  "type": "ultimate",
  "category": "destructive",
  
  "damage": {
    "base": 150,
    "hits": 5,
    "scaling": "combo_based",
    "variance": 0.15
  },
  
  "requirements": {
    "charge_required": 100,
    "cooldown_seconds": 120,
    "min_combo": 10
  },
  
  "effects": [
    {
      "type": "multi_hit_damage",
      "hits": 5,
      "damage_per_hit": 150,
      "target": "selected_enemy",
      "can_be_mitigated": true,
      "black_flash_eligible": true
    },
    {
      "type": "stun_target",
      "duration": 2.0
    }
  ],
  
  "qte_chain": {
    "enabled": true,
    "difficulty": "medium",
    "window_per_hit": 3.0,
    "success_bonus": 50,
    "failure_penalty": "cancel_remaining_hits"
  },
  
  "visuals": {
    "gif_urls": [
      "https://hit1.gif",
      "https://hit2.gif",
      "https://hit3.gif",
      "https://hit4.gif",
      "https://hit5.gif"
    ],
    "color": "#e74c3c",
    "icon": "⚡"
  }
}
```

### Skill Builder Commands

#### `/submitattack`
```python
/submitattack <json_filename>

Submits a JSON attack file for GM approval
File must be in user's local folder or attached to message
```

#### `/approveattack`
```python
/approveattack <filename> <boss_name>

[ADMIN] Approve pending attack and assign to boss
Moves from pending/ to approved/
Registers attack with boss
```

#### `/rejectattack`
```python
/rejectattack <filename> <reason>

[ADMIN] Reject pending attack with feedback
Moves to archive/ with rejection note
```

#### `/listattacks`
```python
/listattacks [boss_name]

Lists all approved attacks
If boss_name provided, shows only that boss's attacks
```

#### `/testattack`
```python
/testattack <attack_id> <@target>

[ADMIN] Test an attack in a safe environment
Doesn't consume cooldown or charges
Shows full animation sequence
```

### Effect Types Supported

```python
EFFECT_TYPES = {
    # Damage
    'damage': 'Direct HP damage',
    'multi_hit_damage': 'Multiple damage instances',
    'damage_over_time': 'DoT effect (burn, poison)',
    'percent_damage': 'Damage based on % of max HP',
    
    # Status Effects
    'stun_target': 'Prevents actions for duration',
    'apply_debuff': 'Apply negative status effect',
    'apply_buff': 'Apply positive status effect',
    'remove_buff': 'Strip buffs from target',
    
    # Utility
    'heal_self': 'Boss heals HP',
    'heal_allies': 'Heal other enemies',
    'summon_minion': 'Spawn additional enemies',
    'teleport': 'Reposition in battle',
    
    # QTE Manipulation
    'trigger_player_qte': 'Force QTE on players',
    'cancel_player_qte': 'Delete active QTE',
    'reverse_qte': 'Swap success/fail conditions',
    
    # Meta
    'consume_resource': 'Drain player resources',
    'steal_buff': 'Take player buff and apply to self',
    'reflect_next_attack': 'Next attack bounces back',
}
```

### Validation System

```python
class AttackValidator:
    """Validates attack JSON files before approval"""
    
    REQUIRED_FIELDS = ['attack_id', 'name', 'type', 'damage', 'effects']
    MAX_DAMAGE_PER_HIT = 500  # Safety limit
    MAX_TOTAL_DAMAGE = 2000   # Ultimate attacks
    
    def validate(self, attack_data: dict) -> Tuple[bool, List[str]]:
        """Returns (is_valid, errors)"""
        errors = []
        
        # Check required fields
        # Validate damage values
        # Check effect syntax
        # Verify GIF URLs (optional)
        # Ensure cooldowns are reasonable
        
        return len(errors) == 0, errors
```

### Integration Points

```python
# File: advanced_qte_hp_system_debug.py

# Add to __init__
self.attack_registry = {}  # {attack_id: attack_data}
self.boss_attack_cooldowns = {}  # {boss_id: {attack_id: next_available_time}}

# Load attacks
def load_boss_attacks(self):
    """Load all approved boss attacks"""
    attack_path = Path("data/boss_attacks/approved")
    for file in attack_path.glob("*.json"):
        with open(file) as f:
            attack = json.load(f)
            self.attack_registry[attack['attack_id']] = attack

# Execute attack
async def execute_boss_attack(self, boss_id: int, attack_id: str, 
                               targets: List[int]):
    """Execute a boss special attack"""
    attack = self.attack_registry.get(attack_id)
    if not attack:
        return
    
    # Check cooldown
    # Validate requirements
    # Run animation sequence
    # Apply effects
    # Update cooldowns
    # Log usage
```

---

## 🔄 IMPLEMENTATION ORDER

### Phase 3A: Foundation (Week 1)
1. ✅ Create directory structure for boss_attacks
2. ✅ Implement AttackValidator class
3. ✅ Build attack loading system
4. ✅ Create template JSON files

### Phase 3B: Boss Creation (Week 1-2)
1. ✅ Implement `/createboss` command
2. ✅ Build boss_registry system
3. ✅ Add `/bossstatus` and `/removeboss`
4. ✅ Test boss creation with Tupper characters

### Phase 3C: Boss QTE System (Week 2)
1. ✅ Implement `trigger_boss_qte()` function
2. ✅ Modify Raiden adaptation to use boss QTEs
3. ✅ Add boss response handlers
4. ✅ Test boss evasion/parry/counter

### Phase 3D: Skill Builder (Week 2-3)
1. ✅ Implement `/submitattack` command
2. ✅ Build approval workflow
3. ✅ Create `execute_boss_attack()` function
4. ✅ Test multi-step attack sequences
5. ✅ Add effect processors for all effect types

### Phase 3E: Block Mechanic (Week 3)
1. ✅ Implement Guard meter system
2. ✅ Add `handle_block_response()`
3. ✅ Build Shield Bash and Fortress abilities
4. ✅ Test block timing tiers

### Phase 3F: Integration & Polish (Week 4)
1. ✅ Connect all systems together
2. ✅ Performance optimization
3. ✅ Documentation
4. ✅ Testing with real gameplay

---

## 📊 DATA FILES NEEDED

```
data/
  boss_registry.json          # Active bosses
  boss_attacks/
    approved/
      *.json                   # Approved attacks
    pending/
      *.json                   # Awaiting approval
    templates/
      ATTACK_TEMPLATE.json     # Copy this to create attacks
      ULTIMATE_TEMPLATE.json
  player_guard.json            # Block/Guard meter tracking
  boss_qte_stats.json          # Boss QTE performance data
  attack_usage_log.json        # Track attack usage/cooldowns
```

---

## 🎯 SUCCESS METRICS

### Block Mechanic
- [ ] Players can *block* with variable reduction (50-90%)
- [ ] Guard meter builds and decays properly
- [ ] Shield Bash stuns enemies
- [ ] Fortress provides immunity

### Boss QTE System
- [ ] Raiden adaptation triggers boss QTE
- [ ] Boss can evade/parry/block/counter
- [ ] Failed boss QTE deals damage to boss
- [ ] QTE difficulty scales properly

### GM Boss Creation
- [ ] Tupper characters can become bosses
- [ ] Boss HP tracks separately from player HP
- [ ] Boss stats are recorded
- [ ] Multiple bosses can exist simultaneously

### Skill Builder
- [ ] Users can submit attack JSON files
- [ ] GM can approve/reject attacks
- [ ] Approved attacks execute correctly
- [ ] Animation sequences play in order
- [ ] All effect types work as intended
- [ ] Cooldowns prevent spam

---

## 🚀 NEXT STEPS

Which system should we implement **first**?

**Recommended Order:**
1. **GM Boss Creation** (foundation for everything)
2. **Boss QTE System** (enables interaction)
3. **Skill Builder** (content creation)
4. **Block Mechanic** (polish)

Let me know which one to start with!
