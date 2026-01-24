# Discord Bot + Eventos App API Integration Guide

This guide explains how to connect your Discord bot to the Eventos App backend API, allowing Discord messages to use the corrected damage calculation system.

## 🎯 Overview

The integration uses an **API Bridge** pattern:
- Discord Bot receives messages
- API Bridge sends requests to FastAPI backend
- Backend processes with corrected game engine
- Results return to Discord for display

## 📋 Prerequisites

1. **Eventos App Backend Running**
   ```bash
   cd eventos-app/backend
   python -m uvicorn api.main:app --host 0.0.0.0 --port 7000
   ```

2. **Discord Bot Dependencies**
   ```bash
   pip install requests  # For HTTP requests to API
   ```

## 🔧 Setup Instructions

### Step 1: Update Your .env File

Add the API URL to your `.env` file:

```env
# Existing Discord bot config
DISCORD_TOKEN=your_token_here
QTE_CHANNEL_ID=your_channel_id
QTE_PLAYER_ROLE_ID=your_role_id
ADMIN_ROLE_ID=your_admin_role_id
HP_BAR_THREAD_ID=your_thread_id

# NEW: Eventos API Integration
EVENTOS_API_URL=http://localhost:7000
```

### Step 2: Integrate API Bridge into Discord Bot

Add this import at the top of `advanced_qte_hp_system_debug.py`:

```python
from api_bridge import EventosAPIBridge
```

Add this in the `__init__` method of `AdvancedQTEBot` class:

```python
# Initialize API Bridge
api_url = os.getenv("EVENTOS_API_URL", "http://localhost:7000")
self.api_bridge = EventosAPIBridge(api_url)

# Health check
if not self.api_bridge.health_check():
    console.print("[yellow]⚠️  Warning: Could not connect to Eventos API[/yellow]")
    console.print("[yellow]   Bot will work in standalone mode[/yellow]")
else:
    console.print("[green]✓ Connected to Eventos API for damage calculations[/green]")
```

### Step 3: Update NLP Attack Handler

Replace the `handle_nlp_attack` method to use the API:

```python
async def handle_nlp_attack(self, message, confidence):
    """Handle NLP-detected attack with API damage calculation"""
    try:
        if message.channel.id != self.qte_channel_id:
            return
        
        user_id = self.resolve_user_id(message)
        
        # Check cooldown
        current_time = time.time()
        if user_id in self.nlp_attack_last_use:
            time_since_last = current_time - self.nlp_attack_last_use[user_id]
            if time_since_last < self.nlp_attack_cooldown:
                remaining = self.nlp_attack_cooldown - time_since_last
                await message.channel.send(
                    f"{message.author.mention} ⏱️ Attack cooldown! **{remaining:.1f}s** remaining."
                )
                return
        
        # Process attack through API
        result = self.api_bridge.process_free_attack(str(user_id), message.content)
        
        if result:
            total_damage = result["damage"]
            combo_multiplier = result.get("combo_multiplier", 1.0)
            combo_count = result.get("combo_count", 0)
            quality_bonus = result.get("quality_bonus", 0)
            action = result.get("action", "unknown")
            
            # Set cooldown
            self.nlp_attack_last_use[user_id] = current_time
            
            # Apply damage to boss if active
            if self.active_boss:
                success = await self.damage_boss(self.active_boss['name'], total_damage)
                
                if success:
                    # Send detailed attack message
                    embed = discord.Embed(
                        title="⚔️ NLP ATTACK! ⚔️",
                        description=f"**{message.author.mention}** attacks with natural language!\n\n"
                                  f"💥 **{total_damage} damage** dealt to **{self.active_boss['name']}**!",
                        color=discord.Color.orange()
                    )
                    
                    # Add combo info if applicable
                    if combo_count > 1:
                        embed.add_field(
                            name="Combo System",
                            value=f"x{combo_multiplier:.1f} multiplier ({combo_count} combo)",
                            inline=True
                        )
                    
                    # Add quality bonus if applicable
                    if quality_bonus > 0:
                        embed.add_field(
                            name="Quality Bonus",
                            value=f"+{quality_bonus} damage",
                            inline=True
                        )
                    
                    # Show detected action
                    embed.add_field(
                        name="Action Type",
                        value=action.capitalize(),
                        inline=True
                    )
                    
                    embed.set_footer(text=f"Base: {result['base_damage']} | Cooldown: {self.nlp_attack_cooldown}s")
                    await message.channel.send(embed=embed)
                    
                    console.print(
                        f"[orange1]⚔️ API ATTACK - {message.author.display_name} dealt {total_damage} damage "
                        f"(combo: x{combo_multiplier:.1f}, quality: +{quality_bonus})[/orange1]"
                    )
        else:
            # Fallback to original system if API fails
            console.print("[yellow]⚠️  API attack failed, using fallback[/yellow]")
            # Original damage calculation code here...
        
    except Exception as e:
        console.print(f"[red]✗ Error in NLP attack handler: {e}[/red]")
        log.error(f"NLP attack error: {e}")
```

