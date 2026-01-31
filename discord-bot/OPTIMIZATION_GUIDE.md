# QTE Bot Optimization Guide

## 📊 Current State Analysis

### Commands Overview (52 total)
The bot currently has 52+ slash commands which is overwhelming. Here's the breakdown:

**Player Commands (12):**
- `/qte` - Toggle participation
- `/register`, `/unregister` - Character management
- `/mycharacters`, `/mystats` - View info
- `/dashboard` - Personal stats
- `/achievements`, `/listachievements` - Achievement system
- `/leaderboard` - Rankings
- `/inventory`, `/objectinfo` - Items
- `/setcountergif` - Personalization

**GM/Admin Commands (25+):**
- `/targetqte`, `/editqte` - QTE control
- `/bossdashboard`, `/registerboss` - Boss management
- `/editvalues` - Value tuning
- `/skills`, `/skillbranch`, `/learnsk`, `/giveskillpoints` - Skill system
- `/giveachievement`, `/removeachievement` - Achievement management
- `/giveobject`, `/takeobject`, `/gmobjects` - Item management
- `/setobjectimage`, `/setobjectspins`, `/setplayerslots` - Object config
- `/approveobject`, `/rejectobject`, `/listpending` - Object approval
- `/manageultimates`, `/charge`, `/resethp` - Combat control
- `/synccommands`, `/cleancommands`, `/restart` - Bot admin

**AI Commands (3):**
- `/ai`, `/aitest`, `/aimodel` - AI configuration

**Utility (5):**
- `/timing` - View timing windows
- `/support` - Help
- `/debuginventory` - Debug
- `/bossdefeatgif` - Boss GIF management
- `/mirrorinvoke` - Special object

---

## 🔧 Recommended Optimizations

### 1. Data Persistence for Railway

**Problem:** Railway containers are ephemeral - data in `/data` is lost on restart.

**Solutions (pick one):**

#### Option A: Railway Persistent Volumes (Recommended)
```json
// railway.json
{
  "build": {"builder": "dockerfile"},
  "deploy": {
    "restartPolicyMaxRetries": 5
  },
  "volumes": {
    "/app/data": {}
  }
}
```

#### Option B: External Database (More Robust)
Use Railway's PostgreSQL or Redis addon:
- PostgreSQL for structured data
- Redis for fast key-value (JSON blobs)

#### Option C: GitHub-based Storage (Simple)
Commit data changes back to a private repo periodically.

### 2. GM Configuration via Discord

Add a `/config` command group that allows GMs to modify settings:

```python
# Proposed /config command structure:
/config view              # View all current settings
/config qte timing <diff> <evade> <parry>  # Adjust QTE timing
/config damage <diff> <min> <max>          # Adjust damage ranges
/config revenge <threshold> <multiplier>   # Revenge mode settings
/config bf <base_chance> <max_chance>      # Black Flash settings
/config ultimate <cooldown> <charge_rate>  # Ultimate settings
/config save              # Save current config to file
/config reset             # Reset to defaults
```

### 3. Command Consolidation

**Reduce from 52 to ~15 commands using groups:**

| New Command | Replaces | Description |
|-------------|----------|-------------|
| `/player` | mystats, mycharacters, dashboard, inventory | All player info |
| `/boss` | registerboss, bossdashboard | Boss management |
| `/qte` | qte, targetqte, editqte | QTE control |
| `/gm` | editvalues, manageultimates, charge, resethp | GM utilities |
| `/objects` | giveobject, takeobject, gmobjects, approve/reject | Object management |
| `/skills` | skills, skillbranch, learnsk, giveskillpoints | Skill management |
| `/achievements` | achievements, give/remove achievement | Achievement management |
| `/config` | (new) | Settings management |
| `/register` | register, unregister | Character registration |
| `/leaderboard` | leaderboard | Rankings |
| `/ai` | ai, aitest, aimodel | AI settings |
| `/admin` | synccommands, cleancommands, restart | Bot admin |
| `/help` | support, timing | Help & info |

### 4. Commands to Remove/Deprecate

