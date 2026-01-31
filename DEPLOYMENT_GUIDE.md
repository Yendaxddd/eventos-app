# Eventos Bot - Deployment & GM Setup Guide

## 🚀 Quick Start - Cloud Deployment

### Option 1: Railway (Recommended for GitHub Education)

1. **Sign up with GitHub Education**
   - Visit [Railway.app](https://railway.app)
   - Click "Login with GitHub"
   - Authorize and get $5/month credit

2. **Deploy the Bot**
   ```bash
   npm install -g @railway/cli
   railway login
   railway init
   ```

3. **Configure Environment**
   - Create `.env` from `.env.example`
   - Fill in your Discord bot token and server IDs
   - Add any custom gameplay values

4. **Deploy**
   ```bash
   railway up
   ```

### Option 2: Render.com (GitHub Partner)

1. Visit [Render.com](https://render.com)
2. Sign up with GitHub
3. Create New → Web Service
4. Connect your GitHub repo
5. Set environment variables from `.env.example`
6. Deploy!

### Option 3: DigitalOcean (GitHub Student Program - $200 credit)

1. Get $200 credit via [GitHub Student Pack](https://education.github.com/pack)
2. Create a Droplet (2GB RAM minimum recommended)
3. SSH into droplet
4. Run deployment script (see below)

---

## 🐳 Docker Deployment

### Local Testing
```bash
cp .env.example .env
# Edit .env with your values
docker-compose up
```

### Production Deployment
```bash
docker build -t eventos-bot:latest .
docker run -d \
  --name eventos-bot \
  --env-file .env \
  -v ./data:/app/data \
  -v ./assets:/app/assets \
  -v ./logs:/app/logs \
  eventos-bot:latest
```

---

## 🔐 Security & Asset Management

### 1. Protect Sensitive Data
```bash
# Create .gitignore entries
echo ".env" >> .gitignore
echo "data/" >> .gitignore
echo "logs/" >> .gitignore
echo "assets/" >> .gitignore  # (optional - if assets are huge)
```

### 2. Cloud Asset Storage (Optional - for huge asset files)

If your assets folder is large, use S3-compatible storage:

```bash
# Install AWS CLI
pip install boto3

# Upload assets to S3
aws s3 sync ./assets s3://your-bucket/assets/
```

Then update your bot to download assets on startup:
```python
# In bot initialization
if os.getenv("USE_CLOUD_ASSETS", "false").lower() == "true":
    download_assets_from_s3()
```

### 3. GitHub Secrets for CI/CD
Add these secrets to your GitHub repo settings:
- `DISCORD_TOKEN` - Your bot token
- `RAILWAY_TOKEN` - Railway.app token
- `AWS_ACCESS_KEY_ID` - (optional, for S3)
- `AWS_SECRET_ACCESS_KEY` - (optional, for S3)

---

## 🎮 GM Commands for Session Management

### Admin/GM Setup
First, ensure your user has the `GM_ROLE_ID` role:

```python
# To set GM role, add this to your Discord server role settings
# Then add the role ID to .env: GM_ROLE_ID=your_role_id
```

### Available GM Commands

#### Session Management
```
*session_start @enemy_name <difficulty>
  Start a new battle session
  Example: *session_start @Sukuna hard

*session_end
  End the current session and show stats

*session_stats
  Display current session statistics

*session_pause
  Pause the current session

*session_resume
  Resume a paused session
```

#### Player Management
```
*player_hp @user <amount>
  Set a player's current HP
  Example: *player_hp @Yenda 50

*player_max_hp @user <amount>
  Set a player's maximum HP
  Example: *player_max_hp @Yenda 200

*player_revive @user
  Revive a dead player

*player_reset @user
  Reset a player's stats

*player_list
  Show all active players in session
```

#### Enemy/Boss Management
```
*boss_spawn <boss_name> <hp> <difficulty>
  Spawn a custom boss
  Example: *boss_spawn Sukuna 500 hard

*boss_hp <amount>
  Set current boss HP
  Example: *boss_hp 300

*boss_status
  Show current boss status

*boss_ability <ability_name> <cooldown>
  Configure boss ability (or trigger it)
  Example: *boss_ability Malevolent_Shrine 60
```

#### Value Tuning (On-the-fly adjustments)
```
*set_multiplier <type> <value>
  Adjust gameplay multipliers
  Types: damage, charge, cooldown, duration
  Example: *set_multiplier damage 1.5

*set_value <key> <value>
  Set any gameplay value from .env
  Example: *set_value ULT_CHARGE_REQUIRED 80

*show_values
  Show all current gameplay values

*reload_config
  Reload all values from .env file
```

#### Domain Management
```
*domain_list
  Show all available domains

*domain_unlock @user <domain_name>
  Unlock a domain for a player
  Example: *domain_unlock @Yenda infinite_void

*domain_set_active @user <domain_name>
  Set active domain for testing
  Example: *domain_set_active @Yenda malevolent_shrine
```

---

## 📝 Environment File Examples

### Minimal Setup (.env)
```env
DISCORD_TOKEN=your_token_here
BOT_PREFIX=*
QTE_CHANNEL_ID=123456789
QTE_PLAYER_ROLE_ID=987654321
GM_ROLE_ID=111111111

# Gameplay
PLAYER_MAX_HP=100
PLAYER_REGEN_PER_CHECKPOINT=30
ULT_CHARGE_REQUIRED=100.0
```

### Full Balanced Setup (.env)
```env
# All values from .env.example with custom tweaks
# For a balanced PvP experience with:
# - 100 HP player pool
# - 5% black flash chance
# - 10 minute domain cooldowns
# - 30 second domain effects
```

### High-Damage Testing (.env)
```env
PLAYER_MAX_HP=500
ULT_MAX_DAMAGE_CAP=2000
DIFFICULTY_HARD_DAMAGE_MULTIPLIER=2.0
DIFFICULTY_IMPOSSIBLE_DAMAGE_MULTIPLIER=3.0
BLACK_FLASH_DAMAGE_MULTIPLIER=5.0
```

---

## 🔧 GM Session Workflow

### 1. Prepare the Server
```bash
# SSH into your deployed server
ssh user@your-server.com

# Pull latest code
git pull origin main

# Update .env if needed
nano .env

# Restart bot
docker-compose restart
```

### 2. Configure Game Values
```
*show_values
  (Review current settings)

*set_value PLAYER_MAX_HP 200
  (Adjust for testing specific mechanic)

*set_multiplier damage 1.5
  (Increase all damage by 50%)
```

### 3. Start Session
```
*session_start @CustomBoss medium

*player_hp @Alice 200
*player_hp @Bob 200

*domain_unlock @Alice infinite_void
*domain_unlock @Bob malevolent_shrine
```

### 4. Monitor
```
*session_stats
  (Check progress)

*player_list
  (See participant status)

*boss_status
  (Boss health/abilities)
```

### 5. End & Export Results
```
*session_end
  (Ends session, shows stats)
```

---

## 📊 Monitoring & Logs

### View Real-time Logs
```bash
docker-compose logs -f bot
```

### Check Bot Status
```bash
docker ps
docker stats
```

### Backup Data
```bash
# Backup player stats
tar -czf backup_$(date +%Y%m%d).tar.gz data/

# Backup to remote
scp backup_*.tar.gz user@backup-server:/backups/
```

---

## 🆘 Troubleshooting

### Bot Won't Start
1. Check token: `echo $DISCORD_TOKEN`
2. Check logs: `docker-compose logs bot`
3. Verify .env exists: `ls -la .env`

### GIFs Not Loading
- Check ASSETS_PATH in .env
- Verify assets folder exists: `ls -la assets/`
- Check file permissions: `chmod 644 assets/*`

### Commands Not Working
- Verify GM role is set: `*show_values | grep GM_ROLE`
- Check user has role: Verify in Discord server
- Test command: `*player_list` (should return player count)

### High CPU Usage
- Reduce QTE frequency
- Disable AI if not needed: `AI_ENABLED=false`
- Check logs for infinite loops

---

## ✅ Deployment Checklist

- [ ] Discord bot token obtained
- [ ] Server IDs added to .env
- [ ] GM role configured
- [ ] .env.example reviewed and customized
- [ ] Docker tested locally: `docker-compose up`
- [ ] Git secrets added (DISCORD_TOKEN, etc.)
- [ ] .gitignore configured (.env, data/, logs/)
- [ ] Deployment platform chosen (Railway/Render/DO)
- [ ] First deployment successful
- [ ] GMs briefed on commands
- [ ] Backup strategy in place
- [ ] Monitoring logs configured

---

## 📚 Additional Resources

- **Railway Docs**: https://docs.railway.app
- **Discord.py Docs**: https://discordpy.readthedocs.io
- **Docker Docs**: https://docs.docker.com
- **GitHub Education**: https://education.github.com

For questions, check the logs first: `docker-compose logs bot | tail -50`
