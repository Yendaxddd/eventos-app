# Simple Discord Bot Integration Guide

This guide shows you how to use the **corrected damage formula** from the Eventos App backend in your Discord bot - without any WebSocket or campaign complexity.

## What This Solves

Your Discord bot was using an incorrect damage formula:
```python
# OLD (INCORRECT):
damage = base_damage * combo_multiplier + quality_bonus
# Example: 50 * 2.0 + 20 = 120 ✗

# NEW (CORRECT):
damage = (base_damage + quality_bonus) * combo_multiplier
# Example: (50 + 20) * 2.0 = 140 ✓
```

## Quick Start

### 1. Start the Backend API (Terminal 1)

```bash
cd eventos-app/backend
python api/main.py
```

You should see:
```
🚀 Eventos App starting...
INFO:     Uvicorn running on http://0.0.0.0:7000
```

### 2. Test the Connection (Terminal 2)

```bash
cd legacy-discord-bot
python test_simple_bridge.py
```

You should see damage calculations working with the corrected formula.

### 3. Integrate into Your Discord Bot

Add this to your Discord bot code:

```python
from simple_api_bridge import SimpleEventosAPI

# Initialize (do this once when bot starts)
api = SimpleEventosAPI("http://localhost:7000")

# Check if API is available
if api.health_check():
    print("✓ Using corrected damage formula from Eventos API")
else:
    print("⚠ API unavailable - using fallback calculations")

# When processing an NLP attack:
async def process_attack(ctx, attack_text):
    user_id = str(ctx.author.id)
    
    # Try to use the API for corrected damage calculation
    result = api.calculate_attack_damage(user_id, attack_text)
    
    if result:
        # Use the corrected damage from API
        damage = result['damage']
        combo_multiplier = result['combo_multiplier']
        combo_count = result['combo_count']
        quality_bonus = result['quality_bonus']
        
        # Apply damage to boss
        await damage_boss(boss_name, damage)
        
        # Show detailed feedback
        combo_text = f" (x{combo_multiplier} combo)" if combo_count > 1 else ""
        quality_text = f" [+{quality_bonus} quality]" if quality_bonus > 0 else ""
        
        await ctx.send(
            f"💥 **{damage} damage**{combo_text}{quality_text}\n"
            f"Action: {result['action']}"
        )
    else:
        # Fallback to your original calculation if API is down
        damage = calculate_damage_locally(attack_text)
        await damage_boss(boss_name, damage)
        await ctx.send(f"💥 {damage} damage")
```

## How It Works

1. **No Campaign Needed**: The API uses a temporary session just for calculations
2. **Combo Tracking**: Each user's combo is tracked separately in memory
3. **Corrected Formula**: Damage = (base_damage + quality_bonus) × combo_multiplier
4. **Fallback Support**: If API is down, your bot can still use local calculations

## API Response Format

```json
{
  "damage": 140,              // Final damage after all calculations
  "base_damage": 50,          // Base damage from NLP analysis
  "combo_multiplier": 2.0,    // Current combo multiplier
  "combo_count": 3,           // Number of consecutive hits
  "quality_bonus": 20,        // Bonus from attack quality
  "action": "attack",         // Detected action type
  "nlp_confidence": 0.95      // NLP confidence score
}
```

## Testing Different Attack Qualities

Try these in your bot to see the corrected formula in action:

```python
# Low quality (short/simple)
"punch"                    # Base ~30, quality +0

# Medium quality
"I slash with my sword"    # Base ~50, quality +10-20

# High quality (descriptive)
"I UNLEASH A DEVASTATING THUNDER STRIKE THAT SHAKES THE HEAVENS!"
                          # Base ~50, quality +30-50
```

## Combo System

- **Combo builds**: Each successful attack increases the multiplier
- **Per-user tracking**: Each Discord user has their own combo counter
- **Resets on miss**: Failed attacks reset the combo
- **Multiplier scaling**: 1.0x → 1.5x → 2.0x → 2.5x → MAX

## Troubleshooting

### "API is not responding"
- Make sure backend is running: `cd eventos-app/backend && python api/main.py`
- Check the port is 7000 (or update the URL in simple_api_bridge.py)

### "WebSocket connection failed"
- The simple bridge doesn't use WebSockets - this error is from the frontend
- For Discord bot, you only need the HTTP endpoint (no WebSocket needed)

### Import errors
- Make sure `requests` is installed: `pip install requests`
- The simple_api_bridge.py should be in the same directory as your bot

## Files Created

- **simple_api_bridge.py**: Lightweight API client (no campaigns/WebSocket)
- **test_simple_bridge.py**: Test script to verify integration
- **eventos-app/backend/api/main.py**: Updated with `/api/calculate_damage` endpoint

## Next Steps

1. Start the backend API
2. Run the test script to verify it works
3. Import SimpleEventosAPI in your Discord bot
4. Replace your damage calculation with API calls
5. Enjoy the corrected formula! 🎉

---

*Note: The backend API runs independently. Your Discord bot just makes HTTP requests to get damage calculations.*
