# 📦 Special Objects System - Tutorial & Reference

## Overview

Special Objects are data-driven game mechanics defined in JSON files. Instead of hardcoding complex abilities, you define them in structured files that the bot loads and interprets at runtime.

---

## Quick Start

1. Copy a template from `/templates/` to `/pending/`
2. Edit the JSON file with your object's data
3. Save the file
4. GM will be notified and can review
5. Once approved, it moves to `/approved/` and activates

---

## Folder Structure

```
data/special_objects/
├── templates/       ← Copy from here
│   ├── TUTORIAL.md
│   ├── template_passive.json
│   ├── template_adaptation.json
│   └── template_triggered.json
├── pending/         ← Put new objects here for review
├── approved/        ← Active objects (GM moves here)
└── archive/         ← Old versions, rejected files
```

---

## JSON Schema Reference

### Basic Structure

```json
{
  "id": "unique_identifier",
  "name": "Display Name",
  "description": "What this object does",
  "version": "1.0",
  "author": "YourName",
  "type": "adaptation | passive | triggered | consumable",
  
  "assignment": { },
  "trigger": { },
  "tracking": { },
  "thresholds": { },
  "conditionals": [ ],
  "effects": [ ]
}
```

---

### Assignment Block

Defines WHO can use this object.

```json
"assignment": {
  "type": "character",
  "characters": ["CharacterName1", "CharacterName2"],
  "transferable": false
}
```

| Field | Values | Description |
|-------|--------|-------------|
| `type` | `"character"`, `"player"`, `"both"` | Who it's assigned to |
| `characters` | Array of strings | Exact Tupper character names |
| `players` | Array of user IDs | Discord user IDs |
| `transferable` | `true`/`false` | Can be given to others |

---

### Trigger Block

Defines HOW this object activates.

```json
"trigger": {
  "command": "*adapt*",
  "window": "parry",
  "replaces_action": true,
  "cooldown": 0
}
```

| Field | Values | Description |
|-------|--------|-------------|
| `command` | String | The command to type (e.g., `"*adapt*"`) |
| `window` | `"parry"`, `"counter"`, `"evade"`, `"any"`, `"passive"` | When it can be used |
| `replaces_action` | `true`/`false` | Does it replace the normal action? |
| `cooldown` | Number (seconds) | Cooldown between uses |

---

### Tracking Block

Defines WHAT data to track for this object.

```json
"tracking": {
  "type": "per_difficulty",
  "values": ["easy", "medium", "hard", "impossible"],
  "persist": true
}
```

| Field | Values | Description |
|-------|--------|-------------|
| `type` | `"per_difficulty"`, `"global"`, `"per_boss"`, `"per_attack"` | What to track separately |
| `values` | Array | The categories to track |
| `persist` | `true`/`false` | Save between sessions |

---

### Thresholds Block

Defines MILESTONES and their rewards.

```json
"thresholds": {
  "easy": [
    {"spins": 4, "effects": ["damage_reduction:10", "heal:10"]},
    {"spins": 7, "effects": ["damage_reduction:30", "heal:20"]},
    {"spins": 10, "effects": ["damage_reduction:50", "heal:50"]}
  ],
  "medium": [
    {"spins": 4, "effects": ["damage_reduction:10"]},
    {"spins": 6, "effects": ["damage_reduction:40"]},
    {"spins": 10, "effects": ["damage_reduction:50"]}
  ]
}
```

Each threshold is an object with:
- `spins`: Number of uses to reach this threshold
- `effects`: Array of effect strings (see Effects Syntax below)

---

### Conditionals Block

Defines COMPLEX RULES with if/then logic.

```json
"conditionals": [
  {
    "if": "spins.impossible >= 12",
    "then": ["damage_reduction.easy:100", "damage_reduction.medium:+50"]
  },
  {
    "if": "enemy.stunned",
    "then": ["guaranteed_hit", "black_flash", "boss_damage_percent:20"]
  }
]
```

#### Condition Syntax

| Pattern | Example | Description |
|---------|---------|-------------|
| `spins.DIFFICULTY` | `spins.hard >= 10` | Check spin count for difficulty |
| `hp.percent` | `hp.percent <= 20` | Player HP percentage |
| `enemy.stunned` | `enemy.stunned` | Boolean check |
| `boss.active` | `boss.active` | Is there an active boss |
| `difficulty.current` | `difficulty.current == "impossible"` | Current QTE difficulty |

#### Operators
- `>=`, `<=`, `>`, `<`, `==`, `!=`
- `and`, `or` for combining

---

## Effects Syntax

