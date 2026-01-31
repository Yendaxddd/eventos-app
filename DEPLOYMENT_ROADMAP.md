# 🗺️ DEPLOYMENT ROADMAP & VISUAL GUIDE

---

## 🎯 Your Journey: From Local to Cloud

```
START
  │
  ├─ 📖 UNDERSTAND
  │   Read: QUICK_DEPLOY.md (10 min)
  │   Read: README_DEPLOYMENT.md (5 min)
  │
  ├─ 🔧 PREPARE LOCALLY
  │   │
  │   ├─ Step 1: Get Discord Bot Token (5 min)
  │   │   └─ Discord Developer Portal → Applications → Bot → Copy Token
  │   │
  │   ├─ Step 2: Get Channel & Role IDs (5 min)
  │   │   ├─ QTE Channel: Right-click → Copy Channel ID
  │   │   ├─ Player Role: Right-click role → Copy Role ID  
  │   │   └─ GM Role: Right-click role → Copy Role ID
  │   │
  │   ├─ Step 3: Create .env File (2 min)
  │   │   ├─ Copy from .env.example
  │   │   ├─ Fill in DISCORD_TOKEN
  │   │   ├─ Fill in QTE_CHANNEL_ID
  │   │   ├─ Fill in QTE_PLAYER_ROLE_ID
  │   │   └─ Fill in GM_ROLE_ID
  │   │
  │   └─ Step 4: Test Locally (10 min)
  │       ├─ docker-compose up -d
  │       ├─ Check: docker logs -f eventos-bot
  │       ├─ Test in Discord: *show_values
  │       └─ Stop: docker-compose down
  │
  ├─ ⚙️ INTEGRATE CODE
  │   │
  │   └─ Follow: INTEGRATION_CHECKLIST.md
  │       ├─ Add import line
  │       ├─ Add init variables
  │       ├─ Add on_ready() handler
  │       ├─ Change command prefix
  │       └─ Test with docker-compose
  │
  ├─ ☁️ DEPLOY TO CLOUD
  │   │
  │   ├─ Option A: Railway.app (RECOMMENDED)
  │   │   ├─ Create account (2 min)
  │   │   │   └─ railway.app → Connect GitHub
  │   │   ├─ Select repository (1 min)
  │   │   ├─ Add secrets (2 min)
  │   │   │   ├─ DISCORD_TOKEN
  │   │   │   ├─ QTE_CHANNEL_ID
  │   │   │   ├─ QTE_PLAYER_ROLE_ID
  │   │   │   └─ GM_ROLE_ID
  │   │   └─ Deploy: git push origin main (2 min)
  │   │
  │   ├─ Option B: Render.com
  │   │   ├─ Create account
  │   │   ├─ Connect GitHub repo
  │   │   ├─ Add environment variables
  │   │   └─ Deploy
  │   │
  │   └─ Option C: DigitalOcean
  │       ├─ Create account
  │       ├─ Create droplet
  │       ├─ SSH and configure
  │       └─ Deploy via GitHub Actions
  │
  ├─ ✅ VERIFY
  │   │
  │   ├─ Check 1: Bot Online (1 min)
  │   │   └─ Look for bot in Discord member list
  │   │
  │   ├─ Check 2: Config Loaded (1 min)
  │   │   └─ In Discord: *show_values → Should display values
  │   │
  │   ├─ Check 3: Commands Work (2 min)
  │   │   ├─ *session_start @TestBot easy
  │   │   ├─ *player_max_hp @TestUser 100
  │   │   └─ *session_end
  │   │
  │   └─ Check 4: Logs Visible (1 min)
  │       └─ Railway dashboard → Logs tab
  │
  └─ 🎉 SUCCESS!
      │
      ├─ Bot running in cloud ✅
      ├─ Accessible 24/7 ✅
      ├─ GMs can manage sessions ✅
      └─ Ready for production ✅

TOTAL TIME: ~30-45 minutes
```

---

## 📊 Command Flow Diagram

