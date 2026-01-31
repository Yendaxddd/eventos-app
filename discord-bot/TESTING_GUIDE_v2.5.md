# Testing Guide v2.5 - "The Tribunal Update"

## 🧪 Pre-Testing Setup

### Requirements
1. Python 3.10+ with all dependencies installed
2. Discord bot token configured in `config.json`
3. **Ollama running locally** (for Court Trial AI judging)
4. Test Discord server with bot permissions

### Start Ollama (for Court Trial tests)
```bash
# Pull the model if not already done
ollama pull llama3:8b

# Create the custom model
ollama create elbot -f ../Modelfile

# Verify it's running
ollama list
```

### Start the Bot
```bash
cd discord-bot
python advanced_qte_hp_system_debug.py
```

---

## 📋 Test Checklist

### 1. QTE Variations

#### ✅ Standard QTE
- [ ] Trigger a battle/boss fight
- [ ] Verify standard QTE mentions player and shows difficulty
- [ ] Test `*evade*` within time window → SUCCESS
- [ ] Test `*parry*` within time window → SUCCESS + counter opportunity
- [ ] Test timeout → FAIL message

#### ✅ Combo QTE
- [ ] Keep triggering QTEs until Combo appears (15% chance)
- [ ] Verify it targets ONE player with 5 sequential QTEs
- [ ] Test completing all 5 → SUCCESS
- [ ] Test failing mid-chain → Shows which QTE failed
- [ ] Verify timing is slightly more lenient (+0.5s)

#### ✅ Direction QTE
- [ ] Keep triggering until Direction QTE appears (15% chance)
- [ ] Verify arrow emoji is shown (←→↑↓)
- [ ] Test inputting OPPOSITE direction → SUCCESS
- [ ] Test inputting SAME direction → FAIL
- [ ] Commands to test: `*left*`, `*right*`, `*up*`, `*down*`

#### ✅ Fake QTE
- [ ] Keep triggering until Fake QTE appears (10% chance)
- [ ] Verify message does NOT mention or ping anyone
- [ ] Test responding with `*evade*` → INSTANT FAIL
- [ ] Test responding with `*parry*` → INSTANT FAIL
- [ ] Test staying silent until timeout → No penalty (success)

---

### 2. Authentic Mutual Love Domain (Cursed Partners)

#### Prerequisites
- [ ] Manually grant achievement or set `save_critical_hp` counter to 5+

#### Domain Activation
- [ ] Use `*domain*` with Authentic Mutual Love unlocked
- [ ] Verify domain activation message
- [ ] Verify visual effects/embed

#### Spec Attacks
- [ ] `*spec1*` → Deals 50 damage to target
- [ ] `*spec2*` → Stuns target for 10 seconds
- [ ] `*spec3*` → Applies bleed + enables double counter

#### Jacob's Ladder
- [ ] `*jacobs*` → Shows 5 second cast warning
- [ ] Verify cast can be interrupted (test by killing caster)
- [ ] Let cast complete → Deals 80% of boss's TOTAL HP
- [ ] Verify damage calculation: `boss_max_hp * 0.8`

#### Overspec System
- [ ] Counter during domain → Gains overspec stack
- [ ] Verify stacks accumulate
- [ ] Test enhanced attacks with stacks

---

### 3. Deadly Sentencing Domain (Court Trial)

#### Prerequisites
- [ ] Manually grant achievement or set impossible save streak to 4+
- [ ] Ensure Ollama is running with `elbot` model

#### Domain Activation
- [ ] Use `*domain*` with Deadly Sentencing unlocked
- [ ] Verify court session starts
- [ ] Verify random "crime" is assigned to target

#### Trial Rounds
- [ ] Round 1: Send a defense argument
- [ ] Verify AI judges and returns score (1-10)
- [ ] Verify score format: "**PUNTUACIÓN: X/10** - [explanation]"
- [ ] Round 2: Send another argument
- [ ] Round 3: Send final argument
- [ ] Verify total is calculated correctly

#### Verdicts
- [ ] Score 10-19 pts → Caster's defense is broken
- [ ] Score 20-29 pts → Caster loses a QTE type
- [ ] Score 30 pts → Defender gets Executioner Sword

#### AI Quality
- [ ] Test weak argument ("idk lol") → Low score (1-4)
- [ ] Test decent argument → Medium score (5-7)
- [ ] Test creative, lore-relevant argument → High score (8-10)
- [ ] Verify AI maintains Spanish and sarcastic tone

---

### 4. Self-Embodiment of Perfection Domain (Soul Manipulator)

#### Prerequisites
- [ ] Manually grant achievement or set conditions

#### Domain Activation
- [ ] Use `*domain*` with Self-Embodiment unlocked
- [ ] Verify domain activation message
- [ ] Verify Transfiguration tracking starts at 0