**Candidates for removal:**
- `/debuginventory` - Merge into `/objects debug`
- `/listobjects`, `/listpending` - Merge into `/objects list`
- `/reloadobjects`, `/testobject` - Merge into `/objects admin`
- `/resetobjectspins`, `/setobjectspins` - Merge into `/objects config`
- `/mirrorinvoke` - Too specific, could be object ability

### 5. Performance Optimizations

#### A. Reduce Discord API Calls
```python
# Current: Multiple sends
await channel.send("Message 1")
await channel.send("Message 2")

# Better: Combined embed
embed.add_field(name="Part 1", value="Message 1")
embed.add_field(name="Part 2", value="Message 2")
await channel.send(embed=embed)
```

#### B. Cache Channel/Role Lookups
```python
# Add at class init:
self._channel_cache = {}
self._role_cache = {}

def get_cached_channel(self, channel_id):
    if channel_id not in self._channel_cache:
        self._channel_cache[channel_id] = self.bot.get_channel(channel_id)
    return self._channel_cache[channel_id]
```

#### C. Batch Database Saves
Already implemented with `_save_interval` throttling ✓

#### D. Reduce Console Spam in Production
```python
# Add environment check
PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT") is not None
if not PRODUCTION:
    console.print(f"[debug] ...")
```

### 6. Lag Prevention

**Current bottlenecks identified:**
1. **File I/O on every action** - Already throttled ✓
2. **Message history searches** - Add `hp_bar_messages` cache ✓
3. **Reaction spam** - Rate limiting implemented ✓
4. **Large embed generation** - Consider lazy loading

**Additional recommendations:**
```python
# 1. Use message reference instead of fetching
await message.reply(embed=embed)  # Good
# vs
msg = await channel.fetch_message(id)  # Bad - API call

# 2. Limit history searches
async for msg in channel.history(limit=10):  # Good
async for msg in channel.history(limit=100): # Bad

# 3. Async file operations (for large data)
import aiofiles
async with aiofiles.open('data.json', 'r') as f:
    data = json.loads(await f.read())
```

---

## 📋 Implementation Priority

### Phase 1: Immediate (This Session)
- [x] Fix Deadly Sentencing AI fallback
- [ ] Add `/config` command for basic GM settings
- [ ] Clean up duplicate/unused commands

### Phase 2: Short-term (Next Session)
- [ ] Consolidate commands into groups
- [ ] Add Railway persistent volume config
- [ ] Add production logging mode

### Phase 3: Medium-term
- [ ] Migrate to Redis/PostgreSQL for persistence
- [ ] Add interactive menus (buttons/dropdowns) instead of many commands
- [ ] Implement command cooldowns

---

## 🔄 What's Left to Work On

### Core Features (Working)
- ✅ QTE System (all variations)
- ✅ HP/Damage System
- ✅ Black Flash chains
- ✅ Domain Expansions
- ✅ Boss Battles
- ✅ Skill Trees
- ✅ Achievements
- ✅ Special Objects

### Needs Improvement
- ⚠️ Command organization (too many)
- ⚠️ GM configuration (hardcoded values)
- ⚠️ Data persistence (ephemeral on Railway)
- ⚠️ AI features (requires external Ollama)

### Future Features
- 🔮 Interactive menus (buttons/selects)
- 🔮 Web dashboard for GMs
- 🔮 Mobile companion app
- 🔮 Multi-server support
- 🔮 Campaign save/load

---

## 📝 Quick Reference: Environment Variables

```env
# Required
DISCORD_TOKEN=xxx
QTE_CHANNEL_ID=xxx
QTE_PLAYER_ROLE_ID=xxx

# Optional - GM/Admin
ADMIN_ROLE_ID=xxx
GM_ROLE_ID=xxx

# Optional - Features
HP_BAR_THREAD_ID=xxx
OLLAMA_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_MODEL=elbot

# Optional - Tuning (proposed)
QTE_EASY_EVADE=6.0
QTE_MEDIUM_EVADE=4.5
QTE_HARD_EVADE=4.0
QTE_IMPOSSIBLE_EVADE=1.5
REVENGE_THRESHOLD=0.20
BF_BASE_CHANCE=0.02
BF_MAX_CHANCE=0.20
```