```
GM Issues Command
  │
  ├─ *show_values
  │  └─ → Loads .env variables → Displays config
  │
  ├─ *session_start @BossName difficulty
  │  ├─ → Creates session record
  │  ├─ → Sets boss health
  │  ├─ → Initializes stat tracking
  │  └─ → Returns session ID
  │
  ├─ *player_max_hp @User amount
  │  ├─ → Updates player health pool
  │  └─ → Persists to data/player_hp.json
  │
  ├─ *set_value KEY value
  │  ├─ → Updates environment variable in memory
  │  ├─ → Changes take effect immediately
  │  └─ → Persists on restart
  │
  ├─ *session_stats
  │  ├─ → Reads self.session_stats
  │  ├─ → Calculates damage/kills/duration
  │  └─ → Displays in Discord
  │
  └─ *session_end
     ├─ → Calculates final stats
     ├─ → Archives session data
     ├─ → Clears active_session
     └─ → Posts summary to Discord
```

---

## 🔄 Data Flow: Local → Cloud

```
Your Computer (Local Development)
  │
  ├─ .env file (NEVER COMMITTED)
  │  └─ Contains: tokens, IDs, local config
  │
  ├─ .env.example (COMMITTED)
  │  └─ Template for deployment
  │
  ├─ gm_commands.py (COMMITTED)
  │  └─ Code for GM commands
  │
  ├─ docker-compose.yml (COMMITTED)
  │  └─ Local testing setup
  │
  └─ Git Push
     │
     ├─ Goes to GitHub
     │  ├─ Triggers .github/workflows/deploy.yml
     │  └─ GitHub Actions:
     │     ├─ Build Docker image
     │     ├─ Push to registry
     │     └─ Deploy to Railway
     │
     └─ Railway Server (Cloud)
        │
        ├─ Pulls image from registry
        ├─ Reads environment variables from Railway dashboard
        ├─ Loads .env values
        ├─ Mounts /data /assets /logs volumes
        ├─ Starts bot.py process
        └─ Bot connects to Discord API
           │
           ├─ Responds to commands
           ├─ Manages QTE sessions
           ├─ Stores data in /data
           └─ Logs to /logs (viewable in Railway)
```

---

## 🎮 Session Lifecycle

```
Session Creation
  │
  ├─ GM: *session_start @Boss hard
  │  ├─ Validates boss name
  │  ├─ Creates session record:
  │  │  {
  │  │    "boss_name": "Boss",
  │  │    "difficulty": "hard",
  │  │    "start_time": timestamp,
  │  │    "participants": [],
  │  │    "boss_hp_current": 100,
  │  │    "boss_hp_max": 100
  │  │  }
  │  └─ Announced in Discord
  │
  ├─ Players Join Naturally
  │  ├─ They start fighting
  │  ├─ Auto-tracked as participants
  │  └─ HP bars appear
  │
  ├─ GM Monitors
  │  ├─ *session_stats → View live stats
  │  ├─ *boss_status → Check boss health
  │  ├─ *player_list → See participants
  │  └─ *player_hp @User 50 → Adjust if stuck
  │
  ├─ GM Adjusts Balance
  │  ├─ *set_multiplier damage 1.5 → Too easy?
  │  ├─ *set_value ULT_CHARGE_REQUIRED 50 → Too hard?
  │  └─ Changes apply immediately
  │
  └─ Session Ends
     ├─ GM: *session_end
     ├─ Bot Calculates:
     │  ├─ Duration
     │  ├─ Total damage dealt
     │  ├─ Players participated
     │  ├─ Boss health remaining
     │  └─ MVP (most damage)
     ├─ Posts summary to Discord
     └─ Session data archived
```

---

## 📦 File Dependencies

```
For Bot to Run:
  │
  ├─ advanced_qte_hp_system_debug.py (main)
  │  ├─ Imports: gm_commands.py
  │  ├─ Imports: simple_api_bridge.py
  │  ├─ Imports: special_objects_manager.py
  │  ├─ Needs: .env file
  │  ├─ Needs: assets/ directory
  │  └─ Creates: data/ directory
  │
  ├─ gm_commands.py
  │  ├─ Requires: discord.py
  │  ├─ Requires: python-dotenv
  │  └─ Reads: .env variables
  │
  ├─ .env file (CRITICAL)
  │  ├─ DISCORD_TOKEN (must be valid)
  │  ├─ QTE_CHANNEL_ID (must exist)
  │  ├─ QTE_PLAYER_ROLE_ID (must exist)
  │  └─ GM_ROLE_ID (must exist)
  │
  └─ assets/ directory
     ├─ counter_gifs/
     ├─ domain_gifs/
     ├─ spec_gifs/
     └─ ... (all GIF assets)

For Deployment:
  │
  ├─ Dockerfile (image recipe)
  ├─ docker-compose.yml (local orchestration)
  ├─ .github/workflows/deploy.yml (CI/CD)
  ├─ .env.example (config template)
  ├─ requirements.txt (Python dependencies)
  └─ Git repository (source control)
```

