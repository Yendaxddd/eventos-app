# 🎯 ROADMAP ANALYSIS & IMPLEMENTATION PLAN - PHASE 2

## 🔧 IMMEDIATE FIX NEEDED: `/editvalues` Command

### Problem:
The command doesn't accept percentages properly because Discord slash commands use `float` type which expects decimal values (0.0-1.0), but users think in percentages (0-100).

### Solution:
**For Black Flash Chance:**
- Current: User must enter `0.05` for 5%
- Should be: User enters `5` and we convert to `0.05`

**Quick Fix Documentation:**
```python
# Change the parameter to accept int for percentage
# Then convert: black_flash_percentage / 100 = black_flash_chance
# Example: User enters 5 → We use 0.05 internally
```

**How to use it NOW:**
- `/editvalues black_flash_chance:0.05` = 5%
- `/editvalues black_flash_chance:0.10` = 10%
- `/editvalues player_hp:150` = 150 HP

---

## 📊 CURRENT ROADMAP STATUS

### ✅ COMPLETED (7/30)
1. ✅ Mas lore y revelaciones del pasado
2. ✅ 4 bossfights
3. ✅ 12 escenarios
4. ✅ Actual dying mechanic
5. ✅ REVENGE
6. ✅ Variable damage system
7. ✅ Anti-spam detection

### 🔨 ON DEVELOPMENT (8/30)
1. 🔨 Mecanica de combos
2. 🔨 Mecanica de vehiculos tierra/aire
3. 🔨 Crossover
4. 🔨 Mas mecanicas
5. 🔨 Hp bars
6. 🔨 Achievements
7. 🔨 Enemy allies

### ⏳ PENDING (15/30)
1. ⏳ Mecánica de carrera
2. ⏳ Mejores vistas (media)
3. ⏳ Mejor codigo
4. ⏳ Mejores bossfights
5. ⏳ Mejor estructura
6. ⏳ Buffs a los pjs
7. ⏳ Mecanicas de bossfights
8. ⏳ 2 Poderes especiales
9. ⏳ counter
10. ⏳ ulti
11. ⏳ slow time
12. ⏳ FAITH
13. ⏳ Support
14. ⏳ OST
15. ⏳ Shooting mechanic
16. ⏳ Killstreaks
17. ⏳ Adrenaline
18. ⏳ interrupting attacks
19. ⏳ Group mechanics
20. ⏳ Rhythm
21. ⏳ True psychosis

---

## 🎨 CREATIVE EXPANSION & CLARIFICATION NEEDED

Before implementing, I need clarification on these mechanics:

### 🏎️ 1. MECÁNICA DE CARRERA (Racing Mechanic)
**Possible Interpretations:**
- Chase sequences (escape from enemy)
- Vehicle races (who reaches checkpoint first)
- Speed-based QTE chains
- Distance/time tracking system

**Questions:**
- Is this a race BETWEEN players or AGAINST an enemy/timer?
- Do players accumulate "distance" with successful QTEs?
- Is there a finish line/goal?
- What happens if you lose/fall behind?

**Creative Expansion Ideas:**
- **Chase Mode**: Enemy pursuing, failure = get caught, damage
- **Checkpoint Racing**: Reach checkpoints within time limits
- **Speed Bonuses**: Faster QTE response = more distance traveled
- **Obstacles**: Random hazards that require specific actions

---

### 🎮 2. MECANICA DE COMBOS (Combo Mechanic) - ON DEVELOPMENT
**Current Understanding:**
- F1 starts, F2 extends, F3 cashes out
- Multipliers: 2x, 3x, 4x based on hits

**Questions:**
- Should combos carry BETWEEN QTEs or reset each time?
- What triggers combo increment? (Any success? Only parries?)
- Should different actions give different combo points?
- Combo breaks on failure or just doesn't increment?

**Creative Expansion Ideas:**
- **Combo Types**: 
  * "Perfect Combo" - All parries
  * "Defensive Combo" - All evades  
  * "Mixed Combo" - Variety bonus
