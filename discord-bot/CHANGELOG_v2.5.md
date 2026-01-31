# Changelog v2.6 - "The Tribunal Update"
**Release Date:** January 30, 2026

---

## 🆕 New Domain Expansions

### 🤝 Authentic Mutual Love (真愛領域 - Shin'ai Ryōiki)
**Achievement Required:** "Cursed Partners" - Save someone under 5HP **OR** save someone from 4 impossible QTEs in a streak

**Type:** Cursed Partners | **Duration:** 60 seconds | **Cast Time:** 5s (interruptible)

**Special Attacks:**
| Attack | Command | Effect | Cooldown |
|--------|---------|--------|----------|
| **Dismantle** | `*spec1*` | 50 direct damage | 8s |
| **Binding Vow** | `*spec2*` | 10 second stun on boss | 15s |
| **Crimson Binding** | `*spec3*` | Inflicts bleed - ALL counters do **double damage** for 30s | 20s |

**Ultimate - Jacob's Ladder (`*jacobs*`):**
- **Requirement:** Land 3 normal specs + 3 overspec counters to unlock
- **Cast Time:** 5 seconds (interruptible!)
- **Damage:** 80% of the boss's **TOTAL MAX HP**
- **Visual:** A devastating beam of divine light
- The most devastating finisher in the game - use it wisely!

**Mechanic - Overspec Counter:**
- Countering during domain accumulates "overspec" stacks
- Need 3 overspec stacks + 3 spec attacks to unlock Jacob's Ladder
- Basically: Play aggressively with specs AND land parry counters

---

### ⚖️ Deadly Sentencing (死刑宣告 - Shikei Senkoku)
**Achievement Required:** "Incriminating Evidence" - In a SINGLE bossfight: Deal the last hit, save 5 people, AND deal minimum 300 damage

**Type:** Court Trial | **Cast Time:** 5s (interruptible)

**The Trial System:**
1. Caster activates domain → Target is "accused" of a random crime
2. **3 rounds**, 60 seconds each
3. Target must argue their defense in chat
4. AI Judge (El Bot) scores each argument from 1-10 points
5. Total determines verdict

**Verdicts by Total Score:**
| Score | Verdict | Effect |
|-------|---------|--------|
| 10-19 pts | Guilty (Light) | Breaks the caster's defense |
| 20-29 pts | Guilty (Medium) | Caster loses one QTE variation |
| **30 pts** | **NOT GUILTY** | Target wins the **Executioner Sword**! |

**AI Judge Criteria:**
- Rhetorical quality and creativity
- Conviction and persuasiveness  
- Relevance to the "crime"
- Yendaverse lore integration (bonus points!)

---

### 🗡️ Executioner Sword (Prize from Deadly Sentencing)
**How to Obtain:** Score a perfect 30/30 in the Court Trial

**Stats:**
- **Damage Multiplier:** 4x on ALL attacks
- **Type:** Temporary (replaces your normal ults)
- **Rarity:** Mythic

**Executioner Sword Attacks:**
| Attack | Command | Effect |
|--------|---------|--------|
| **Executioner Lunge** | `*ult1*` | 10s cast, deals 50% of target's total HP |
| **Final Judgement** | `*ult2*` | QTE RACE: 10 QTEs in 20s. Win = instant kill. Lose = boss heals 20% |

⚠️ **Warning:** Final Judgement is high-risk high-reward. Miss the QTE race and the boss heals!

---

### 🔮 Self-Embodiment of Perfection (自己完璧体現 - Jiko Kanpeki Taigen)
**Achievement Required:** "Soul Manipulator" - Kill 2 bosses in streak with 2+ black flashes each, then land a 3rd black flash under 50HP

**Type:** Soul Manipulator | **Duration:** 45 seconds | **Cast Time:** 5s (interruptible)

**Passive - Instant Counter:**
- Every successful `*evade*` during this domain AUTOMATICALLY grants a counter opportunity
- No need to parry - evading is enough to counter!

**Transfiguration System:**
- Each successful attack/action adds a Transfiguration stack
- Damage multiplier: `1.03^n` where n = number of stacks
- **Maximum multiplier: 6x damage** (capped)
- Stacks persist for the duration of the domain

