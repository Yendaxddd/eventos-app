"""
GM Commands Module - Game Master session management and value tuning
This module provides commands for GMs to manage sessions, adjust gameplay values, and control bot behavior
"""

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv, set_key
import json
from datetime import datetime

load_dotenv()

class GMCommands(commands.Cog):
    """Game Master administrative commands"""
    
    def __init__(self, bot, qte_manager):
        self.bot = bot
        self.qte = qte_manager
        self.gm_role_id = int(os.getenv("GM_ROLE_ID", "0"))
        self.session_active = False
        self.session_start_time = None
        self.session_stats = {}
    
    def is_gm(self):
        """Check if user has GM role"""
        async def predicate(ctx):
            if not self.gm_role_id:
                return ctx.author.id == ctx.guild.owner_id
            role = ctx.guild.get_role(self.gm_role_id)
            return role in ctx.author.roles if role else False
        return commands.check(predicate)
    
    # ========== SESSION MANAGEMENT ==========
    
    @commands.command(name="session_start")
    @is_gm()
    async def session_start(self, ctx, enemy_name: str = "Boss", difficulty: str = "medium"):
        """Start a new battle session (GM only)
        Usage: *session_start @BossName hard
        Difficulties: easy, medium, hard, impossible
        """
        if self.session_active:
            await ctx.send("⚠️ A session is already active! Use `*session_end` first.")
            return
        
        if difficulty not in ["easy", "medium", "hard", "impossible"]:
            difficulty = "medium"
        
        self.session_active = True
        self.session_start_time = datetime.now()
        self.session_stats = {
            "boss": enemy_name,
            "difficulty": difficulty,
            "participants": [],
            "duration": 0,
            "total_damage_dealt": 0,
            "total_damage_taken": 0
        }
        
        embed = discord.Embed(
            title="⚔️ NEW SESSION STARTED",
            description=f"**Boss:** {enemy_name}\n**Difficulty:** {difficulty.upper()}",
            color=discord.Color.red()
        )
        embed.add_field(name="Session Started", value=f"<t:{int(self.session_start_time.timestamp())}:T>")
        embed.add_field(name="GM", value=ctx.author.mention)
        embed.set_footer(text="Use *player_list to see participants | *session_stats for updates")
        
        await ctx.send(embed=embed)
        print(f"[GM] {ctx.author.name} started session vs {enemy_name} ({difficulty})")
    
    @commands.command(name="session_end")
    @is_gm()
    async def session_end(self, ctx):
        """End the current battle session (GM only)"""
        if not self.session_active:
            await ctx.send("❌ No active session!")
            return
        
        self.session_active = False
        duration = (datetime.now() - self.session_start_time).total_seconds() / 60
        self.session_stats["duration"] = duration
        
        embed = discord.Embed(
            title="✅ SESSION ENDED",
            color=discord.Color.green()
        )
        embed.add_field(name="Boss", value=self.session_stats["boss"])
        embed.add_field(name="Duration", value=f"{duration:.1f} minutes")
        embed.add_field(name="Difficulty", value=self.session_stats["difficulty"].upper())
        embed.add_field(name="Participants", value=str(len(self.session_stats.get("participants", []))), inline=False)
        embed.add_field(name="Total Damage Dealt", value=str(self.session_stats.get("total_damage_dealt", 0)))
        embed.add_field(name="Total Damage Taken", value=str(self.session_stats.get("total_damage_taken", 0)))
        
        await ctx.send(embed=embed)
        print(f"[GM] {ctx.author.name} ended session")
    
    @commands.command(name="session_stats")
    @is_gm()
    async def session_stats(self, ctx):
        """Display current session statistics (GM only)"""
        if not self.session_active:
            await ctx.send("❌ No active session!")
            return
        
        duration = (datetime.now() - self.session_start_time).total_seconds() / 60
        
        embed = discord.Embed(
            title="📊 SESSION STATISTICS",
            color=discord.Color.blue()
        )
        embed.add_field(name="Boss", value=self.session_stats["boss"])
        embed.add_field(name="Elapsed Time", value=f"{duration:.1f} minutes")
        embed.add_field(name="Difficulty", value=self.session_stats["difficulty"].upper())
        embed.add_field(name="Active Participants", value=str(len(self.session_stats.get("participants", []))), inline=False)
        
        await ctx.send(embed=embed)
    
    # ========== PLAYER MANAGEMENT ==========
    
    @commands.command(name="player_hp")
    @is_gm()
    async def player_hp(self, ctx, target: discord.User, hp: int):
        """Set a player's current HP (GM only)
        Usage: *player_hp @PlayerName 75
        """
        if target.id not in self.qte.player_hp:
            await ctx.send(f"❌ {target.mention} not in active fight!")
            return
        
        self.qte.player_hp[target.id]["current"] = max(0, min(hp, self.qte.player_hp[target.id]["max"]))
        await ctx.send(f"✅ Set {target.mention}'s HP to **{hp}**")
    
    @commands.command(name="player_max_hp")
    @is_gm()
    async def player_max_hp(self, ctx, target: discord.User, max_hp: int):
        """Set a player's maximum HP (GM only)"""
        if target.id not in self.qte.player_hp:
            self.qte.player_hp[target.id] = {"current": max_hp, "max": max_hp, "alive": True}
        
        self.qte.player_hp[target.id]["max"] = max_hp
        self.qte.player_hp[target.id]["current"] = min(self.qte.player_hp[target.id]["current"], max_hp)
        
        await ctx.send(f"✅ Set {target.mention}'s max HP to **{max_hp}**")
    
    @commands.command(name="player_revive")
    @is_gm()
    async def player_revive(self, ctx, target: discord.User):
        """Revive a dead player (GM only)"""
        if target.id not in self.qte.player_hp:
            await ctx.send(f"❌ {target.mention} not in fight!")
            return
        
        max_hp = self.qte.player_hp[target.id]["max"]
        self.qte.player_hp[target.id]["current"] = max_hp
        self.qte.player_hp[target.id]["alive"] = True
        
        await ctx.send(f"💚 **{target.mention}** revived with **{max_hp} HP**!")
    
    @commands.command(name="player_list")
    @is_gm()
    async def player_list(self, ctx):
        """Display all active players in session (GM only)"""
        if not self.qte.player_hp:
            await ctx.send("❌ No active players!")
            return
        
        embed = discord.Embed(title="👥 ACTIVE PLAYERS", color=discord.Color.blue())
        
        for user_id, hp_data in self.qte.player_hp.items():
            try:
                user = await self.bot.fetch_user(user_id)
                status = "🟢 ALIVE" if hp_data["alive"] else "💀 DEAD"
                embed.add_field(
                    name=f"{user.name} {status}",
                    value=f"HP: {hp_data['current']}/{hp_data['max']}",
                    inline=False
                )
            except:
                pass
        
        await ctx.send(embed=embed)
    
    # ========== BOSS MANAGEMENT ==========
    
    @commands.command(name="boss_hp")
    @is_gm()
    async def boss_hp(self, ctx, hp: int):
        """Set current boss HP (GM only)"""
        if not self.qte.active_boss:
            await ctx.send("❌ No active boss!")
            return
        
        self.qte.active_boss["current_hp"] = max(0, hp)
        await ctx.send(f"✅ Boss HP set to **{hp}**")
    
    @commands.command(name="boss_status")
    @is_gm()
    async def boss_status(self, ctx):
        """Display current boss status (GM only)"""
        if not self.qte.active_boss:
            await ctx.send("❌ No active boss!")
            return
        
        boss = self.qte.active_boss
        embed = discord.Embed(
            title=f"👹 {boss['name']}",
            color=discord.Color.red()
        )
        embed.add_field(name="HP", value=f"{boss.get('current_hp', boss['max_hp'])}/{boss['max_hp']}")
        embed.add_field(name="Difficulty", value=boss.get("difficulty", "unknown").upper())
        embed.add_field(name="Stunned", value="Yes 🌀" if self.qte.enemy_stunned else "No")
        
        await ctx.send(embed=embed)
    
    # ========== VALUE TUNING ==========
    
    @commands.command(name="show_values")
    @is_gm()
    async def show_values(self, ctx):
        """Show all current gameplay values from .env (GM only)"""
        embed = discord.Embed(
            title="⚙️ GAMEPLAY VALUES",
            color=discord.Color.blue()
        )
        
        categories = {
            "HP & Regen": ["PLAYER_MAX_HP", "PLAYER_REGEN_PER_CHECKPOINT"],
            "Charge System": ["ULT_CHARGE_PER_DAMAGE_DEALT", "ULT_CHARGE_PER_DAMAGE_TAKEN", "ULT_BASE_COOLDOWN_SECONDS"],
            "QTE": ["QTE_BASE_DAMAGE", "QTE_EASY_DAMAGE_MIN", "QTE_HARD_DAMAGE_MAX"],
            "Domains": ["DOMAIN_BASE_COOLDOWN_SECONDS", "DOMAIN_BASE_STUN_DURATION", "VAR_CAST_TIME_SECONDS"],
        }
        
        for category, keys in categories.items():
            values = []
            for key in keys:
                val = os.getenv(key, "NOT SET")
                values.append(f"`{key}`: {val}")
            embed.add_field(name=category, value="\n".join(values), inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="set_value")
    @is_gm()
    async def set_value(self, ctx, key: str, value: str):
        """Set a gameplay value in .env (GM only)
        Usage: *set_value PLAYER_MAX_HP 200
        Changes persist until bot restart
        """
        try:
            # Try to convert to number if possible
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass  # Keep as string
            
            # Update in-memory and .env file
            os.environ[key] = str(value)
            
            # Persist to .env file
            env_path = ".env"
            if os.path.exists(env_path):
                set_key(env_path, key, str(value))
            
            await ctx.send(f"✅ Set `{key}` = `{value}`")
            print(f"[GM] {ctx.author.name} set {key} = {value}")
            
        except Exception as e:
            await ctx.send(f"❌ Error setting value: {e}")
    
    @commands.command(name="set_multiplier")
    @is_gm()
    async def set_multiplier(self, ctx, mult_type: str, value: float):
        """Set a gameplay multiplier (GM only)
        Types: damage, charge, cooldown, duration
        Usage: *set_multiplier damage 1.5
        """
        multiplier_map = {
            "damage": "DIFFICULTY_HARD_DAMAGE_MULTIPLIER",
            "charge": "ULT_CHARGE_PER_DAMAGE_DEALT",
            "cooldown": "DOMAIN_BASE_COOLDOWN_SECONDS",
            "duration": "DOMAIN_BASE_STUN_DURATION",
        }
        
        if mult_type not in multiplier_map:
            await ctx.send(f"❌ Unknown multiplier type. Use: {', '.join(multiplier_map.keys())}")
            return
        
        key = multiplier_map[mult_type]
        os.environ[key] = str(value)
        
        env_path = ".env"
        if os.path.exists(env_path):
            set_key(env_path, key, str(value))
        
        await ctx.send(f"✅ Multiplier `{mult_type}` set to `{value}`")
        print(f"[GM] {ctx.author.name} set {mult_type} multiplier to {value}")
    
    @commands.command(name="reload_config")
    @is_gm()
    async def reload_config(self, ctx):
        """Reload all configuration from .env file (GM only)"""
        try:
            load_dotenv(override=True)
            await ctx.send("✅ Configuration reloaded from .env")
            print(f"[GM] {ctx.author.name} reloaded config")
        except Exception as e:
            await ctx.send(f"❌ Error reloading config: {e}")
    
    # ========== DOMAIN MANAGEMENT ==========
    
    @commands.command(name="domain_unlock")
    @is_gm()
    async def domain_unlock(self, ctx, target: discord.User, domain_name: str):
        """Unlock a domain for a player (GM only)
        Usage: *domain_unlock @Player infinite_void
        """
        user_id_str = str(target.id)
        
        if user_id_str not in self.qte.player_achievements:
            self.qte.player_achievements[user_id_str] = {"domains": [], "powers": []}
        
        if domain_name not in self.qte.player_achievements[user_id_str]["domains"]:
            self.qte.player_achievements[user_id_str]["domains"].append(domain_name)
        
        await ctx.send(f"✅ Unlocked **{domain_name}** for {target.mention}")
        print(f"[GM] Unlocked {domain_name} for {target.name}")
    
    @commands.command(name="domain_set_active")
    @is_gm()
    async def domain_set_active(self, ctx, target: discord.User, domain_name: str):
        """Set active domain for a player (GM only)"""
        user_id_str = str(target.id)
        
        if user_id_str not in self.qte.player_achievements:
            await ctx.send(f"❌ Player not initialized!")
            return
        
        self.qte.player_achievements[user_id_str]["active_domain"] = domain_name
        
        await ctx.send(f"✅ Set active domain to **{domain_name}** for {target.mention}")

# Setup function to add cog to bot
async def setup(bot, qte_manager):
    """Load GM commands cog"""
    await bot.add_cog(GMCommands(bot, qte_manager))
    print("✅ GM Commands module loaded")