## 🧪 Testing the Integration

### Test 1: Health Check
```python
# In Python console or test script
from api_bridge import EventosAPIBridge

bridge = EventosAPIBridge("http://localhost:7000")
print(bridge.health_check())  # Should return True
```

### Test 2: Attack Test
```python
# Test attack through API
result = bridge.process_free_attack("test_user_123", "I slash the enemy with my sword!")
print(result)
# Should return: {'damage': X, 'base_damage': Y, 'combo_multiplier': Z, ...}
```

### Test 3: Discord Bot Test
1. Start the backend: `cd eventos-app/backend && python -m uvicorn api.main:app --host 0.0.0.0 --port 7000`
2. Start the Discord bot: `python advanced_qte_hp_system_debug.py`
3. In Discord, type an attack message: "I strike the boss with lightning!"
4. Verify the damage numbers use the API's calculations

## 📊 What the Integration Provides

### ✅ Benefits

1. **Corrected Damage Formula**
   - Uses the fixed `(base * combo) + quality` calculation
   - No more multiplication bugs

2. **Combo System**
   - Tracks consecutive attacks per user
   - Applies correct multipliers (x1.0 → x1.5 → x2.0)
   - Decays after 10 seconds

3. **Quality System**
   - Analyzes attack descriptions via NLP
   - Awards bonus damage for creative attacks
   - Confidence-based scaling

4. **Centralized Logic**
   - One source of truth for game mechanics
   - Easier to update and maintain
   - Consistent across all platforms

### 📈 Data Flow

```
Discord Message
    ↓
Discord Bot (NLP Detection)
    ↓
API Bridge (HTTP Request)
    ↓
FastAPI Backend (/api/players/{user_id}/action)
    ↓
Game Engine (process_free_attack)
    ↓
Combat System (calculate_nlp_attack_damage)
    ↓
Response (damage, combo, quality data)
    ↓
Discord Bot (Display Results)
    ↓
Discord Channel (Embed Message)
```

## 🔍 Troubleshooting

### Issue: "Could not connect to Eventos API"
**Solution:** Ensure the backend is running on port 7000:
```bash
cd eventos-app/backend
python -m uvicorn api.main:app --host 0.0.0.0 --port 7000
```

### Issue: "Attack failed" response
**Solution:** Check backend logs for errors:
```bash
# Backend terminal should show error details
```

### Issue: Bot works but doesn't use API
**Solution:** Check that `EVENTOS_API_URL` is in `.env` and bridge initialized successfully

### Issue: Damage numbers seem wrong
**Solution:** The API uses the CORRECT formula now. Old numbers may have been inflated due to the bug.

## 🚀 Production Deployment

For production on Linux (Bazzite):

1. **Run backend as systemd service:**
```bash
# Create service file: /etc/systemd/system/eventos-api.service
sudo systemctl enable eventos-api
sudo systemctl start eventos-api
```

2. **Update API URL for production:**
```env
EVENTOS_API_URL=http://localhost:7000
# Or use your domain:
# EVENTOS_API_URL=https://api.yourdomain.com
```

3. **Monitor both services:**
```bash
# Backend logs
journalctl -u eventos-api -f

# Discord bot logs
tail -f qte_bot.log
```

## 📝 Notes

- The Discord bot can work standalone if API is unavailable (fallback mode)
- API uses port 7000 by default (FastAPI)
- Discord bot stores character data locally in `data/` directory
- API creates campaigns automatically ("discord_campaign")
- Boss HP is synchronized between systems

## 🎮 Next Steps

1. Test the integration thoroughly
2. Monitor for any issues
3. Consider migrating more bot features to API
4. Set up WebSocket for real-time updates (future enhancement)

---

**Questions?** Check the bot logs (`qte_bot.log`) and API logs for detailed error messages.