- **Combo Rewards**:
  * Temporary invincibility at 10x
  * Team heal at 15x
  * Instant Black Flash at 20x
- **Visual Effects**: Progressive intensity, screen effects
- **Combo Share**: Team combos where everyone contributes

---

### 🚗 3. MECANICA DE VEHICULOS (Vehicle Mechanics) - ON DEVELOPMENT
**Possible Interpretations:**
- Players can "enter" vehicles for different abilities
- Ground vehicles vs Air vehicles have different mechanics
- Vehicle HP separate from player HP
- Vehicle-specific QTE types

**Questions:**
- Are vehicles temporary power-ups or persistent?
- Do they have their own HP/durability?
- What advantages do they provide? (Speed? Damage? Protection?)
- Can they be destroyed?
- How do players "get" a vehicle?

**Creative Expansion Ideas:**
- **Ground Vehicles**:
  * Tank: High HP, slow, damage reduction
  * Bike: Fast, fragile, speed bonuses
  * Car: Balanced, can ram enemies
- **Air Vehicles**:
  * Jet: Ultra fast, dogfight mechanics
  * Helicopter: Hovering, support abilities
  * Glider: Evasion bonuses, no damage
- **Vehicle Actions**: 
  * `*boost*` - Speed burst
  * `*shoot*` - Vehicle weapons
  * `*maneuver*` - Evasive action

---

### 🌟 4. CROSSOVER - ON DEVELOPMENT
**Possible Interpretations:**
- Characters from other series appear
- Special events with different mechanics
- Boss crossovers (e.g., DBZ villain appears)
- Ability crossovers (use powers from other series)

**Questions:**
- Is this narrative (story crossover) or mechanical (ability crossover)?
- Are crossover characters temporary or permanent?
- Do they have unique mechanics?
- Is this event-based or always available?

**Creative Expansion Ideas:**
- **Crossover Bosses**: Unique mechanics per universe
- **Crossover Abilities**: Temporary power-ups themed to other series
- **Crossover Events**: Limited-time special rules
- **Crossover Reactions**: Special interactions between universes

---

### 🎬 5. MEJORES VISTAS (Better Media/Visuals)
**Possible Interpretations:**
- More GIFs per action type
- Animated HP bars
- Rich embeds with images
- Boss splash screens
- Victory screens

**Questions:**
- Priority: GIFs, Embeds, or Both?
- Do you have GIF collections ready?
- Should media be random or context-specific?
- Performance concerns with many GIFs?

**Creative Expansion Ideas:**
- **Dynamic GIFs**:
  * Success tier GIFs (Good, Great, Perfect)
  * Character-specific GIFs
  * Boss-specific GIFs
  * Black Flash special animation
- **Enhanced Embeds**:
  * Player avatar in HP bar
  * Boss portrait with HP
  * Action thumbnails
  * Combo meter visualization

---

### 💪 6. BUFFS A LOS PJS (Character Buffs)
**Possible Interpretations:**
- Permanent stat increases
- Temporary power-ups
- Equipment/gear system
- Level-up system
- Achievement-based bonuses

**Questions:**
- Are buffs permanent or temporary?
- How are buffs earned? (Achievements? Currency? Time?)
- What can be buffed? (HP? Damage? Speed? BF chance?)
- Can buffs be lost?

**Creative Expansion Ideas:**
- **Buff Types**:
  * Passive: Always active (e.g., +10% HP)
  * Active: Must be triggered (e.g., shield ability)
  * Temporary: Duration-based (e.g., 5 minutes of +damage)
- **Buff Sources**:
  * Achievement unlocks
  * Boss defeats
  * Combo milestones
  * Checkpoint rewards
- **Buff Categories**:
  * Offensive: Damage, crit chance
  * Defensive: HP, damage reduction
  * Utility: Speed, cooldown reduction

---

### 🎭 7. 2 PODERES ESPECIALES (2 Special Powers)
**Possible Interpretations:**
- Two "ultimate" abilities per player
- Two distinct power systems
- Two team-wide abilities
- Two boss-specific counters