---

## 🎛️ Configuration Hierarchy

```
DEFAULT VALUES (in code)
  │
  ├─ Hardcoded in Python
  │  └─ Used if no .env found
  │
  ▼ OVERRIDDEN BY ▼
  │
.env FILE VALUES
  │
  ├─ Loaded on startup
  │  └─ Used for this session
  │
  ▼ OVERRIDDEN BY ▼
  │
RAILWAY ENVIRONMENT VARIABLES
  │
  ├─ Set in Railway dashboard
  │  └─ Injected into container
  │
  ▼ OVERRIDDEN BY ▼
  │
GM COMMAND ADJUSTMENTS
  │
  ├─ *set_value KEY value
  │  └─ Changes in-memory, persists in current session only
  │
  ▼ FINAL RESULT ▼
  │
ACTIVE BOT BEHAVIOR
  │
  └─ What actually happens in Discord
```

**Priority Order:** Railway vars > .env file > Code defaults

---

## 🔐 Secret Management Flow

```
You (Developer)
  │
  ├─ Create Discord Bot
  │  └─ Get DISCORD_TOKEN
  │
  ├─ Get Server IDs
  │  └─ QTE_CHANNEL_ID, role IDs
  │
  ├─ Create .env locally
  │  ├─ Contains secrets
  │  └─ .env → .gitignore (never commit)
  │
  ├─ Test locally
  │  ├─ docker-compose reads .env
  │  └─ Bot works with local secrets
  │
  ├─ Create Railway.app account
  │  └─ OAuth with GitHub (secure)
  │
  ├─ Add Secrets to Railway
  │  ├─ In Railway dashboard
  │  ├─ Variables tab
  │  └─ Copy values from your .env
  │
  ├─ Push code to GitHub
  │  ├─ Only .env.example (no secrets)
  │  ├─ gm_commands.py (code)
  │  ├─ Dockerfile (recipe)
  │  └─ No secrets exposed
  │
  ├─ Railway Auto-Deploys
  │  ├─ Pulls code from GitHub
  │  ├─ Builds Docker image
  │  └─ Injects Railway secrets into container
  │
  └─ Bot Runs in Cloud
     ├─ Has access to secrets
     └─ Secrets never exposed in code/Git
```

---

## ⚠️ Common Mistakes & Prevention

```
MISTAKE 1: Committing .env to Git
  Problem: Secrets exposed publicly
  ❌ Don't: git add .env → git push
  ✅ Do: .env → .gitignore
  ✅ Verify: git status (should NOT show .env)

MISTAKE 2: Wrong Role/Channel IDs
  Problem: Bot can't find channel or assign roles
  ❌ Don't: Guess or copy wrong ID
  ✅ Do: Right-click in Discord → Copy ID
  ✅ Verify: *show_values shows correct IDs

MISTAKE 3: Missing python-dotenv
  Problem: .env file not loaded
  ❌ Don't: Assume it's installed
  ✅ Do: pip install python-dotenv
  ✅ Verify: import dotenv works

MISTAKE 4: gm_commands.py not imported
  Problem: No GM commands available
  ❌ Don't: Forget import statement
  ✅ Do: Add at top of bot file
  ✅ Verify: *show_values works as GM

MISTAKE 5: Forgetting to set Railway Secrets
  Problem: Bot starts but crashes immediately
  ❌ Don't: Deploy without Railway variables
  ✅ Do: Add all secrets in Railway dashboard
  ✅ Verify: Check Railway logs for startup
```

---

## 📈 Scaling Path (Future)