#### Transfiguration Stacks
- [ ] Perform successful action → Stack added
- [ ] Verify multiplier: `1.03^stacks`
- [ ] Test at 10 stacks → ~1.34x multiplier
- [ ] Test at 50 stacks → ~4.38x multiplier
- [ ] Test at 60+ stacks → Capped at 6x

#### Instant Counter (if implemented)
- [ ] Successfully evade during domain
- [ ] Verify counter opportunity is granted automatically

---

### 5. Infinite Void VAR Mode

#### Prerequisites
- [ ] Have Infinite Void domain unlocked

#### Activation
- [ ] Use `*var*` command
- [ ] Verify 10 second quick deploy (faster than normal)
- [ ] Verify VAR mode indicator in status

#### Spammable Ult1
- [ ] Use `*ult1*` during VAR mode
- [ ] Verify 50 damage dealt
- [ ] Use `*ult1*` again immediately
- [ ] Verify it can be used repeatedly (no normal cooldown)

#### Deactivation
- [ ] Let VAR mode expire
- [ ] Verify normal domain behavior resumes

---

### 6. Weapon System

#### Split Soul Katana
- [ ] Grant weapon: Set player's weapon to `split_soul_katana`
- [ ] Perform counter attack
- [ ] Verify damage is multiplied by 1.5x
- [ ] Calculate: `base_damage * 1.5`

#### Executioner Sword
- [ ] Win Court Trial with 30 points
- [ ] Verify Executioner Sword is granted
- [ ] Perform counter attack
- [ ] Verify damage is multiplied by 4x
- [ ] Verify weapon expires after duration

#### Combined Multipliers
- [ ] Have weapon + Transfiguration stacks active
- [ ] Verify: `base_damage * weapon_mult * transfig_mult`

---

### 7. AI (El Bot) Testing

#### Mechanics Knowledge
- [ ] Ask: "¿Cómo funciona el QTE fake?"
- [ ] Verify accurate explanation of Fake QTE mechanics

- [ ] Ask: "qué es el domain clash"
- [ ] Verify accurate domain clash explanation

- [ ] Ask: "explica la transfiguración"
- [ ] Verify Transfiguration system explanation

#### Court Judging
- [ ] Send: "PUNTUACIÓN para: [weak argument]"
- [ ] Verify low score with sarcastic explanation

- [ ] Send: "PUNTUACIÓN para: [creative argument]"
- [ ] Verify higher score with appreciation

#### Lore Knowledge
- [ ] Ask: "quién es Yenda"
- [ ] Verify accurate Yendaverse lore response

- [ ] Ask: "qué es un ET"
- [ ] Verify Total Erradication explanation

---

## 🔴 Edge Cases to Test

### QTE Edge Cases
- [ ] Two players respond to same QTE simultaneously
- [ ] Player responds to Fake QTE then immediately to real QTE
- [ ] Combo QTE interrupted by domain activation
- [ ] Direction QTE with wrong format (e.g., "left" without asterisks)

### Domain Edge Cases
- [ ] Activate domain while another is active
- [ ] Domain clash between new domain types
- [ ] Jacob's Ladder on boss with <5 HP (overkill check)
- [ ] Court Trial with Ollama offline (error handling)

### Weapon Edge Cases
- [ ] Equip weapon while one is already equipped
- [ ] Temporary weapon expires mid-combat
- [ ] Weapon multiplier + critical hit + Transfiguration

---

## 📊 Expected Test Results

| Feature | Expected Behavior |
|---------|-------------------|
| QTE Variation Selection | Weighted random: 60/15/15/10 |
| Combo QTE Timing | Standard + 0.5s per QTE |
| Direction QTE | Opposite arrow = success |
| Fake QTE | Any response = fail |
| Jacob's Ladder | 80% of boss MAX HP |
| Court Trial | 3 rounds, AI scores 1-10 each |
| Transfiguration | 1.03^n, capped at 6x |
| VAR Mode | 10s deploy, spammable 50dmg ult |
| Split Soul Katana | 1.5x damage always |
| Executioner Sword | 4x damage temporary |

---

## 🐛 Bug Reporting Template

```
**Feature:** [e.g., Combo QTE]
**Expected:** [What should happen]
**Actual:** [What happened]
**Steps to Reproduce:**
1. ...
2. ...
3. ...
**Error Message (if any):**
```

---

## ✅ Sign-Off Checklist

- [ ] All QTE variations working correctly
- [ ] All 3 new domains functional
- [ ] VAR mode activates and works
- [ ] Weapon multipliers apply correctly
- [ ] AI judges court trials appropriately
- [ ] No Python syntax errors
- [ ] No crashes during extended testing
- [ ] Edge cases handled gracefully

---

*Happy testing! May the tribunal judge you favorably.* ⚖️