**Questions:**
- Are these PER PLAYER or shared by all?
- How are they activated? (Command? Hotkey? Auto?)
- What's the cooldown/charge system?
- Are they unique per character or universal?

**Creative Expansion Ideas:**
- **Power Slot 1: "Ultimate"**:
  * Massive damage burst
  * Requires charge (successful QTEs)
  * Single use per battle
  * Dramatic visual effect
- **Power Slot 2: "Support"**:
  * Team heal or buff
  * Shorter cooldown
  * More utility-focused
  * Can save losing battles

---

### ⚡ 8. COUNTER (Counter Mechanic)
**Current Understanding:**
- Separate from parry
- Has anti-spam (max 2 per 10s, 3rd gets countered)

**Questions:**
- What makes counter different from parry mechanically?
- Should counter do MORE damage than parry?
- Does counter have a tighter window?
- Should counter have a visual distinction?

**Creative Expansion Ideas:**
- **Counter Variants**:
  * Perfect Counter: Frame-perfect timing, massive damage
  * Counter Chain: Successful counter enables team counter
  * Counter Stance: Defensive mode, easier counters
- **Counter Rewards**:
  * Reflects damage to attacker
  * Stuns enemy (skip next QTE)
  * Opens enemy for team attack

---

### 🌊 9. SLOW TIME
**Possible Interpretations:**
- Extends QTE windows temporarily
- Bullet-time visual effect
- Strategic ability with cooldown
- Last-resort mechanic at low HP

**Questions:**
- Is this a player ability or automatic effect?
- How much does it slow? (2x window? 3x?)
- How long does it last? (One QTE? 10 seconds?)
- Cooldown or limited uses?

**Creative Expansion Ideas:**
- **Slow Time Triggers**:
  * Manual activation (F5 hotkey?)
  * Auto-trigger at 10 HP
  * Achievement reward
  * Costs resource (Faith?)
- **Slow Time Effects**:
  * Windows double in size
  * Visual screen effect
  * Audio slowdown
  * Extended combo time
- **Slow Time Costs**:
  * One use per event
  * Costs 20 HP to activate
  * Requires full FAITH meter
  * Cooldown: 60 seconds

---

### 🙏 10. FAITH System
**Most Mysterious Mechanic**

**Possible Interpretations:**
- Resource that builds through team actions
- Dead players contribute to living
- Miracle save mechanic
- Belief-based power system
- Team synergy meter

**Questions:**
- How is FAITH gained? (Team actions? Saves? Combos?)
- What does FAITH DO? (Resurrection? Power-up? Miracle?)
- Is it shared by team or per player?
- Does it decay or persist?

**Creative Expansion Ideas:**
- **FAITH Gauge (0-100)**:
  * +10 for successful saves
  * +5 for parries
  * +20 when teammate dies (belief)
  * -30 when spent
- **FAITH Abilities**:
  * **50 FAITH**: Shield ally from one attack
  * **75 FAITH**: Heal team 30 HP
  * **100 FAITH**: **Resurrect one dead player**
- **Dead Player Contribution**:
  * Dead players add +1 FAITH per living player QTE success
  * Creates "They believe in you!" moment
  * Keeps dead players engaged
  * Can save the team from wipe

---

### 💉 11. SUPPORT Mechanic
**Possible Interpretations:**
- Healing action type
- Support role class
- Team buff abilities
- Resurrection mechanic

**Questions:**
- Is this a new action type like evade/parry?
- Is it a role or available to everyone?
- What can Support do? (Heal? Buff? Cleanse?)
- Cooldown system?

**Creative Expansion Ideas:**
- **Support Actions**:
  * `*heal*` - Restore 30 HP to target
  * `*shield*` - Block next damage
  * `*buff*` - Increase damage 50% for 30s
  * `*cleanse*` - Remove debuffs
- **Support Limitations**:
  * Can't target self
  * 30-second cooldown
  * Requires line-of-sight (same QTE)
  * Costs 10 HP to use (sacrifice)

