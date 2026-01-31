# GM Commands Integration Guide

## Quick Setup

### Step 1: Add GM Commands Module to Bot

In your `advanced_qte_hp_system_debug.py`, find the setup section (around line 300-400) and add:

```python
# ========== LOAD GM COMMANDS ==========
# Add this in the __init__ or setup section:

# At the top, add:
from gm_commands import GMCommands

# In the bot initialization (around where you load other commands):
self.gm_commands = None

# In on_ready() or after bot is ready:
async def setup_gm_commands():
    self.gm_commands = GMCommands(self.bot, self)
    print("✅ GM Commands loaded")

# Call this after bot is ready
asyncio.create_task(setup_gm_commands())
```

### Step 2: Create `.env` File

Copy `.env.example` and customize:

```bash
cp .env.example .env
nano .env
```

Fill in required values:
```env
DISCORD_TOKEN=your_bot_token
QTE_CHANNEL_ID=your_channel_id
QTE_PLAYER_ROLE_ID=your_role_id
GM_ROLE_ID=your_gm_role_id
PLAYER_MAX_HP=100
ULT_BASE_COOLDOWN_SECONDS=600
```

### Step 3: Load Environment Variables in Bot

Add to imports in `advanced_qte_hp_system_debug.py`:

```python
from dotenv import load_dotenv
import os

# At the very start of the file:
load_dotenv()

# Use values like:
PLAYER_MAX_HP = int(os.getenv("PLAYER_MAX_HP", 100))
ULT_BASE_COOLDOWN = int(os.getenv("ULT_BASE_COOLDOWN_SECONDS", 600))
```

### Step 4: Assign GM Role

1. Create a role in Discord called "GM" or use existing
2. Add the role ID to .env: `GM_ROLE_ID=your_role_id`
3. Give trusted GMs this role
4. Test: `*show_values` (should work for GMs only)

---

## Common GM Workflows

### Session 1: Testing New Domain Mechanics

```
*session_start @TestEnemy hard
*player_max_hp @Alice 500  (give big HP pool for testing)
*player_max_hp @Bob 500

*domain_unlock @Alice infinite_void
*domain_unlock @Bob malevolent_shrine

*set_value INFINITE_VOID_COOLDOWN 5  (reduce cooldown for testing)

(Alice casts domain, tests mechanics)

*session_stats
*session_end
```

### Session 2: Balance Testing Damage

```
*session_start @BalanceTest medium

*set_multiplier damage 2.0  (2x damage to test scaling)

*player_list
*boss_status

*set_multiplier damage 1.0  (reset to normal)

*session_end
```

### Session 3: Player Power Testing

```
*session_start @PowerCheck impossible

*player_max_hp @Alice 1000  (huge HP pool)

*domain_unlock @Alice infinite_void
*domain_unlock @Alice malevolent_shrine
*domain_unlock @Alice authentic_mutual_love

*set_value ULT_CHARGE_REQUIRED 10  (easy ult spam for testing)

(Test all domains and ultimates)

*set_value ULT_CHARGE_REQUIRED 100  (reset)

*session_end
```

---

## Environment Variables Quick Reference

### Frequently Changed Values

```env
# Difficulty Scaling (change these most often)
PLAYER_MAX_HP=100                          # Player health pool
DIFFICULTY_HARD_DAMAGE_MULTIPLIER=1.2      # Boss damage multiplier
ULT_MAX_DAMAGE_CAP=500                      # Ultimate damage limit

# Cooldowns (for testing)
DOMAIN_BASE_COOLDOWN_SECONDS=300            # 5 minutes
ULT_BASE_COOLDOWN_SECONDS=600               # 10 minutes
AUTHENTIC_MUTUAL_LOVE_SPEC_COOLDOWN=10     # 10 seconds

# Charge System (for balance)
ULT_CHARGE_PER_DAMAGE_DEALT=2.0
ULT_CHARGE_PER_DAMAGE_TAKEN=5.0
ULT_CHARGE_REQUIRED=100.0
```

### Rarely Changed (Set Once)

```env
# Identity
DISCORD_TOKEN=...
BOT_PREFIX=*
GM_ROLE_ID=...

# Statics (usually don't change)
QTE_BASE_DAMAGE=15
COUNTER_BASE_DAMAGE=25
BLACK_FLASH_DAMAGE_MULTIPLIER=2.0
```

---

## Command Quick Reference

```
SESSION COMMANDS:
*session_start @BossName hard       Start new session
*session_end                        End session and show stats
*session_stats                      Show live stats
*player_list                        List all active players

PLAYER COMMANDS:
*player_hp @User 75                Set player current HP
*player_max_hp @User 200           Set player max HP
*player_revive @User               Bring player back to life

BOSS COMMANDS:
*boss_hp 300                       Set boss current HP
*boss_status                       Show boss health/status

VALUE TUNING:
*show_values                       Display all .env values
*set_value KEY value              Set specific value
*set_multiplier damage 1.5        Quick multiplier adjustment
*reload_config                    Reload all .env values

DOMAIN COMMANDS:
*domain_unlock @User infinite_void  Unlock domain
*domain_set_active @User malevolent_shrine  Set active domain
```

---

## Troubleshooting GM Commands

### Commands not appearing
- Check if user has GM_ROLE_ID role
- Verify role exists in Discord: Settings → Roles → Find it
- Sync commands: Restart bot after adding role

### `*set_value` not persisting
- .env file must exist in bot directory
- File must be writable: `chmod 644 .env`
- Changes take effect immediately in-memory
- Persist to file for next restart

### Values not changing
- Use exact key names from .env
- Check `*show_values` to confirm set worked
- Some values only apply on next domain/session

### Player commands not finding user
- User must be in active fight
- Use `*player_list` to see who's active
- Can add players by setting their HP: `*player_max_hp @NewUser 100`

---

## Example Full Test Session

```
// Start controlled test
*session_start @TestBot medium

// Spawn players
*player_max_hp @Alice 100
*player_max_hp @Bob 100

// Unlock domains for testing
*domain_unlock @Alice infinite_void
*domain_unlock @Bob malevolent_shrine

// Tweak balance
*set_value ULT_CHARGE_REQUIRED 50  (fast ult charge)
*set_multiplier damage 1.2         (slightly harder)

// Monitor
*session_stats
*player_list
*boss_status

// During play, adjust if needed
*set_multiplier damage 1.5         (too easy, up damage)
*player_hp @Alice 50               (manually damage if stuck)

// End and review
*session_end
// Session shows: duration, damage dealt/taken, participants
```

---

## Support

For issues:
1. Check bot logs: `docker-compose logs bot`
2. Verify .env exists: `ls -la .env`
3. Test reload: `*reload_config`
4. Check permissions: `*show_values` (should show values)

All errors appear in console - check there first!
