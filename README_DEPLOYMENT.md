# 🎮 EVENTOS DISCORD BOT - COMPLETE DEPLOYMENT PACKAGE

**Status:** ✅ Production Ready for Cloud Deployment  
**Date:** 2024  
**Version:** 1.0

---

## 📦 What's Included

### Tier 1: Quick Start (Read First)
```
START HERE:
QUICK_DEPLOY.md
    ↓
    Complete cloud deployment in 10 minutes
    Recommended: Railway.app (GitHub Education FREE)
```

### Tier 2: Implementation (Then Do This)
```
INTEGRATION_CHECKLIST.md
    ↓
    Step-by-step code integration
    Copy-paste ready code snippets
    Line numbers provided
```

### Tier 3: Full Reference (When You Need Details)
```
├── DEPLOYMENT_GUIDE.md
│   └─ Comprehensive deployment reference (420 lines)
│   └─ 3 platform options: Railway/Render/DigitalOcean
│   └─ Security practices & troubleshooting
│
├── GM_COMMANDS_GUIDE.md
│   └─ GM command usage guide (250 lines)
│   └─ Workflow examples & balance testing
│   └─ Session management instructions
│
└── DEPLOYMENT_SUMMARY.md
    └─ This overview & quick reference
```

### Tier 4: Code & Infrastructure

**New Code Files:**
```
gm_commands.py (300+ lines)
    ├─ GMCommands cog class
    ├─ 14 GM commands for session/player/boss management
    ├─ Permission checks (GM role required)
    └─ Session stat tracking

.env.example (150+ lines)
    ├─ Configuration template
    ├─ ALL gameplay values documented
    ├─ Copy to .env and customize
    └─ Never commit .env!
```

**Infrastructure Files:**
```
Dockerfile
    └─ Python 3.11 container image
    └─ Installs dependencies, creates directories
    └─ Production-ready

docker-compose.yml
    └─ Local testing orchestration
    └─ Volume mounts for persistence
    └─ Environment variable injection

.github/workflows/deploy.yml
    └─ GitHub Actions CI/CD pipeline
    └─ Auto-build and deploy to Railway
    └─ Triggered on push to main

.gitignore (updated)
    └─ Prevents .env from being committed
    └─ Ignores assets, logs, data
```

**Modified Code:**
```
advanced_qte_hp_system_debug.py
    └─ Fixed GIF paths (ASSETS_DIR constant)
    └─ VAR command now requires Infinite Void domain
    └─ Ready for .env variable loading
```

---

## 🚀 Deployment Flow

### Phase 1: Preparation (5 min)
```
1. Copy .env from .env.example
2. Fill in DISCORD_TOKEN and channel/role IDs
3. (Optional) Test locally with docker-compose
```

### Phase 2: Integration (10 min)
```
1. Add import: from gm_commands import GMCommands
2. Add self.gm_commands = None to __init__
3. Add on_ready() event handler
4. Change command prefix to '*'
5. Test locally
```

### Phase 3: Deploy (10 min)
```
1. Create Railway.app account (GitHub Education partner)
2. Connect GitHub repository
3. Add environment variables in Railway dashboard
4. Push to main branch
5. Auto-deploys in ~2 minutes
```

### Phase 4: Verify (5 min)
```
1. Check bot online in Discord
2. Test: *show_values command
3. Run: *session_start @TestBot easy
4. Confirm logs appear in Railway
```

**Total Time: ~30 minutes from scratch**

---

## 📊 Environment Variables Breakdown

### Configuration Sections (150+ total)

**Discord Setup (5 vars)**
```
DISCORD_TOKEN
BOT_PREFIX
QTE_CHANNEL_ID
QTE_PLAYER_ROLE_ID
GM_ROLE_ID
```

