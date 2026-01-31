# Skill Tree Activity

A Discord Activity for interactive skill tree visualization and management.

## Setup

### 1. Prerequisites
- Node.js 18+
- A Discord Application with Activities enabled
- `cloudflared` for local development tunneling

### 2. Discord Developer Portal Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create or select your application
3. Go to **Activities** → **Settings** and enable Activities
4. Go to **OAuth2** and add `https://127.0.0.1` as a Redirect URI
5. Copy your **Client ID** and **Client Secret**

### 3. Environment Setup

```bash
cp example.env .env
```

Edit `.env` with your credentials:
```
VITE_DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
```

### 4. Install Dependencies

```bash
npm install
```

### 5. Start Development Server

Terminal 1 - Start the app:
```bash
npm start
```

Terminal 2 - Start cloudflared tunnel:
```bash
cloudflared tunnel --url http://localhost:5173
```

### 6. Configure URL Mapping

1. Copy the URL from cloudflared output (e.g., `https://xyz.trycloudflare.com`)
2. In Discord Developer Portal, go to **Activities** → **URL Mappings**
3. Add a mapping: `/` → `your-cloudflared-url`

### 7. Launch in Discord

1. Open Discord with Developer Mode enabled
2. In any voice channel, open the App Launcher
3. Search for your app and launch it!

## Project Structure

```
skill-tree-activity/
├── index.html              # Main HTML entry
├── src/
│   ├── main.js             # Discord SDK setup & app init
│   ├── components/
│   │   └── SkillTree.js    # Skill tree rendering & interaction
│   ├── managers/
│   │   └── PlayerManager.js # Player data management
│   ├── data/
│   │   └── skills.js       # Skill tree definitions
│   └── styles/
│       ├── main.css        # Core styles
│       ├── skill-tree.css  # Tree-specific styles
│       └── animations.css  # Animation effects
├── server/
│   └── server.js           # Express backend for auth & API
├── package.json
└── vite.config.js
```

## Bot Integration

To connect this activity with your bot's player data:

1. Set `BOT_API_URL` in your `.env` to your bot's API endpoint
2. Implement these endpoints in your bot:
   - `GET /player/:userId/skills` - Get player skill data
   - `POST /player/:userId/skills/unlock` - Unlock a skill

Example response for GET:
```json
{
  "level": 5,
  "skillPoints": 3,
  "unlockedSkills": ["combat_basics", "power_strike"],
  "stats": {}
}
```

## Skill Trees

Four skill trees are available:
- **Combat** ⚔️ - Offensive abilities and damage
- **Defense** 🛡️ - Survivability and mitigation
- **Utility** ✨ - Healing, support, and special abilities
- **Domain** 🌀 - Domain Expansion enhancements

## Features

- Pan and zoom with mouse/touch
- Visual skill connections
- Tier-based progression
- Animated unlock effects
- Mobile-responsive design
- Real-time sync with bot
