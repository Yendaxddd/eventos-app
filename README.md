# 🎮 EVENTOS APP - Real-time RPG Campaign System

**Fast-track MVP for December deadline!**

A standalone web application for real-time roleplay campaigns with QTE (Quick Time Events) mechanics, migrated from Discord bot to avoid API rate limits.

## ✨ Features

### Core Mechanics
- **Real-time QTE System**: Evade, Parry, Save actions with precise timing
- **HP & Damage System**: Variable damage based on difficulty
- **REVENGE Mode**: Activates at 20% HP with enhanced abilities
- **Black Flash**: Perfect timing special mechanic
- **Power System**: Charge-based ultimate abilities
- **WebSocket Real-time**: Instant communication, no Discord rate limits!

### Current Status (MVP)
- ✅ Backend API with FastAPI
- ✅ WebSocket real-time communication
- ✅ Core game engine migrated from Discord bot
- ✅ Web frontend with live QTE display
- ✅ HP bars and power gauges
- ✅ Combat log system
- 🔨 Discord bridge mode (coming soon)
- 🔨 Mobile app (next phase)

## 🚀 Quick Start

### Method 1: Automatic (Linux/Mac)
```bash
chmod +x start.sh
./start.sh
```

### Method 2: Manual
```bash
# 1. Install dependencies
cd backend
pip install fastapi uvicorn python-socketio

# 2. Start backend server
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# 3. Open frontend/index.html in your browser
```

## 🎯 How to Play

1. **Join Campaign**: Enter username and click "Join Campaign"
2. **Wait for QTE**: QTEs will appear with countdown timers
3. **React Quickly**: 
   - Press **Q/A** for EVADE
   - Press **W/S** for PARRY
   - Press **E/D** for SAVE
4. **Track HP**: Watch your HP bar - at 20% REVENGE mode activates!
5. **Build Power**: Deal/take damage to charge ultimate abilities

## 📁 Project Structure

```
eventos-app/
├── backend/
│   ├── api/
│   │   └── main.py          # FastAPI server & WebSocket
│   ├── core/
│   │   └── game_engine.py   # QTE logic from Discord bot
│   └── requirements.txt
├── frontend/
│   └── index.html           # Single-page web app
├── start.sh                 # Quick start script
└── README.md
```

## 🔧 Configuration

### Backend Settings
- **Server**: `http://localhost:8000`
- **WebSocket**: `ws://localhost:8000/ws/{user_id}`
- **CORS**: Enabled for all origins (development)

### QTE Timing Windows
| Difficulty | Evade | Parry | Damage |
|------------|-------|-------|--------|
| Easy       | 6.0s  | 4-7s  | 1-3    |
| Medium     | 4.5s  | 3-5s  | 1-5    |
| Hard       | 4.0s  | 2.5-4.5s | 1-10 |
| Impossible | 1.5s  | 0.8-1.7s | 15   |

## 🌟 Special Mechanics

### REVENGE Mode
- Triggers at 20% HP
- Parry windows shift 0.3s earlier
- Windows 30% tighter
- +50% damage multiplier
- +10% Black Flash chance

### Black Flash
- Base 2% chance on perfect parry
- +1% permanent increase per success
- Capped at 20% maximum
- Only on Medium+ difficulty

## 🛠️ Development

### Tech Stack
- **Backend**: Python, FastAPI, WebSocket
- **Frontend**: Vanilla JS, HTML5, CSS3
- **Game Engine**: Extracted from Discord bot
- **Real-time**: WebSocket (no polling!)

### Running Tests
```bash
# Start server
cd backend
python -m uvicorn api.main:app --reload

# Open frontend and click "Test QTE"
```

### API Endpoints
- `GET /` - Health check
- `POST /api/trigger_qte` - Trigger QTE event
- `POST /api/campaigns/quick_create` - Create test campaign
- `GET /api/players/{user_id}/stats` - Player statistics
- `POST /api/players/{user_id}/hp` - Update HP

### WebSocket Events
- `join_campaign` - Join a campaign
- `qte_response` - Send QTE action
- `qte_triggered` - Receive QTE event
- `hp_update` - HP changes
- `qte_result` - Action results

## 📱 Future Plans (December)

### Phase 1: Polish MVP ✅
- Core mechanics working
- Web interface complete
- Real-time combat functional

### Phase 2: Discord Bridge (This Week)
- Keep Discord bot running
- Bridge mode for transition
- Sync between app and Discord

### Phase 3: Mobile App (November)
- React Native or Capacitor
- Touch controls
- Push notifications

### Phase 4: Enhanced Features
- Campaign persistence
- Character customization
- Boss battles
- Multiplayer campaigns

## 🐛 Known Issues
- CORS may block file:// protocol in some browsers - use a local server or the start script
- WebSocket reconnection not yet implemented
- No persistence yet (resets on server restart)

## 📝 Migration from Discord Bot

This app contains the core mechanics from the original Discord bot:
- `advanced_qte_hp_system_debug.py` → `game_engine.py`
- Discord commands → REST API
- Discord WebSocket → Native WebSocket
- Message reactions → Button clicks

## 🚢 Deployment

For production deployment:

1. **Update CORS** in `backend/api/main.py`
2. **Use HTTPS** for secure WebSocket
3. **Add authentication** for user accounts
4. **Setup database** for persistence
5. **Deploy backend** to cloud (Heroku/Railway/etc)
6. **Host frontend** on CDN/static hosting

## 📄 License

Built with urgency for December deadline! 🏃‍♂️💨

---

**Need help?** The code is self-documenting - dive in and experiment!

**Remember:** This is a rapid MVP - polish comes after it works!
