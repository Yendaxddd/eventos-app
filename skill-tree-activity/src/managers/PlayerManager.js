import { SKILL_TREES } from "../data/skills.js";

export class PlayerManager {
  constructor(userId, data) {
    this.userId = userId;
    this.level = data.level || 1;
    this.skillPoints = data.skillPoints || 0;
    this.unlockedSkills = new Set(data.unlockedSkills || []);
    this.stats = data.stats || {};
  }
  
  hasSkill(skillId) {
    return this.unlockedSkills.has(skillId);
  }
  
  canUnlockSkill(skillId) {
    // Already unlocked
    if (this.hasSkill(skillId)) {
      return false;
    }
    
    // Find the skill in any tree
    let skill = null;
    for (const treeKey of Object.keys(SKILL_TREES)) {
      const found = SKILL_TREES[treeKey].skills.find((s) => s.id === skillId);
      if (found) {
        skill = found;
        break;
      }
    }
    
    if (!skill) return false;
    
    // Check level requirement
    if (skill.levelRequired && this.level < skill.levelRequired) {
      return false;
    }
    
    // Check skill points
    const cost = skill.cost || 1;
    if (this.skillPoints < cost) {
      return false;
    }
    
    // Check required skills
    if (skill.requires) {
      for (const reqId of skill.requires) {
        if (!this.hasSkill(reqId)) {
          return false;
        }
      }
    }
    
    return true;
  }
  
  unlockSkill(skillId) {
    // Find skill to get cost
    let skill = null;
    for (const treeKey of Object.keys(SKILL_TREES)) {
      const found = SKILL_TREES[treeKey].skills.find((s) => s.id === skillId);
      if (found) {
        skill = found;
        break;
      }
    }
    
    if (skill) {
      const cost = skill.cost || 1;
      this.skillPoints -= cost;
      this.unlockedSkills.add(skillId);
    }
  }
  
  getSkillEffects() {
    // Aggregate all effects from unlocked skills
    const effects = {
      damage_bonus: 0,
      defense_bonus: 0,
      heal_bonus: 0,
      crit_chance: 0,
      crit_damage: 0,
      evade_chance: 0,
      counter_damage: 0,
      ult_charge_rate: 0,
      domain_duration: 0,
      special_effects: [],
    };
    
    for (const skillId of this.unlockedSkills) {
      for (const treeKey of Object.keys(SKILL_TREES)) {
        const skill = SKILL_TREES[treeKey].skills.find((s) => s.id === skillId);
        if (skill && skill.bonuses) {
          for (const [key, value] of Object.entries(skill.bonuses)) {
            if (key === "special") {
              effects.special_effects.push(value);
            } else if (effects[key] !== undefined) {
              effects[key] += value;
            }
          }
        }
      }
    }
    
    return effects;
  }
}
