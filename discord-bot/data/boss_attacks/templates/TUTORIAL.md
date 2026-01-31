# ⚔️ SKILL BUILDER TUTORIAL
**Create Custom Boss Attacks with JSON!**

---

## 📋 TABLE OF CONTENTS

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [File Structure](#file-structure)
4. [Attack Types](#attack-types)
5. [Effect Reference](#effect-reference)
6. [Animation Sequences](#animation-sequences)
7. [Examples](#examples)
8. [Submission Process](#submission-process)
9. [Best Practices](#best-practices)

---

## 🎯 INTRODUCTION

The **Skill Builder System** lets you create custom boss attacks using JSON files. No coding required - just fill in the template, submit it, and if approved by the GM, it becomes a real attack in the game!

### What You Can Create:
- ⚔️ Special attacks with custom damage/effects
- 🌟 Ultimate abilities with multi-hit sequences
- 🔥 Status effects (burn, poison, stun)
- ⏱️ QTE chains for players to respond to
- 🎬 Cinematic animation sequences

---

## 🚀 QUICK START

### Step 1: Copy a Template
Choose a template from this folder:
- `ATTACK_TEMPLATE.json` - Basic special attack
- `ULTIMATE_TEMPLATE.json` - Multi-hit ultimate ability
- `EXAMPLE_*.json` - Working examples

### Step 2: Edit the JSON
Open in any text editor and customize:
- Change `attack_id`, `name`, `description`
- Set `damage` values
- Define `effects` (what it does)
- Add `visuals` (GIFs, colors, icons)
- Create `animation_sequence` (timing and messages)

### Step 3: Save & Submit
- Save with a unique filename: `my_awesome_attack.json`
- Use `/submitattack <filename>` in Discord
- Wait for GM approval!

---

## 📁 FILE STRUCTURE

Every attack JSON has these sections:

```json
{
  "attack_id": "unique_identifier",     // Required: No spaces, lowercase
  "name": "Display Name",               // Required: What players see
  "description": "What this attack does", // Required
  "type": "special_attack",             // Required: See types below
  "category": "destructive",            // Required: See categories below
  
  "damage": { ... },                    // Required: Damage configuration
  "requirements": { ... },              // Optional: Usage restrictions
  "effects": [ ... ],                   // Required: What happens
  "visuals": { ... },                   // Optional: How it looks
  "animation_sequence": [ ... ],        // Optional: Timing/messages
  "triggers_boss_qte": false,           // Optional: Default false
  
  "metadata": { ... }                   // Auto-filled on submission
}
```

---

## 🎨 ATTACK TYPES

### `special_attack`
Standard ability usable multiple times per battle
- Has cooldown (30-120 seconds typical)
- Can have limited uses (max_uses_per_battle)
- Moderate damage (50-300 base)

### `ultimate`
Powerful ability with long cooldown
- Requires charge or long cooldown (120-300 seconds)
- High damage (150-500 base)
- Often multi-hit or has special effects
- May require combo or HP threshold

### `counter_attack`
Reactive ability triggered by player actions
- Activates when specific condition met
- Usually instant (no charge time)
- Often interrupts or punishes player

### `passive`
Ongoing effect, not a direct attack
- No cooldown (always active)
- Modifies boss behavior or stats
- Examples: damage reduction, HP regen, immunity

---

## 📊 CATEGORIES

- `destructive` - Pure damage focus
- `control` - Stuns, slows, debuffs
- `defensive` - Heals, shields, blocks
- `utility` - Summons, teleports, buffs
- `mixed` - Combination of above

---

## ⚡ EFFECT REFERENCE

### Damage Effects

#### `damage`
```json
{
  "type": "damage",
  "target": "all_players",        // or "selected_player", "random_player"
  "value": 150,
  "can_be_mitigated": true        // Can players evade/parry/block?
}
```

#### `multi_hit_damage`
```json
{
  "type": "multi_hit_damage",
  "hits": 5,
  "damage_per_hit": 100,
  "target": "selected_player",
  "can_be_mitigated": true,
  "black_flash_eligible": false   // Can this trigger BF for boss?
}
```

#### `damage_over_time`
```json
{
  "type": "damage_over_time",
  "target": "all_players",
  "damage_per_tick": 10,
  "ticks": 5,
  "tick_interval": 3,             // seconds between ticks
  "debuff_name": "Burning"
}
```

#### `percent_damage`
```json
{
  "type": "percent_damage",
  "target": "selected_player",
  "percent": 25,                  // 25% of max HP
  "min_damage": 50,               // Minimum damage dealt
  "can_be_mitigated": true
}
```

---

### Status Effects

#### `stun_target`
```json
{
  "type": "stun_target",
  "target": "selected_player",
  "duration": 3.0                 // seconds
}
```

#### `apply_debuff`
```json
{
  "type": "apply_debuff",
  "target": "all_players",
  "debuff": "weakness",           // Custom name
  "duration": 30,                 // seconds
  "effect": "damage_reduction:-20" // Reduces player damage by 20%
}
```
**Debuff effect types:**
- `damage_reduction:±X` - Modify damage dealt by X%
- `defense_reduction:±X` - Modify damage taken by X%
- `speed_reduction:±X` - Modify QTE window by X%
- `accuracy_reduction:±X` - Reduce parry window by X%

#### `apply_buff`
```json
{
  "type": "apply_buff",
  "target": "self",               // Boss buffs itself
  "buff": "enraged",
  "duration": 45,
  "effect": "damage_boost:50"     // +50% damage
}
```

---

### Utility Effects

#### `heal_self`
```json
{
  "type": "heal_self",
  "value": 200,                   // Flat heal
  "percent": 0                    // Or % of max HP
}
```

#### `summon_minion`
```json
{
  "type": "summon_minion",
  "minion_type": "shadow_clone",
  "hp": 500,
  "damage": 50,
  "count": 2                      // Number of minions
}
```

#### `teleport`
```json
{
  "type": "teleport",
  "message": "The boss vanishes into shadows...",
  "invulnerable_duration": 3.0    // Seconds of invulnerability
}
```

---

### QTE Effects

#### `trigger_player_qte`
```json
{
  "type": "trigger_player_qte",
  "difficulty": "hard",           // easy, medium, hard, impossible
  "timeout": 5.0,                 // seconds to respond
  "damage_on_fail": 200,
  "effect_on_fail": "stun:2.0",   // Optional extra punishment
  "target": "all_players"         // or specific target
}
```

#### `cancel_player_qte`
```json
{
  "type": "cancel_player_qte",
  "target": "all_active"          // Cancels all active QTEs
}
```

#### `reverse_qte`
```json
{
  "type": "reverse_qte",
  "target": "selected_player",
  "duration": 10                  // Next 10s, success=fail and vice versa
}
```

---

### Meta Effects

#### `steal_buff`
```json
{
  "type": "steal_buff",
  "target": "selected_player",
  "buff_types": ["all"]           // or ["damage", "defense"]
}
```

#### `reflect_next_attack`
```json
{
  "type": "reflect_next_attack",
  "duration": 5.0,                // Window to reflect
  "reflect_percent": 150          // Reflect 150% of damage
}
```

#### `consume_resource`
```json
{
  "type": "consume_resource",
  "target": "all_players",
  "resource": "guard",            // guard, faith, combo, etc.
  "amount": 50                    // Flat amount or percent
}
```

---

## 🎬 ANIMATION SEQUENCES

Control timing and messages with animation_sequence:

```json
"animation_sequence": [
  {
    "delay": 0,                           // Start immediately
    "message": "⚫ **VOID ANNIHILATION** ⚫",
    "description": "Seth begins channeling antimatter..."
  },
  {
    "delay": 2,                           // 2 seconds later
    "message": "The air crackles with gamma radiation!",
    "trigger_player_qte": {
      "difficulty": "hard",
      "timeout": 5.0,
      "damage_on_fail": 200
    }
  },
  {
    "delay": 4,                           // 4 seconds from start
    "message": "💥 ANNIHILATION WAVE! 💥",
    "apply_effects": true,                // Execute all effects now
    "gif_url": "https://..."              // Override main GIF
  },
  {
    "delay": 6,
    "message": "Reality warps and tears...",
    "apply_effects": [0, 2]               // Apply only effects at index 0 and 2
  }
]
```

**Tips:**
- `delay` is cumulative from attack start
- Use `apply_effects: true` to trigger all effects at this step
- Use `apply_effects: [0, 1, 2]` to trigger specific effects by index
- `trigger_player_qte` creates a QTE at this moment
- Messages appear in order, creating a cinematic sequence

---

## 📚 EXAMPLES

### Example 1: Simple Damage Attack

```json
{
  "attack_id": "meteor_strike",
  "name": "Meteor Strike",
  "description": "Summons a meteor from the sky",
  "type": "special_attack",
  "category": "destructive",
  
  "damage": {
    "base": 180,
    "scaling": "fixed",
    "variance": 0.15
  },
  
  "requirements": {
    "cooldown_seconds": 45,
    "max_uses_per_battle": -1
  },
  
  "effects": [
    {
      "type": "damage",
      "target": "all_players",
      "value": 180,
      "can_be_mitigated": true
    }
  ],
  
  "visuals": {
    "gif_url": "https://media.tenor.com/meteor.gif",
    "color": "#e74c3c",
    "icon": "☄️"
  }
}
```

### Example 2: Multi-Hit Ultimate

```json
{
  "attack_id": "rapid_assault",
  "name": "Rapid Assault Barrage",
  "description": "Unleashes 7 consecutive strikes",
  "type": "ultimate",
  "category": "destructive",
  
  "damage": {
    "base": 80,
    "hits": 7,
    "scaling": "combo_based",
    "variance": 0.1
  },
  
  "requirements": {
    "charge_required": 100,
    "cooldown_seconds": 180,
    "min_boss_hp": 0
  },
  
  "effects": [
    {
      "type": "multi_hit_damage",
      "hits": 7,
      "damage_per_hit": 80,
      "target": "selected_player",
      "can_be_mitigated": true
    },
    {
      "type": "stun_target",
      "target": "selected_player",
      "duration": 2.0
    }
  ],
  
  "animation_sequence": [
    {
      "delay": 0,
      "message": "⚡ **RAPID ASSAULT!** ⚡"
    },
    {
      "delay": 1,
      "message": "Seven devastating strikes rain down!",
      "apply_effects": true
    }
  ],
  
  "visuals": {
    "color": "#f39c12",
    "icon": "⚡"
  }
}
```

### Example 3: Status Effect Attack

```json
{
  "attack_id": "toxic_cloud",
  "name": "Toxic Cloud",
  "description": "Releases poisonous gas that damages over time",
  "type": "special_attack",
  "category": "control",
  
  "damage": {
    "base": 30,
    "scaling": "fixed",
    "variance": 0
  },
  
  "requirements": {
    "cooldown_seconds": 60
  },
  
  "effects": [
    {
      "type": "damage",
      "target": "all_players",
      "value": 30,
      "can_be_mitigated": true
    },
    {
      "type": "damage_over_time",
      "target": "all_players",
      "damage_per_tick": 15,
      "ticks": 6,
      "tick_interval": 3,
      "debuff_name": "Poisoned"
    },
    {
      "type": "apply_debuff",
      "target": "all_players",
      "debuff": "sickness",
      "duration": 20,
      "effect": "accuracy_reduction:-30"
    }
  ],
  
  "visuals": {
    "gif_url": "https://media.tenor.com/poison.gif",
    "color": "#27ae60",
    "icon": "☠️"
  }
}
```

### Example 4: Complex Animation Sequence

```json
{
  "attack_id": "dimension_rift",
  "name": "Dimensional Rift",
  "description": "Tears open a rift to another dimension",
  "type": "special_attack",
  "category": "mixed",
  
  "damage": {
    "base": 250,
    "scaling": "fixed",
    "variance": 0.2
  },
  
  "requirements": {
    "cooldown_seconds": 90,
    "min_boss_hp": 30
  },
  
  "effects": [
    {
      "type": "damage",
      "target": "random_player",
      "value": 250,
      "can_be_mitigated": true
    },
    {
      "type": "teleport",
      "message": "The boss phases through dimensions...",
      "invulnerable_duration": 3.0
    },
    {
      "type": "summon_minion",
      "minion_type": "void_spawn",
      "hp": 300,
      "damage": 40,
      "count": 1
    }
  ],
  
  "animation_sequence": [
    {
      "delay": 0,
      "message": "🌀 Reality begins to fracture... 🌀"
    },
    {
      "delay": 2,
      "message": "A rift tears open in the fabric of space!",
      "trigger_player_qte": {
        "difficulty": "hard",
        "timeout": 4.0,
        "damage_on_fail": 100
      }
    },
    {
      "delay": 5,
      "message": "💥 DIMENSIONAL COLLAPSE! 💥",
      "apply_effects": [0]
    },
    {
      "delay": 7,
      "message": "Something emerges from the void...",
      "apply_effects": [1, 2]
    }
  ],
  
  "visuals": {
    "gif_url": "https://media.tenor.com/rift.gif",
    "color": "#9b59b6",
    "icon": "🌀"
  }
}
```

---

## 📤 SUBMISSION PROCESS

### 1. Prepare Your File
- Use a unique `attack_id` (no duplicates)
- Fill all required fields
- Test JSON syntax (use jsonlint.com if needed)
- Keep damage reasonable (see limits below)

### 2. Submit via Discord
```
/submitattack filename:my_attack.json
```

If the file is on your computer:
1. Upload the .json file to Discord
2. Use `/submitattack` and attach the file

### 3. Wait for Review
- GM reviews for balance and appropriateness
- May request changes
- Approved attacks move to `approved/` folder

### 4. Attack Goes Live!
- Once approved, attack is available in-game
- Can be assigned to bosses
- Appears in `/listattacks`

---

## ⚖️ BALANCE LIMITS

To keep the game fair, these limits are enforced:

### Damage Limits
- **Single Hit Max**: 500 damage
- **Total Attack Max**: 2000 damage (for ultimates)
- **DoT Max**: 50 damage per tick

### Duration Limits
- **Stun Max**: 5 seconds
- **Debuff Max**: 60 seconds
- **Invulnerability Max**: 5 seconds

### Cooldown Minimums
- **Special Attack**: 30 seconds minimum
- **Ultimate**: 120 seconds minimum
- **Counter**: 15 seconds minimum

### Other Limits
- **Max Minions**: 3 per summon
- **Max Animation Steps**: 10
- **Max Effects**: 8 per attack

**Note:** GM may approve exceptions for special boss battles.

---

## ✨ BEST PRACTICES

### Naming
- ✅ `void_annihilation` - Good: lowercase, underscores
- ❌ `Void Annihilation!!!` - Bad: spaces, special chars
- ✅ `meteor_strike_v2` - Good: version numbering

### Balance
- Start with moderate damage (100-200)
- Don't stack too many effects (2-3 is good)
- Longer cooldown = more powerful
- Give players a way to counter (QTE, dodgeable)

### Visuals
- Use GIFs that match the attack theme
- Pick colors that stand out but aren't jarring
- Choose emoji icons that represent the attack

### Animation
- 2-4 steps is usually enough
- Don't make players wait too long (total < 10s)
- Build tension with messages
- Put the biggest impact at the climax

### Testing
- Ask yourself: "Is this fun to fight against?"
- Would you enjoy dodging this attack?
- Is the risk/reward balanced?
- Does it create interesting gameplay moments?

---

## 🆘 COMMON MISTAKES

### JSON Syntax Errors
```json
// ❌ WRONG - Missing comma
{
  "name": "Attack"
  "type": "special_attack"
}

// ✅ CORRECT
{
  "name": "Attack",
  "type": "special_attack"
}
```

### Invalid Effect Type
```json
// ❌ WRONG - "explode" is not a valid effect type
{
  "type": "explode",
  "damage": 500
}

// ✅ CORRECT - Use valid effect types
{
  "type": "damage",
  "value": 200
}
```

### Missing Required Fields
```json
// ❌ WRONG - Missing description
{
  "attack_id": "test",
  "name": "Test Attack",
  "type": "special_attack"
}

// ✅ CORRECT - All required fields
{
  "attack_id": "test",
  "name": "Test Attack",
  "description": "A test attack",
  "type": "special_attack",
  "category": "destructive",
  "damage": { "base": 100, "scaling": "fixed" },
  "effects": [...]
}
```

---

## 🎓 NEXT STEPS

1. **Copy** `ATTACK_TEMPLATE.json` or `ULTIMATE_TEMPLATE.json`
2. **Edit** to create your attack
3. **Validate** JSON syntax
4. **Submit** via `/submitattack`
5. **Wait** for GM approval
6. **Enjoy** your creation in-game!

---

## 📞 NEED HELP?

- Check the templates for working examples
- Ask in the Discord server
- Tag the GM for clarification
- Review approved attacks for inspiration

**Happy Creating!** ⚔️✨
