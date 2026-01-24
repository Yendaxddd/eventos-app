# 🎯 NEW MECHANICS IMPLEMENTATION GUIDE

## ✅ Phase 1 Mechanics - COMPLETED

All requested mechanics have been successfully implemented and integrated!

---

## 🎲 1. Variable Damage System

### How It Works
Damage is no longer fixed - it varies by difficulty level with randomization:

```python
Easy:       1-3 damage   (Random)
Medium:     1-5 damage   (Random)
Hard:       1-10 damage  (Random)
Impossible: 15 damage    (Fixed)
```

### Impact on Gameplay

**Easy Fights (1-3 damage):**
- 5 failures = 5-15 damage → Very forgiving
- Players can make many mistakes
- Good for learning/casual events

**Medium Fights (1-5 damage):**
- 5 failures = 5-25 damage → Moderate punishment
- Balance between mercy and consequence
- Standard for most events

**Hard Fights (1-10 damage):**
- 5 failures = 5-50 damage → High variance
- Can get lucky (low rolls) or punished hard
- Adds exciting unpredictability

**Impossible Fights (15 damage):**
- 5 failures = 75 damage → Severe but survivable
- Reserved for epic boss moments
- Requires near-perfect execution

### Example Scenarios

**Scenario 1: Lucky Easy Event**
```
Fail 1: -1 HP  (100 → 99)
Fail 2: -1 HP  (99 → 98)
Fail 3: -2 HP  (98 → 96)
Fail 4: -3 HP  (96 → 93)
Fail 5: -2 HP  (93 → 91)
Result: Still 91 HP after 5 failures! ✅
```

**Scenario 2: Unlucky Hard Event**
```
Fail 1: -9 HP  (100 → 91)
Fail 2: -10 HP (91 → 81)
Fail 3: -8 HP  (81 → 73)
Fail 4: -10 HP (73 → 63)
Fail 5: -9 HP  (63 → 54)
Result: Down to 54 HP - critical! ⚠️
```

---

## ⚡ 2. REVENGE Mode System

### Activation
**Triggers automatically at 20% HP (20 HP or below)**

### Visual Feedback
Epic crimson embed message:
```
⚡ REVENGE MODE ACTIVATED ⚡
[Player] enters a state of desperation!

💥 +50% Damage
⚡ Faster Parry Windows
🌟 +10% Black Flash Chance
```

### Mechanical Changes

#### 1. Parry Window Adjustments
```python
# Normal parry window (Medium): 2.5s - 4.5s
# REVENGE parry window:         2.2s - 4.2s

Shift:      -0.3s earlier (respond faster)
Tightness:  70% of original (more precise)
```

**Why This Matters:**
- Earlier window = Must react faster
- Tighter window = Requires precision
- High risk, high reward gameplay

#### 2. Damage Multiplier
```python
Base damage:    20
REVENGE damage: 30 (+50%)
```

**Effect:**
- Successful parries/evades do MORE damage back to enemies
- Makes desperate situations dramatic
- Clutch plays more impactful

#### 3. Black Flash Bonus
```python
Base BF chance:    10% (at cap)
REVENGE BF chance: 20% (+10%)
```

**Effect:**
- Doubles chance of epic moments
- Rewards skill under pressure
- Creates memorable comebacks

### Strategic Implications

**For Players:**
- Don't give up at low HP
- Practice precision timing
- REVENGE mode is a comeback mechanic

**For Narrators:**
- Low HP = most exciting phase
- Plan boss phases around this
- Allows underdog victories

### Example REVENGE Sequence

```
Player HP: 22 → Takes 5 damage → 17 HP
🔥 REVENGE MODE ACTIVATED!

Next QTE:
- Normal timing:  Parry at 3.5s
- REVENGE timing: Parry at 3.2s (earlier!)
- Window:         2.2s - 4.2s (tighter!)
- Success? → Deal 30 damage + possible Black Flash!
```

---

## 🏥 3. HP Regeneration Checkpoints

### How to Use
**Press F8** to trigger a checkpoint heal

### What Happens
1. All living players heal **+30 HP**
2. Epic green embed announces checkpoint
3. Lists all healed players
4. Console shows heal count

