# Step-by-Step Integration Guide
## Adding Eventos API to Your Discord Bot

This guide shows **exactly** where to add code in your `advanced_qte_hp_system_debug.py` file to integrate the damage calculation API.

---

## Step 1: Import the API Bridge

**Location:** At the top of your file, with the other imports (around line 20-30)

**Add this line:**
```python
from simple_api_bridge import SimpleEventosAPI
```

**Full import section should look like:**
```python
import discord
from discord.ext import commands
from discord import app_commands
import requests
import keyboard
import time
# ... other imports ...

# NEW: Add this import
from simple_api_bridge import SimpleEventosAPI

# NLP and Dashboard imports
try:
    from nlp_detector import ActionDetector
    NLP_AVAILABLE = True
except ImportError:
    # ...
```

---

## Step 2: Initialize the API in `__init__`

**Location:** In the `AdvancedQTEBot.__init__()` method, after line 60 where you set up bot configuration

**Add these lines:**
```python
# Initialize Eventos API Bridge
try:
    self.eventos_api = SimpleEventosAPI("http://localhost:7001")
    if self.eventos_api.health_check():
        console.print("[green]✓ Eventos API connected - using corrected damage formula[/green]")
        self.api_available = True
    else:
        console.print("[yellow]⚠ Eventos API unavailable - using fallback calculations[/yellow]")
        self.api_available = False
except Exception as e:
    console.print(f"[red]✗ Eventos API connection failed: {e}[/red]")
    self.api_available = False
```

**Where to add it:**
```python
def __init__(self):
    # Bot configuration from environment variables
    self.bot_token = os.getenv("DISCORD_TOKEN")
    self.qte_channel_id = int(os.getenv("QTE_CHANNEL_ID", "0"))
    # ... more config ...
    
    # NEW: Add Eventos API initialization HERE (after config, before bot setup)
    try:
        self.eventos_api = SimpleEventosAPI("http://localhost:7001")
        if self.eventos_api.health_check():
            console.print("[green]✓ Eventos API connected - using corrected damage formula[/green]")
            self.api_available = True
        else:
            console.print("[yellow]⚠ Eventos API unavailable - using fallback calculations[/yellow]")
            self.api_available = False
    except Exception as e:
        console.print(f"[red]✗ Eventos API connection failed: {e}[/red]")
        self.api_available = False
    
    # Bot setup with slash commands
    intents = discord.Intents.default()
    # ... rest of __init__ ...
```

---

## Step 3: Update the NLP Attack Handler

**Location:** Find the `handle_nlp_attack` method (around line 850-900)

**Replace the damage calculation part** with API call:

**FIND THIS CODE** (around line 882-885):
```python
# Calculate damage with confidence-based multiplier
confidence_bonus = confidence * self.nlp_confidence_damage_multiplier
total_damage = int(self.nlp_attack_base_damage * (1 + confidence_bonus))
```

**REPLACE WITH:**
```python
# Calculate damage using API if available
if self.api_available:
    try:
        result = self.eventos_api.calculate_attack_damage(
            str(user_id), 
            message.content
        )
        if result:
            total_damage = result['damage']
            console.print(
                f"[cyan]🎯 API Damage: {total_damage} "
                f"(combo: x{result['combo_multiplier']}, "
                f"quality: +{result['quality_bonus']})[/cyan]"
            )
        else:
            # Fallback to local calculation
            confidence_bonus = confidence * self.nlp_confidence_damage_multiplier
            total_damage = int(self.nlp_attack_base_damage * (1 + confidence_bonus))
    except Exception as e:
        console.print(f"[yellow]⚠ API call failed, using fallback: {e}[/yellow]")
        confidence_bonus = confidence * self.nlp_confidence_damage_multiplier
        total_damage = int(self.nlp_attack_base_damage * (1 + confidence_bonus))
else:
    # API not available, use original calculation
    confidence_bonus = confidence * self.nlp_confidence_damage_multiplier
    total_damage = int(self.nlp_attack_base_damage * (1 + confidence_bonus))
```

---

## Step 4: Update the Counter Attack Handler

**Location:** Find the `handle_counter_attack` method (around line 730-770)

**FIND THIS CODE** (around line 750):
```python
# ===== PHASE 5: ADD CHARGE FROM COUNTER ATTACK =====
# Counter attacks deal 20 damage to enemy
counter_damage = 20
self.add_charge_from_damage_dealt(user_id, counter_damage)
```

**REPLACE WITH:**
```python
# Calculate counter damage using API
if self.api_available:
    try:
        result = self.eventos_api.calculate_attack_damage(
            str(user_id),
            "counter attack"  # Generic counter text
        )
        if result:
            counter_damage = result['damage'] * 2  # Counter does 2x damage
            console.print(f"[gold]💥 API Counter Damage: {counter_damage}[/gold]")
        else:
            counter_damage = 20  # Fallback
    except Exception as e:
        console.print(f"[yellow]⚠ API call failed for counter: {e}[/yellow]")
        counter_damage = 20
else:
    counter_damage = 20

self.add_charge_from_damage_dealt(user_id, counter_damage)
```

---

## Step 5: Start the Backend Server

Before running your Discord bot, make sure the backend is running:

```bash
cd eventos-app/backend
python -m uvicorn api.main:app --host 0.0.0.0 --port 7001
```

**Or run it in the background:**
```bash
cd eventos-app/backend
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 7001 > /tmp/backend.log 2>&1 &
```

---

## Step 6: Test the Integration

1. **Start the backend** (as shown in Step 5)

2. **Run the test script:**
   ```bash
   cd legacy-discord-bot
   python test_simple_bridge.py
   ```

3. **Start your Discord bot:**
   ```bash
   python advanced_qte_hp_system_debug.py
   ```

4. **Look for this message on startup:**
   ```
   ✓ Eventos API connected - using corrected damage formula
   ```

5. **Test in Discord:**
   - Use NLP attacks (type attack descriptions)
   - Use counter attacks (`*attack*` after dodging)
   - Watch for improved damage calculations with combo system!

---

## What This Does

✅ **Corrected Formula:** Uses the fixed damage calculation from the new backend  
✅ **Combo System:** Tracks combos automatically across attacks  
✅ **Quality Bonuses:** Better attack descriptions = more damage  
✅ **Fallback:** If API is down, uses original calculations  
✅ **Per-User Tracking:** Each user has their own combo counter  

---

## Troubleshooting

### "Eventos API unavailable"
- Make sure backend is running on port 7001
- Check with: `curl http://localhost:7001/`

### "API call failed"
- Check backend logs: `tail -f /tmp/backend.log`
- Verify port 7001 is not blocked by firewall

### Still using old damage?
- Make sure you added the import at the top
- Check the initialization code ran (look for the green checkmark)
- Restart both backend and Discord bot

---

## Quick Summary

1. **Add import** → Top of file
2. **Initialize API** → In `__init__` method
3. **Update `handle_nlp_attack`** → Use API for damage
4. **Update `handle_counter_attack`** → Use API for counter damage
5. **Start backend** → Port 7001
6. **Start Discord bot** → Should auto-connect to API
7. **Test!** → Attacks now use corrected formula with combos

---

## Need Help?

The integration test shows everything works:
- ✓ Health check: PASSED
- ✓ Damage calculations: WORKING
- ✓ Combo tracking: WORKING
- ✓ Quality bonuses: WORKING

If you see those checkmarks when running `test_simple_bridge.py`, the API is ready to use in your Discord bot!