**Player Mechanics (15+ vars)**
```
PLAYER_MAX_HP                                    # Health pool
PLAYER_HP_REGEN_AMOUNT                           # Checkpoint healing
PLAYER_REVENGE_THRESHOLD                         # Triggers at 20% HP
PLAYER_REVENGE_DAMAGE_MULTIPLIER                 # 1.5x damage
PLAYER_COUNTER_WINDOW                            # Parry timing
PLAYER_COUNTER_DAMAGE_MULTIPLIER                 # Counter scaling
```

**QTE System (20+ vars)**
```
QTE_BASE_DAMAGE                                  # 1v1 damage
QTE_DIFFICULTY_EASY_MIN/MAX                     # 1-3 damage
QTE_DIFFICULTY_MEDIUM_MIN/MAX                   # 1-5 damage
QTE_DIFFICULTY_HARD_MIN/MAX                     # 1-10 damage
QTE_DIFFICULTY_IMPOSSIBLE_DAMAGE                # Fixed 15
```

**Domain Expansion (30+ vars)**
```
# Per each of 6 domains:
INFINITE_VOID_COOLDOWN                           # Seconds
INFINITE_VOID_DURATION                           # Seconds
INFINITE_VOID_CAST_TIME                          # Milliseconds
INFINITE_VOID_BASE_DAMAGE                        # Damage dealt
INFINITE_VOID_DAMAGE_MULTIPLIER                  # Scaling
# + Malevolent Shrine, Authentic Mutual Love, Jackpot, etc.
```

**Spec Attacks (50+ vars)**
```
# Per spec: cooldown, damage, cost, multiplier
PURPLE_COOLDOWN / PURPLE_DAMAGE / PURPLE_MULTIPLIER
JACKPOT_COOLDOWN / JACKPOT_DAMAGE / JACKPOT_MULTIPLIER
DOMAIN_CLASH_COOLDOWN / DOMAIN_CLASH_COST / etc.
```

**Status Effects (10+ vars)**
```
BLEED_DAMAGE_PER_TICK
STUN_DURATION
WEAKNESS_DAMAGE_REDUCTION
PARALYSIS_DURATION
```

**Ultimate System (10+ vars)**
```
ULT_BASE_COOLDOWN_SECONDS                       # 10 minutes
ULT_CHARGE_REQUIRED                              # 100%
ULT_CHARGE_PER_DAMAGE_DEALT                      # 2%
ULT_CHARGE_PER_DAMAGE_TAKEN                      # 5%
ULT_CHARGE_PER_COUNTER                           # 3%
ULT_MAX_DAMAGE_CAP                               # 500 damage
ULT_DAMAGE_MULTIPLIER                            # 1.0x
```

---

## 🎮 GM Commands Reference

### 14 Total Commands Available

```
SESSION MANAGEMENT (3)
  *session_start @BossName difficulty
  *session_end
  *session_stats

PLAYER CONTROL (4)
  *player_hp @User amount
  *player_max_hp @User amount
  *player_revive @User
  *player_list

BOSS CONTROL (2)
  *boss_hp amount
  *boss_status

VALUE TUNING (3)
  *show_values
  *set_value KEY value
  *set_multiplier damage|cost 1.5

DOMAIN MANAGEMENT (2)
  *domain_unlock @User domain_id
  *domain_set_active @User domain_id
```

### Usage Examples

```
🎮 Start a Session:
   *session_start @VolutermeGod hard
   
👥 Add Players:
   *player_max_hp @Alice 100
   *player_max_hp @Bob 100
   
🔧 Balance Tweaking:
   *set_value ULT_CHARGE_REQUIRED 50     (easier ult)
   *set_multiplier damage 1.5             (50% more damage)
   
📊 Monitor:
   *session_stats
   *boss_status
   
🏁 End Session:
   *session_end
```

---

## ☁️ Cloud Platform Comparison