### Simple Effects

```
damage_reduction:50       → Reduce incoming damage by 50%
heal:30                   → Heal 30 HP
heal_percent:15           → Heal 15% of max HP
charge_ultimate:100       → Charge ultimate by 100%
charge_ultimate_full      → Fully charge ultimate
stun_enemy:2.5            → Stun enemy for 2.5 seconds
damage_boss:50            → Deal 50 damage to boss
boss_damage_percent:20    → Deal 20% of boss max HP
guaranteed_hit            → Next attack cannot miss
black_flash               → Trigger a black flash
invoke_qte:medium         → Create a QTE of that difficulty
cooldown_reduce:30        → Reduce cooldowns by 30 seconds
```

### Modifier Prefixes

```
damage_reduction:50       → SET to 50%
damage_reduction:+20      → ADD 20% to current
damage_reduction.easy:100 → Only for easy difficulty
```

### Special Effects

```
copy_attack               → Copy the current attack (Raiden)
counter_for_enemy         → Reverse counter mechanic
remove_timing_requirement → No perfect timing needed
on_evade:heal_percent:15  → Trigger effect on successful evade
```

---

## Complete Example: Seth's Adaptation

```json
{
  "id": "seth_adaptation",
  "name": "Reactive Adaptation",
  "description": "Seth adapts to damage over time, reducing incoming damage and healing at thresholds.",
  "version": "1.0",
  "author": "GM",
  "type": "adaptation",
  
  "assignment": {
    "type": "character",
    "characters": ["🌑┋𝐒𝐞𝐭𝐡", "Seth"],
    "transferable": false
  },
  
  "trigger": {
    "command": "*adapt*",
    "window": "parry",
    "replaces_action": true,
    "cooldown": 0
  },
  
  "tracking": {
    "type": "per_difficulty",
    "values": ["easy", "medium", "hard", "impossible"],
    "persist": true
  },
  
  "thresholds": {
    "easy": [
      {"spins": 4, "effects": ["damage_reduction:10", "heal:10"]},
      {"spins": 7, "effects": ["damage_reduction:30", "heal:20"]},
      {"spins": 10, "effects": ["damage_reduction:50", "heal:50"]}
    ],
    "medium": [
      {"spins": 4, "effects": ["damage_reduction:10", "heal:10"]},
      {"spins": 6, "effects": ["damage_reduction:40", "heal:20"]},
      {"spins": 10, "effects": ["damage_reduction:50", "heal:50"]}
    ],
    "hard": [
      {"spins": 3, "effects": ["damage_reduction:15", "heal:10"]},
      {"spins": 7, "effects": ["damage_reduction:40", "heal:20"]},
      {"spins": 10, "effects": ["damage_reduction:70", "heal:50"]}
    ],
    "impossible": [
      {"spins": 2, "effects": ["damage_reduction:20", "heal:10"]},
      {"spins": 6, "effects": ["damage_reduction:60", "heal:20"]},
      {"spins": 9, "effects": ["damage_reduction:70", "heal:50"]},
      {"spins": 12, "effects": ["damage_reduction:90"]}
    ]
  },
  
  "conditionals": [
    {
      "if": "spins.impossible >= 12",
      "then": [
        "damage_reduction.easy:100",
        "damage_reduction.medium:+50",
        "damage_reduction.hard:+10"
      ]
    }
  ]
}
```

---

## GM Commands

| Command | Description |
|---------|-------------|
| `/listobjects` | List all approved special objects |
| `/listpending` | List objects awaiting approval |
| `/approveobject <filename>` | Approve and activate an object |
| `/rejectobject <filename> [reason]` | Reject with optional reason |
| `/reloadobjects` | Hot-reload all approved objects |
| `/testobject <filename>` | Dry-run validation without activating |
| `/archiveobject <id>` | Move object to archive (deactivate) |

---

## Tips

1. **Start simple** - Copy a template, change only what you need
2. **Test first** - Use `/testobject` before approving
3. **Version your files** - Keep old versions in archive for reference
4. **Use descriptive IDs** - `seth_adaptation` not `obj1`
5. **Document effects** - Use the description field well

---

## Troubleshooting

**Object not loading?**
- Check JSON syntax (use a validator)
- Ensure file is in `/approved/` folder
- Run `/reloadobjects`

**Effects not working?**
- Check effect syntax matches reference
- Verify trigger conditions are met
- Check console logs for errors

**Threshold not triggering?**
- Verify spin count with `/checkadaptation @user`
- Check difficulty matches

---

## Need Help?

Contact the GM or check the bot logs for detailed error messages.
