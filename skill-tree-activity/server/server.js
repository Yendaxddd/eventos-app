import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// In-memory storage (replace with database in production)
const playerSkills = new Map();

// OAuth2 Token Exchange
app.post('/api/token', async (req, res) => {
  const { code } = req.body;
  
  try {
    const response = await fetch('https://discord.com/api/oauth2/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: process.env.VITE_DISCORD_CLIENT_ID,
        client_secret: process.env.DISCORD_CLIENT_SECRET,
        grant_type: 'authorization_code',
        code,
      }),
    });
    
    const data = await response.json();
    
    if (data.error) {
      console.error('Token exchange error:', data);
      return res.status(400).json({ error: data.error });
    }
    
    res.json({ access_token: data.access_token });
  } catch (error) {
    console.error('Token exchange failed:', error);
    res.status(500).json({ error: 'Failed to exchange token' });
  }
});

// Get player skill data
app.get('/api/player/:userId/skills', async (req, res) => {
  const { userId } = req.params;
  
  // Try to get from bot API first
  try {
    const botApiUrl = process.env.BOT_API_URL;
    if (botApiUrl) {
      const response = await fetch(`${botApiUrl}/player/${userId}/skills`);
      if (response.ok) {
        const data = await response.json();
        return res.json(data);
      }
    }
  } catch (error) {
    console.log('Bot API not available, using local storage');
  }
  
  // Fallback to local storage
  let data = playerSkills.get(userId);
  
  if (!data) {
    // Initialize new player
    data = {
      level: 1,
      skillPoints: 5,
      unlockedSkills: [],
      stats: {},
    };
    playerSkills.set(userId, data);
  }
  
  res.json(data);
});

// Unlock a skill
app.post('/api/player/:userId/skills/unlock', async (req, res) => {
  const { userId } = req.params;
  const { skillId } = req.body;
  
  // Try bot API first
  try {
    const botApiUrl = process.env.BOT_API_URL;
    if (botApiUrl) {
      const response = await fetch(`${botApiUrl}/player/${userId}/skills/unlock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skillId }),
      });
      
      if (response.ok) {
        const data = await response.json();
        return res.json(data);
      }
    }
  } catch (error) {
    console.log('Bot API not available, using local storage');
  }
  
  // Fallback to local storage
  let data = playerSkills.get(userId);
  
  if (!data) {
    return res.status(404).json({ error: 'Player not found' });
  }
  
  // Simple validation (real validation should check requirements)
  if (data.skillPoints < 1) {
    return res.status(400).json({ success: false, error: 'Not enough skill points' });
  }
  
  if (data.unlockedSkills.includes(skillId)) {
    return res.status(400).json({ success: false, error: 'Skill already unlocked' });
  }
  
  // Unlock the skill
  data.unlockedSkills.push(skillId);
  data.skillPoints -= 1; // TODO: Use actual skill cost
  playerSkills.set(userId, data);
  
  res.json({
    success: true,
    skillId,
    skillName: skillId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    skillPoints: data.skillPoints,
  });
});

// Sync with bot (called by the bot to push updates)
app.post('/api/sync/:userId', (req, res) => {
  const { userId } = req.params;
  const data = req.body;
  
  playerSkills.set(userId, data);
  res.json({ success: true });
});

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: Date.now() });
});

app.listen(PORT, () => {
  console.log(`Skill Tree Activity server running on port ${PORT}`);
});