| Stacks | Multiplier | Example (100 base damage) |
|--------|------------|---------------------------|
| 1 | 1.03x | 103 |
| 5 | 1.16x | 116 |
| 10 | 1.34x | 134 |
| 20 | 1.81x | 181 |
| 50 | 4.38x | 438 |
| 60+ | 6.00x | 600 (cap) |

**Strategy:** Stack Transfiguration early by landing many hits, then finish with massive damage!

---

## ⚡ Infinite Void VAR Mode

**Activation:** `*var*` (requires Infinite Void domain unlocked)

**Changes from Normal Mode:**
- **Quick Deploy:** Only 10 seconds to activate (vs normal 5s cast)
- **Spammable Ult1:** Can use `*ult1*` repeatedly during VAR mode
- **Reduced Damage:** Each ult1 deals 50 damage (balanced for spam)

**Use Case:** Rapid pressure and chip damage rather than big single hits

---

## 🎯 QTE Variations

The QTE system now has 4 distinct variations that can trigger randomly:

### Standard QTE (60% chance)
- Normal `*evade*` or `*parry*` mechanics
- Time windows based on difficulty

### Combo QTE (15% chance)
- **5 consecutive QTEs** targeting one player
- Slightly more lenient timing (+0.5s window per QTE)
- 15 second total timeout
- Must complete ALL 5 to succeed

### Direction QTE (15% chance)
- Shows an arrow: ← → ↑ ↓
- **You must input the OPPOSITE direction!**
- Example: Arrow shows `→`, correct answer is `←`
- Commands: `*left*`, `*right*`, `*up*`, `*down*`

### Fake QTE (10% chance)
- ⚠️ **THE TRAP** ⚠️
- Message does NOT mention or ping anyone
- **ANY response = instant fail**
- Correct play: Stay silent, don't react
- If timeout expires with no responses, nobody loses

---

## ⚔️ Weapon System

### Split Soul Katana
- **Multiplier:** 1.5x damage on all attacks
- **Type:** Permanent equip
- **How to obtain:** Achievement or special event reward

### Executioner Sword
- **Multiplier:** 4x damage on all attacks
- **Type:** Temporary (duration-based)
- **How to obtain:** Score 30 points in Court Trial domain

**Damage Calculation:**
```
final_damage = base_damage × weapon_multiplier × transfiguration_multiplier
```

---

## 🤖 AI Enhancement

**El Bot** has been upgraded with:
- Complete knowledge of ALL bot mechanics
- Court Judge capability for Deadly Sentencing trials
- Yendaverse lore integration (characters, locations, events)
- Spanish native with sarcastic Discord personality

**New AI Capabilities:**
- Explain any game mechanic in detail
- Judge court trial arguments (1-10 scoring)
- Reference Yendaverse lore accurately
- Maintain consistent personality across interactions

---

## 📊 Achievement Requirements Summary

| Achievement | Requirement | Unlocks |
|-------------|-------------|---------|
| **Cursed Partners** | Save someone under 5HP OR save 4 impossible QTEs in streak | Authentic Mutual Love |
| **Incriminating Evidence** | In 1 bossfight: Last hit + Save 5 people + 300 damage | Deadly Sentencing |
| **Soul Manipulator** | Kill 2 bosses with 2+ black flashes each, then 3rd BF under 50HP | Self-Embodiment of Perfection |

---

## 🔧 Technical Changes

- Added domain type dispatch for: `cursed_partners`, `court_trial`, `soul_manipulator`
- Implemented `select_qte_variation()` with weighted random selection
- Added weapon damage multiplier system
- Integrated Transfiguration stack tracking
- Added Ollama AI integration for court judging
- New command handlers: `*var*`, `*spec1/2/3*`, `*jacobs*`
- Direction QTE commands: `*left*`, `*right*`, `*up*`, `*down*`

---

## 🐛 Known Limitations

1. VAR mode ult1 spam limit not yet enforced (cooldown TBD)
2. Soul Manipulator instant counter requires evade success hook refinement
3. Court trial AI requires Ollama running locally
4. Weapon equip UI/slash command not yet implemented

---

*"The tribunal of the Yendaverse does not forgive mediocrity."* ⚖️