| Aspect | Railway | Render | DigitalOcean |
|--------|---------|--------|--------------|
| **Best For** | GitHub users | Simple deploys | Developers |
| **Setup Time** | 5 min | 15 min | 30 min |
| **GitHub Integration** | Native | Good | Manual |
| **Free Tier** | ✅ $500/mo credits | ✅ 7-day trial | ❌ Paid only |
| **Cost After Free** | $5/month start | $7/month | $5/month |
| **Education Benefit** | ⭐⭐⭐ GitHub Ed | ⭐ No | ⭐⭐ Student Pack |
| **Auto-Deploy** | ✅ Yes | ✅ Yes | ❌ Manual |
| **Scaling** | Easy | Easy | Advanced |
| **Documentation** | Good | Excellent | Excellent |

**🏆 BEST CHOICE: Railway for GitHub Education**

---

## 📋 Deployment Checklist

### Before You Start
- [ ] GitHub account with this repo
- [ ] Discord bot token from Developer Portal
- [ ] Discord server with QTE channel
- [ ] Role IDs (right-click in Discord → Copy ID)

### Code Integration
- [ ] Added `from gm_commands import GMCommands` import
- [ ] Added `self.gm_commands = None` to `__init__`
- [ ] Added `on_ready()` event handler
- [ ] Changed command prefix to `*`
- [ ] Tested locally with `docker-compose`

### Deployment
- [ ] Created .env file (copy from .env.example)
- [ ] Filled in DISCORD_TOKEN
- [ ] Filled in QTE_CHANNEL_ID
- [ ] Filled in QTE_PLAYER_ROLE_ID
- [ ] Filled in GM_ROLE_ID
- [ ] Created Railway.app account
- [ ] Connected GitHub repository
- [ ] Added environment variables in Railway
- [ ] Pushed to main branch

### Verification
- [ ] Bot appears online in Discord
- [ ] `*show_values` displays configuration
- [ ] `*session_start` works
- [ ] Session stats display correctly
- [ ] Logs appear in Railway dashboard

---

## 📚 Documentation Map

```
START HERE (Choose Your Path)
│
├─ 🚀 I want to deploy in 10 minutes
│  └─ Read: QUICK_DEPLOY.md
│
├─ 🔧 I want to integrate code
│  └─ Read: INTEGRATION_CHECKLIST.md
│
├─ 📖 I want complete reference
│  └─ Read: DEPLOYMENT_GUIDE.md
│
├─ 👥 I need to brief GMs
│  └─ Read: GM_COMMANDS_GUIDE.md
│
├─ ❓ I need quick reference
│  └─ Read: DEPLOYMENT_SUMMARY.md (YOU ARE HERE)
│
└─ 🆘 I have a problem
   ├─ Check: DEPLOYMENT_GUIDE.md → Troubleshooting
   ├─ Check: Railway logs → Dashboard
   └─ Check: Docker logs → `docker logs eventos-bot`
```

---

## 💾 File Organization

### Discord Bot Directory Structure
```
discord-bot/
├── 📄 advanced_qte_hp_system_debug.py (main bot - MODIFIED)
├── 🆕 gm_commands.py (GM command module)
├── 🆕 .env (your config - DO NOT COMMIT)
├── 🆕 .env.example (template - COMMIT THIS)
├── 🆕 Dockerfile (container image)
├── 🆕 docker-compose.yml (local testing)
├── 📝 requirements.txt
├── 🔗 simple_api_bridge.py
├── 🔗 special_objects_manager.py
├── 📂 .github/
│   └── workflows/
│       └── deploy.yml (CI/CD pipeline)
├── 📂 assets/
│   ├── counter_gifs/
│   ├── domain_gifs/
│   └── ...
├── 📂 data/ (persisted between restarts)
└── 📂 logs/

Root Directory (eventos-app/)
├── 🆕 QUICK_DEPLOY.md (10-minute guide)
├── 🆕 INTEGRATION_CHECKLIST.md (code integration)
├── 🆕 DEPLOYMENT_GUIDE.md (comprehensive reference)
├── 🆕 GM_COMMANDS_GUIDE.md (for GMs)
└── 🆕 DEPLOYMENT_SUMMARY.md (this file)
```

