# Integration Steps: Adding GM Commands to Advanced QTE Bot

## Overview
This file contains the exact code snippets you need to add to `advanced_qte_hp_system_debug.py` to integrate the GM commands module.

---

## Step 1: Add Import at Top of File

**Location:** After line 17 (after `from simple_api_bridge import SimpleEventosAPI`)

**Add this line:**
```python
from gm_commands import GMCommands
```

**Full context (lines 15-20):**
```python
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from gm_commands import GMCommands  # ← ADD THIS LINE
from rich.table import Table
```

---

## Step 2: Add GM Commands Setup in __init__

**Location:** After line 290 (after all the data loading, around where `self.boss_defeat_gifs` is loaded)

**Add this after line 290:**
```python
        # ========== GM COMMANDS SYSTEM ==========
        self.gm_commands = None  # Will be loaded in on_ready
        self.active_session = None  # {boss_name, difficulty, start_time, participants, stats}
        self.session_stats = {}  # Track damage/kills/etc per session
        # ==========================================
```

**Full context (lines 285-295):**
```python
        self.boss_defeat_gifs = load_data("boss_defeat_gifs", [])  # Boss defeat celebration GIFs (list)
        self.player_buffs = load_data("player_buffs", {})  # Active buffs: {user_id: {buff_type: {value, expires}}}
        
        # ========== SKILL TREE & ACHIEVEMENTS ==========
        # ========== GM COMMANDS SYSTEM ==========
        self.gm_commands = None  # Will be loaded in on_ready
        self.active_session = None  # {boss_name, difficulty, start_time, participants, stats}
        self.session_stats = {}  # Track damage/kills/etc per session
        # ==========================================
        self.player_skills = load_data("skill_trees/player_skills", {})
```

---

## Step 3: Setup Event Handlers

**Location:** Find the `@self.bot.event` handlers section (around line 2200+)

**Add this new event handler method:**
```python
    @self.bot.event
    async def on_ready():
        """Bot is ready - setup GM commands"""
        console.print(f"[cyan]✓ Bot logged in as {self.bot.user}[/cyan]")
        
        # Initialize GM commands
        if self.gm_commands is None:
            self.gm_commands = GMCommands(self.bot, self)
            console.print("[green]✓ GM Commands system initialized[/green]")
```

---

## Step 4: Register Commands Prefix

**Location:** In the same place where command prefix is set (line 250)

**Verify this exists:**
```python
        self.bot = commands.Bot(command_prefix='!', intents=intents)
```

**Update it to use asterisk prefix:**
```python
        self.bot = commands.Bot(command_prefix='*', intents=intents)  # Changed from '!' to '*'
```

---

## Step 5: Add Run Method Call

**Location:** At the very end of your main execution block (usually bottom of file)

**Find where the bot runs and update it:**

**Before (if you have this):**
```python
if __name__ == "__main__":
    bot = AdvancedQTEManager()
    bot.run()
```

**After (updated):**
```python
if __name__ == "__main__":
    bot = AdvancedQTEManager()
    asyncio.run(bot.run())  # Ensure async compatibility
```

---

## Step 6: Create .env File

**Location:** Same directory as `advanced_qte_hp_system_debug.py`

**Copy from template:**
```bash
cd discord-bot/
cp .env.example .env
nano .env
```

**Minimum required values:**
```env
DISCORD_TOKEN=your_bot_token_here
QTE_CHANNEL_ID=123456789
QTE_PLAYER_ROLE_ID=123456789
GM_ROLE_ID=123456789
PLAYER_MAX_HP=100
```

---

## Step 7: Install python-dotenv (if not already installed)

```bash
pip install python-dotenv
```

Or if using requirements.txt:
```bash
echo "python-dotenv" >> requirements.txt
pip install -r requirements.txt
```

---

## Verification Checklist

- [ ] `from gm_commands import GMCommands` added to imports
- [ ] `self.gm_commands = None` added to `__init__`
- [ ] `self.active_session = None` added to `__init__`
- [ ] `self.session_stats = {}` added to `__init__`
- [ ] `on_ready()` event handler added
- [ ] Command prefix changed to `*`
- [ ] `.env` file created in discord-bot/ directory
- [ ] `DISCORD_TOKEN` filled in .env
- [ ] `QTE_CHANNEL_ID`, `QTE_PLAYER_ROLE_ID`, `GM_ROLE_ID` filled in .env
- [ ] `python-dotenv` installed: `pip install python-dotenv`

---

## Testing the Integration

### 1. Start Bot
```bash
cd discord-bot/
python advanced_qte_hp_system_debug.py
```

### 2. Look for initialization message
```
✓ GM Commands system initialized
```

### 3. In Discord, verify GM commands work
```
*show_values    # Should display all environment variables
*session_start @TestBot medium   # Should start a session
```

### 4. Troubleshooting

**Commands not showing:**
- Ensure user has GM role (check .env `GM_ROLE_ID`)
- Verify role exists in Discord server
- Restart bot after changing roles

**Bot crashes on startup:**
- Check .env file syntax (no quotes around values)
- Verify DISCORD_TOKEN is correct
- Check logs: `tail -f logs/qte_bot.log`

**`from gm_commands import GMCommands` - Module not found:**
- Ensure `gm_commands.py` is in same directory as main bot file
- Check file exists: `ls -la discord-bot/gm_commands.py`

---

## Environment Variable Reference

**Critical (must set):**
```env
DISCORD_TOKEN=your_token                    # Bot token from Discord Developer Portal
QTE_CHANNEL_ID=123456789                   # Channel ID where QTE battles happen
QTE_PLAYER_ROLE_ID=123456789               # Role ID for players
GM_ROLE_ID=123456789                       # Role ID for GMs (admin commands)
```

**Optional (defaults provided):**
```env
PLAYER_MAX_HP=100                          # Player max HP (default: 100)
ULT_BASE_COOLDOWN_SECONDS=600              # Ultimate cooldown (default: 600)
DIFFICULTY_EASY_DMG_MIN=1                  # Min damage easy (default: 1)
DIFFICULTY_EASY_DMG_MAX=3                  # Max damage easy (default: 3)
# ... see .env.example for all 150+ options
```

---

## Quick GM Command Examples

After integration:

```
*session_start @Boss1 hard
  └─ Start new battle against Boss1 on hard difficulty

*show_values
  └─ Display all loaded environment variables

*player_max_hp @Alice 500
  └─ Set Alice's max HP to 500

*set_value ULT_CHARGE_REQUIRED 50
  └─ Change ultimate charge requirement to 50% (easier ults)

*session_end
  └─ End session and show stats
```

---

## File Structure After Integration

```
discord-bot/
├── advanced_qte_hp_system_debug.py  (✓ Updated with imports + init + on_ready)
├── gm_commands.py                   (✓ Module with all GM commands)
├── .env                             (✓ Configuration file - DO NOT COMMIT)
├── .env.example                     (✓ Template for reference)
├── requirements.txt                 (✓ Updated with python-dotenv)
├── simple_api_bridge.py
├── special_objects_manager.py
├── assets/
│   ├── counter_gifs/
│   ├── domain_gifs/
│   └── ...
└── data/
```

---

## Next Steps After Integration

1. **Test locally** - Run bot and test GM commands
2. **Deploy** - Use Docker and Railway (see DEPLOYMENT_GUIDE.md)
3. **Brief GMs** - Send them GM_COMMANDS_GUIDE.md
4. **Monitor** - Check logs for errors

See `GM_COMMANDS_GUIDE.md` for detailed usage instructions.