### Visual Feedback
```
🏥 CHECKPOINT: Checkpoint 1
All players restored 30 HP!

@Player1 @Player2 @Player3
```

### Strategic Use Cases

**During Boss Fights:**
```
Phase 1: Boss at 75% HP
  → Players at 50-70 HP
  → F8 Checkpoint!
  → Players at 80-100 HP
Phase 2: Continue with renewed health
```

**Between Events:**
```
Event 1 Complete → Players at 40-60 HP
  → F8 Checkpoint!
  → Event 2 Start → Players ready!
```

**Narrative Moments:**
```
"You find a healing shrine..."
  → F8 Checkpoint!
"You rest at the camp..."
  → F8 Checkpoint!
```

### Healing Limits
- Cannot heal above max HP (100)
- Only affects living players
- Dead players stay dead

### Example Heal Sequence
```
Player A: 45 HP → +30 → 75 HP ✅
Player B: 85 HP → +15 → 100 HP (capped)
Player C: 0 HP  → +0  → 0 HP (dead)
```

---

## 🎮 COMPLETE HOTKEY REFERENCE

### QTE Triggers
| Hotkey | Action |
|--------|--------|
| **F9** | Single Easy QTE |
| **F10** | Single Medium QTE |
| **F11** | Single Hard QTE |
| **F12** | Single Impossible QTE |
| **Shift+F9** | Group Easy QTE |
| **Shift+F10** | Group Medium QTE |
| **Shift+F11** | Group Hard QTE |
| **Shift+F12** | Group Impossible QTE |
| **F8** | 🏥 Checkpoint (+30 HP to all) |

---

## 💡 GAMEPLAY STRATEGY GUIDE

### For Narrators

**Event Pacing:**
```
1. Start: Easy/Medium QTEs (warm up)
2. Middle: Hard QTEs (build tension)
3. Boss Phase 1: Hard QTEs
4. Checkpoint: F8 (brief respite)
5. Boss Phase 2: Impossible QTEs
6. Finale: REVENGE mode clutch moments
```

**Damage Balancing:**
```
Easy Event:    10-15 QTEs, mostly Easy/Medium
Normal Event:  8-12 QTEs, mix of all
Hard Event:    6-10 QTEs, mostly Hard/Impossible
Boss Fight:    15-20 QTEs with checkpoints
```

**Checkpoint Timing:**
```
✅ DO use checkpoints:
- Between boss phases
- After major story beats
- When 50%+ players below 50 HP

❌ DON'T spam checkpoints:
- More than once per 5 minutes
- During active combat
- When players above 80 HP
```

### For Players

**Surviving Hard Events:**
- Focus on Medium/Hard practice first
- Master timing before Impossible
- REVENGE mode is your friend
- Trust your teammates for saves

**Maximizing REVENGE:**
- Don't panic at low HP
- It's a BUFF, not a punishment
- Practice earlier timing
- Use for Black Flash attempts

**Team Coordination:**
- Support players with saves
- Communicate timing
- Share tips in chat
- Celebrate clutch moments

---

## 📊 DAMAGE PROBABILITY TABLE

### Expected Damage Per Failure

| Difficulty | Min | Max | Average | 5 Failures (Avg) |
|------------|-----|-----|---------|------------------|
| Easy | 1 | 3 | 2 | 10 HP |
| Medium | 1 | 5 | 3 | 15 HP |
| Hard | 1 | 10 | 5.5 | 27.5 HP |
| Impossible | 15 | 15 | 15 | 75 HP |

### REVENGE Thresholds

| Starting HP | Fails to REVENGE | HP at REVENGE |
|-------------|------------------|---------------|
| 100 | 4 (Medium) | 15-20 HP |
| 100 | 3 (Hard) | 10-20 HP |
| 100 | 1 (Impossible) | Dead (15 HP left if started at 35) |

### Survival Rates (Estimated)

**Without Checkpoints:**
```
Short Event (5 QTEs):
  Easy:       95% survival
  Medium:     85% survival
  Hard:       65% survival
  Impossible: 30% survival

Long Event (15 QTEs):
  Easy:       75% survival
  Medium:     45% survival
  Hard:       20% survival
  Impossible: Dead without skill
```