---

## 🔒 Security Essentials

### Do ✅
- ✅ Keep .env file secret (add to .gitignore)
- ✅ Use unique, strong DISCORD_TOKEN
- ✅ Limit GM role to trusted users only
- ✅ Review command logs regularly
- ✅ Rotate token if compromised
- ✅ Use Railway Secrets for sensitive values
- ✅ Enable 2FA on GitHub & Discord

### Don't ❌
- ❌ Commit .env file to GitHub
- ❌ Share DISCORD_TOKEN publicly
- ❌ Give GM role to untrusted users
- ❌ Store secrets in code comments
- ❌ Use default/weak passwords
- ❌ Disable 2FA on accounts
- ❌ Share bot token in Discord chat

---

## 🎯 Success Indicators

✅ **Your deployment is successful when:**

1. Bot appears online in Discord
2. `*show_values` command displays configuration
3. `*session_start @TestBot easy` creates a session
4. Session stats display after gameplay
5. Logs appear in Railway dashboard
6. GMs can execute commands independently
7. No crash logs or errors in Railway

❌ **Troubleshoot if:**
- Bot doesn't appear online
- Commands aren't recognized
- .env variables don't load
- Railway shows deploy errors
- Memory/CPU usage spikes unexpectedly

---

## 📞 Quick Support

### "Where do I get the bot token?"
→ Discord Developer Portal → Applications → Bot → Copy Token

### "What's my channel ID?"
→ Right-click channel in Discord → Copy Channel ID

### "How do I test locally first?"
→ `docker-compose up -d` then check `docker logs eventos-bot`

### "Can I change values without restarting?"
→ Yes! Use `*set_value KEY value` command (GM only)

### "Will GMs have access to everything?"
→ No! GM commands only manage sessions/players/config, not backend

### "What if I make a mistake in deployment?"
→ Delete project in Railway, re-deploy when ready

---

## 🎊 Congratulations!

You now have a complete, production-ready deployment package for your Discord QTE bot:

✅ **Automated Infrastructure**
- Docker containerization
- GitHub Actions CI/CD
- One-click Railway deployment

✅ **GM Management System**
- 14 commands for session control
- Player/boss management
- Real-time value adjustments

✅ **Comprehensive Documentation**
- Quick start guides
- Step-by-step integration
- Complete reference materials

✅ **Security & Best Practices**
- Environment-based configuration
- Secret management
- Permission-based access control

---

## 🚀 Next Steps (In Order)

1. **Right Now:** Read QUICK_DEPLOY.md
2. **Next 5 min:** Create Railway account
3. **Next 10 min:** Deploy to cloud
4. **Next 15 min:** Verify bot is online
5. **Next 30 min:** Integrate GM commands locally
6. **Next 1 hour:** Test with docker-compose
7. **Next 2 hours:** Brief GMs on commands

---

## 📊 By The Numbers

```
Files Created:        9
Code Generated:       1000+ lines
Configuration:        150+ variables
Commands:             14 GM commands
Docs:                 1200+ lines
Cloud Options:        3 platforms
Setup Time:           30 minutes
Uptime Target:        99.9% (Railway)
```

---

**Questions? Errors? Confusion?**

Each documentation file has detailed sections:
- **QUICK_DEPLOY.md** → Fastest path to cloud
- **INTEGRATION_CHECKLIST.md** → Exact code to add
- **DEPLOYMENT_GUIDE.md** → Complete reference
- **GM_COMMANDS_GUIDE.md** → Command examples
- **DEPLOYMENT_SUMMARY.md** → This overview

**You've got everything you need. Time to deploy! 🎮🚀**

---

**Version:** 1.0  
**Status:** ✅ Complete & Ready  
**Last Updated:** 2024  
**Maintained by:** Eventos Bot Team
