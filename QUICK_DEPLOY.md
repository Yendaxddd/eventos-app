# 🚀 QUICK START: Deploy Bot to Cloud in 10 Minutes

> **Target:** Railway.app (GitHub Education Partner - FREE for 1 year)
> **Prerequisites:** GitHub account, Discord bot token, basic Git knowledge

---

## 🎯 5-Step Deployment

### Step 1: Prepare Repository (2 min)

```bash
# In discord-bot directory
cp .env.example .env
nano .env
# Fill in:
#   DISCORD_TOKEN=your_token_here
#   QTE_CHANNEL_ID=123...
#   QTE_PLAYER_ROLE_ID=123...
#   GM_ROLE_ID=123...

# Don't commit .env!
git add .env.example .github/workflows/ Dockerfile docker-compose.yml
git commit -m "Add deployment infrastructure and GM commands"
git push origin main
```

### Step 2: Create Railway Account (2 min)

1. Go to [railway.app](https://railway.app)
2. Click "Start a New Project"
3. Connect GitHub account
4. Select this repository

### Step 3: Configure Railway Secrets (2 min)

1. In Railway dashboard, go to Variables
2. Add these from your .env:
   ```
   DISCORD_TOKEN=xxxx
   QTE_CHANNEL_ID=123...
   QTE_PLAYER_ROLE_ID=123...
   GM_ROLE_ID=123...
   PLAYER_MAX_HP=100
   ```

### Step 4: Enable Auto-Deploy (1 min)

1. In Railway, go to Deployments
2. Toggle "Auto Deploy" ON
3. Set branch to `main`

### Step 5: Deploy! (1 min)

```bash
# Push any change to trigger deployment
git push origin main

# Or manually deploy in Railway dashboard
# Click "Deploy" button
```

---

## 🔍 Verify Deployment

### Check if bot is running:
```bash
# In Discord, go to #qte-channel (or your QTE channel)
@bot_mention *show_values

# Should display all config values
```

### View logs:
```
Railway Dashboard → Logs tab → Filter for "qte_bot_" 
```

### SSH into container (advanced):
```
Railway Dashboard → Extensions → Terminal
cd /app
ls -la
```

---

## 💰 Cost Breakdown

| Platform | Cost | GitHub Benefits |
|----------|------|-----------------|
| **Railway** | $5/month start | FREE tier + $500 credits/month for education |
| Render | $7/month start | FREE tier available |
| DigitalOcean | $5/month start | $200 credit with GitHub Student Pack |
| Heroku | $7/month start | Deprecated free tier |

**🏆 Railway is best for GitHub users!**

---

## 🐳 Local Testing Before Deployment

Test locally first to catch errors:

```bash
# Install Docker
# https://docs.docker.com/get-docker/

cd discord-bot/

# Build image
docker build -t eventos-bot:latest .

# Run container
docker run -d \
  --name eventos-bot \
  -e DISCORD_TOKEN=your_token \
  -e QTE_CHANNEL_ID=123... \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/assets:/app/assets \
  eventos-bot:latest

# Check logs
docker logs -f eventos-bot

# Stop
docker stop eventos-bot
docker rm eventos-bot
```

Or use docker-compose:

```bash
docker-compose up -d
docker-compose logs -f bot
docker-compose down
```

---

## 🛠️ Common Issues

### Bot not starting
```bash
# Check environment variables are set
docker exec eventos-bot env | grep DISCORD_TOKEN

# Check logs for errors
docker logs eventos-bot | grep ERROR
```

### Bot is running but not responding
- Verify bot has permissions in Discord server
- Check bot is in the QTE channel
- Verify QTE_CHANNEL_ID is correct: `Right-click channel → Copy ID`

### Commands not working
- Ensure GM has GM_ROLE_ID role
- Check command prefix is `*` (not `!`)
- Try: `*show_values` to verify it loads

### Redeploy to fix issues
```bash
# Push changes
git add .
git commit -m "Fix issue"
git push origin main

# Railway auto-deploys in ~2 minutes
# Check deployment status in Railway dashboard
```

---

## 📋 Pre-Deployment Checklist

Before pushing to Railway:

- [ ] Created .env with all required values
- [ ] .env NOT committed (check .gitignore)
- [ ] `.env.example` IS committed with dummy values
- [ ] DISCORD_TOKEN verified (bot runs locally)
- [ ] QTE_CHANNEL_ID is correct (right-click → Copy ID)
- [ ] GM_ROLE_ID exists in Discord server
- [ ] Dockerfile and docker-compose.yml exist
- [ ] GitHub Actions workflow exists (.github/workflows/deploy.yml)
- [ ] gm_commands.py integrated in main bot file
- [ ] Bot tested locally with `docker-compose up`

---

## 🎮 First Session on Cloud

Once deployed:

1. **Announce to GMs:** Send them GM_COMMANDS_GUIDE.md
2. **Start test session:**
   ```
   *session_start @TestBot hard
   *player_max_hp @Alice 100
   *player_max_hp @Bob 100
   *session_stats
   *session_end
   ```
3. **Monitor:** Railway dashboard → Logs
4. **Adjust:** Use `*set_value` to tweak balance if needed

---

## 🔒 Security Best Practices

- ✅ Never commit .env file
- ✅ Use Railway Secrets for sensitive values
- ✅ Rotate DISCORD_TOKEN if exposed
- ✅ Restrict bot to specific channel/role
- ✅ Log all GM commands (built-in)
- ✅ Run as limited Discord bot (not admin)
- ✅ Use read-only assets storage

---

## 📞 Support

**Bot won't start:**
- Check Railway logs: `Railway Dashboard → Logs`
- Verify Docker image built: `docker images`
- Re-deploy: Push to main branch

**Commands not working:**
- Verify .env loaded: `*show_values` command
- Check user has GM role
- Restart bot in Railway

**Crash during gameplay:**
- Check logs for error message
- Roll back to previous version if needed
- Create issue with logs

---

## 🚀 After Successful Deployment

1. **Celebrate!** 🎉 Bot is live in the cloud
2. **Monitor** first session - watch for errors
3. **Collect feedback** from GMs
4. **Iterate** - use `*set_value` to adjust balance
5. **Document** any configuration tweaks in .env.example

---

## 📚 Advanced

### Auto-scaling (Railway Pro)
Set min/max containers in Railway dashboard

### Custom domain
Railway → Domain → Add custom domain

### Webhooks for logging
Add in gm_commands.py to send events to Discord

### Database backup
Mount `/app/data` volume to persistent Railway disk

---

## ✅ You're Done!

Your Discord QTE bot is now:
- ✅ Running in the cloud
- ✅ Accessible 24/7 without your PC
- ✅ Configurable via .env file
- ✅ Manageable by GMs via commands
- ✅ Logged and monitored

**Time to go! 🎮**