**With Checkpoints (1 per 10 QTEs):**
```
Long Event (20 QTEs + 2 Checkpoints):
  Easy:       90% survival
  Medium:     75% survival
  Hard:       55% survival
  Impossible: 40% survival
```

---

## 🎬 EXAMPLE EVENT FLOW

### "The Desperate Stand" (Boss Fight)

**Setup:**
- 4 players
- Boss with 3 phases
- 20 minute event

**Phase 1: The Opening (0-6 min)**
```
QTEs: 5x Medium (1-5 damage each)
Player HP: 100 → ~85 HP
Mood: Confident, learning boss patterns
```

**Phase 2: The Pressure (6-12 min)**
```
QTEs: 6x Hard (1-10 damage each)
Player HP: 85 → ~50 HP
Mood: Tense, some failures
Deaths: 0-1 players
```

**🏥 CHECKPOINT - "The boss stumbles, giving you a moment to breathe"**
```
F8 Pressed
All living players: +30 HP
Player HP: 50 → 80 HP
Mood: Relieved, ready for final phase
```

**Phase 3: The Finale (12-20 min)**
```
QTEs: 8x Impossible (15 damage each)
Player HP: 80 → 20-40 HP
Mood: DESPERATE

Player A: 18 HP ⚡ REVENGE ACTIVATED
Player B: 22 HP ⚡ REVENGE ACTIVATED
Player C: Dead 💀
Player D: 45 HP

Final QTE:
  Player A: Perfect parry + BLACK FLASH!
  Player B: Success!
  Player D: Success!

BOSS DEFEATED! 🎉
```

**Result:**
- Epic struggle
- Deaths mattered
- REVENGE mode clutch
- Checkpoint strategic
- Memorable victory

---

## 🔧 CONFIGURATION OPTIONS

### Adjustable Values (in code)

**HP System:**
```python
self.max_hp = 100                # Starting/max HP
self.regen_amount = 30           # Checkpoint heal amount
```

**Damage Ranges:**
```python
self.damage_ranges = {
    'easy': (1, 3),              # Min, Max
    'medium': (1, 5),
    'hard': (1, 10),
    'impossible': (15, 15)
}
```

**REVENGE Mode:**
```python
self.revenge_threshold = 0.20    # 20% HP trigger
self.revenge_parry_shift = -0.3  # Window shift (seconds)
self.revenge_parry_tightness = 0.7  # 70% of original width
self.revenge_damage_multiplier = 1.5  # 150% damage
self.revenge_bf_bonus = 0.10     # +10% Black Flash
```

---

## ✅ TESTING CHECKLIST

Before your first event with new mechanics:

- [ ] Test variable damage (trigger Easy vs Impossible)
- [ ] Verify REVENGE activates at 20 HP
- [ ] Confirm parry windows shift in REVENGE
- [ ] Test checkpoint heal (F8)
- [ ] Verify dead players don't get healed
- [ ] Check HP bars update correctly
- [ ] Confirm damage shows in console
- [ ] Test Black Flash bonus in REVENGE

---

## 🎯 QUICK REFERENCE CARD

**For Narrators During Events:**

```
F9-F12:        Single QTEs (Easy → Impossible)
Shift+F9-F12:  Group QTEs
F8:            Checkpoint Heal (+30 HP)

Damage:
  Easy = 1-3
  Medium = 1-5
  Hard = 1-10  
  Impossible = 15

REVENGE at 20 HP:
  ⚡ Earlier timing
  💥 +50% damage
  🌟 +10% Black Flash

Checkpoint every 10 QTEs recommended
```

---

## 🚀 NEXT PHASE FEATURES (Coming Soon)

Based on your roadmap:

**Phase 2:**
- Counter mechanic (max 2/10s, 3rd countered)
- Combo system (F1/F2/F3 controls)
- Support/Heal action
- Adrenaline meter

**Phase 3:**
- FAITH system
- Killstreaks
- Shooting mechanic
- Slow time ability

**Phase 4+:**
- Boss mechanics
- Vehicle systems
- Racing sequences
- And much more!

---

**The foundation is solid! Test these mechanics and provide feedback for further refinement.** 🎮