```
Now (MVP - Production Ready)
  │
  ├─ Single bot instance
  ├─ Railway free tier
  ├─ Basic GM commands
  └─ Manual session management

Later (Growth)
  │
  ├─ Add database (PostgreSQL)
  │  └─ Persistent session history
  │
  ├─ Add WebUI dashboard
  │  └─ Web interface for GMs
  │
  ├─ Add analytics
  │  └─ Player stats, leaderboard
  │
  ├─ Add automated tournaments
  │  └─ Schedule battles
  │
  └─ Scale to multiple servers
     └─ Bot guild sharding

Future (Enterprise)
  │
  ├─ Multiple bot instances (sharding)
  ├─ Kubernetes orchestration
  ├─ Redis caching
  ├─ CDN for assets
  ├─ Analytics database
  └─ Subscription tier system
```

---

## 🚨 Troubleshooting Decision Tree

```
Is bot online in Discord?
├─ YES → Go to next check
└─ NO → 
    ├─ Check Railway logs
    ├─ Check DISCORD_TOKEN is correct
    ├─ Check bot invited to server
    ├─ Check bot has server permissions
    └─ Redeploy: git push origin main

Can you see *show_values output?
├─ YES → Config loaded! Go to next check
└─ NO → 
    ├─ Check .env file exists
    ├─ Check variables are in Railway
    ├─ Check bot has read permissions
    └─ Restart bot in Railway

Can you start a session (*session_start)?
├─ YES → Basics working! Go to next check
└─ NO → 
    ├─ Check gm_commands.py imported
    ├─ Check on_ready() handler exists
    ├─ Check command prefix is *
    └─ Redeploy

Do commands run but values don't change?
├─ Session running? → yes/no
├─ Try *reload_config
├─ Check var names in .env.example
└─ Some values need restart

Bot crashes during gameplay?
├─ Check Railway logs for error
├─ Check .env has all required vars
├─ Test locally with docker-compose
├─ Check asset paths with ASSETS_DIR
└─ Report with full error message
```

---

## 📞 Where to Find Answers

| Question | Reference |
|----------|-----------|
| How to deploy? | QUICK_DEPLOY.md |
| How to integrate code? | INTEGRATION_CHECKLIST.md |
| What are all the commands? | GM_COMMANDS_GUIDE.md |
| Full deployment details? | DEPLOYMENT_GUIDE.md |
| Quick overview? | README_DEPLOYMENT.md |
| Troubleshooting? | DEPLOYMENT_GUIDE.md → Troubleshooting section |
| Environment variables? | .env.example (150+ documented) |
| Code examples? | gm_commands.py (usage patterns) |

---

## ✨ Success Checklist (Final)

Before saying "I'm done!":

- [ ] Bot appears online in Discord
- [ ] `*show_values` displays configuration  
- [ ] `*session_start @Test easy` works
- [ ] `*player_max_hp @User 100` sets health
- [ ] `*set_value` changes apply in real-time
- [ ] `*session_end` shows stats
- [ ] Logs appear in Railway dashboard
- [ ] GM commands require GM role
- [ ] GMs can manage sessions independently
- [ ] No errors in last hour of logs
- [ ] No sensitive data in GitHub repo
- [ ] .env file is git-ignored
- [ ] Assets directory exists
- [ ] Data persistence working

**All checked? 🎉 You're production-ready!**

---

## 🎯 Quick Links

```
📖 Documentation
├─ QUICK_DEPLOY.md .................... 10-minute deployment
├─ INTEGRATION_CHECKLIST.md ........... Code integration steps
├─ DEPLOYMENT_GUIDE.md ............... Full reference
├─ GM_COMMANDS_GUIDE.md .............. Command usage
├─ README_DEPLOYMENT.md .............. Overview & summary
└─ DEPLOYMENT_ROADMAP.md ............ (This file)

💾 Code & Config
├─ advanced_qte_hp_system_debug.py .... Main bot (modified)
├─ gm_commands.py .................... GM commands module
├─ .env.example ...................... Config template
├─ Dockerfile ........................ Container recipe
├─ docker-compose.yml ............... Local testing
└─ .github/workflows/deploy.yml ...... GitHub Actions CI/CD

🔗 External Resources
├─ Railway.app ....................... https://railway.app
├─ Discord Developer Portal ......... https://discord.com/developers
├─ Docker Docs ...................... https://docs.docker.com
└─ discord.py Docs .................. https://discordpy.readthedocs.io
```

---

**You have everything needed to go from zero to deployed in ~30 minutes. Time to ship! 🚀**
