import { DiscordSDK } from "@discord/embedded-app-sdk";
import { SkillTree } from "./components/SkillTree.js";
import { PlayerManager } from "./managers/PlayerManager.js";

// Discord SDK instance
const discordSdk = new DiscordSDK(import.meta.env.VITE_DISCORD_CLIENT_ID);

// Global state
let auth = null;
let playerManager = null;
let skillTree = null;

// Initialize the application
async function init() {
  try {
    await setupDiscordSdk();
    await loadPlayerData();
    initializeSkillTree();
    hideLoading();
  } catch (error) {
    console.error("Initialization failed:", error);
    showError("Failed to connect. Please try again.");
  }
}

async function setupDiscordSdk() {
  console.log("Setting up Discord SDK...");
  await discordSdk.ready();
  console.log("Discord SDK is ready");

  // Authorize with Discord
  const { code } = await discordSdk.commands.authorize({
    client_id: import.meta.env.VITE_DISCORD_CLIENT_ID,
    response_type: "code",
    state: "",
    prompt: "none",
    scope: ["identify", "guilds"],
  });

  // Exchange code for access token
  const response = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });

  const { access_token } = await response.json();

  // Authenticate with Discord
  auth = await discordSdk.commands.authenticate({ access_token });

  if (!auth) {
    throw new Error("Authentication failed");
  }

  console.log("Authenticated as:", auth.user.username);
  updatePlayerDisplay(auth.user);
}

async function loadPlayerData() {
  const userId = auth.user.id;
  
  // Fetch player skill data from our backend
  const response = await fetch(`/api/player/${userId}/skills`);
  const data = await response.json();
  
  playerManager = new PlayerManager(userId, data);
  
  // Update UI
  document.getElementById("skill-points-value").textContent = data.skillPoints || 0;
  document.getElementById("player-level").textContent = `Lvl ${data.level || 1}`;
}

function updatePlayerDisplay(user) {
  const avatarUrl = user.avatar
    ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.webp?size=64`
    : `https://cdn.discordapp.com/embed/avatars/${parseInt(user.discriminator) % 5}.png`;
  
  document.getElementById("player-avatar").src = avatarUrl;
  document.getElementById("player-name").textContent = user.username;
}

function initializeSkillTree() {
  const container = document.getElementById("skill-tree");
  const nodesContainer = document.getElementById("skill-nodes");
  const connectionsContainer = document.getElementById("skill-connections");
  
  skillTree = new SkillTree({
    container,
    nodesContainer,
    connectionsContainer,
    playerManager,
    onSkillSelect: showSkillDetails,
    onSkillUnlock: handleSkillUnlock,
  });
  
  skillTree.render();
  
  // Navigation buttons
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const treeType = btn.dataset.tree;
      skillTree.switchTree(treeType);
      
      // Update active state
      document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
  
  // Set default tree
  document.querySelector('[data-tree="combat"]').classList.add("active");
}

function showSkillDetails(skill) {
  const panel = document.getElementById("skill-details");
  const unlockBtn = document.getElementById("unlock-btn");
  
  document.getElementById("detail-name").textContent = skill.name;
  document.getElementById("detail-description").textContent = skill.description;
  
  // Requirements
  const reqList = document.getElementById("requirements-list");
  reqList.innerHTML = "";
  skill.requirements.forEach((req) => {
    const li = document.createElement("li");
    li.textContent = req.text;
    li.className = req.met ? "met" : "unmet";
    reqList.appendChild(li);
  });
  
  // Effects
  const effectsList = document.getElementById("effects-list");
  effectsList.innerHTML = "";
  skill.effects.forEach((effect) => {
    const li = document.createElement("li");
    li.textContent = effect;
    effectsList.appendChild(li);
  });
  
  // Unlock button
  const canUnlock = playerManager.canUnlockSkill(skill.id);
  unlockBtn.disabled = !canUnlock;
  unlockBtn.onclick = () => handleSkillUnlock(skill.id);
  
  panel.classList.remove("hidden");
}

async function handleSkillUnlock(skillId) {
  try {
    const response = await fetch(`/api/player/${auth.user.id}/skills/unlock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skillId }),
    });
    
    const result = await response.json();
    
    if (result.success) {
      playerManager.unlockSkill(skillId);
      skillTree.updateNode(skillId);
      
      // Update skill points display
      document.getElementById("skill-points-value").textContent = result.skillPoints;
      
      // Show success feedback
      showNotification(`Unlocked: ${result.skillName}!`);
    } else {
      showNotification(result.error, "error");
    }
  } catch (error) {
    console.error("Failed to unlock skill:", error);
    showNotification("Failed to unlock skill", "error");
  }
}

function showNotification(message, type = "success") {
  // Create notification element
  const notification = document.createElement("div");
  notification.className = `notification ${type}`;
  notification.textContent = message;
  document.body.appendChild(notification);
  
  // Animate in
  requestAnimationFrame(() => {
    notification.classList.add("show");
  });
  
  // Remove after delay
  setTimeout(() => {
    notification.classList.remove("show");
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}

function hideLoading() {
  document.getElementById("loading-screen").classList.add("hidden");
  document.getElementById("skill-tree-container").classList.remove("hidden");
}

function showError(message) {
  const loading = document.getElementById("loading-screen");
  loading.innerHTML = `
    <div class="error-message">
      <p>⚠️ ${message}</p>
      <button onclick="location.reload()">Retry</button>
    </div>
  `;
}

// Close details panel
document.getElementById("close-details")?.addEventListener("click", () => {
  document.getElementById("skill-details").classList.add("hidden");
});

// Start the app
init();
