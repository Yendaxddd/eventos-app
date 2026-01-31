import { SKILL_TREES } from "../data/skills.js";

export class SkillTree {
  constructor({ container, nodesContainer, connectionsContainer, playerManager, onSkillSelect, onSkillUnlock }) {
    this.container = container;
    this.nodesContainer = nodesContainer;
    this.connectionsContainer = connectionsContainer;
    this.playerManager = playerManager;
    this.onSkillSelect = onSkillSelect;
    this.onSkillUnlock = onSkillUnlock;
    this.currentTree = "combat";
    this.nodes = new Map();
    
    // Pan and zoom state
    this.transform = { x: 0, y: 0, scale: 1 };
    this.isDragging = false;
    this.lastPosition = { x: 0, y: 0 };
    
    this.setupPanZoom();
  }
  
  setupPanZoom() {
    // Mouse wheel zoom
    this.container.addEventListener("wheel", (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      this.transform.scale = Math.min(Math.max(this.transform.scale * delta, 0.5), 2);
      this.applyTransform();
    });
    
    // Pan with mouse drag
    this.container.addEventListener("mousedown", (e) => {
      if (e.target === this.container || e.target === this.nodesContainer) {
        this.isDragging = true;
        this.lastPosition = { x: e.clientX, y: e.clientY };
        this.container.style.cursor = "grabbing";
      }
    });
    
    window.addEventListener("mousemove", (e) => {
      if (this.isDragging) {
        const dx = e.clientX - this.lastPosition.x;
        const dy = e.clientY - this.lastPosition.y;
        this.transform.x += dx;
        this.transform.y += dy;
        this.lastPosition = { x: e.clientX, y: e.clientY };
        this.applyTransform();
      }
    });
    
    window.addEventListener("mouseup", () => {
      this.isDragging = false;
      this.container.style.cursor = "grab";
    });
    
    // Touch support
    let touchStart = null;
    this.container.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) {
        touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }
    });
    
    this.container.addEventListener("touchmove", (e) => {
      if (touchStart && e.touches.length === 1) {
        const dx = e.touches[0].clientX - touchStart.x;
        const dy = e.touches[0].clientY - touchStart.y;
        this.transform.x += dx;
        this.transform.y += dy;
        touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        this.applyTransform();
      }
    });
  }
  
  applyTransform() {
    const transformStr = `translate(${this.transform.x}px, ${this.transform.y}px) scale(${this.transform.scale})`;
    this.nodesContainer.style.transform = transformStr;
    this.connectionsContainer.style.transform = transformStr;
  }
  
  switchTree(treeType) {
    this.currentTree = treeType;
    this.transform = { x: 0, y: 0, scale: 1 };
    this.applyTransform();
    this.render();
  }
  
  render() {
    const tree = SKILL_TREES[this.currentTree];
    if (!tree) return;
    
    this.nodesContainer.innerHTML = "";
    this.connectionsContainer.innerHTML = "";
    this.nodes.clear();
    
    // Render connections first (below nodes)
    this.renderConnections(tree);
    
    // Render nodes
    tree.skills.forEach((skill) => {
      this.renderNode(skill);
    });
  }
  
  renderConnections(tree) {
    tree.skills.forEach((skill) => {
      if (skill.requires) {
        skill.requires.forEach((reqId) => {
          const reqSkill = tree.skills.find((s) => s.id === reqId);
          if (reqSkill) {
            this.drawConnection(reqSkill, skill);
          }
        });
      }
    });
  }
  
  drawConnection(fromSkill, toSkill) {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    
    // Calculate center positions
    const x1 = fromSkill.position.x + 40; // Half of node width
    const y1 = fromSkill.position.y + 40;
    const x2 = toSkill.position.x + 40;
    const y2 = toSkill.position.y + 40;
    
    line.setAttribute("x1", x1);
    line.setAttribute("y1", y1);
    line.setAttribute("x2", x2);
    line.setAttribute("y2", y2);
    
    // Style based on unlock status
    const fromUnlocked = this.playerManager.hasSkill(fromSkill.id);
    const toUnlocked = this.playerManager.hasSkill(toSkill.id);
    
    if (fromUnlocked && toUnlocked) {
      line.classList.add("connection-unlocked");
    } else if (fromUnlocked) {
      line.classList.add("connection-available");
    } else {
      line.classList.add("connection-locked");
    }
    
    this.connectionsContainer.appendChild(line);
  }
  
  renderNode(skill) {
    const node = document.createElement("div");
    node.className = "skill-node";
    node.dataset.skillId = skill.id;
    
    // Position
    node.style.left = `${skill.position.x}px`;
    node.style.top = `${skill.position.y}px`;
    
    // Icon
    const icon = document.createElement("div");
    icon.className = "skill-icon";
    icon.textContent = skill.icon;
    node.appendChild(icon);
    
    // Name tooltip
    const tooltip = document.createElement("div");
    tooltip.className = "skill-tooltip";
    tooltip.textContent = skill.name;
    node.appendChild(tooltip);
    
    // State classes
    const isUnlocked = this.playerManager.hasSkill(skill.id);
    const canUnlock = this.playerManager.canUnlockSkill(skill.id);
    
    if (isUnlocked) {
      node.classList.add("unlocked");
    } else if (canUnlock) {
      node.classList.add("available");
    } else {
      node.classList.add("locked");
    }
    
    // Tier indicator
    if (skill.tier) {
      node.dataset.tier = skill.tier;
    }
    
    // Click handler
    node.addEventListener("click", (e) => {
      e.stopPropagation();
      this.selectNode(skill);
    });
    
    this.nodesContainer.appendChild(node);
    this.nodes.set(skill.id, node);
  }
  
  selectNode(skill) {
    // Remove previous selection
    this.nodesContainer.querySelectorAll(".selected").forEach((n) => {
      n.classList.remove("selected");
    });
    
    // Select new node
    const node = this.nodes.get(skill.id);
    if (node) {
      node.classList.add("selected");
    }
    
    // Build requirements info
    const requirements = [];
    
    // Level requirement
    if (skill.levelRequired) {
      requirements.push({
        text: `Level ${skill.levelRequired}`,
        met: this.playerManager.level >= skill.levelRequired,
      });
    }
    
    // Skill points
    requirements.push({
      text: `${skill.cost || 1} Skill Point(s)`,
      met: this.playerManager.skillPoints >= (skill.cost || 1),
    });
    
    // Required skills
    if (skill.requires) {
      skill.requires.forEach((reqId) => {
        const reqSkill = SKILL_TREES[this.currentTree].skills.find((s) => s.id === reqId);
        if (reqSkill) {
          requirements.push({
            text: `Requires: ${reqSkill.name}`,
            met: this.playerManager.hasSkill(reqId),
          });
        }
      });
    }
    
    // Trigger callback with enriched skill data
    this.onSkillSelect({
      ...skill,
      requirements,
    });
  }
  
  updateNode(skillId) {
    // Re-render the entire tree to update connections too
    this.render();
  }
}