---

### 🎵 12. OST (Soundtrack) System
**Possible Interpretations:**
- Music links per boss phase
- Ambient music per scenario
- Player-controlled playlist
- Dynamic music based on HP/intensity

**Questions:**
- Are these YouTube links posted in chat?
- Does bot control playback or just suggest?
- Per event or continuous?
- Community-curated or fixed?

**Creative Expansion Ideas:**
- **Dynamic Music**:
  * Calm at full HP
  * Intense at <50% HP
  * Dramatic during REVENGE
  * Epic during boss finale
- **Boss Themes**:
  * Each boss has signature track
  * Phase transitions change music
  * Victory fanfare on win
- **Implementation**:
  * Post YouTube link as embed
  * Timestamp for phase changes
  * Community playlist integration
  * Optional (some prefer silence)

---

### 🔫 13. SHOOTING Mechanic
**Possible Interpretations:**
- New QTE action type
- Ranged combat mode
- Accuracy-based system
- Multi-target mechanic

**Questions:**
- Is this `*shoot*` action like evade/parry?
- Does it do damage to enemies/boss?
- Is there accuracy/miss chance?
- Ammo or cooldown system?

**Creative Expansion Ideas:**
- **Shooting Actions**:
  * `*shoot*` - Basic attack, timing-based damage
  * `*aimed_shot*` - Precise timing, high damage
  * `*rapid_fire*` - Multiple quick QTEs
  * `*reload*` - Required after X shots
- **Shooting Mechanics**:
  * Early: Graze, low damage
  * Perfect: Critical hit, high damage
  * Late: Miss, no damage
- **Boss Integration**:
  * Break boss armor
  * Interrupt boss attacks
  * Target weak points
  * Support role: Cover fire

---

### 🎯 14. KILLSTREAKS
**Possible Interpretations:**
- Consecutive successful QTEs
- Enemy defeats tracked
- Escalating rewards
- Call of Duty style system

**Questions:**
- What counts as a "kill"? (QTE success? Boss phase?)
- Are streaks personal or team?
- What do streaks unlock?
- Do streaks persist across events?

**Creative Expansion Ideas:**
- **Streak Rewards**:
  * 3 Streak: Minor buff (+10% damage)
  * 5 Streak: Special ability unlocked
  * 7 Streak: Team heal
  * 10 Streak: **LEGENDARY** status, special effect
- **Streak Types**:
  * Perfect Streak: Only perfects
  * Combo Streak: Mixed actions
  * Speed Streak: Ultra-fast responses
- **Announcements**:
  * "DOUBLE KILL!"
  * "KILLING SPREE!"
  * "UNSTOPPABLE!"
  * "GODLIKE!"

---

### 💪 15. ADRENALINE System
**Possible Interpretations:**
- Resource that builds with action
- Temporary speed boost
- Risk/reward mechanic
- Combat flow enhancer

**Questions:**
- How does adrenaline build? (QTE successes?)
- What does max adrenaline DO?
- Is it temporary or permanent?
- Does it decay over time?

**Creative Expansion Ideas:**
- **Adrenaline Gauge (0-100)**:
  * +10 per QTE success
  * +20 for perfect timing
  * +30 for near-death experience (<20 HP)
  * Drains 5 per second when not acting
- **Adrenaline Effects**:
  * **50% Full**: +10% damage
  * **75% Full**: Faster QTE windows (tighter but more rewarding)
  * **100% Full**: **OVERDRIVE MODE**
- **OVERDRIVE MODE**:
  * All successful QTEs are crits
  * HP regeneration (+5/sec)
  * Visual screen effect
  * Lasts 15 seconds
  * Exhaustion after (-20% damage for 30s)

---

### ⚡ 16. INTERRUPTING ATTACKS
**Possible Interpretations:**
- Cancel enemy attacks mid-charge
- Perfect-timed prevention
- Team coordination mechanic
- Boss-specific counters

**Questions:**
- Is this during boss "telegraph" phase?
- What's the window to interrupt?
- What happens on success? (Attack canceled? Damage reflected?)
- Is it per player or team effort?

**Creative Expansion Ideas:**
- **Interrupt Mechanics**:
  * Boss shows telegraph (3 seconds)
  * Players must `*interrupt*` during window
  * Success: Attack canceled, boss stunned
  * Failure: Attack executes, heavy damage
- **Interrupt Types**:
  * Solo interrupt: One perfect timing
  * Team interrupt: 3+ players together
  * Counter interrupt: Requires counter action
- **Rewards**:
  * Stun boss (skip boss turn)
  * Expose weak point (2x damage)
  * Break boss combo chain
  * Team buff (shield)

---

### 🏆 17. ACHIEVEMENTS - ON DEVELOPMENT
**Current Understanding:**
- Track player accomplishments
- Unlock special rewards/titles

**Questions:**
- Do achievements give tangible rewards or just prestige?
- Are they hidden or visible?
- Tracked per character or per player?
- Any "secret" achievements?

**Creative Expansion Ideas:**
- **Achievement Categories**:
  * **Combat**: First Blood, 100 QTEs, 10 Black Flashes
  * **Survival**: Survive with 1 HP, No Damage Taken, Clutch Win
  * **Team**: Save 10 allies, Perfect Sync, Comeback King
  * **Mastery**: All Evades, All Parries, Speed Demon
  * **Secret**: Hidden conditions, easter eggs
- **Rewards**:
  * Titles (displayed in `/mystats`)
  * Stat bonuses (+5% BF chance)
  * Cosmetic effects (special embeds)
  * Unlockable abilities

---

### 👥 18. GROUP MECHANICS
**Possible Interpretations:**
- Enhanced team coordination features
- Synchronized actions
- Team combos
- Shared resources

**Questions:**
- What's missing from current group QTEs?
- Are these new actions or enhanced existing?
- Do players need to coordinate timing?
- Shared rewards?

**Creative Expansion Ideas:**
- **Synchronized Actions**:
  * All players `*sync*` within 0.5s = team bonus
  * Combo multiplier if all succeed
  * Failure penalties if anyone fails
- **Team Abilities**:
  * **Formation**: Players declare roles (tank, DPS, support)
  * **Chain Attack**: Success enables next player's bonus
  * **Last Stand**: All players <50% HP = team buff
- **Shared Resources**:
  * Team FAITH meter
  * Group combo counter
  * Collective killstreak

---

### 🎶 19. RHYTHM Mechanic
**Possible Interpretations:**
- Musical timing-based QTEs
- Beat-matching system
- Pattern recognition
- Dance Dance Revolution style

**Questions:**
- Is this a separate mode or integrated?
- Does it require music?
- Are beats pre-defined or random?
- Punishment for off-beat?

**Creative Expansion Ideas:**
- **Rhythm QTEs**:
  * Show beat pattern: `o-o-o--o-o--o`
  * Players must match the rhythm
  * Perfect rhythm = big bonus
  * Off-beat = penalty
- **Difficulty Scales**:
  * Easy: Slow beats, 4/4 time
  * Hard: Complex polyrhythms, syncopation
  * Impossible: Double-time, offbeats
- **Integration**:
  * Special boss phases
  * Certain scenarios
  * Optional challenge mode
  * Combo ender (cash out with rhythm game)

---

### 👹 20. ENEMY ALLIES - ON DEVELOPMENT
**Possible Interpretations:**
- Boss summons minions
- Split player attention
- Multi-target combat
- Priority target system

**Questions:**
- Are these additional QTE targets?
- Do they attack players?
- Can they be killed?
- How many at once?

**Creative Expansion Ideas:**
- **Minion Types**:
  * **Scouts**: Fast, low HP, evade-focused
  * **Tanks**: Slow, high HP, parry-focused
  * **Support**: Heals boss, priority target
  * **Berserker**: High damage, must interrupt
- **Mechanics**:
  * Boss summons during phase transitions
  * Split QTE targets (some for minions, some for boss)
  * Minions enable boss specials if alive
  * Reward for killing all minions quickly
- **Strategy**:
  * Ignore and focus boss (risky)
  * Kill minions first (safe but slow)
  * Split team (requires coordination)

---

### 🌀 21. TRUE PSYCHOSIS
**Most Cryptic Mechanic**

**Possible Interpretations:**
- Reality-bending final phase
- Psychological horror element
- Unpredictable mechanics
- Meta-breaking moment
- Secret endgame content

**Questions:**
- Is this a boss phase? A mode? A state?
- What makes it "true" vs regular psychosis?
- Is it accessible or hidden?
- What are its effects?

**Creative Expansion (WILD) Ideas:**
- **Reality Break**:
  * QTE text becomes garbled
  * Windows reverse (shorter = better?)
  * Success/failure messages swap
  * Visual distortion effects
  * Boss attacks without telegraph
- **Psychological Effects**:
  * HP bars lie about values
  * Fake death messages
  * Mirror QTEs (do opposite)
  * Teammate hallucinations
  * Time distortion
- **Trigger Conditions**:
  * Secret boss phase at 1% HP
  * Entire team dies simultaneously
  * 100+ QTE streak
  * Specific item combination
  * April Fools event
- **Victory Condition**:
  * Resist the madness
  * Complete impossible QTE sequence
  * Team synchronization under chaos
  * Break the illusion (meta action?)

---

## 🎯 RECOMMENDED IMPLEMENTATION PRIORITY

### PHASE 2A: Core Combat (2-3 weeks)
1. Fix `/editvalues` (percentage support)
2. **Counter** mechanic (anti-spam working, needs distinction)
3. **Shooting** mechanic (ranged combat)
4. **Interrupting Attacks** (boss counterplay)
5. **Support** actions (healing/buffing)

### PHASE 2B: Resources & Progression (2-3 weeks)
6. **FAITH** system (team resource)
7. **Adrenaline** meter (combat flow)
8. **Killstreaks** (reward system)
9. **Achievements** (progression tracking)
10. **Buffs** system (character growth)

### PHASE 2C: Advanced Mechanics (3-4 weeks)
11. **2 Special Powers** (ultimates)
12. **Slow Time** (strategic ability)
13. **Combo** system (manual, already started)
14. **Racing** mechanic (chase sequences)
15. **Rhythm** system (musical timing)

### PHASE 2D: Content & Polish (2-3 weeks)
16. **Better Media** (GIFs, embeds)
17. **OST** integration (music)
18. **Boss Mechanics** (enhanced fights)
19. **Group Mechanics** (team synergy)
20. **Vehicle** mechanics (if still desired)

### PHASE 2E: Endgame & Secrets (1-2 weeks)
21. **Enemy Allies** (boss minions)
22. **Crossover** content (special events)
23. **True Psychosis** (secret content)

---

## ❓ QUESTIONS SUMMARY

Before implementing ANY of these mechanics, I need to know:

### 🔥 HIGHEST PRIORITY (Need answers to proceed):
1. **Counter** - What makes it different from parry?
2. **FAITH** - How is it gained and what does it do?
3. **2 Special Powers** - Per player or universal?
4. **Racing** - Race against what/who?

### 🟡 MEDIUM PRIORITY:
5. **Vehicles** - Are they worth the complexity?
6. **Shooting** - Just a new action or a whole system?
7. **Support** - New action type or role?
8. **Rhythm** - Integrated or separate mode?

### 🟢 LOW PRIORITY (Can infer/design):
9. **Media** - GIF library ready?
10. **OST** - YouTube links or something else?
11. **True Psychosis** - What IS this?
12. **Crossover** - Narrative or mechanical?

---

## 🚀 NEXT STEPS

1. **Answer priority questions** about mechanics
2. **Fix `/editvalues`** for proper percentage support
3. **Choose 2-3 mechanics** from Phase 2A to start
4. **Switch to Code mode** to implement
5. **Test and iterate**

**Ready to proceed! What mechanics should we tackle first?** 🎮