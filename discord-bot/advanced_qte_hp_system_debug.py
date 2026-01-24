# Advanced QTE Discord Bot - With Black Flash System
# Install required packages: pip install discord.py requests keyboard rich python-dotenv

import discord
from discord.ext import commands
from discord import app_commands
import requests
import time
import threading
import asyncio
import json
import random
import os
import pathlib
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box

# Import Eventos API Bridge
from simple_api_bridge import SimpleEventosAPI

# Optional keyboard library (requires root on Linux)
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    print("⚠️ Keyboard hotkeys not available. Install 'keyboard' or run with sudo for hotkey support.")
    KEYBOARD_AVAILABLE = False
except Exception as e:
    print(f"⚠️ Keyboard library error: {e}")
    KEYBOARD_AVAILABLE = False

# Initialize Rich console
console = Console()

# Load environment variables
load_dotenv()

# Setup logging (file only, console handled by Rich)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler("qte_bot.log", encoding="utf-8", mode="a")
    ],
)
log = logging.getLogger("QTE_Bot")

# Persistence helpers
DATA_DIR = pathlib.Path("data")
DATA_DIR.mkdir(exist_ok=True)

def load_data(name, default):
    """Load JSON data from file"""
    try:
        filepath = DATA_DIR / f"{name}.json"
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            log.debug(f"Loaded {name}.json successfully")
            # Convert string keys to int for user_id-based dicts
            if name in ("player_stats", "user_characters", "power_charges", "user_counter_gifs"):
                data = {int(k): v for k, v in data.items()}
            return data
    except FileNotFoundError:
        log.info(f"{name}.json not found, using default")
        return default
    except Exception as e:
        log.error(f"Error loading {name}.json: {e}")
        return default

def save_data(name, data):
    """Save JSON data to file"""
    try:
        filepath = DATA_DIR / f"{name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.debug(f"Saved {name}.json successfully")
    except Exception as e:
        log.error(f"Error saving {name}.json: {e}")

class AdvancedQTEBot:
    def __init__(self):
        # Bot configuration from environment variables
        self.bot_token = os.getenv("DISCORD_TOKEN")
        self.qte_channel_id = int(os.getenv("QTE_CHANNEL_ID", "0"))
        self.qte_player_role_id = int(os.getenv("QTE_PLAYER_ROLE_ID", "0"))
        self.admin_role_id = int(os.getenv("ADMIN_ROLE_ID", "0"))  # For restricted commands

        # Validate configuration
        if not self.bot_token:
            raise RuntimeError("DISCORD_TOKEN not found in environment variables! Create a .env file.")
        if not self.qte_channel_id:
            raise RuntimeError("QTE_CHANNEL_ID not found in environment variables!")
        if not self.qte_player_role_id:
            raise RuntimeError("QTE_PLAYER_ROLE_ID not found in environment variables!")

        console.print("[green]✓ Configuration loaded[/green]")
        console.print(f"[cyan]  Channel ID: {self.qte_channel_id}[/cyan]")
        console.print(f"[magenta]  Role ID: {self.qte_player_role_id}[/magenta]")
        if self.admin_role_id:
            console.print(f"[yellow]  Admin Role ID: {self.admin_role_id}[/yellow]")

        # Initialize Eventos API Bridge
        try:
            self.eventos_api = SimpleEventosAPI("http://localhost:7001")
            if self.eventos_api.health_check():
                console.print("[green]✓ Eventos API connected - using corrected damage formula[/green]")
                self.api_available = True
            else:
                console.print("[yellow]⚠ Eventos API unavailable - using fallback calculations[/yellow]")
                self.api_available = False
        except Exception as e:
            console.print(f"[red]✗ Eventos API connection failed: {e}[/red]")
            self.api_available = False

        # Bot setup with slash commands
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        self.bot = commands.Bot(command_prefix='!', intents=intents)

        # Load persistent data
        self.character_registry = load_data("character_registry", {})
        self.user_characters = load_data("user_characters", {})
        self.player_stats = load_data("player_stats", {})
        self.character_powers = load_data("character_powers", {})
        self.power_charges = load_data("power_charges", {})  # Persist ultimate charges
        self.user_counter_gifs = load_data("user_counter_gifs", {})  # User custom counter GIFs (now supports arrays)
        self.player_buffs = load_data("player_buffs", {})  # Active buffs: {user_id: {buff_type: {value, expires}}}

        console.print(f"[yellow]✓ Loaded {len(self.character_registry)} character registrations[/yellow]")
        console.print(f"[yellow]✓ Loaded stats for {len(self.player_stats)} players[/yellow]")
        console.print(f"[purple]✓ Loaded powers for {len(self.character_powers)} characters[/purple]")
        console.print(f"[purple]✓ Loaded charges for {len(self.power_charges)} players[/purple]")
        console.print(f"[purple]✓ Loaded counter GIFs for {len(self.user_counter_gifs)} players[/purple]")

        # QTE State Management - Support multiple concurrent QTEs
        self.active_qtes = {}  # Dictionary: qte_id -> qte_data
        self.qte_counter = 0   # Counter for unique QTE IDs
        self.afk_users = set()
        self.last_qte_completion = {}  # {user_id: timestamp} for anti-spam
        
        # ========== WEBHOOK ROTATION SYSTEM ==========
        # Each webhook has its own rate limit bucket - rotating = 3x throughput!
        self.webhooks = []  # List of discord.Webhook objects
        self.webhook_index = 0  # Current webhook in rotation
        self.webhook_names = ["QTE-Alpha", "QTE-Beta", "QTE-Gamma"]
        self.webhooks_initialized = False
        # =============================================
        
        # Boss system
        self.active_boss = None  # {name, hp_current, hp_max, gif_url, participants}

        # ========== HP BAR SYSTEM ==========
        self.hp_bar_thread_id = int(os.getenv("HP_BAR_THREAD_ID", 0))
        self.player_hp = {}  # {user_id: {"current": 100, "max": 100, "alive": True, "revenge_mode": False}}
        self.max_hp = 100
        self.hp_bar_messages = {}  # Cache: {user_id_or_boss_name: message_id} - prevents slow history searches
        
        # Variable damage per difficulty
        self.damage_ranges = {
            'easy': (1, 3),        # Random 1-3 damage
            'medium': (1, 5),      # Random 1-5 damage
            'hard': (1, 10),       # Random 1-10 damage
            'impossible': (15, 15) # Fixed 15 damage
        }
        
        # REVENGE mode configuration (triggers at 20% HP)
        self.revenge_threshold = 0.20  # 20% HP
        self.revenge_parry_shift = -0.3  # Parry window 0.3s earlier
        self.revenge_parry_tightness = 0.7  # Windows 30% tighter
        self.revenge_damage_multiplier = 1.5  # 50% more damage
        self.revenge_bf_bonus = 0.10  # +10% Black Flash chance
        
        # HP Regeneration checkpoints
        self.regen_checkpoints = []  # List of checkpoint markers
        self.regen_amount = 30  # HP restored per checkpoint
        # ===== PHASE 5: ULTIMATE POWER CHARGE SYSTEM =====
        # power_charges is loaded from file above - do NOT overwrite here
        self.charge_per_damage_dealt = 2.0  # NERFED: 2% per 10 damage dealt (was 5%)
        self.charge_per_damage_taken = 5.0  # NERFED: 5% per 5 damage taken (was 10%)
        self.charge_per_counter = 3.0  # NERFED: 3% per counter (was 5%)
        self.ultimate_cost = 100.0  # 100% charge required to use ultimate
        self.ultimate_gif = "https://media1.tenor.com/m/SvDVJdCkjagAAAAd/domain-expansion.gif"
        self.ultimate_self_recharge = False  # Toggle: Does landing ultimate recharge itself?
        self.ultimate_damage_multiplier = 1.0  # Full damage (reverted)
        self.ultimate_cooldown_per_damage = 0.5  # Extra seconds of cooldown per damage point
        # =================================================
        

        
        # ========== COUNTER MECHANIC ==========
        self.counter_enabled_players = {}  # {user_id: qte_id}
        self.counter_window = 1.5  # LOWERED: 1.5 seconds from QTE start (was 2.0)
        self.enemy_stunned = False
        self.stun_end_time = None
        self.counter_gif = "https://media.tenor.com/E0-GqnPpV8AAAAAC/jjk-black-flash.gif"
        self.counter_streaks = {}  # {user_id: streak_count} - for stun scaling
        # ======================================
        
        # ========== BLACK FLASH CHAIN SYSTEM ==========
        self.bf_chain_active = {}  # {user_id: chain_count} - tracks active BF chains (max 4)
        self.bf_chain_damage = {1: 25, 2: 50, 3: 100, 4: 200}  # Damage per chain level
        self.bf_parry_cooldowns = {1: 10, 2: 30, 3: 60, 4: 120}  # Cooldowns in seconds after each BF
        self.bf_timing_window = 0.5  # First BF timing tolerance (was 0.1)
        self.bf_chain_timing_window = 0.7  # Subsequent chain BFs timing window
        self.player_parry_cooldown = {}  # {user_id: timestamp} - parry locked until this time
        # ===============================================
        
        # ========== QTE BATCH MODE ==========
        self.batch_mode_active = False
        self.pending_qte_batch = []  # List of {'difficulty': str} during batch collection
        self.player_qte_queues = {}  # {user_id: [list of qte dicts]} - sequential processing
        self.player_current_qte = {}  # {user_id: qte_data} - currently active QTE per player
        # ====================================
        
        # ========== FAITH SYSTEM (LYRA'S SAFEGUARD) ==========
        self.faith_used_players = set()  # Track who used FAITH this event
        self.lyra_character_name = "Lyra"  # Case-insensitive check
        self.faith_gif_undertale = "https://i.imgur.com/undertale_determination.gif"  # Placeholder
        self.faith_gif_omori = "https://i.imgur.com/omori_persist.gif"  # Placeholder
        # =====================================================
        
        # ========== SPECIAL POWERS SYSTEM (ET - TOTAL ERADICATION) ==========
        self.power_cooldowns = {}  # {user_id: {"power1": timestamp, "power2": timestamp}}
        self.power_types = ["destructive", "support", "defend", "build", "control"]
        # character_powers is already loaded above - do NOT overwrite!
        # ====================================================================

        # Role caching
        self.qte_players = []
        self.last_cache_update = None
        self.cache_duration = timedelta(minutes=5)

        # Session stats
        self.session_stats = {
            'qtes_triggered': 0,
            'black_flashes_today': 0,
            'start_time': datetime.now()
        }
        
        # Data save throttling - prevents excessive disk writes
        self._last_save_time = 0
        self._save_interval = 10.0  # Minimum seconds between saves
        self._pending_save = False  # Flag for deferred saves

        # Black Flash configuration
        self.black_flash_base_chance = 0.02  # 2%
        self.black_flash_increment = 0.01    # 1% per success
        self.black_flash_cap = 0.20          # 20% maximum
        self.black_flash_gif = "https://media1.tenor.com/m/4JqGPWch2CYAAAAC/itadori-yuji-black-flash.gif"

        # Latency compensation (250ms grace for Discord/bot/internet delays)
        self.latency_offset = 0.25

        # QTE timing configurations (+500ms for better balance)
        self.qte_times = {
            'easy': {
                'evade_window': 6.0,      # Was 5.5, +0.5s
                'parry_window': (4.0, 7.0),  # Was (3.5, 6.5), +0.5s
                'perfect_parry': 5.5      # Center adjusted
            },
            'medium': {
                'evade_window': 4.5,      # Was 4.0, +0.5s
                'parry_window': (3.0, 5.0),  # Was (2.5, 4.5), +0.5s
                'perfect_parry': 4.0
            },
            'hard': {
                'evade_window': 4.0,      # Was 3.5, +0.5s
                'parry_window': (2.5, 4.5),  # Was (2.0, 4.0), +0.5s
                'perfect_parry': 3.5
            },
            'impossible': {
                'evade_window': 1.5,      # Was 1.0, +0.5s
                'parry_window': (0.8, 1.7),  # Was (0.3, 1.2), +0.5s
                'perfect_parry': 1.25
            }
        }

        # Difficulty emoji indicators
        self.difficulty_emoji = {
            'easy': '🟢',
            'medium': '🟡',
            'hard': '🔴',
            'impossible': '💀'
        }

        self.setup_events()
        self.setup_slash_commands()
        if KEYBOARD_AVAILABLE:
            self.setup_hotkeys()
        else:
            console.print("[yellow]⚠️  Keyboard hotkeys disabled (library not available or requires root)[/yellow]")

    def save_all_data(self, force=False):
        """Save all persistent data to files with throttling to prevent disk spam"""
        current_time = time.time()
        
        # Check if we should save now or defer
        if not force and (current_time - self._last_save_time) < self._save_interval:
            self._pending_save = True
            return
        
        save_data("character_registry", self.character_registry)
        save_data("user_characters", self.user_characters)
        save_data("player_stats", self.player_stats)
        save_data("character_powers", self.character_powers)
        save_data("power_charges", self.power_charges)  # Persist ultimate charges
        save_data("user_counter_gifs", self.user_counter_gifs)  # User custom counter GIFs
        save_data("player_buffs", self.player_buffs)  # Active buffs
        
        self._last_save_time = current_time
        self._pending_save = False
        console.print("[green]💾 Data saved to disk[/green]")
    
    async def periodic_save(self):
        """Periodically save pending data - call from event loop"""
        if self._pending_save:
            self.save_all_data(force=True)

    # ========== RATE-LIMITED MESSAGING ==========
    # ========== WEBHOOK ROTATION SYSTEM ==========
    async def initialize_webhooks(self):
        """Create or get existing webhooks for the QTE channel"""
        if self.webhooks_initialized:
            return
        
        try:
            channel = self.bot.get_channel(self.qte_channel_id)
            if not channel:
                console.print("[red]✗ Cannot initialize webhooks - channel not found[/red]")
                return
            
            # Get existing webhooks
            existing_webhooks = await channel.webhooks()
            
            # Find or create our webhooks
            for name in self.webhook_names:
                found = None
                for wh in existing_webhooks:
                    if wh.name == name:
                        found = wh
                        break
                
                if found:
                    self.webhooks.append(found)
                    console.print(f"[cyan]🪝 Found existing webhook: {name}[/cyan]")
                else:
                    # Create new webhook
                    new_wh = await channel.create_webhook(name=name)
                    self.webhooks.append(new_wh)
                    console.print(f"[green]🪝 Created webhook: {name}[/green]")
            
            self.webhooks_initialized = True
            console.print(f"[green]✓ {len(self.webhooks)} webhooks ready for rate-limit bypass![/green]")
            
        except discord.errors.Forbidden:
            console.print("[yellow]⚠️ No permission to manage webhooks - using fallback[/yellow]")
        except Exception as e:
            console.print(f"[red]✗ Webhook init error: {e}[/red]")
    
    def get_next_webhook(self):
        """Get the next webhook in rotation"""
        if not self.webhooks:
            return None
        webhook = self.webhooks[self.webhook_index]
        self.webhook_index = (self.webhook_index + 1) % len(self.webhooks)
        return webhook
    
    async def webhook_send(self, content=None, embed=None):
        """Send via rotating webhooks for rate limit bypass. Uses bot's name and avatar."""
        if not self.webhooks:
            # Fallback to regular channel send
            channel = self.bot.get_channel(self.qte_channel_id)
            if channel:
                return await channel.send(content=content, embed=embed)
            return None
        
        webhook = self.get_next_webhook()
        try:
            # Use bot's name and avatar for seamless appearance
            bot_name = self.bot.user.display_name if self.bot.user else "QTE Bot"
            bot_avatar = str(self.bot.user.avatar.url) if self.bot.user and self.bot.user.avatar else None
            
            # wait=True returns the message object
            msg = await webhook.send(
                content=content, 
                embed=embed, 
                username=bot_name, 
                avatar_url=bot_avatar,
                wait=True
            )
            return msg
        except discord.errors.HTTPException as e:
            if e.status == 429:
                # Even webhooks can rate limit - rotate to next and retry
                retry_after = getattr(e, 'retry_after', 0.3)
                await asyncio.sleep(retry_after)
                webhook = self.get_next_webhook()
                try:
                    return await webhook.send(
                        content=content, 
                        embed=embed, 
                        username=bot_name, 
                        avatar_url=bot_avatar,
                        wait=True
                    )
                except:
                    return None
            return None
        except Exception as e:
            log.error(f"Webhook send error: {e}")
            return None

    async def safe_send(self, channel, content=None, embed=None, priority=False, use_webhook=True):
        """Send a message. Uses webhook rotation for QTE channel, regular send otherwise."""
        if channel is None:
            return None
        
        # Use webhook for QTE channel (fast path)
        if use_webhook and channel.id == self.qte_channel_id and self.webhooks:
            return await self.webhook_send(content=content, embed=embed)
        
        # Regular send for other channels
        try:
            return await channel.send(content=content, embed=embed)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 1.0)
                await asyncio.sleep(retry_after)
                try:
                    return await channel.send(content=content, embed=embed)
                except:
                    return None
            return None
        except Exception as e:
            log.error(f"Error sending message: {e}")
            return None
    
    async def safe_add_reaction(self, message, emoji):
        """Add a reaction with rate limit protection"""
        try:
            await message.add_reaction(emoji)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 0.5)
                await asyncio.sleep(retry_after)
                try:
                    await message.add_reaction(emoji)
                except:
                    pass
        except:
            pass
    # =============================================

    def check_black_flash(self, user_id, response_time, difficulty, is_chain=False):
        """Check if a black flash occurred"""
        # Get player's current black flash chance
        if user_id not in self.player_stats:
            return False

        stats = self.player_stats[user_id]
        if 'black_flash_chance' not in stats:
            stats['black_flash_chance'] = self.black_flash_base_chance
            stats['black_flashes'] = 0

        # Get adjusted perfect timing if in REVENGE mode
        perfect_timing = self.get_adjusted_parry_center(difficulty, user_id)
        timing_deviation = abs(response_time - perfect_timing)

        # Use wider timing for first BF (0.5s), tighter for chains (0.3s)
        timing_window = self.bf_chain_timing_window if is_chain else self.bf_timing_window
        if timing_deviation > timing_window:
            return False  # Not perfect enough timing

        # Base chance + REVENGE bonus if active + buff bonus
        chance = stats['black_flash_chance']
        if user_id in self.player_hp and self.player_hp[user_id].get("revenge_mode", False):
            chance += self.revenge_bf_bonus
        
        # Add buff bonus from support skills
        chance += self.get_bf_boost(user_id)
            
        roll = random.random()

        if roll < chance:
            # BLACK FLASH!
            stats['black_flashes'] += 1

            # Increase permanent chance (capped)
            if stats['black_flash_chance'] < self.black_flash_cap:
                stats['black_flash_chance'] += self.black_flash_increment
                stats['black_flash_chance'] = min(stats['black_flash_chance'], self.black_flash_cap)

            self.session_stats['black_flashes_today'] += 1
            return True

        return False
    
    async def trigger_bf_chain_qte(self, user_id, channel, member, difficulty, chain_level):
        """Trigger a Black Flash chain QTE - special QTE that only checks for BF, no damage on fail"""
        try:
            qte_id = self.qte_counter
            self.qte_counter += 1
            
            # Store chain QTE data
            self.active_qtes[qte_id] = {
                'difficulty': difficulty,
                'mode': 'bf_chain',
                'start': datetime.now(timezone.utc),
                'target': member,
                'chain_level': chain_level,
                'user_id': user_id,
                'participants': {},
                'responses': set()
            }
            
            # Update active chain
            self.bf_chain_active[user_id] = chain_level
            
            damage = self.bf_chain_damage.get(chain_level, 200)
            chain_names = {1: "FIRST", 2: "DOUBLE", 3: "TRIPLE", 4: "QUAD"}
            chain_name = chain_names.get(chain_level, "CHAIN")
            
            # Dramatic chain announcement
            embed = discord.Embed(
                title=f"⚡🔥 {chain_name} BLACK FLASH CHAIN! 🔥⚡",
                description=f"**{member.mention}** is in the zone!\n\n"
                           f"🎯 Land another `*parry*` for **{damage} DAMAGE!**\n"
                           f"⏱️ You have **3 seconds!**\n\n"
                           f"*No damage on miss - just chain ends!*",
                color=discord.Color.from_rgb(255, 0, 255)  # Hot pink
            )
            embed.set_footer(text=f"Chain {chain_level}/4 | Perfect timing required!")
            await self.safe_send(channel, embed=embed)
            
            # Add exclamation reaction to indicate chain opportunity
            try:
                recent_msgs = [msg async for msg in channel.history(limit=5)]
                for msg in recent_msgs:
                    if msg.author.id == user_id or (hasattr(msg, 'webhook_id') and msg.webhook_id):
                        await msg.add_reaction("❗")
                        break
            except:
                pass
            
            console.print(Panel.fit(
                f"[bold magenta]⚡ BF CHAIN {chain_level} TRIGGERED![/bold magenta]\n"
                f"[cyan]{member.name}[/cyan] can deal {damage} damage!",
                border_style="magenta"
            ))
            
            # Timeout for chain QTE (3 seconds)
            asyncio.create_task(self.bf_chain_timeout(qte_id, user_id, channel, 3.0))
            
        except Exception as e:
            console.print(f"[red]✗ Error triggering BF chain: {e}[/red]")
    
    async def bf_chain_timeout(self, qte_id, user_id, channel, timeout):
        """Handle timeout for BF chain QTE"""
        await asyncio.sleep(timeout)
        
        if qte_id in self.active_qtes:
            qte_data = self.active_qtes.pop(qte_id, None)
            if qte_data and qte_data.get('mode') == 'bf_chain':
                chain_level = qte_data.get('chain_level', 1)
                
                # Apply parry cooldown based on chain achieved
                cooldown_seconds = self.bf_parry_cooldowns.get(chain_level, 10)
                self.player_parry_cooldown[user_id] = time.time() + cooldown_seconds
                
                # Reset chain
                if user_id in self.bf_chain_active:
                    del self.bf_chain_active[user_id]
                
                await self.webhook_send(content=f"⏱️ **Chain ended!** {qte_data['target'].mention} - Parry cooldown: **{cooldown_seconds}s**")
                console.print(f"[yellow]⏱ BF Chain {chain_level} ended (timeout) - {cooldown_seconds}s parry cooldown[/yellow]")
    
    async def handle_bf_chain_response(self, qte_id, qte_data, message, user_id, content, response_time):
        """Handle response during a Black Flash chain QTE"""
        try:
            channel = message.channel
            chain_level = qte_data.get('chain_level', 1)
            difficulty = qte_data['difficulty']
            target = qte_data['target']
            
            # Only the chain target can respond
            if user_id != qte_data['user_id']:
                return False
            
            if '*parry*' not in content:
                return False
            
            # Get parry window
            parry_min, parry_max = self.get_adjusted_parry_window(difficulty, user_id)
            
            # Check if parry is in window
            if parry_min <= response_time <= parry_max:
                # Check for BLACK FLASH with chain timing
                black_flash = self.check_black_flash(user_id, response_time, difficulty, is_chain=True)
                
                if black_flash:
                    # SUCCESS! Deal chain damage
                    damage = self.bf_chain_damage.get(chain_level, 200)
                    
                    # Apply damage to boss if active
                    if self.active_boss:
                        await self.damage_boss(self.active_boss['name'], damage)
                    
                    # Stun enemy for 1 second (guaranteed on BF)
                    self.enemy_stunned = True
                    self.stun_end_time = time.time() + 1.0
                    
                    chain_names = {1: "FIRST", 2: "DOUBLE", 3: "TRIPLE", 4: "QUAD MAXIMUM"}
                    chain_name = chain_names.get(chain_level, "CHAIN")
                    
                    embed = discord.Embed(
                        title=f"⚡💥💥 {chain_name} BLACK FLASH! 💥💥⚡",
                        description=f"**{message.author.mention}** CHAINS INTO ANOTHER BLACK FLASH!\n\n"
                                   f"💢 **{damage} DEVASTATING DAMAGE!**\n"
                                   f"🌀 Enemy stunned!\n"
                                   f"🔥 Chain Level: **{chain_level}/4**",
                        color=discord.Color.from_rgb(255, 0, 255)
                    )
                    embed.set_image(url=self.black_flash_gif)
                    await self.webhook_send(embed=embed)
                    
                    # Add charge
                    self.add_charge_from_damage_dealt(user_id, damage)
                    
                    console.print(Panel.fit(
                        f"[bold magenta]⚡💥 CHAIN {chain_level} BLACK FLASH! 💥⚡[/bold magenta]\n"
                        f"[cyan]{message.author.name}[/cyan] dealt {damage} damage!",
                        border_style="magenta"
                    ))
                    
                    # Remove this QTE
                    self.active_qtes.pop(qte_id, None)
                    
                    # Check if can continue chain (max 4)
                    if chain_level < 4:
                        # Trigger next chain QTE after short delay
                        await asyncio.sleep(0.5)
                        await self.trigger_bf_chain_qte(user_id, channel, target, difficulty, chain_level + 1)
                    else:
                        # Max chain reached! Apply full cooldown
                        cooldown_seconds = self.bf_parry_cooldowns.get(4, 120)
                        self.player_parry_cooldown[user_id] = time.time() + cooldown_seconds
                        
                        if user_id in self.bf_chain_active:
                            del self.bf_chain_active[user_id]
                        
                        await self.webhook_send(
                            content=f"🏆 **MAXIMUM BLACK FLASH CHAIN COMPLETE!** {message.author.mention}\n"
                            f"Total damage potential unleashed! Parry cooldown: **{cooldown_seconds}s**"
                        )
                        console.print(f"[bold gold1]🏆 MAX BF CHAIN ACHIEVED! {message.author.name}[/bold gold1]")
                    
                    self.save_all_data()
                    return True
                else:
                    # Parry success but NO Black Flash - chain ends (no damage penalty)
                    cooldown_seconds = self.bf_parry_cooldowns.get(chain_level, 10)
                    self.player_parry_cooldown[user_id] = time.time() + cooldown_seconds
                    
                    if user_id in self.bf_chain_active:
                        del self.bf_chain_active[user_id]
                    
                    self.active_qtes.pop(qte_id, None)
                    
                    await self.webhook_send(
                        content=f"⚔️ {message.author.mention} **parried but no Black Flash!** Chain ends.\n"
                        f"Parry cooldown: **{cooldown_seconds}s**"
                    )
                    console.print(f"[yellow]⚔ BF Chain ended (no flash) - {message.author.name}[/yellow]")
                    self.save_all_data()
                    return True
            else:
                # Parry mistimed - chain ends (no damage penalty)
                cooldown_seconds = self.bf_parry_cooldowns.get(chain_level, 10)
                self.player_parry_cooldown[user_id] = time.time() + cooldown_seconds
                
                if user_id in self.bf_chain_active:
                    del self.bf_chain_active[user_id]
                
                self.active_qtes.pop(qte_id, None)
                
                await self.webhook_send(
                    content=f"❌ {message.author.mention} **mistimed!** Chain ends. (No damage taken)\n"
                    f"Parry cooldown: **{cooldown_seconds}s**"
                )
                console.print(f"[yellow]❌ BF Chain ended (mistimed) - {message.author.name}[/yellow]")
                self.save_all_data()
                return True
            
            return False
            
        except Exception as e:
            console.print(f"[red]✗ Error in BF chain handler: {e}[/red]")
            return False

    def get_adjusted_parry_window(self, difficulty, user_id):
        """Get parry window adjusted for REVENGE mode"""
        parry_min, parry_max = self.qte_times[difficulty]['parry_window']
        
        # Check if player is in REVENGE mode
        if user_id in self.player_hp and self.player_hp[user_id].get("revenge_mode", False):
            # Shift window earlier
            parry_min += self.revenge_parry_shift
            parry_max += self.revenge_parry_shift
            
            # Make window tighter
            center = (parry_min + parry_max) / 2
            width = (parry_max - parry_min) * self.revenge_parry_tightness
            parry_min = center - width / 2
            parry_max = center + width / 2
            
        return parry_min, parry_max

    def get_adjusted_parry_center(self, difficulty, user_id):
        """Get the center of parry window for Black Flash checks"""
        parry_min, parry_max = self.get_adjusted_parry_window(difficulty, user_id)
        return (parry_min + parry_max) / 2

    def setup_events(self):
        @self.bot.event
        async def on_ready():
            console.print(Panel.fit(
                "[cyan bold]✓ Bot logged in as " + str(self.bot.user) + "[/cyan bold]\n"
                "[green]✓ QTE System Ready![/green]",
                title="[bold]QTE BOT ONLINE[/bold]",
                border_style="green"
            ))
            
            # ========== CONFIGURATION VERIFICATION ==========
            # Resolve and display actual names for troubleshooting
            config_table = Table(title="📋 Configuration Check", box=box.ROUNDED, border_style="cyan")
            config_table.add_column("Setting", style="white")
            config_table.add_column("ID", style="dim")
            config_table.add_column("Name", style="green")
            config_table.add_column("Status", style="bold")
            
            # QTE Channel
            qte_channel = self.bot.get_channel(self.qte_channel_id)
            if qte_channel:
                config_table.add_row("QTE Channel", str(self.qte_channel_id), f"#{qte_channel.name}", "✅")
            else:
                config_table.add_row("QTE Channel", str(self.qte_channel_id), "NOT FOUND", "[red]❌[/red]")
            
            # HP Bar Thread
            hp_thread = self.bot.get_channel(self.hp_bar_thread_id) if self.hp_bar_thread_id else None
            if hp_thread:
                config_table.add_row("HP Bar Thread", str(self.hp_bar_thread_id), f"#{hp_thread.name}", "✅")
            elif self.hp_bar_thread_id:
                config_table.add_row("HP Bar Thread", str(self.hp_bar_thread_id), "NOT FOUND", "[red]❌[/red]")
            else:
                config_table.add_row("HP Bar Thread", "Not set", "-", "[yellow]⚠️[/yellow]")
            
            # QTE Player Role
            qte_role = None
            admin_role = None
            if qte_channel:
                qte_role = qte_channel.guild.get_role(self.qte_player_role_id)
                admin_role = qte_channel.guild.get_role(self.admin_role_id) if self.admin_role_id else None
            
            if qte_role:
                config_table.add_row("QTE Player Role", str(self.qte_player_role_id), f"@{qte_role.name}", "✅")
            else:
                config_table.add_row("QTE Player Role", str(self.qte_player_role_id), "NOT FOUND", "[red]❌[/red]")
            
            # Admin Role
            if admin_role:
                config_table.add_row("Admin Role", str(self.admin_role_id), f"@{admin_role.name}", "✅")
            elif self.admin_role_id:
                config_table.add_row("Admin Role", str(self.admin_role_id), "NOT FOUND", "[red]❌[/red]")
            else:
                config_table.add_row("Admin Role", "Not set", "-", "[yellow]⚠️[/yellow]")
            
            console.print(config_table)
            # ================================================

            try:
                # Force sync slash commands to all guilds
                synced_count = 0
                for guild in self.bot.guilds:
                    # Clear existing commands first
                    self.bot.tree.clear_commands(guild=guild)
                    # Copy commands to guild
                    self.bot.tree.copy_global_to(guild=guild)
                    # Sync to this guild
                    await self.bot.tree.sync(guild=guild)
                    synced_count += 1
                    console.print(f"[yellow]✓ Synced {len(self.bot.tree.get_commands())} commands to guild: {guild.name}[/yellow]")
                
                if synced_count == 0:
                    # Fallback to global sync
                    await self.bot.tree.sync()
                    console.print(f"[yellow]✓ Slash commands synced globally[/yellow]")
                
                console.print(f"[green]✓ Total commands available: {len(self.bot.tree.get_commands())}[/green]")
                
                # Auto-cleanup old commands on startup
                try:
                    removed = await self.cleanup_old_commands()
                    if removed:
                        console.print(f"[green]✓ Auto-removed {len(removed)} old commands[/green]")
                except Exception as e:
                    console.print(f"[yellow]⚠ Could not auto-cleanup commands: {e}[/yellow]")
                
                # Initialize webhooks for rate-limit bypass
                await self.initialize_webhooks()
                
                # Start periodic save task
                self.bot.loop.create_task(self._periodic_save_loop())
                console.print("[green]✓ Periodic save task started (every 30s)[/green]")
                
            except Exception as e:
                console.print(f"[red]✗ Failed to sync slash commands: {e}[/red]")
                log.error(f"Command sync error: {e}")
        
        async def _periodic_save_loop():
            """Background task to save pending data periodically"""
            while True:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self.periodic_save()
        
        self._periodic_save_loop = _periodic_save_loop

        @self.bot.event
        async def on_message(message):
            if message.author.bot:
                return
            
            content_lower = message.content.lower()

            # Handle *attack* counter command
            if '*attack*' in content_lower:
                await self.handle_counter_attack(message)
                return
            
            # Handle *power1* and *power2* activation
            if '*power1*' in content_lower:
                await self.handle_power_activation(message, 1)
                return
            elif '*power2*' in content_lower:
                await self.handle_power_activation(message, 2)
                return
            
            # Check for trigger phrases (text in quotes)
            if '"' in message.content:
                await self.check_trigger_phrase(message)

            # Handle QTE responses
            await self.handle_qte_response(message)

        @self.bot.event
        async def on_member_update(before, after):
            """Detect role changes and update cache"""
            try:
                # Check if QTE player role was added or removed
                qte_role_id = self.qte_player_role_id
                
                before_has_role = any(role.id == qte_role_id for role in before.roles)
                after_has_role = any(role.id == qte_role_id for role in after.roles)
                
                if before_has_role != after_has_role:
                    # QTE role changed - update cache immediately
                    console.print(f"[cyan]🔄 Role change detected for {after.name} - refreshing cache[/cyan]")
                    await self.update_qte_player_cache()
                    
                    if after_has_role:
                        console.print(f"[green]✓ {after.name} added to QTE player pool[/green]")
                    else:
                        console.print(f"[yellow]⚠ {after.name} removed from QTE player pool[/yellow]")
            except Exception as e:
                log.error(f"Error in on_member_update: {e}")

        @self.bot.event
        async def on_error(event, *args, **kwargs):
            log.exception(f"Unhandled error in event: {event}")

    def setup_slash_commands(self):
        @self.bot.tree.command(name="qte", description="Toggle your QTE participation status")
        async def qte_command(interaction: discord.Interaction):
            try:
                user_id = interaction.user.id

                if user_id in self.afk_users:
                    self.afk_users.remove(user_id)
                    await interaction.response.send_message("✅ You are now **active** for QTE events!", ephemeral=True)
                    console.print(f"[green]✓ {interaction.user.name} marked as ACTIVE[/green]")
                else:
                    self.afk_users.add(user_id)
                    await interaction.response.send_message("💤 You are now **inactive** and won't be targeted in QTE events.", ephemeral=True)
                    console.print(f"[yellow]💤 {interaction.user.name} marked as INACTIVE[/yellow]")
            except Exception as e:
                log.error(f"Error in qte command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="register",
            description="Register your Tupperbox character. Copy the EXACT character name from Tupperbox."
        )
        async def register_command(interaction: discord.Interaction, character_name: str):
            try:
                user_id = interaction.user.id

                if character_name in self.character_registry:
                    await interaction.response.send_message(
                        f"❌ Character **{character_name}** is already registered!",
                        ephemeral=True
                    )
                    return

                self.character_registry[character_name] = user_id

                if user_id not in self.user_characters:
                    self.user_characters[user_id] = []
                self.user_characters[user_id].append(character_name)

                self.save_all_data()

                await interaction.response.send_message(
                    f"✅ Character **{character_name}** registered to your account!",
                    ephemeral=True
                )
                console.print(f"[cyan]✓ Character registered: {character_name} -> {interaction.user.name}[/cyan]")
            except Exception as e:
                log.error(f"Error in register command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="mycharacters",
            description="View all Tupperbox characters you have registered to your Discord account"
        )
        async def mycharacters_command(interaction: discord.Interaction):
            try:
                user_id = interaction.user.id

                if user_id not in self.user_characters or not self.user_characters[user_id]:
                    await interaction.response.send_message(
                        "❌ You have no registered characters. Use `/register` to add one!",
                        ephemeral=True
                    )
                    return

                characters = self.user_characters[user_id]
                char_list = "\n".join([f"• {char}" for char in characters])

                await interaction.response.send_message(
                    f"**Your Registered Characters:**\n{char_list}",
                    ephemeral=True
                )
            except Exception as e:
                log.error(f"Error in mycharacters command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        # ========== DASHBOARD WITH MODAL ==========
        
        class DashboardView(discord.ui.View):
            def __init__(self, bot_instance):
                super().__init__(timeout=300)
                self.bot_instance = bot_instance
            
            @discord.ui.button(label="📊 My Stats", style=discord.ButtonStyle.primary, row=0)
            async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                user_id = interaction.user.id
                stats = self.bot_instance.player_stats.get(user_id, {})
                
                embed = discord.Embed(title="📊 Your Stats", color=discord.Color.blue())
                embed.add_field(name="Total Attempts", value=stats.get('total_attempts', 0), inline=True)
                embed.add_field(name="Successful", value=stats.get('successful', 0), inline=True)
                embed.add_field(name="Black Flashes", value=stats.get('black_flashes', 0), inline=True)
                embed.add_field(name="Best Parry Streak", value=stats.get('best_parry_streak', 0), inline=True)
                embed.add_field(name="BF Chance", value=f"{stats.get('black_flash_chance', 0.01)*100:.1f}%", inline=True)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            @discord.ui.button(label="⚡ My Charges", style=discord.ButtonStyle.success, row=0)
            async def charges_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                user_id = interaction.user.id
                charges = self.bot_instance.power_charges.get(user_id, {"power1": 0, "power2": 0})
                
                def make_bar(percent):
                    filled = int(percent / 10)
                    return "█" * filled + "░" * (10 - filled)
                
                p1 = charges.get("power1", 0)
                p2 = charges.get("power2", 0)
                
                embed = discord.Embed(title="⚡ Ultimate Charges", color=discord.Color.gold())
                embed.add_field(name="Power 1", value=f"`{make_bar(p1)}` {p1:.0f}%", inline=False)
                embed.add_field(name="Power 2", value=f"`{make_bar(p2)}` {p2:.0f}%", inline=False)
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            @discord.ui.button(label="🎨 Counter Images", style=discord.ButtonStyle.secondary, row=0)
            async def images_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                user_id = interaction.user.id
                gifs = self.bot_instance.user_counter_gifs.get(user_id, [])
                if isinstance(gifs, str):
                    gifs = [gifs]
                
                if not gifs:
                    embed = discord.Embed(
                        title="🎨 Your Counter Images",
                        description="No counter images set!\n\nUse `/setcountergif` to add images.",
                        color=discord.Color.orange()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Show first image as main embed
                embed = discord.Embed(
                    title="🎨 Your Counter Images",
                    description=f"**{len(gifs)}** image(s) in rotation\n\n"
                               f"Images cycle randomly when you counter!",
                    color=discord.Color.orange()
                )
                
                # List all image URLs (truncated)
                image_list = ""
                for i, url in enumerate(gifs[:10], 1):  # Max 10 in list
                    short_url = url[:50] + "..." if len(url) > 50 else url
                    image_list += f"{i}. `{short_url}`\n"
                
                if len(gifs) > 10:
                    image_list += f"*...and {len(gifs) - 10} more*"
                
                embed.add_field(name="Image URLs", value=image_list or "None", inline=False)
                embed.set_image(url=gifs[0])  # Show first image as preview
                embed.set_footer(text="Use /setcountergif add to add more, or clear to remove all")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            @discord.ui.button(label="🎭 My Characters", style=discord.ButtonStyle.secondary, row=1)
            async def characters_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                user_id = interaction.user.id
                chars = self.bot_instance.user_characters.get(user_id, [])
                
                if not chars:
                    await interaction.response.send_message("❌ No characters registered! Use `/register` first.", ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="🎭 Your Registered Characters",
                    color=discord.Color.purple()
                )
                
                for char_name in chars:
                    # Get powers for this character
                    powers = self.bot_instance.character_powers.get(char_name, {})
                    power_text = ""
                    
                    for slot in ["power1", "power2"]:
                        if slot in powers:
                            p = powers[slot]
                            power_text += f"**{slot.upper()}**: {p['name']}\n"
                            power_text += f"  └ {p['type'].capitalize()} | CD: {p['cooldown']}s\n"
                    
                    if not power_text:
                        power_text = "*No powers registered*"
                    
                    embed.add_field(name=f"🎭 {char_name}", value=power_text, inline=False)
                
                embed.set_footer(text="Use /registerpower to add powers!")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            @discord.ui.button(label="🔧 Skill Builder", style=discord.ButtonStyle.danger, row=1)
            async def skill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                modal = SkillBuilderModal(self.bot_instance)
                await interaction.response.send_modal(modal)
        
        class SkillBuilderModal(discord.ui.Modal):
            def __init__(self, bot_instance):
                super().__init__(title="🔧 Support Skill Builder")
                self.bot_instance = bot_instance
                
                # Add text inputs as instance attributes
                self.skill_name = discord.ui.TextInput(
                    label="Skill Name",
                    placeholder="e.g., Divine Blessing",
                    max_length=50
                )
                self.add_item(self.skill_name)
                
                self.target = discord.ui.TextInput(
                    label="Target (self / ally / @username)",
                    placeholder="self",
                    default="self",
                    max_length=50
                )
                self.add_item(self.target)
                
                self.effect_type = discord.ui.TextInput(
                    label="Effect Type",
                    placeholder="bf_boost:10 / damage_boost:20 / heal:30 / ult_charge:15",
                    max_length=100
                )
                self.add_item(self.effect_type)
                
                self.duration = discord.ui.TextInput(
                    label="Duration in seconds (0 = instant)",
                    placeholder="0",
                    default="0",
                    max_length=10
                )
                self.add_item(self.duration)
                
                self.cooldown_input = discord.ui.TextInput(
                    label="Cooldown in seconds",
                    placeholder="60",
                    default="60",
                    max_length=10
                )
                self.add_item(self.cooldown_input)
            
            async def on_submit(self, interaction: discord.Interaction):
                user_id = interaction.user.id
                
                # Parse effect
                effect_str = str(self.effect_type.value).strip()
                target_str = str(self.target.value).strip().lower()
                duration_val = int(self.duration.value) if self.duration.value.isdigit() else 0
                cooldown_val = int(self.cooldown_input.value) if self.cooldown_input.value.isdigit() else 60
                
                # Build support effect string
                support_effect = f"support:{target_str}:{effect_str}:{duration_val}"
                
                embed = discord.Embed(
                    title="✅ Support Skill Created!",
                    description=f"**{self.skill_name.value}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Target", value=target_str.capitalize(), inline=True)
                embed.add_field(name="Effect", value=effect_str, inline=True)
                embed.add_field(name="Duration", value=f"{duration_val}s" if duration_val > 0 else "Instant", inline=True)
                embed.add_field(name="Cooldown", value=f"{cooldown_val}s", inline=True)
                embed.add_field(name="Effect Code", value=f"`{support_effect}`", inline=False)
                embed.set_footer(text="Use this effect code in /registerpower")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="dashboard",
            description="Open your personal dashboard with stats, settings, and skill builder"
        )
        async def dashboard_command(interaction: discord.Interaction):
            try:
                user_id = interaction.user.id
                
                # Get user data
                chars = self.user_characters.get(user_id, [])
                stats = self.player_stats.get(user_id, {})
                charges = self.power_charges.get(user_id, {})
                
                embed = discord.Embed(
                    title=f"🎮 {interaction.user.display_name}'s Dashboard",
                    description="Welcome to your personal QTE dashboard!",
                    color=discord.Color.blurple()
                )
                
                # Quick stats
                embed.add_field(
                    name="📊 Quick Stats",
                    value=f"Characters: **{len(chars)}**\n"
                          f"QTE Success Rate: **{(stats.get('successful', 0) / max(1, stats.get('total_attempts', 1)) * 100):.1f}%**\n"
                          f"Black Flashes: **{stats.get('black_flashes', 0)}**",
                    inline=True
                )
                
                # Charges
                p1 = charges.get("power1", 0)
                p2 = charges.get("power2", 0)
                embed.add_field(
                    name="⚡ Ultimate Charges",
                    value=f"Power 1: **{p1:.0f}%**\nPower 2: **{p2:.0f}%**",
                    inline=True
                )
                
                embed.set_footer(text="Click a button below to explore!")
                
                view = DashboardView(self)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                
            except Exception as e:
                log.error(f"Error in dashboard command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="unregister",
            description="Remove a character registration. You'll need to provide the exact character name."
        )
        async def unregister_command(interaction: discord.Interaction, character_name: str):
            try:
                user_id = interaction.user.id

                if character_name not in self.character_registry:
                    await interaction.response.send_message(
                        f"❌ Character **{character_name}** is not registered!",
                        ephemeral=True
                    )
                    return

                if self.character_registry[character_name] != user_id:
                    await interaction.response.send_message(
                        f"❌ Character **{character_name}** is not registered to you!",
                        ephemeral=True
                    )
                    return

                del self.character_registry[character_name]
                if user_id in self.user_characters:
                    self.user_characters[user_id].remove(character_name)

                self.save_all_data()

                await interaction.response.send_message(
                    f"✅ Character **{character_name}** unregistered!",
                    ephemeral=True
                )
                console.print(f"[yellow]✓ Character unregistered: {character_name}[/yellow]")
            except Exception as e:
                log.error(f"Error in unregister command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="mystats",
            description="View your QTE performance stats: attempts, success rate, best time, Black Flashes, etc."
        )
        async def mystats_command(interaction: discord.Interaction):
            try:
                user_id = interaction.user.id

                if user_id not in self.player_stats:
                    await interaction.response.send_message(
                        "❌ You have no stats yet! Participate in some QTEs first.",
                        ephemeral=True
                    )
                    return

                stats = self.player_stats[user_id]
                success_rate = (stats['successful'] / stats['total_attempts'] * 100) if stats['total_attempts'] > 0 else 0
                bf_chance = stats.get('black_flash_chance', 0.02) * 100
                bf_count = stats.get('black_flashes', 0)

                embed = discord.Embed(
                    title=f"📊 Stats for {interaction.user.display_name}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Total Attempts", value=stats['total_attempts'], inline=True)
                embed.add_field(name="Successful", value=f"{stats['successful']} ({success_rate:.1f}%)", inline=True)
                embed.add_field(name="Misses", value=stats['failed'], inline=True)
                embed.add_field(name="Evades", value=stats['evades'], inline=True)
                embed.add_field(name="Parries", value=stats['parries'], inline=True)
                embed.add_field(name="Saves", value=stats['saves'], inline=True)
                embed.add_field(name="Best Time", value=f"{stats['best_time']:.2f}s", inline=True)
                embed.add_field(name="Avg Time", value=f"{stats['avg_time']:.2f}s", inline=True)
                embed.add_field(name="Current Streak", value=stats['current_streak'], inline=True)
                
                # Parry streak info
                parry_streak = stats.get('parry_streak', 0)
                best_parry_streak = stats.get('best_parry_streak', 0)
                streak_multiplier = min(2.0, 1.0 + (parry_streak * 0.1))
                embed.add_field(name="⚔️ Parry Streak", value=f"{parry_streak} (Best: {best_parry_streak}) | {streak_multiplier:.1f}x DMG", inline=False)
                
                embed.add_field(name="⚡ Black Flashes", value=f"{bf_count} (Chance: {bf_chance:.1f}%)", inline=False)

                await interaction.response.send_message(embed=embed, ephemeral=True)

            except Exception as e:
                log.error(f"Error in mystats command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="leaderboard",
            description="View the top players by various stats"
        )
        @app_commands.describe(
            category="What to rank by"
        )
        @app_commands.choices(category=[
            app_commands.Choice(name="Success Rate", value="success_rate"),
            app_commands.Choice(name="Black Flashes", value="black_flashes"),
            app_commands.Choice(name="Parry Streak", value="parry_streak"),
            app_commands.Choice(name="Total Attempts", value="total_attempts"),
            app_commands.Choice(name="Best Time", value="best_time"),
        ])
        async def leaderboard_command(interaction: discord.Interaction, category: str = "success_rate"):
            try:
                if not self.player_stats:
                    await interaction.response.send_message("❌ No player stats yet!", ephemeral=True)
                    return
                
                await interaction.response.defer()  # May take time to fetch users
                
                # Get guild members for display names
                guild = interaction.guild
                
                # Build leaderboard data
                leaderboard = []
                for user_id, stats in self.player_stats.items():
                    # Try to get member from guild cache first
                    member = guild.get_member(user_id)
                    if member:
                        name = member.display_name
                        avatar_url = member.display_avatar.url
                    else:
                        # Fallback: try to fetch user from Discord
                        try:
                            user = await self.bot.fetch_user(user_id)
                            name = user.display_name
                            avatar_url = user.display_avatar.url
                        except:
                            name = f"Unknown User"
                            avatar_url = None
                    
                    if category == "success_rate":
                        value = (stats['successful'] / stats['total_attempts'] * 100) if stats['total_attempts'] > 0 else 0
                        display = f"{value:.1f}%"
                    elif category == "black_flashes":
                        value = stats.get('black_flashes', 0)
                        display = str(value)
                    elif category == "parry_streak":
                        value = stats.get('best_parry_streak', 0)
                        display = str(value)
                    elif category == "total_attempts":
                        value = stats['total_attempts']
                        display = str(value)
                    elif category == "best_time":
                        value = stats['best_time'] if stats['best_time'] != float('inf') else 999
                        display = f"{value:.2f}s" if value != 999 else "N/A"
                        value = -value  # Invert for sorting (lower is better)
                    else:
                        value = 0
                        display = "0"
                    
                    leaderboard.append((name, value, display, avatar_url))
                
                # Sort by value (descending)
                leaderboard.sort(key=lambda x: x[1], reverse=True)
                
                # Build embed
                category_titles = {
                    "success_rate": "🏆 Success Rate",
                    "black_flashes": "⚡ Black Flashes",
                    "parry_streak": "⚔️ Best Parry Streak",
                    "total_attempts": "📊 Total Attempts",
                    "best_time": "⏱️ Best Response Time"
                }
                
                embed = discord.Embed(
                    title=f"🏅 Leaderboard: {category_titles.get(category, category)}",
                    color=discord.Color.gold()
                )
                
                # Top 10
                description = ""
                medals = ["🥇", "🥈", "🥉"]
                for i, (name, value, display, avatar_url) in enumerate(leaderboard[:10]):
                    medal = medals[i] if i < 3 else f"`{i+1}.`"
                    description += f"{medal} **{name}** - {display}\n"
                
                embed.description = description if description else "No data yet!"
                
                # Set thumbnail to #1 player's avatar if available
                if leaderboard and leaderboard[0][3]:
                    embed.set_thumbnail(url=leaderboard[0][3])
                
                embed.set_footer(text=f"Total players: {len(leaderboard)}")
                
                await interaction.followup.send(embed=embed)
                
            except Exception as e:
                log.error(f"Error in leaderboard command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        # ========== ADMIN COMMANDS ==========
        
        @self.bot.tree.command(
            name="registerboss",
            description="[ADMIN] Register a boss. Provide: name, max HP, and upload an image/GIF."
        )
        @app_commands.describe(
            name="Boss name (e.g., 'Shadow King')",
            hp="Boss maximum HP (e.g., 1000)",
            image="Upload an image or GIF for the boss display"
        )
        async def registerboss_command(interaction: discord.Interaction, name: str, hp: int, image: discord.Attachment):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
                    return
                
                # Validate it's an image
                if not image.content_type or not image.content_type.startswith(('image/', 'video/')):
                    await interaction.response.send_message("⚠️ Please upload an image or GIF file!", ephemeral=True)
                    return
                
                # Use Discord CDN URL
                gif_url = image.url
                
                # Register boss
                self.active_boss = {
                    'name': name,
                    'hp_current': hp,
                    'hp_max': hp,
                    'gif_url': gif_url,
                    'participants': []
                }
                
                # Create boss embed
                embed = discord.Embed(
                    title=f"👹 BOSS REGISTERED: {name}",
                    description=f"**HP**: {hp}\n**Status**: Ready for battle!",
                    color=discord.Color.dark_red()
                )
                embed.set_image(url=gif_url)
                embed.set_footer(text="Use QTE commands to engage the boss!")
                
                await interaction.response.send_message(embed=embed)
                console.print(f"[red]👹 Boss registered: {name} with {hp} HP[/red]")
                
                # Display boss HP in thread immediately
                await self.update_hp_bar_display(name, is_boss=True)
                console.print(f"[cyan]Boss HP bar sent to thread[/cyan]")
                
            except Exception as e:
                log.error(f"Error in registerboss command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="editvalues",
            description="[ADMIN] Adjust game values in real-time"
        )
        @app_commands.describe(
            player_hp="Set max player HP (e.g., 150)",
            black_flash_percentage="Black Flash base chance % (0-100)",
            lives="Number of lives (future feature)",
            charge_dealt="% charge per 10 damage dealt (0-20, default 2)",
            charge_taken="% charge per 5 damage taken (0-20, default 5)",
            charge_counter="% charge per counter (0-20, default 3)",
            counter_window="Counter window in seconds (0.5-5, default 1.5)",
            ult_cooldown_per_dmg="Extra cooldown seconds per damage point (0-5, default 0.5)"
        )
        async def editvalues_command(
            interaction: discord.Interaction,
            player_hp: int = None,
            black_flash_percentage: int = None,
            lives: int = None,
            charge_dealt: float = None,
            charge_taken: float = None,
            charge_counter: float = None,
            counter_window: float = None,
            ult_cooldown_per_dmg: float = None
        ):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
                    return
                
                changes = []
                
                # Update player max HP
                if player_hp is not None and player_hp > 0:
                    old_hp = self.max_hp
                    self.max_hp = player_hp
                    # Update all existing players
                    for user_id, hp_data in self.player_hp.items():
                        hp_data['max'] = player_hp
                        # Scale current HP proportionally
                        hp_percent = hp_data['current'] / old_hp
                        hp_data['current'] = int(hp_percent * player_hp)
                        await self.update_hp_bar_display(user_id)
                    changes.append(f"Player Max HP: {old_hp} → {player_hp}")
                
                # Update Black Flash base chance (now accepts percentage)
                if black_flash_percentage is not None:
                    if not (0 <= black_flash_percentage <= 100):
                        await interaction.response.send_message("❌ Black Flash percentage must be between 0-100!", ephemeral=True)
                        return
                    
                    old_bf_percent = self.black_flash_base_chance * 100
                    black_flash_chance = black_flash_percentage / 100.0
                    self.black_flash_base_chance = black_flash_chance
                    changes.append(f"Black Flash Base Chance: {old_bf_percent:.1f}% → {black_flash_percentage}%")
                
                # Update ultimate damage multiplier - REMOVED (damage stays at 100%)
                
                # Update charge from damage dealt
                if charge_dealt is not None:
                    if not (0 <= charge_dealt <= 20.0):
                        await interaction.response.send_message("❌ Charge per damage dealt must be 0-20!", ephemeral=True)
                        return
                    old_val = self.charge_per_damage_dealt
                    self.charge_per_damage_dealt = charge_dealt
                    changes.append(f"Charge/10 Damage Dealt: {old_val:.1f}% → {charge_dealt:.1f}%")
                
                # Update charge from damage taken
                if charge_taken is not None:
                    if not (0 <= charge_taken <= 20.0):
                        await interaction.response.send_message("❌ Charge per damage taken must be 0-20!", ephemeral=True)
                        return
                    old_val = self.charge_per_damage_taken
                    self.charge_per_damage_taken = charge_taken
                    changes.append(f"Charge/5 Damage Taken: {old_val:.1f}% → {charge_taken:.1f}%")
                
                # Update charge from counters
                if charge_counter is not None:
                    if not (0 <= charge_counter <= 20.0):
                        await interaction.response.send_message("❌ Charge per counter must be 0-20!", ephemeral=True)
                        return
                    old_val = self.charge_per_counter
                    self.charge_per_counter = charge_counter
                    changes.append(f"Charge/Counter: {old_val:.1f}% → {charge_counter:.1f}%")
                
                # Update counter window
                if counter_window is not None:
                    if not (0.5 <= counter_window <= 5.0):
                        await interaction.response.send_message("❌ Counter window must be 0.5-5 seconds!", ephemeral=True)
                        return
                    old_val = self.counter_window
                    self.counter_window = counter_window
                    changes.append(f"Counter Window: {old_val:.1f}s → {counter_window:.1f}s")
                
                # Update cooldown per damage
                if ult_cooldown_per_dmg is not None:
                    if not (0 <= ult_cooldown_per_dmg <= 5.0):
                        await interaction.response.send_message("❌ Ult cooldown/dmg must be 0-5!", ephemeral=True)
                        return
                    old_cd = self.ultimate_cooldown_per_damage
                    self.ultimate_cooldown_per_damage = ult_cooldown_per_dmg
                    changes.append(f"Ult Cooldown Per Damage: {old_cd:.2f}s → {ult_cooldown_per_dmg:.2f}s")
                
                # Lives system (to be implemented with future death/revive mechanics)
                if lives is not None and lives > 0:
                    changes.append(f"Lives set to: {lives} (system pending)")
                
                if changes:
                    embed = discord.Embed(
                        title="⚙️ Game Values Updated",
                        description="\n".join(f"• {change}" for change in changes),
                        color=discord.Color.blue()
                    )
                    await interaction.response.send_message(embed=embed)
                    console.print(f"[yellow]⚙️  Game values updated by {interaction.user.name}[/yellow]")
                else:
                    await interaction.response.send_message("❌ No valid values provided!", ephemeral=True)
                
            except Exception as e:
                log.error(f"Error in editvalues command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="registerpower",
            description="Register a custom power/attack for your character. Character must be registered first!"
        )
        @app_commands.describe(
            character_name="Exact character name (must match registered name)",
            slot="Power slot: 1 (lore power) or 2 (story power)",
            power_name="Power name (e.g., 'Time Freeze', 'Divine Scythe')",
            description="What the power does (e.g., 'Stops time for 2 seconds')",
            power_type="Type: destructive, support, defend, build, or control",
            cooldown="Cooldown in seconds (e.g., 60 for 1 minute)",
            effect="Effect: 'damage:50', 'heal:30', 'stun', or 'buff:attack'",
            image="Optional: Upload an image/GIF for this power",
            trigger_phrase="Optional: A phrase in quotes that auto-triggers this power (e.g., 'Domain Expansion')"
        )
        async def registerpower_command(
            interaction: discord.Interaction,
            character_name: str,
            slot: int,
            power_name: str,
            description: str,
            power_type: str,
            cooldown: int,
            effect: str,
            image: discord.Attachment = None,
            trigger_phrase: str = None
        ):
            try:
                user_id = interaction.user.id
                
                # Check if user owns this character
                if character_name not in self.character_registry:
                    await interaction.response.send_message(f"❌ Character '{character_name}' not registered!", ephemeral=True)
                    return
                
                owner_id = self.character_registry[character_name]
                if owner_id != user_id:
                    # Allow admins to override
                    if not (self.admin_role_id and self.admin_role_id in [role.id for role in interaction.user.roles]):
                        await interaction.response.send_message(f"❌ You don't own this character!", ephemeral=True)
                        return
                
                # Validate slot
                if slot not in [1, 2]:
                    await interaction.response.send_message("❌ Slot must be 1 or 2!", ephemeral=True)
                    return
                
                # Validate type
                if power_type not in self.power_types:
                    await interaction.response.send_message(f"❌ Type must be: {', '.join(self.power_types)}", ephemeral=True)
                    return
                
                # Check if character exists
                if character_name not in self.character_registry:
                    await interaction.response.send_message(f"❌ Character '{character_name}' not registered!", ephemeral=True)
                    return
                
                # Validate image if provided
                if image and not image.content_type.startswith(('image/', 'video/')):
                    await interaction.response.send_message("⚠️ Please upload an image or GIF file!", ephemeral=True)
                    return
                
                # Register power
                if character_name not in self.character_powers:
                    self.character_powers[character_name] = {}
                
                power_key = f"power{slot}"
                self.character_powers[character_name][power_key] = {
                    "name": power_name,
                    "description": description,
                    "type": power_type,
                    "cooldown": cooldown,
                    "effect": effect,
                    "image_url": image.url if image else None,
                    "trigger_phrase": trigger_phrase.lower().strip() if trigger_phrase else None
                }
                
                self.save_all_data()
                
                embed = discord.Embed(
                    title=f"⚡ Power Registered",
                    description=f"**{power_name}** registered for **{character_name}**",
                    color=discord.Color.purple()
                )
                embed.add_field(name="Slot", value=f"Power {slot}", inline=True)
                embed.add_field(name="Type", value=power_type.capitalize(), inline=True)
                embed.add_field(name="Cooldown", value=f"{cooldown}s", inline=True)
                embed.add_field(name="Description", value=description, inline=False)
                embed.add_field(name="Effect", value=effect, inline=False)
                if trigger_phrase:
                    embed.add_field(name="🗣️ Trigger Phrase", value=f'"{trigger_phrase}"', inline=False)
                if image:
                    embed.set_image(url=image.url)
                
                await interaction.response.send_message(embed=embed)
                console.print(f"[purple]⚡ Power registered: {power_name} for {character_name}[/purple]")
                
            except Exception as e:
                log.error(f"Error in registerpower command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="support",
            description="Use a support skill to buff yourself or an ally!"
        )
        @app_commands.describe(
            skill_type="Type of support to cast",
            target="Target user (leave empty for self)",
            power="Power level (depends on skill type)"
        )
        @app_commands.choices(skill_type=[
            app_commands.Choice(name="💚 Heal (HP)", value="heal"),
            app_commands.Choice(name="✨ Black Flash Boost (%)", value="bf_boost"),
            app_commands.Choice(name="⚔️ Damage Boost (%)", value="damage_boost"),
            app_commands.Choice(name="⚡ Ultimate Charge (%)", value="ult_charge"),
        ])
        async def support_command(
            interaction: discord.Interaction, 
            skill_type: str, 
            power: int,
            target: discord.Member = None
        ):
            try:
                caster_id = interaction.user.id
                target_id = target.id if target else caster_id
                target_name = target.display_name if target else interaction.user.display_name
                
                # Build effect string (30 second duration for buffs, 0 for instant heal/charge)
                duration = 30 if skill_type in ["bf_boost", "damage_boost"] else 0
                effect_string = f"support:{'ally' if target else 'self'}:{skill_type}:{power}:{duration}"
                
                success, result_msg = await self.apply_support_effect(caster_id, target_id, effect_string)
                
                if success:
                    embed = discord.Embed(
                        title="💫 Support Skill Used!",
                        description=f"**{interaction.user.display_name}** → **{target_name}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Effect", value=result_msg, inline=False)
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(f"❌ {result_msg}", ephemeral=True)
                    
            except Exception as e:
                log.error(f"Error in support command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="setcountergif",
            description="Add a counter GIF/image. Multiple images will be randomized!"
        )
        @app_commands.describe(
            image="Upload your counter GIF or image to ADD to your collection.",
            action="Action to perform"
        )
        @app_commands.choices(action=[
            app_commands.Choice(name="Add Image", value="add"),
            app_commands.Choice(name="Clear All", value="clear"),
            app_commands.Choice(name="View Collection", value="view"),
        ])
        async def setcountergif_command(interaction: discord.Interaction, action: str = "add", image: discord.Attachment = None):
            try:
                user_id = interaction.user.id
                
                if action == "add":
                    if not image:
                        await interaction.response.send_message("⚠️ Please upload an image to add!", ephemeral=True)
                        return
                    
                    # Validate it's an image/gif
                    if not image.content_type or not image.content_type.startswith(('image/', 'video/')):
                        await interaction.response.send_message("⚠️ Please upload an image or GIF file!", ephemeral=True)
                        return
                    
                    # Use the Discord CDN URL (always works!)
                    image_url = image.url
                    
                    # Initialize as list if not exists or convert from string
                    if user_id not in self.user_counter_gifs:
                        self.user_counter_gifs[user_id] = []
                    elif isinstance(self.user_counter_gifs[user_id], str):
                        # Convert old format (single string) to list
                        self.user_counter_gifs[user_id] = [self.user_counter_gifs[user_id]]
                    
                    self.user_counter_gifs[user_id].append(image_url)
                    self.save_all_data()
                    
                    count = len(self.user_counter_gifs[user_id])
                    embed = discord.Embed(
                        title="⚡ Counter Image Added!",
                        description=f"You now have **{count}** counter image(s)!\nThey will be randomized when you counter.",
                        color=discord.Color.orange()
                    )
                    embed.set_image(url=image_url)
                    await interaction.response.send_message(embed=embed)
                    console.print(f"[orange1]⚡ Counter image added for {interaction.user.display_name} (total: {count})[/orange1]")
                
                elif action == "clear":
                    if user_id in self.user_counter_gifs:
                        del self.user_counter_gifs[user_id]
                        self.save_all_data()
                    await interaction.response.send_message("✅ All counter images cleared! Using default now.", ephemeral=True)
                
                elif action == "view":
                    gifs = self.user_counter_gifs.get(user_id, [])
                    if isinstance(gifs, str):
                        gifs = [gifs]
                    
                    if not gifs:
                        await interaction.response.send_message("📭 No custom counter images set. Using default.", ephemeral=True)
                        return
                    
                    embed = discord.Embed(
                        title="🎨 Your Counter Image Collection",
                        description=f"**{len(gifs)}** image(s) in rotation",
                        color=discord.Color.orange()
                    )
                    for i, url in enumerate(gifs[:5], 1):  # Show first 5
                        embed.add_field(name=f"Image {i}", value=f"[Link]({url})", inline=True)
                    if len(gifs) > 5:
                        embed.set_footer(text=f"... and {len(gifs) - 5} more")
                    embed.set_thumbnail(url=gifs[0])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
            except Exception as e:
                log.error(f"Error in setcountergif command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="synccommands",
            description="[ADMIN] Manually sync slash commands with Discord. Use if commands aren't showing."
        )
        async def synccommands_command(interaction: discord.Interaction):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
                    return
                
                await interaction.response.defer(ephemeral=True)
                
                synced_guilds = []
                # Clear and sync to each guild
                for guild in self.bot.guilds:
                    self.bot.tree.clear_commands(guild=guild)
                    self.bot.tree.copy_global_to(guild=guild)
                    await self.bot.tree.sync(guild=guild)
                    synced_guilds.append(guild.name)
                
                total_commands = len(self.bot.tree.get_commands())
                
                embed = discord.Embed(
                    title="✅ Commands Synced Successfully",
                    description=f"**{total_commands} commands** synced to **{len(synced_guilds)} guilds**\n\n" +
                              "\n".join(f"• {name}" for name in synced_guilds),
                    color=discord.Color.green()
                )
                embed.set_footer(text="Commands should appear in a few seconds. Try closing and reopening Discord if needed.")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                console.print(f"[green]✓ Commands manually synced by {interaction.user.name}[/green]")
                
            except Exception as e:
                log.error(f"Error in synccommands: {e}")
                try:
                    await interaction.followup.send("❌ An error occurred during sync.", ephemeral=True)
                except:
                    await interaction.response.send_message("❌ An error occurred during sync.", ephemeral=True)

        @self.bot.tree.command(
            name="cleancommands",
            description="[ADMIN] Remove old/deprecated commands from Discord. Cleans up command list."
        )
        async def cleancommands_command(interaction: discord.Interaction):
            # Check admin role
            if not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            removed = await self.cleanup_old_commands()
            
            if removed:
                await interaction.followup.send(
                    f"✅ Removed {len(removed)} old commands: {', '.join(removed)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("✅ No old commands found!", ephemeral=True)
        
        @self.bot.tree.command(
            name="restart",
            description="[ADMIN] Restart the bot gracefully. Saves all data before restarting."
        )
        async def restart_command(interaction: discord.Interaction):
            # Check admin role
            if not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            await interaction.response.send_message("🔄 **Bot restarting in 3 seconds...** All data will be saved.")
            
            # Wait a moment for message to send
            await asyncio.sleep(3)
            
            console.print("[red]🔄 Bot restart requested via command[/red]")
            
            # Save all data before restart
            self.save_all_data()
            
            # Close bot gracefully
            await self.bot.close()
            
            # Restart process
            import sys
            os.execv(sys.executable, ['python'] + sys.argv)

        @self.bot.tree.command(
            name="manageultimates",
            description="[ADMIN] View and manage registered ultimates, cooldowns, and settings."
        )
        @app_commands.describe(
            action="Action to perform",
            character_name="Character name (for editing powers)",
            new_cooldown="New cooldown in seconds (for set_cooldown action)",
            self_recharge="Toggle self-recharge (for toggle_recharge action)"
        )
        @app_commands.choices(action=[
            app_commands.Choice(name="List All Powers", value="list"),
            app_commands.Choice(name="Set Power Cooldown", value="set_cooldown"),
            app_commands.Choice(name="Toggle Self-Recharge", value="toggle_recharge"),
        ])
        async def manageultimates_command(
            interaction: discord.Interaction,
            action: str,
            character_name: str = None,
            new_cooldown: int = None,
            self_recharge: bool = None
        ):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                    return
                
                if action == "list":
                    # List all registered powers
                    if not self.character_powers:
                        await interaction.response.send_message("📋 No powers registered yet!", ephemeral=True)
                        return
                    
                    embed = discord.Embed(
                        title="⚡ Registered Ultimate Powers",
                        description=f"**Self-Recharge Mode**: {'✅ ON' if self.ultimate_self_recharge else '❌ OFF'}",
                        color=discord.Color.purple()
                    )
                    
                    for char_name, powers in self.character_powers.items():
                        power_text = ""
                        for slot in ["power1", "power2"]:
                            if slot in powers:
                                p = powers[slot]
                                power_text += f"**{slot.upper()}**: {p['name']}\n"
                                power_text += f"  └ Type: {p['type']} | CD: {p['cooldown']}s | Effect: {p['effect']}\n"
                        if power_text:
                            embed.add_field(name=f"🎭 {char_name}", value=power_text, inline=False)
                    
                    await interaction.response.send_message(embed=embed)
                
                elif action == "set_cooldown":
                    if not character_name:
                        await interaction.response.send_message("❌ Provide character_name!", ephemeral=True)
                        return
                    if new_cooldown is None or new_cooldown < 0:
                        await interaction.response.send_message("❌ Provide valid new_cooldown (>= 0)!", ephemeral=True)
                        return
                    
                    if character_name not in self.character_powers:
                        await interaction.response.send_message(f"❌ Character '{character_name}' has no powers!", ephemeral=True)
                        return
                    
                    # Update cooldown for all powers of this character
                    updated = []
                    for slot in ["power1", "power2"]:
                        if slot in self.character_powers[character_name]:
                            old_cd = self.character_powers[character_name][slot]['cooldown']
                            self.character_powers[character_name][slot]['cooldown'] = new_cooldown
                            updated.append(f"{slot}: {old_cd}s → {new_cooldown}s")
                    
                    self.save_all_data()
                    await interaction.response.send_message(
                        f"✅ Updated cooldowns for **{character_name}**:\n" + "\n".join(updated)
                    )
                
                elif action == "toggle_recharge":
                    if self_recharge is None:
                        # Just toggle
                        self.ultimate_self_recharge = not self.ultimate_self_recharge
                    else:
                        self.ultimate_self_recharge = self_recharge
                    
                    status = "✅ ON" if self.ultimate_self_recharge else "❌ OFF"
                    await interaction.response.send_message(
                        f"⚡ **Ultimate Self-Recharge**: {status}\n\n"
                        f"When ON: Landing an ultimate also recharges your ultimate meter!"
                    )
                
            except Exception as e:
                log.error(f"Error in manageultimates command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="charge",
            description="View your current ultimate power charge percentages and cooldowns"
        )
        async def charge_command(interaction: discord.Interaction):
            try:
                user_id = interaction.user.id
                
                # Get charge percentages
                p1_charge = self.get_charge_percentage(user_id, 1)
                p2_charge = self.get_charge_percentage(user_id, 2)
                
                # Create visual charge bars
                def make_bar(percent):
                    filled = int(percent / 10)
                    return "█" * filled + "░" * (10 - filled)
                
                # Check if user has registered character with powers
                power1_name = "Power 1"
                power2_name = "Power 2"
                if user_id in self.user_characters and self.user_characters[user_id]:
                    char_name = self.user_characters[user_id][0]
                    if char_name in self.character_powers:
                        powers = self.character_powers[char_name]
                        if "power1" in powers:
                            power1_name = powers["power1"]["name"]
                        if "power2" in powers:
                            power2_name = powers["power2"]["name"]
                
                # Check cooldowns
                cd1_text = "Ready" if self.can_use_ultimate(user_id, 1) else f"{p1_charge:.0f}%"
                cd2_text = "Ready" if self.can_use_ultimate(user_id, 2) else f"{p2_charge:.0f}%"
                
                embed = discord.Embed(
                    title="⚡ Ultimate Power Charges",
                    color=discord.Color.purple()
                )
                embed.add_field(
                    name=f"🔮 {power1_name}",
                    value=f"`{make_bar(p1_charge)}` {cd1_text}",
                    inline=False
                )
                embed.add_field(
                    name=f"✨ {power2_name}",
                    value=f"`{make_bar(p2_charge)}` {cd2_text}",
                    inline=False
                )
                embed.set_footer(text="Use *power1* or *power2* when at 100% to activate!")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except Exception as e:
                log.error(f"Error in charge command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="resethp",
            description="[ADMIN] Reset HP for a specific player or all players"
        )
        @app_commands.describe(
            player="The player to reset HP for (leave empty for all players)"
        )
        async def resethp_command(interaction: discord.Interaction, player: discord.Member = None):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                    return
                
                if player:
                    # Reset single player
                    if player.id in self.player_hp:
                        self.player_hp[player.id] = {
                            "current": self.max_hp,
                            "max": self.max_hp,
                            "alive": True,
                            "revenge_mode": False
                        }
                        await self.update_hp_bar_display(player.id)
                        await interaction.response.send_message(
                            f"✅ Reset HP for **{player.display_name}** to {self.max_hp}!",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ {player.display_name} has no HP data yet!",
                            ephemeral=True
                        )
                else:
                    # Reset all players
                    count = 0
                    for user_id in list(self.player_hp.keys()):
                        self.player_hp[user_id] = {
                            "current": self.max_hp,
                            "max": self.max_hp,
                            "alive": True,
                            "revenge_mode": False
                        }
                        await self.update_hp_bar_display(user_id)
                        count += 1
                    
                    # Also reset FAITH system for new event
                    self.reset_faith_system()
                    
                    await interaction.response.send_message(
                        f"✅ Reset HP for **{count} players** to {self.max_hp}!",
                        ephemeral=True
                    )
                    console.print(f"[green]✓ HP reset for {count} players by {interaction.user.name}[/green]")
                    
            except Exception as e:
                log.error(f"Error in resethp command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)


    # ========== HP BAR SYSTEM METHODS ==========

    async def initialize_player_hp(self, user_id):
        """Initialize HP for a new player"""
        if user_id not in self.player_hp:
            self.player_hp[user_id] = {
                "current": self.max_hp,
                "max": self.max_hp,
                "alive": True,
                "revenge_mode": False
            }
            console.print(f"[green]💚 Initialized HP for user {user_id}[/green]")
            # Update display immediately
            await self.update_hp_bar_display(user_id)

    def calculate_damage(self, difficulty, attacker_id=None):
        """Calculate damage based on difficulty with randomization and buffs"""
        min_dmg, max_dmg = self.damage_ranges[difficulty]
        damage = random.randint(min_dmg, max_dmg)
        
        # Apply damage boost buff if attacker has one
        if attacker_id:
            damage = self.apply_damage_buff(attacker_id, damage)
        
        return damage
    
    # ========== BUFF SYSTEM HELPERS ==========
    
    def get_active_buff(self, user_id, buff_type):
        """Get active buff value if not expired, otherwise clean it up"""
        user_id = str(user_id)
        if user_id not in self.player_buffs:
            return None
        
        buff = self.player_buffs[user_id].get(buff_type)
        if not buff:
            return None
        
        # Check expiration (0 means permanent until used once)
        import time
        if buff.get("expires", 0) > 0 and time.time() > buff["expires"]:
            del self.player_buffs[user_id][buff_type]
            self.save_all_data()
            return None
        
        return buff
    
    def apply_buff(self, user_id, buff_type, value, duration=0):
        """Apply a buff to a user"""
        import time
        user_id = str(user_id)
        
        if user_id not in self.player_buffs:
            self.player_buffs[user_id] = {}
        
        expires = time.time() + duration if duration > 0 else 0
        self.player_buffs[user_id][buff_type] = {
            "value": value,
            "expires": expires
        }
        self.save_all_data()
        log.info(f"Applied buff {buff_type}={value} to user {user_id}, expires in {duration}s")
    
    def consume_buff(self, user_id, buff_type):
        """Consume (remove) a one-time buff after use"""
        user_id = str(user_id)
        if user_id in self.player_buffs and buff_type in self.player_buffs[user_id]:
            del self.player_buffs[user_id][buff_type]
            self.save_all_data()
    
    def apply_damage_buff(self, user_id, base_damage):
        """Apply damage boost buff to base damage"""
        buff = self.get_active_buff(user_id, "damage_boost")
        if buff:
            boost_percent = buff["value"] / 100.0
            boosted = int(base_damage * (1 + boost_percent))
            log.info(f"Damage boosted: {base_damage} -> {boosted} (+{buff['value']}%)")
            # Consume if instant (expires=0)
            if buff.get("expires", 0) == 0:
                self.consume_buff(user_id, "damage_boost")
            return boosted
        return base_damage
    
    def get_bf_boost(self, user_id):
        """Get black flash chance boost for user"""
        buff = self.get_active_buff(user_id, "bf_boost")
        if buff:
            # Consume if instant
            if buff.get("expires", 0) == 0:
                self.consume_buff(user_id, "bf_boost")
            return buff["value"] / 100.0  # Convert percent to decimal
        return 0.0
    
    async def apply_support_effect(self, caster_id, target_id, effect_string):
        """Parse and apply a support skill effect
        Format: support:target:effect_type:value:duration
        Examples:
            support:self:heal:30:0 - Heal self 30 HP instantly
            support:ally:bf_boost:10:60 - Boost ally BF chance 10% for 60s
            support:self:damage_boost:20:0 - Boost own damage 20% (one use)
        """
        parts = effect_string.split(":")
        if len(parts) < 4 or parts[0] != "support":
            return False, "Invalid effect format"
        
        _, target_type, effect_type, value_str = parts[:4]
        duration = int(parts[4]) if len(parts) > 4 else 0
        value = int(value_str.split(":")[0])  # Handle nested colons
        
        # Determine actual target
        actual_target = target_id if target_type == "ally" else caster_id
        
        result_msg = ""
        
        if effect_type == "heal":
            # Instant heal
            if actual_target in self.player_hp:
                hp_data = self.player_hp[actual_target]
                old_hp = hp_data["current"]
                hp_data["current"] = min(hp_data["max"], hp_data["current"] + value)
                healed = hp_data["current"] - old_hp
                result_msg = f"💚 Healed **{healed}** HP!"
                await self.update_hp_bar_display(actual_target)
        
        elif effect_type == "bf_boost":
            self.apply_buff(actual_target, "bf_boost", value, duration)
            dur_text = f"for {duration}s" if duration > 0 else "(next use)"
            result_msg = f"✨ Black Flash chance +**{value}%** {dur_text}"
        
        elif effect_type == "damage_boost":
            self.apply_buff(actual_target, "damage_boost", value, duration)
            dur_text = f"for {duration}s" if duration > 0 else "(next attack)"
            result_msg = f"⚔️ Damage +**{value}%** {dur_text}"
        
        elif effect_type == "ult_charge":
            # Add ultimate charge
            if actual_target not in self.power_charges:
                self.power_charges[actual_target] = {"power1": 0, "power2": 0}
            self.power_charges[actual_target]["power1"] = min(100, 
                self.power_charges[actual_target].get("power1", 0) + value)
            self.power_charges[actual_target]["power2"] = min(100,
                self.power_charges[actual_target].get("power2", 0) + value)
            self.save_all_data()
            result_msg = f"⚡ Ultimate charge +**{value}%**!"
        
        elif effect_type == "cd_reduce":
            # This would need cooldown tracking - for now just message
            result_msg = f"⏱️ Cooldowns reduced by **{value}s**!"
        
        else:
            return False, f"Unknown effect type: {effect_type}"
        
        return True, result_msg
    
    # ========== END BUFF SYSTEM ==========

    async def damage_player(self, user_id, difficulty):
        """Deal damage to a player based on difficulty"""
        # Initialize if needed
        if user_id not in self.player_hp:
            await self.initialize_player_hp(user_id)

        hp_data = self.player_hp[user_id]
        if not hp_data["alive"]:
            return False  # Player is already dead

        # Calculate variable damage
        damage = self.calculate_damage(difficulty)
        
        # Apply damage
        old_hp = hp_data["current"]
        hp_data["current"] = max(0, hp_data["current"] - damage)
        actual_damage = old_hp - hp_data["current"]

        console.print(f"[red]💔 User {user_id} took {actual_damage} damage! HP: {hp_data['current']}/{hp_data['max']}[/red]")
        
        # Reset counter streak on taking damage
        if user_id in self.counter_streaks:
            self.counter_streaks[user_id] = 0
        
        # ===== PHASE 5: ADD CHARGE FROM DAMAGE TAKEN =====
        self.add_charge_from_damage_taken(user_id, actual_damage)
        # =================================================

        # Check if REVENGE mode should activate (at 20% HP)
        hp_percent = hp_data["current"] / hp_data["max"]
        if hp_percent <= self.revenge_threshold and not hp_data["revenge_mode"] and hp_data["alive"]:
            await self.activate_revenge_mode(user_id)

        # Check if player died
        if hp_data["current"] == 0:
            await self.trigger_death(user_id)
            return False

        # Update HP bar display
        await self.update_hp_bar_display(user_id)
        return True

    async def activate_revenge_mode(self, user_id):
        """Activate REVENGE mode for a player"""
        try:
            hp_data = self.player_hp[user_id]
            hp_data["revenge_mode"] = True
            
            channel = self.bot.get_channel(self.qte_channel_id)
            if channel:
                member = channel.guild.get_member(user_id)
                if member:
                    embed = discord.Embed(
                        title="⚡ REVENGE MODE ACTIVATED ⚡",
                        description=f"**{member.mention}** enters a state of desperation!\n\n"
                                  f"💥 **+50% Damage**\n"
                                  f"⚡ **Faster Parry Windows**\n"
                                  f"🌟 **+10% Black Flash Chance**",
                        color=discord.Color.from_rgb(220, 20, 60)  # Crimson
                    )
                    await self.webhook_send(embed=embed)
            
            console.print(Panel.fit(
                f"[bold red]⚡ REVENGE MODE ⚡[/bold red]\n"
                f"[yellow]{member.display_name if member else user_id} activated REVENGE![/yellow]",
                border_style="red"
            ))
            
        except Exception as e:
            log.error(f"Error activating revenge mode: {e}")

    async def heal_player(self, user_id, amount):
        """Heal a player (for checkpoint system)"""
        if user_id not in self.player_hp:
            return False
            
        hp_data = self.player_hp[user_id]
        if not hp_data["alive"]:
            return False
            
        old_hp = hp_data["current"]
        hp_data["current"] = min(hp_data["max"], hp_data["current"] + amount)
        actual_heal = hp_data["current"] - old_hp
        
        if actual_heal > 0:
            console.print(f"[green]💚 User {user_id} healed {actual_heal} HP! HP: {hp_data['current']}/{hp_data['max']}[/green]")
            await self.update_hp_bar_display(user_id)
            return True
        return False

    async def trigger_checkpoint_heal(self, checkpoint_name):
        """Trigger HP regeneration for all living players at a checkpoint"""
        try:
            channel = self.bot.get_channel(self.qte_channel_id)
            healed_players = []
            
            for user_id, hp_data in self.player_hp.items():
                if hp_data["alive"]:
                    if await self.heal_player(user_id, self.regen_amount):
                        member = channel.guild.get_member(user_id) if channel else None
                        if member:
                            healed_players.append(member.mention)
            
            if channel and healed_players:
                embed = discord.Embed(
                    title=f"🏥 CHECKPOINT: {checkpoint_name}",
                    description=f"All players restored **{self.regen_amount} HP**!\n\n" +
                              " ".join(healed_players),
                    color=discord.Color.green()
                )
                await channel.send(embed=embed)
                
            console.print(f"[green]🏥 Checkpoint '{checkpoint_name}': Healed {len(healed_players)} players[/green]")
            
        except Exception as e:
            log.error(f"Error triggering checkpoint heal: {e}")

    def has_lyra_safeguard(self, user_id):
        """Check if player has Lyra registered"""
        if user_id not in self.user_characters:
            return False
        
        user_chars = self.user_characters[user_id]
        for char in user_chars:
            if char.lower() == self.lyra_character_name.lower():
                return True
        return False

    async def update_hp_bar_display(self, user_id_or_boss_name, is_boss=False):
        """Update HP bar in dedicated thread - OPTIMIZED with message caching"""
        try:
            if self.hp_bar_thread_id == 0:
                return
            
            thread = self.bot.get_channel(self.hp_bar_thread_id)
            if not thread:
                return
            
            # Generate cache key
            cache_key = f"boss_{user_id_or_boss_name}" if is_boss else f"player_{user_id_or_boss_name}"
            
            # Handle Boss HP
            if is_boss:
                boss_name = user_id_or_boss_name
                if not self.active_boss or self.active_boss['name'] != boss_name:
                    return
                
                boss = self.active_boss
                current = boss.get('hp_current', boss['hp_max'])
                max_hp = boss['hp_max']
                
                # HP percentage and visual bar
                hp_percent = (current / max_hp) * 100 if max_hp > 0 else 0
                filled = int((current / max_hp) * 20) if max_hp > 0 else 0
                bar = "█" * filled + "░" * (20 - filled)
                
                # Color based on HP
                if hp_percent > 60:
                    color = discord.Color.red()
                    emoji = "👹"
                elif hp_percent > 30:
                    color = discord.Color.orange()
                    emoji = "⚔️"
                else:
                    color = discord.Color.dark_red()
                    emoji = "💀"
                
                status = "⚔️ Active" if current > 0 else "💀 Defeated"
                
                embed = discord.Embed(
                    title=f"{emoji} **BOSS: {boss_name}**",
                    description=f"`{bar}`\n**{current}/{max_hp} HP** ({hp_percent:.1f}%)",
                    color=color
                )
                embed.set_footer(text=f"Status: {status}")
                
                if boss.get('gif_url'):
                    embed.set_thumbnail(url=boss['gif_url'])
                
                # Use cached message ID for instant edit
                await self._send_or_edit_hp_embed(thread, cache_key, embed)
                return
            
            # Handle Player HP
            user_id = user_id_or_boss_name
            hp_data = self.player_hp.get(user_id)
            if not hp_data:
                return
            
            current = hp_data["current"]
            max_hp = hp_data["max"]
            
            # Get member info
            channel = self.bot.get_channel(self.qte_channel_id)
            if not channel:
                return
            
            member = channel.guild.get_member(user_id)
            if not member:
                return
            
            # Calculate HP percentage
            hp_percent = (current / max_hp) * 100 if max_hp > 0 else 0
            
            # Create visual HP bar (20 characters)
            filled_blocks = int((current / max_hp) * 20)
            bar = "█" * filled_blocks + "░" * (20 - filled_blocks)
            
            # Determine color based on HP level
            if hp_percent > 60:
                color = discord.Color.green()
                status_emoji = "💚"
            elif hp_percent > 30:
                color = discord.Color.yellow()
                status_emoji = "💛"
            else:
                color = discord.Color.red()
                status_emoji = "❤️"
            
            # Alive/dead status
            status_text = "⚔️ Fighting" if hp_data["alive"] else "💀 Defeated"
            
            # Get ultimate charge
            p1_charge = self.get_charge_percentage(user_id, 1)
            p2_charge = self.get_charge_percentage(user_id, 2)
            
            # Create charge bars (10 chars each)
            def make_charge_bar(pct):
                filled = int(pct / 10)
                return "⚡" * filled + "○" * (10 - filled)
            
            charge_text = f"\n⚡ **Ultimate Charge**\nP1: `{make_charge_bar(p1_charge)}` {p1_charge:.0f}%\nP2: `{make_charge_bar(p2_charge)}` {p2_charge:.0f}%"
            
            # Create embed
            embed = discord.Embed(
                title=f"{status_emoji} {member.display_name}",
                description=f"```{bar}```\n**{current}/{max_hp} HP** ({hp_percent:.1f}%){charge_text}",
                color=color
            )
            embed.set_footer(text=f"Status: {status_text}")
            
            # Use cached message ID for instant edit
            await self._send_or_edit_hp_embed(thread, cache_key, embed)
        
        except Exception as e:
            log.error(f"Error updating HP bar: {e}")

    async def _send_or_edit_hp_embed(self, thread, cache_key, embed):
        """Helper: Edit cached message or send new one - avoids slow history search"""
        try:
            # Try to use cached message ID
            if cache_key in self.hp_bar_messages:
                try:
                    message = await thread.fetch_message(self.hp_bar_messages[cache_key])
                    await message.edit(embed=embed)
                    return
                except discord.NotFound:
                    # Message was deleted, remove from cache
                    del self.hp_bar_messages[cache_key]
                except Exception:
                    pass
            
            # No cached message, send new one and cache the ID
            new_message = await thread.send(embed=embed)
            self.hp_bar_messages[cache_key] = new_message.id
            
        except Exception as e:
            log.error(f"Error in HP bar send/edit: {e}")

    async def trigger_death(self, user_id):
        """Handle player death or FAITH resurrection - single embed for rate limiting"""
        try:
            # FAITH SYSTEM CHECK
            if self.has_lyra_safeguard(user_id) and user_id not in self.faith_used_players:
                await self.trigger_faith_safeguard(user_id)
                return
            
            hp_data = self.player_hp.get(user_id)
            if not hp_data:
                return

            # Mark as dead
            hp_data["alive"] = False

            # Get channel and member
            channel = self.bot.get_channel(self.qte_channel_id)
            if not channel:
                return

            member = channel.guild.get_member(user_id)
            if not member:
                return

            # Death sequence - SINGLE EMBED for rate limiting
            embed = discord.Embed(
                title="🕊️",
                description=f"*{member.display_name} has fallen in combat...*\n\n"
                           f"{member.mention} — Speak your final words...",
                color=discord.Color.dark_grey()
            )
            embed.set_footer(text="Rest in peace...")
            await channel.send(embed=embed)

            # Update HP bar to show defeated
            await self.update_hp_bar_display(user_id)

            console.print(Panel.fit(
                f"[bold red]💀 {member.display_name} has DIED[/bold red]",
                border_style="red"
            ))

        except Exception as e:
            log.error(f"Error in death sequence: {e}")
            console.print(f"[red]❌ Error in death sequence: {e}[/red]")

    async def counter_window_timeout(self, user_id, qte_id, duration):
        """Remove counter enable after timeout and delete message"""
        await asyncio.sleep(duration)
        
        if user_id in self.counter_enabled_players and self.counter_enabled_players[user_id] == qte_id:
            del self.counter_enabled_players[user_id]
        
        # Delete the counter window message
        if hasattr(self, 'counter_messages') and user_id in self.counter_messages:
            try:
                await self.counter_messages[user_id].delete()
                del self.counter_messages[user_id]
            except Exception:
                pass  # Message might already be deleted

    async def send_success_with_counter(self, channel, author_mention, response_time, user_id, qte_id):
        """Send SUCCESS + COUNTER message merged into one - saves rate limit"""
        self.counter_enabled_players[user_id] = qte_id
        
        # Initialize counter_messages dict if needed
        if not hasattr(self, 'counter_messages'):
            self.counter_messages = {}
        
        # MERGED: Success + Counter window in ONE message
        counter_msg = await self.webhook_send(
            content=f"✅ {author_mention} **evaded!** ({response_time:.2f}s) "
            f"| ⚡ **COUNTER** `*attack*` <t:{int(time.time() + 5)}:R>"
        )
        
        self.counter_messages[user_id] = counter_msg
        
        # Set counter window timeout (will delete message when expired)
        asyncio.create_task(self.counter_window_timeout(user_id, qte_id, 5.0))

    async def enable_counter_window(self, user_id, qte_id, channel, author_mention):
        """Enable counter window for a player - LEGACY, use send_success_with_counter instead"""
        await self.send_success_with_counter(channel, author_mention, 0.0, user_id, qte_id)

    async def trigger_faith_safeguard(self, user_id):
        """Trigger Lyra's FAITH safeguard resurrection"""
        try:
            channel = self.bot.get_channel(self.qte_channel_id)
            member = channel.guild.get_member(user_id)
            
            if not member:
                return
            
            # Mark as used
            self.faith_used_players.add(user_id)
            
            # Visual sequence
            await self.webhook_send(content="🕊️")
            await asyncio.sleep(2)
            await self.webhook_send(content="...")
            await asyncio.sleep(2)
            
            # Choose message variation randomly
            messages = [
                f"But **{member.display_name}** refused.",
                f"**{member.display_name}** did not succumb.",
                f"**{member.display_name}** held on to their faith.",
                f"The goddess's protection shields **{member.display_name}**."
            ]
            chosen_message = random.choice(messages)
            
            # Choose GIF randomly
            chosen_gif = random.choice([self.faith_gif_undertale, self.faith_gif_omori])
            
            # Create embed
            embed = discord.Embed(
                title="✨ FAITH ✨",
                description=chosen_message,
                color=discord.Color.gold()
            )
            embed.set_image(url=chosen_gif)
            embed.set_footer(text="Lyra's Safeguard - One-time protection")
            
            await self.webhook_send(embed=embed)
            await asyncio.sleep(1)
            
            # Resurrect to 1 HP
            self.player_hp[user_id]["current"] = 1
            self.player_hp[user_id]["alive"] = True
            await self.update_hp_bar_display(user_id)
            
            await self.webhook_send(content=f"💫 **{member.display_name}** rises again with **1 HP**! The faith endures.")
            
            console.print(f"[gold]✨ FAITH ACTIVATED - {member.display_name} resurrected![/gold]")
            
        except Exception as e:
            log.error(f"Error triggering FAITH safeguard: {e}")

    def reset_faith_system(self):
        """Reset FAITH safeguard for new event"""
        self.faith_used_players.clear()
        console.print("[cyan]🔄 FAITH system reset for new event[/cyan]")
    
    async def damage_boss(self, boss_name, damage):
        """Deal damage to a boss and update HP bar"""
        try:
            if not self.active_boss or self.active_boss['name'] != boss_name:
                return False
            
            boss = self.active_boss
            old_hp = boss['hp_current']
            boss['hp_current'] = max(0, boss['hp_current'] - damage)
            actual_damage = old_hp - boss['hp_current']
            
            console.print(f"[red]💥 Boss {boss_name} took {actual_damage} damage! HP: {boss['hp_current']}/{boss['hp_max']}[/red]")
            
            # Update HP bar display
            await self.update_hp_bar_display(boss_name, is_boss=True)
            
            # Check if boss defeated
            if boss['hp_current'] == 0:
                channel = self.bot.get_channel(self.qte_channel_id)
                if channel:
                    embed = discord.Embed(
                        title="💀 BOSS DEFEATED! 💀",
                        description=f"**{boss_name}** has been vanquished!",
                        color=discord.Color.gold()
                    )
                    await channel.send(embed=embed)
                console.print(f"[gold]👹 Boss {boss_name} DEFEATED![/gold]")
                return False
            
            return True
        except Exception as e:
            log.error(f"Error damaging boss: {e}")
            return False
    
    async def cleanup_old_commands(self):
        """Remove old/deprecated commands from Discord"""
        try:
            # Get current command tree
            commands = await self.bot.tree.fetch_commands()
            
            # List of commands to keep (current valid commands)
            valid_commands = {
                'qte', 'register', 'mycharacters', 'unregister', 'mystats',
                'registerboss', 'editvalues', 'registerpower', 'synccommands',
                'cleancommands', 'restart', 'charge', 'resethp', 'dashboard'
            }
            
            # Remove any command not in valid list
            removed = []
            for cmd in commands:
                if cmd.name not in valid_commands:
                    # remove_command is NOT async - don't await it
                    self.bot.tree.remove_command(cmd.name)
                    removed.append(cmd.name)
            
            if removed:
                # Sync to apply changes
                await self.bot.tree.sync()
                console.print(f"[green]✓ Removed old commands: {', '.join(removed)}[/green]")
            else:
                console.print("[cyan]No old commands to remove[/cyan]")
            
            return removed
        except Exception as e:
            log.error(f"Error cleaning commands: {e}")
            return []
    
    # ===== PHASE 5A: ULTIMATE POWER CHARGE METHODS =====
    
    def initialize_power_charges(self, user_id):
        """Initialize power charges for a new player"""
        if user_id not in self.power_charges:
            self.power_charges[user_id] = {
                "power1": 0.0,
                "power2": 0.0
            }
            console.print(f"[purple]⚡ Initialized power charges for user {user_id}[/purple]")
    
    def add_charge_from_damage_taken(self, user_id, damage_amount):
        """Add charge when player takes damage"""
        self.initialize_power_charges(user_id)
        
        # 2% per 5 damage taken = 0.4% per damage
        charge_gain = (damage_amount / 5.0) * self.charge_per_damage_taken
        
        # Add to both powers
        for power_key in ["power1", "power2"]:
            old_charge = self.power_charges[user_id][power_key]
            self.power_charges[user_id][power_key] = min(100.0, old_charge + charge_gain)
            new_charge = self.power_charges[user_id][power_key]
            
            if new_charge >= 100.0 and old_charge < 100.0:
                console.print(f"[gold1]⚡ User {user_id} {power_key.upper()} FULLY CHARGED![/gold1]")
        
        console.print(f"[cyan]⚡ User {user_id} gained {charge_gain:.1f}% charge from taking {damage_amount} damage[/cyan]")
    
    def add_charge_from_damage_dealt(self, user_id, damage_amount):
        """Add charge when player deals damage"""
        self.initialize_power_charges(user_id)
        
        # 1% per 10 damage dealt = 0.1% per damage
        charge_gain = (damage_amount / 10.0) * self.charge_per_damage_dealt
        
        # Add to both powers
        for power_key in ["power1", "power2"]:
            old_charge = self.power_charges[user_id][power_key]
            self.power_charges[user_id][power_key] = min(100.0, old_charge + charge_gain)
            new_charge = self.power_charges[user_id][power_key]
            
            if new_charge >= 100.0 and old_charge < 100.0:
                console.print(f"[gold1]⚡ User {user_id} {power_key.upper()} FULLY CHARGED![/gold1]")
        
        console.print(f"[cyan]⚡ User {user_id} gained {charge_gain:.1f}% charge from dealing {damage_amount} damage[/cyan]")
    
    def add_charge_from_counter(self, user_id):
        """Add charge when player lands a counter"""
        self.initialize_power_charges(user_id)
        
        # 15% charge for counter
        charge_gain = 15.0
        
        # Add to both powers
        for power_key in ["power1", "power2"]:
            old_charge = self.power_charges[user_id][power_key]
            self.power_charges[user_id][power_key] = min(100.0, old_charge + charge_gain)
            new_charge = self.power_charges[user_id][power_key]
            
            if new_charge >= 100.0 and old_charge < 100.0:
                console.print(f"[gold1]⚡ User {user_id} {power_key.upper()} FULLY CHARGED![/gold1]")
        
        console.print(f"[cyan]⚡ User {user_id} gained {charge_gain:.1f}% charge from counter[/cyan]")

    def can_use_ultimate(self, user_id, power_slot):
        """Check if player has enough charge for ultimate"""
        if user_id not in self.power_charges:
            return False
        
        power_key = f"power{power_slot}"
        return self.power_charges[user_id].get(power_key, 0.0) >= self.ultimate_cost
    
    def consume_ultimate_charge(self, user_id, power_slot):
        """Consume ultimate charge when power is used"""
        if user_id not in self.power_charges:
            return False
        
        power_key = f"power{power_slot}"
        if self.power_charges[user_id].get(power_key, 0.0) >= self.ultimate_cost:
            self.power_charges[user_id][power_key] = 0.0
            console.print(f"[yellow]⚡ User {user_id} consumed {power_key.upper()} charge![/yellow]")
            return True
        return False
    
    def get_charge_percentage(self, user_id, power_slot):
        """Get current charge percentage for a power"""
        if user_id not in self.power_charges:
            return 0.0
        
        power_key = f"power{power_slot}"
        return self.power_charges[user_id].get(power_key, 0.0)
    
    # ====================================================

    # ==============================================


    async def update_qte_player_cache(self):
        """Update the cache of QTE players"""
        try:
            channel = self.bot.get_channel(self.qte_channel_id)
            if not channel:
                console.print("[red]✗ QTE channel not found![/red]")
                return

            guild = channel.guild
            role = guild.get_role(self.qte_player_role_id)

            if not role:
                console.print("[red]✗ QTE player role not found![/red]")
                return

            self.qte_players = [
                member for member in role.members
                if member.id not in self.afk_users and not member.bot
            ]

            self.last_cache_update = datetime.now()
            console.print(f"[cyan]✓ QTE player cache updated: {len(self.qte_players)} active players[/cyan]")

        except Exception as e:
            console.print(f"[red]✗ Error updating QTE player cache: {e}[/red]")

    def should_update_cache(self):
        """Check if cache needs updating"""
        if not self.last_cache_update:
            return True
        return datetime.now() - self.last_cache_update > self.cache_duration

    async def qte_timeout_handler(self, qte_id, difficulty, mode, target=None):
        """Handle QTE timeout - waits for window to expire then triggers failure"""
        try:
            channel = self.bot.get_channel(self.qte_channel_id)
            
            # Total timeout based on difficulty (no intermediate emoji sends)
            timeout_durations = {
                'easy': 6.75,
                'medium': 5.0,
                'hard': 5.75,
                'impossible': 3.5
            }
            
            await asyncio.sleep(timeout_durations.get(difficulty, 5.0))
            
            if qte_id in self.active_qtes:
                await self.finish_qte_failure(qte_id, channel, mode, target)

        except Exception as e:
            console.print(f"[red]✗ Error in timeout handler: {e}[/red]")

    async def finish_qte_failure(self, qte_id, channel, mode, target):
        """Finish QTE with failure message"""
        try:
            if qte_id not in self.active_qtes:
                return  # Already handled

            qte_data = self.active_qtes.pop(qte_id, None)  # Atomically remove and get
            if not qte_data:
                return  # Another task handled it

            if mode == 'single' and target:
                await self.webhook_send(content=f"💥 {target.mention} **failed to respond in time!**")
                await self.damage_player(target.id, qte_data['difficulty'])
                console.print(f"[red]✗ Single QTE TIMEOUT - {target.name} failed[/red]")

                if target.id in self.player_stats:
                    self.player_stats[target.id]['failed'] += 1
                    self.player_stats[target.id]['current_streak'] = 0

            elif mode == 'group':
                participants = qte_data.get('participants', {})
                failed = [p['member'] for p in participants.values() if not p['responded']]
                if failed:
                    mentions = " ".join([m.mention for m in failed])
                    await self.webhook_send(content=f"💥 {mentions} **failed to respond in time!**")
                    console.print(f"[red]✗ Group QTE TIMEOUT - {len(failed)} players failed[/red]")

                    # Damage each failed player
                    for member in failed:
                        await self.damage_player(member.id, qte_data['difficulty'])
                        if member.id in self.player_stats:
                            self.player_stats[member.id]['failed'] += 1
                            self.player_stats[member.id]['current_streak'] = 0

            # Already removed via pop() above
            self.save_all_data()

        except Exception as e:
            console.print(f"[red]✗ Error finishing QTE failure: {qte_id}[/red]")

    async def trigger_single_qte(self, difficulty):
        """Trigger a single-target QTE"""
        try:
            if self.should_update_cache():
                await self.update_qte_player_cache()

            if not self.qte_players:
                console.print("[red]✗ No QTE players available![/red]")
                return

            target_member = random.choice(self.qte_players)

            qte_id = self.qte_counter
            self.qte_counter += 1

            self.active_qtes[qte_id] = {
                'difficulty': difficulty,
                'mode': 'single',
                'start': datetime.now(timezone.utc),
                'target': target_member,
                'participants': {},
                'responses': set()
            }

            self.session_stats['qtes_triggered'] += 1

            channel = self.bot.get_channel(self.qte_channel_id)
            emoji = self.difficulty_emoji.get(difficulty, '⚡')

            qte_message = await self.webhook_send(content=f"⚡ **{difficulty.upper()} QTE** {emoji} | {target_member.mention}")
            if not qte_message:
                # Fallback to regular send if webhook fails
                qte_message = await channel.send(f"⚡ **{difficulty.upper()} QTE** {emoji} | {target_member.mention}")
            self.active_qtes[qte_id]['message'] = qte_message  # Store for reactions

            # Rich console output
            table = Table(show_header=False, box=box.ROUNDED, border_style="yellow")
            table.add_row("[cyan]⚡ SINGLE QTE TRIGGERED[/cyan]")
            table.add_row(f"[white]ID:[/white] [magenta]{qte_id}[/magenta]")
            table.add_row(f"[white]Difficulty:[/white] [magenta]{difficulty.upper()}[/magenta]")
            table.add_row(f"[white]Target:[/white] [green]{target_member.name}[/green]")
            console.print(table)

            # Send parry warning star, then black flash indicator
            parry_min = self.qte_times[difficulty]['parry_window'][0]
            perfect_center = self.qte_times[difficulty]['perfect_parry']
            bf_window_start = perfect_center - self.bf_timing_window  # When BF window begins
            
            # Schedule star at parry start, then exclamation at BF window
            asyncio.create_task(self.send_parry_and_bf_warning(qte_message, parry_min, bf_window_start))

            asyncio.create_task(
                self.qte_timeout_handler(qte_id, difficulty, 'single', target_member)
            )

        except Exception as e:
            console.print(f"[red]✗ Error triggering single QTE: {e}[/red]")

    async def send_parry_and_bf_warning(self, qte_message, parry_start, bf_start):
        """Add parry warning star, then replace with exclamation when BF window opens"""
        try:
            # Wait until parry window starts
            if parry_start > 0:
                await asyncio.sleep(parry_start)
            await self.safe_add_reaction(qte_message, "⭐")
            
            # Wait until black flash window starts, then replace star with exclamation
            bf_delay = max(0, bf_start - parry_start)
            if bf_delay > 0:
                await asyncio.sleep(bf_delay)
            # Remove star and add exclamation to signal BF window
            try:
                await qte_message.clear_reaction("⭐")
            except:
                pass
            await self.safe_add_reaction(qte_message, "❗")
        except Exception:
            pass

    async def send_parry_warning(self, qte_message, delay):
        """Add parry warning star reaction to QTE message (legacy fallback)"""
        try:
            await asyncio.sleep(delay)
            await self.safe_add_reaction(qte_message, "⭐")
        except Exception:
            pass

    async def process_batch_qtes(self):
        """Process collected batch of QTEs - distribute randomly to players and process sequentially"""
        try:
            self.batch_mode_active = False
            
            if not self.pending_qte_batch:
                console.print("[yellow]📦 No QTEs queued in batch[/yellow]")
                return
            
            # Update player cache
            if self.should_update_cache():
                await self.update_qte_player_cache()
            
            if not self.qte_players:
                console.print("[red]✗ No QTE players available![/red]")
                self.pending_qte_batch = []
                return
            
            channel = self.bot.get_channel(self.qte_channel_id)
            if not channel:
                console.print("[red]✗ QTE channel not found![/red]")
                return
            
            # Randomly distribute QTEs to players
            import random
            player_qtes = {player.id: [] for player in self.qte_players}
            
            for qte in self.pending_qte_batch:
                # Randomly pick a player
                target = random.choice(self.qte_players)
                player_qtes[target.id].append(qte)
            
            # Clear pending batch
            self.pending_qte_batch = []
            
            # Console summary
            console.print(Panel.fit(
                f"[bold green]📦 BATCH DISTRIBUTED[/bold green]\n"
                f"[cyan]Distributed to {len([p for p in player_qtes.values() if p])} players[/cyan]",
                border_style="green"
            ))
            
            # Send summary to channel and process per player
            for player in self.qte_players:
                qtes = player_qtes.get(player.id, [])
                if not qtes:
                    continue
                
                # Count by difficulty
                counts = {}
                for q in qtes:
                    diff = q['difficulty']
                    counts[diff] = counts.get(diff, 0) + 1
                
                # Format summary: "EASY x3, HARD x2"
                summary_parts = []
                for diff in ['easy', 'medium', 'hard', 'impossible']:
                    if diff in counts:
                        emoji = self.difficulty_emoji.get(diff, '⚡')
                        summary_parts.append(f"{emoji} {diff.upper()} x{counts[diff]}")
                
                summary = ", ".join(summary_parts)
                await self.safe_send(channel, content=f"⚡ {player.mention}: {summary}")
                
                # Store queue for this player
                self.player_qte_queues[player.id] = qtes
                self.player_current_qte[player.id] = None
                
                # Start processing first QTE for this player
                asyncio.create_task(self.process_next_player_qte(player))
        
        except Exception as e:
            console.print(f"[red]✗ Error processing batch QTEs: {e}[/red]")
            self.batch_mode_active = False
            self.pending_qte_batch = []

    async def process_next_player_qte(self, player):
        """Process the next QTE in a player's queue"""
        try:
            user_id = player.id
            
            # Check if there are more QTEs in queue
            if user_id not in self.player_qte_queues or not self.player_qte_queues[user_id]:
                # Queue empty, clean up
                if user_id in self.player_qte_queues:
                    del self.player_qte_queues[user_id]
                if user_id in self.player_current_qte:
                    del self.player_current_qte[user_id]
                return
            
            # Get next QTE from queue
            qte_data = self.player_qte_queues[user_id].pop(0)
            difficulty = qte_data['difficulty']
            
            # Initialize HP if needed
            if user_id not in self.player_hp:
                await self.initialize_player_hp(user_id)
            
            # Create QTE entry
            qte_id = self.qte_counter
            self.qte_counter += 1
            
            self.active_qtes[qte_id] = {
                'difficulty': difficulty,
                'mode': 'single',
                'start': datetime.now(timezone.utc),
                'target': player,
                'participants': {},
                'responses': set(),
                'batch_mode': True  # Mark as batch QTE
            }
            
            self.player_current_qte[user_id] = qte_id
            
            channel = self.bot.get_channel(self.qte_channel_id)
            emoji = self.difficulty_emoji.get(difficulty, '⚡')
            
            remaining = len(self.player_qte_queues.get(user_id, []))
            remaining_text = f" ({remaining} remaining)" if remaining > 0 else ""
            
            await self.webhook_send(content=f"⚡ **{difficulty.upper()} QTE** {emoji} | {player.mention}{remaining_text}")
            
            # Send parry warning
            parry_min = self.qte_times[difficulty]['parry_window'][0]
            warning_time = max(0, parry_min - 0.3)
            if warning_time > 0:
                asyncio.create_task(self.send_parry_warning(channel, warning_time))
            
            # Start timeout handler
            asyncio.create_task(
                self.batch_qte_timeout_handler(qte_id, difficulty, player)
            )
            
        except Exception as e:
            console.print(f"[red]✗ Error processing player QTE queue: {e}[/red]")

    async def batch_qte_timeout_handler(self, qte_id, difficulty, target):
        """Handle timeout for batch QTE - move to next QTE after"""
        try:
            timeout_durations = {
                'easy': 6.5,
                'medium': 5.0,
                'hard': 4.5,
                'impossible': 4.0
            }
            
            await asyncio.sleep(timeout_durations.get(difficulty, 5.0))
            
            if qte_id in self.active_qtes:
                # Timeout occurred
                channel = self.bot.get_channel(self.qte_channel_id)
                await self.webhook_send(content=f"💥 {target.mention} **failed to respond in time!**")
                await self.damage_player(target.id, difficulty)
                await self.update_player_stats(target.id, 'evade', False, timeout_durations.get(difficulty, 5.0))
                
                console.print(f"[red]✗ Batch QTE TIMEOUT - {target.name}[/red]")
                
                self.active_qtes.pop(qte_id, None)
                self.save_all_data()
                
                # Process next QTE in queue
                await self.process_next_player_qte(target)

        except Exception as e:
            console.print(f"[red]✗ Error in batch timeout handler: {e}[/red]")

    async def trigger_group_qte(self, difficulty):
        """Trigger a group QTE"""
        try:
            if self.should_update_cache():
                await self.update_qte_player_cache()

            if not self.qte_players:
                console.print("[red]✗ No QTE players available![/red]")
                return

            qte_id = self.qte_counter
            self.qte_counter += 1

            self.active_qtes[qte_id] = {
                'difficulty': difficulty,
                'mode': 'group',
                'start': datetime.now(timezone.utc),
                'target': None,
                'participants': {member.id: {'responded': False, 'success': False, 'member': member} 
                                for member in self.qte_players},
                'responses': set()
            }

            self.session_stats['qtes_triggered'] += 1

            channel = self.bot.get_channel(self.qte_channel_id)
            role = channel.guild.get_role(self.qte_player_role_id)
            emoji = self.difficulty_emoji.get(difficulty, '⚡')

            await channel.send(f"🚨 **GROUP {difficulty.upper()} QTE** {emoji} | {role.mention}")

            # Rich console output
            table = Table(show_header=False, box=box.ROUNDED, border_style="red")
            table.add_row("[magenta]🚨 GROUP QTE TRIGGERED[/magenta]")
            table.add_row(f"[white]ID:[/white] [red]{qte_id}[/red]")
            table.add_row(f"[white]Difficulty:[/white] [red]{difficulty.upper()}[/red]")
            table.add_row(f"[white]Players:[/white] [cyan]{len(self.qte_players)}[/cyan]")
            console.print(table)

            asyncio.create_task(
                self.qte_timeout_handler(qte_id, difficulty, 'group')
            )

        except Exception as e:
            console.print(f"[red]✗ Error triggering group QTE: {e}[/red]")

    async def handle_qte_response(self, message):
        """Handle player responses to QTE events - OPTIMIZED"""
        try:
            # Early exits for performance
            if not self.active_qtes:
                return

            if message.channel.id != self.qte_channel_id:
                return
            
            content = message.content.lower()
            
            # Fast check: Only process if message contains a QTE command
            if '*evade*' not in content and '*parry*' not in content and '*save*' not in content:
                return

            user_id = self.resolve_user_id(message)
            now = datetime.now(timezone.utc)

            # Iterate over copy of keys to allow safe deletion
            for qte_id in list(self.active_qtes.keys()):
                qte_data = self.active_qtes.get(qte_id)
                if not qte_data:
                    continue
                    
                response_time = (now - qte_data['start']).total_seconds() - self.latency_offset

                timing = self.qte_times[qte_data['difficulty']]
                evade_window = timing['evade_window']
                parry_min, parry_max = timing['parry_window']

                if qte_data['mode'] == 'single':
                    result = await self.handle_single_qte_response(
                        qte_id, qte_data, message, user_id, content, 
                        response_time, evade_window, parry_min, parry_max
                    )
                    if result:
                        break

                elif qte_data['mode'] == 'bf_chain':
                    result = await self.handle_bf_chain_response(
                        qte_id, qte_data, message, user_id, content, response_time
                    )
                    if result:
                        break

                elif qte_data['mode'] == 'group':
                    await self.handle_group_qte_response(
                        qte_id, qte_data, message, user_id, content, 
                        response_time, evade_window, parry_min, parry_max
                    )

        except Exception as e:
            console.print(f"[red]✗ Error handling QTE response: {e}[/red]")

    def resolve_user_id(self, message):
        """Resolve user ID, handling Tupperbox characters"""
        author_name = message.author.display_name
        if author_name in self.character_registry:
            return self.character_registry[author_name]
        return message.author.id

    async def find_tupper_message(self, channel, user_id, original_message, timeout=1.0):
        """Find the Tupper webhook message that replaces the user's original message.
        
        Tupper deletes the original message and sends a webhook message.
        This function waits briefly and looks for a recent webhook message
        from a registered character owned by this user.
        
        OPTIMIZED for heavy load: Reduced wait time and limit checks.
        """
        try:
            await asyncio.sleep(0.15)  # Reduced from 0.3s for faster response under load
            
            # Look through recent messages for a webhook from a registered character
            # Reduced limit from 5 to 3 for performance
            async for msg in channel.history(limit=3, after=original_message):
                # Webhook messages have webhook_id attribute
                if msg.webhook_id:
                    char_name = msg.author.display_name
                    # Check if this character is registered to this user
                    if char_name in self.character_registry:
                        if self.character_registry[char_name] == user_id:
                            return msg
            
            # Fallback: return original message if no Tupper message found
            return original_message
        except Exception as e:
            log.debug(f"Error finding Tupper message: {e}")
            return original_message

    async def add_reaction_to_response(self, channel, user_id, original_message, emoji):
        """Add reaction to the correct message (Tupper webhook or original)."""
        try:
            target_msg = await self.find_tupper_message(channel, user_id, original_message)
            await target_msg.add_reaction(emoji)
        except Exception:
            pass

    async def handle_single_qte_response(self, qte_id, qte_data, message, user_id, content, response_time, evade_window, parry_min, parry_max):
        """Handle responses for single-target QTE"""
        try:
            channel = message.channel
            target = qte_data['target']
            responses = qte_data['responses']
            difficulty = qte_data['difficulty']

            # Initialize HP for player if first time participating
            if user_id not in self.player_hp:
                await self.initialize_player_hp(user_id)

            if user_id in responses:
                return False

            if user_id == target.id:
                if '*evade*' in content:
                    # Check for spam attempts after QTE completion
                    current_time = time.time()
                    if user_id in self.last_qte_completion:
                        time_since_last = current_time - self.last_qte_completion[user_id]
                        if time_since_last < 1.0 and qte_id not in self.active_qtes:
                            # Spam attempt within 1 second after QTE completion
                            await self.webhook_send(content=f"❌ {message.author.mention} **missed HARD QTE attempt!** (spam detected)")
                            await self.damage_player(user_id, 'hard')
                            console.print(f"[red]✗ SPAM EVADE BLOCKED - {message.author.name}[/red]")
                            return False
                    
                    if response_time <= evade_window:
                        responses.add(user_id)
                        await self.update_player_stats(user_id, 'evade', True, response_time)
                        console.print(f"[green]✓ EVADE SUCCESS - {message.author.name} in {response_time:.2f}s[/green]")
                        
                        # Add success reaction to Tupper message (or original if not using Tupper)
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "✅"))
                        
                        # Enable counter window if evaded fast enough
                        if response_time < self.counter_window:
                            await self.send_success_with_counter(channel, message.author.mention, response_time, user_id, qte_id)
                            console.print(f"[yellow]⚡ COUNTER ENABLED for {message.author.name}[/yellow]")
                        # No separate success message - reaction emoji is enough
                        
                        self.last_qte_completion[user_id] = current_time
                        is_batch = qte_data.get('batch_mode', False)
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        
                        # Process next batch QTE if applicable
                        if is_batch:
                            await self.process_next_player_qte(target)
                        return True
                    else:
                        await self.webhook_send(content=f"❌ {message.author.mention} **evade too slow!** ({response_time:.2f}s)")
                        await self.damage_player(user_id, difficulty)
                        await self.update_player_stats(user_id, 'evade', False, response_time)
                        console.print(f"[red]✗ EVADE FAILED (too slow) - {message.author.name}[/red]")
                        
                        # Add failure reaction to Tupper message (or original if not using Tupper)
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "❌"))
                        
                        self.last_qte_completion[user_id] = current_time
                        is_batch = qte_data.get('batch_mode', False)
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        
                        # Process next batch QTE if applicable
                        if is_batch:
                            await self.process_next_player_qte(target)
                        return True

                elif '*parry*' in content:
                    # Check parry cooldown from BF chain
                    if user_id in self.player_parry_cooldown:
                        if time.time() < self.player_parry_cooldown[user_id]:
                            remaining = int(self.player_parry_cooldown[user_id] - time.time())
                            await self.webhook_send(content=f"⏱️ {message.author.mention} **Parry on cooldown!** {remaining}s remaining")
                            return False
                    
                    # Get adjusted parry window for REVENGE mode
                    parry_min, parry_max = self.get_adjusted_parry_window(difficulty, user_id)
                    
                    if parry_min <= response_time <= parry_max:
                        responses.add(user_id)

                        # Check for BLACK FLASH
                        black_flash = self.check_black_flash(user_id, response_time, difficulty)

                        if black_flash:
                            # EPIC BLACK FLASH MESSAGE - Start of chain!
                            base_damage = self.bf_chain_damage.get(1, 25)
                            
                            # Apply first BF damage to boss
                            if self.active_boss:
                                await self.damage_boss(self.active_boss['name'], base_damage)
                            
                            # Stun enemy for 1 second (guaranteed on BF)
                            self.enemy_stunned = True
                            self.stun_end_time = time.time() + 1.0
                            
                            # Add charge
                            self.add_charge_from_damage_dealt(user_id, base_damage)
                            
                            embed = discord.Embed(
                                title="⚡💥 BLACK FLASH! 💥⚡",
                                description=f"**{message.author.mention}** landed a **PERFECT BLACK FLASH!**\n\n"
                                           f"💢 **{base_damage} DAMAGE!**\n"
                                           f"🌀 Enemy stunned for 1s!\n"
                                           f"🔥 **CHAIN OPPORTUNITY INCOMING!**",
                                color=discord.Color.from_rgb(138, 43, 226)  # Purple
                            )
                            embed.set_image(url=self.black_flash_gif)
                            bf_chance = self.player_stats[user_id]['black_flash_chance'] * 100
                            embed.set_footer(text=f"Black Flash Chance: {bf_chance:.1f}% | Response Time: {response_time:.2f}s")
                            await self.safe_send(channel, embed=embed)
                            
                            # Add exclamation reaction
                            asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "❗"))

                            console.print(Panel.fit(
                                f"[bold magenta]⚡💥 BLACK FLASH! 💥⚡[/bold magenta]\n"
                                f"[cyan]{message.author.name}[/cyan] landed a PERFECT parry!\n"
                                f"[yellow]Time: {response_time:.2f}s | New Chance: {bf_chance:.1f}%[/yellow]",
                                border_style="magenta"
                            ))
                            
                            # Start BF Chain after short delay
                            await self.update_player_stats(user_id, 'parry', True, response_time)
                            current_time = time.time()
                            self.last_qte_completion[user_id] = current_time
                            
                            is_batch = qte_data.get('batch_mode', False)
                            self.active_qtes.pop(qte_id, None)
                            self.save_all_data()
                            
                            # Trigger BF Chain QTE (level 2 since this was level 1)
                            await asyncio.sleep(0.5)
                            await self.trigger_bf_chain_qte(user_id, channel, target, difficulty, 2)
                            
                            # Process next batch QTE if applicable (after chain ends naturally)
                            # Don't process here - let chain complete first
                            return True
                        else:
                            # No separate success message - reaction emoji is enough
                            console.print(f"[cyan]⚔ PARRY SUCCESS - {message.author.name} in {response_time:.2f}s[/cyan]")

                        # Add success reaction to Tupper message (or original if not using Tupper)
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "✅"))

                        await self.update_player_stats(user_id, 'parry', True, response_time)
                        current_time = time.time()
                        self.last_qte_completion[user_id] = current_time
                        
                        # Important: Don't delete QTE yet to prevent issues
                        is_batch = qte_data.get('batch_mode', False)
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        
                        # Process next batch QTE if applicable
                        if is_batch:
                            await self.process_next_player_qte(target)
                        return True
                    else:
                        await self.webhook_send(content=f"❌ {message.author.mention} **parry mistimed!** ({response_time:.2f}s)")
                        await self.damage_player(user_id, difficulty)
                        await self.update_player_stats(user_id, 'parry', False, response_time)
                        console.print(f"[red]✗ PARRY FAILED (mistimed) - {message.author.name}[/red]")
                        
                        # Add failure reaction to Tupper message (or original if not using Tupper)
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "❌"))
                        
                        current_time = time.time()
                        self.last_qte_completion[user_id] = current_time
                        
                        is_batch = qte_data.get('batch_mode', False)
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        
                        # Process next batch QTE if applicable
                        if is_batch:
                            await self.process_next_player_qte(target)
                        return True

            else:
                if '*save*' in content and target:
                    if response_time <= evade_window:
                        responses.add(user_id)
                        await self.webhook_send(content=f"🛡️ {message.author.mention} **saved {target.mention}!** ({response_time:.2f}s)")
                        await self.update_player_stats(user_id, 'save', True, response_time)
                        await self.update_player_stats(target.id, 'saved', True, response_time)
                        console.print(f"[magenta]🛡 SAVE SUCCESS - {message.author.name} saved {target.name}[/magenta]")
                        current_time = time.time()
                        self.last_qte_completion[user_id] = current_time
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        return True
                    else:
                        await self.webhook_send(content=f"❌ {message.author.mention} **save too slow!** ({response_time:.2f}s)")
                        await self.damage_player(user_id, difficulty)
                        await self.update_player_stats(user_id, 'save', False, response_time)
                        console.print(f"[red]✗ SAVE FAILED (too slow) - {message.author.name}[/red]")
                        current_time = time.time()
                        self.last_qte_completion[user_id] = current_time

            return False

        except Exception as e:
            console.print(f"[red]✗ Error in single QTE response handler: {e}[/red]")
            return False

    async def handle_group_qte_response(self, qte_id, qte_data, message, user_id, content, response_time, evade_window, parry_min, parry_max):
        """Handle responses for group QTE"""
        try:
            channel = message.channel
            participants = qte_data['participants']
            difficulty = qte_data['difficulty']

            # Initialize HP for player if first time participating
            if user_id not in self.player_hp:
                await self.initialize_player_hp(user_id)

            if user_id not in participants:
                return False

            participant = participants[user_id]

            if participant['responded']:
                return False

            participant['responded'] = True
            success = False
            action = None

            if '*evade*' in content:
                action = 'evade'
                current_time = time.time()
                
                if response_time <= evade_window:
                    success = True
                    participant['success'] = True
                    console.print(f"[green]✓ {message.author.name} - EVADE - {response_time:.2f}s[/green]")
                    
                    # Enable counter window if evaded fast enough - MERGED with success message
                    if response_time < self.counter_window:
                        await self.send_success_with_counter(channel, message.author.mention, response_time, user_id, qte_id)
                        console.print(f"[yellow]⚡ COUNTER ENABLED for {message.author.name}[/yellow]")
                    else:
                        await self.webhook_send(content=f"✅ {message.author.mention} evaded! ({response_time:.2f}s)")
                    
                    self.last_qte_completion[user_id] = current_time
                else:
                    await self.webhook_send(content=f"❌ {message.author.mention} evade too slow! ({response_time:.2f}s)")
                    await self.damage_player(user_id, difficulty)
                    console.print(f"[red]✗ {message.author.name} - EVADE FAILED - {response_time:.2f}s[/red]")
                    self.last_qte_completion[user_id] = current_time

            elif '*parry*' in content:
                action = 'parry'
                current_time = time.time()
                
                # Check parry cooldown from BF chain
                if user_id in self.player_parry_cooldown:
                    if time.time() < self.player_parry_cooldown[user_id]:
                        remaining = int(self.player_parry_cooldown[user_id] - time.time())
                        await self.webhook_send(content=f"⏱️ {message.author.mention} **Parry on cooldown!** {remaining}s remaining")
                        return False
                
                # Get adjusted parry window for REVENGE mode
                parry_min, parry_max = self.get_adjusted_parry_window(difficulty, user_id)
                
                if parry_min <= response_time <= parry_max:
                    success = True
                    participant['success'] = True

                    # Check for BLACK FLASH in group QTE too
                    black_flash = self.check_black_flash(user_id, response_time, difficulty)

                    if black_flash:
                        base_damage = self.bf_chain_damage.get(1, 25)
                        
                        # Apply first BF damage to boss
                        if self.active_boss:
                            await self.damage_boss(self.active_boss['name'], base_damage)
                        
                        # Stun enemy for 1 second
                        self.enemy_stunned = True
                        self.stun_end_time = time.time() + 1.0
                        
                        embed = discord.Embed(
                            title="⚡💥 BLACK FLASH! 💥⚡",
                            description=f"**{message.author.mention}** landed a **BLACK FLASH** in the chaos!\n\n"
                                       f"💢 **{base_damage} DAMAGE!**\n"
                                       f"🔥 **CHAIN OPPORTUNITY!**",
                            color=discord.Color.from_rgb(138, 43, 226)
                        )
                        embed.set_image(url=self.black_flash_gif)
                        await self.webhook_send(embed=embed)
                        
                        # Add exclamation reaction
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "❗"))
                        
                        console.print(f"[bold magenta]⚡💥 BLACK FLASH - {message.author.name}![/bold magenta]")
                        
                        # Start BF chain for this player
                        member = message.author
                        asyncio.create_task(self.trigger_bf_chain_qte(user_id, channel, member, difficulty, 2))
                    else:
                        await self.webhook_send(content=f"⚔️ {message.author.mention} parried! ({response_time:.2f}s)")
                        console.print(f"[cyan]⚔ {message.author.name} - PARRY - {response_time:.2f}s[/cyan]")
                    self.last_qte_completion[user_id] = current_time
                else:
                    await self.webhook_send(content=f"❌ {message.author.mention} parry mistimed! ({response_time:.2f}s)")
                    await self.damage_player(user_id, difficulty)
                    console.print(f"[red]✗ {message.author.name} - PARRY FAILED - {response_time:.2f}s[/red]")
                    self.last_qte_completion[user_id] = current_time

            if action:
                await self.update_player_stats(user_id, action, success, response_time)

            if all(p['responded'] for p in participants.values()):
                await self.finish_group_qte(qte_id, channel)
                return True

            return False

        except Exception as e:
            console.print(f"[red]✗ Error in group QTE response handler: {e}[/red]")
            return False

    async def finish_group_qte(self, qte_id, channel):
        """Finish group QTE and show results"""
        try:
            if qte_id not in self.active_qtes:
                return

            qte_data = self.active_qtes[qte_id]
            participants = qte_data['participants']

            successful = sum(1 for p in participants.values() if p['success'])
            total = len(participants)

            await channel.send(f"📊 **Group QTE Complete!** {successful}/{total} succeeded")

            console.print(Panel.fit(
                f"[cyan]📊 GROUP QTE FINISHED (ID: {qte_id})[/cyan]\n"
                f"[green]Successful: {successful}/{total}[/green]",
                border_style="cyan"
            ))

            self.active_qtes.pop(qte_id, None)
            self.save_all_data()

        except Exception as e:
            console.print(f"[red]✗ Error finishing group QTE: {e}[/red]")

    async def check_trigger_phrase(self, message):
        """Check if message contains a trigger phrase for any registered power"""
        try:
            import re
            # Extract quoted text from message
            quoted_texts = re.findall(r'"([^"]+)"', message.content)
            if not quoted_texts:
                return
            
            user_id = self.resolve_user_id(message)
            
            # Check if user has characters
            if user_id not in self.user_characters or not self.user_characters[user_id]:
                return
            
            # Check each character's powers for matching trigger phrases
            for character_name in self.user_characters[user_id]:
                if character_name not in self.character_powers:
                    continue
                
                for power_slot in [1, 2]:
                    power_key = f"power{power_slot}"
                    if power_key not in self.character_powers[character_name]:
                        continue
                    
                    power = self.character_powers[character_name][power_key]
                    trigger = power.get("trigger_phrase")
                    
                    if not trigger:
                        continue
                    
                    # Check if any quoted text matches the trigger
                    for quoted in quoted_texts:
                        if quoted.lower().strip() == trigger:
                            console.print(f"[purple]⚡ Trigger phrase detected: \"{trigger}\" -> {power['name']}[/purple]")
                            await self.handle_power_activation(message, power_slot)
                            return  # Only trigger one power per message
        
        except Exception as e:
            log.error(f"Error checking trigger phrase: {e}")

    async def handle_power_activation(self, message, power_slot):
        """Handle power activation (*power1* or *power2*)"""
        try:
            user_id = message.author.id
            channel = message.channel
            
            # Check if player has registered characters
            if user_id not in self.user_characters or not self.user_characters[user_id]:
                await channel.send(f"{message.author.mention} You need to register a character first! Use `/register`")
                return
            
            # Get first registered character (or implement character selection)
            character_name = self.user_characters[user_id][0]
            
            # Check if character has powers
            if character_name not in self.character_powers:
                await channel.send(f"{message.author.mention} No powers registered for **{character_name}**!")
                return
            
            power_key = f"power{power_slot}"
            if power_key not in self.character_powers[character_name]:
                await channel.send(f"{message.author.mention} **{character_name}** doesn't have Power {power_slot}!")
                return
            
            # ===== PHASE 5: CHECK ULTIMATE CHARGE REQUIREMENT =====
            if not self.can_use_ultimate(user_id, power_slot):
                current_charge = self.get_charge_percentage(user_id, power_slot)
                await channel.send(
                    f"{message.author.mention} ⚡ **Not enough charge!** "
                    f"Current: {current_charge:.1f}% | Required: {self.ultimate_cost:.0f}%"
                )
                return
            # ======================================================
            
            # Check cooldown
            current_time = time.time()
            if user_id not in self.power_cooldowns:
                self.power_cooldowns[user_id] = {}
            
            if power_key in self.power_cooldowns[user_id]:
                cooldown_end = self.power_cooldowns[user_id][power_key]
                if current_time < cooldown_end:
                    remaining = int(cooldown_end - current_time)
                    await channel.send(f"{message.author.mention} ⏱️ Power on cooldown! **{remaining}s** remaining.")
                    return
            
            # Get power data
            power = self.character_powers[character_name][power_key]
            
            # ===== PHASE 5: CONSUME ULTIMATE CHARGE =====
            self.consume_ultimate_charge(user_id, power_slot)
            # ============================================
            
            # Set cooldown
            self.power_cooldowns[user_id][power_key] = current_time + power["cooldown"]
            
            # Apply power effect
            await self.apply_power_effect(message.author, power, channel)
            
            console.print(f"[purple]⚡ {message.author.name} used {power['name']}[/purple]")
            
        except Exception as e:
            log.error(f"Error handling power activation: {e}")

    async def apply_power_effect(self, user, power, channel):
        """Apply power effects based on effect string"""
        try:
            effect = power["effect"]
            power_name = power["name"]
            base_cooldown = power["cooldown"]
            
            # Create activation embed
            embed = discord.Embed(
                title=f"⚡ {power_name.upper()} ⚡",
                description=power["description"],
                color=self.get_power_color(power["type"])
            )
            
            # Parse effect string
            if effect.startswith("damage:"):
                damage = int(effect.split(":")[1])
                
                # Calculate dynamic cooldown based on damage
                extra_cooldown = int(damage * self.ultimate_cooldown_per_damage)
                total_cooldown = base_cooldown + extra_cooldown
                
                embed.add_field(name="Effect", value=f"💥 {damage} damage to enemy!", inline=False)
                embed.add_field(name="Dynamic Cooldown", value=f"⏱️ {total_cooldown}s (base {base_cooldown}s + {extra_cooldown}s)", inline=False)
                
                # Update the actual cooldown for this use
                if user.id in self.power_cooldowns:
                    for key in self.power_cooldowns[user.id]:
                        # Find which power is currently on cooldown and update it
                        if self.power_cooldowns[user.id][key] > time.time():
                            self.power_cooldowns[user.id][key] = time.time() + total_cooldown
                
                # ===== PHASE 5: ADD CHARGE FROM POWER DAMAGE (only if self-recharge enabled) =====
                if self.ultimate_self_recharge:
                    self.add_charge_from_damage_dealt(user.id, damage)
                # =================================================
                
                # Apply damage to boss if active
                if self.active_boss:
                    await self.damage_boss(self.active_boss['name'], damage)
                
            elif effect.startswith("heal:"):
                heal_amount = int(effect.split(":")[1])
                if user.id in self.player_hp:
                    old_hp = self.player_hp[user.id]["current"]
                    self.player_hp[user.id]["current"] = min(
                        self.player_hp[user.id]["current"] + heal_amount,
                        self.player_hp[user.id]["max"]
                    )
                    new_hp = self.player_hp[user.id]["current"]
                    healed = new_hp - old_hp
                    await self.update_hp_bar_display(user.id)
                    embed.add_field(name="Effect", value=f"💚 Healed **{healed} HP**!", inline=False)
            
            elif effect == "stun":
                self.enemy_stunned = True
                self.stun_end_time = time.time() + 3.0  # 3 second stun
                embed.add_field(name="Effect", value="🌀 Enemy stunned for **3 seconds**!", inline=False)
            
            elif effect.startswith("buff:"):
                buff_type = effect.split(":")[1]
                embed.add_field(name="Effect", value=f"✨ {buff_type.capitalize()} buff applied!", inline=False)
                # TODO: Implement buff system if needed
            
            else:
                embed.add_field(name="Effect", value=f"⚡ {effect}", inline=False)
            
            # Add power image (custom if set, otherwise default ultimate GIF)
            power_image = power.get("image_url") or self.ultimate_gif
            embed.set_image(url=power_image)
            embed.set_footer(text=f"Cooldown: {power['cooldown']}s | Type: {power['type'].capitalize()}")
            await channel.send(embed=embed)
            
        except Exception as e:
            log.error(f"Error applying power effect: {e}")

    def get_power_color(self, power_type):
        """Get embed color based on power type"""
        colors = {
            "destructive": discord.Color.red(),
            "support": discord.Color.green(),
            "defend": discord.Color.blue(),
            "build": discord.Color.gold(),
            "control": discord.Color.purple()
        }
        return colors.get(power_type, discord.Color.dark_purple())

    async def handle_counter_attack(self, message):
        """Handle *attack* counter command - triggers instant counter with GIF"""
        try:
            if message.channel.id != self.qte_channel_id:
                return
            
            user_id = self.resolve_user_id(message)
            
            # Check if user has counter enabled
            if user_id not in self.counter_enabled_players:
                return
            
            # COUNTER SUCCESS! Remove from counter-enabled immediately
            del self.counter_enabled_players[user_id]
            
            channel = message.channel
            
            # Increment counter streak
            if user_id not in self.counter_streaks:
                self.counter_streaks[user_id] = 0
            self.counter_streaks[user_id] += 1
            counter_streak = self.counter_streaks[user_id]
            
            # Fixed counter damage with parry streak multiplier
            base_damage = 25
            parry_streak = self.player_stats.get(user_id, {}).get('parry_streak', 0)
            streak_multiplier = min(2.0, 1.0 + (parry_streak * 0.1))
            counter_damage = int(base_damage * streak_multiplier)
            
            # Add charge from counter
            self.add_charge_from_damage_dealt(user_id, counter_damage)
            self.add_charge_from_counter(user_id)
            
            # Apply damage to boss if active
            if self.active_boss:
                await self.damage_boss(self.active_boss['name'], counter_damage)
            
            # STUN SCALING: Base 0.5-1s, DOUBLED at 5 streak (1-2s), caps at 2s for 5+ streak
            if counter_streak >= 5:
                stun_duration = 2.0  # Full 2 seconds at 5+ streak
                stun_text = "**MASSIVE STUN!** (5+ counter streak!)"
            else:
                base_stun = random.uniform(0.5, 1.0)
                stun_bonus = counter_streak * 0.2  # +0.2s per streak
                stun_duration = min(1.5, base_stun + stun_bonus)
                stun_text = f"{stun_duration:.1f}s"
            
            self.enemy_stunned = True
            self.stun_end_time = time.time() + stun_duration
            
            # Send dramatic counter message with user's custom GIF or default
            user_gifs = self.user_counter_gifs.get(user_id)
            if user_gifs:
                # Support both single URL (string) and multiple URLs (list)
                if isinstance(user_gifs, list) and user_gifs:
                    counter_gif_url = random.choice(user_gifs)
                else:
                    counter_gif_url = user_gifs
            else:
                counter_gif_url = self.counter_gif
            
            # Get ultimate charge for display
            p1_charge = self.get_charge_percentage(user_id, 1)
            p2_charge = self.get_charge_percentage(user_id, 2)
            charge_text = f"⚡ Ult: P1 {p1_charge:.0f}% | P2 {p2_charge:.0f}%"
            
            embed = discord.Embed(
                title="⚡💥 FEROCIOUS COUNTER! 💥⚡",
                description=f"**{message.author.mention}** unleashes a devastating counterattack!\n\n"
                           f"💢 **{counter_damage} DAMAGE!**\n"
                           f"🌀 Enemy stunned for {stun_text}\n"
                           f"🔥 Counter Streak: **{counter_streak}**\n"
                           f"{charge_text}",
                color=discord.Color.from_rgb(255, 69, 0)  # Orange-Red
            )
            embed.set_image(url=counter_gif_url)
            await channel.send(embed=embed)
            
            # Add reaction to Tupper message (or original if not using Tupper)
            asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "✅"))
            
            # Delete the counter window message if exists
            if hasattr(self, 'counter_messages') and user_id in self.counter_messages:
                try:
                    await self.counter_messages[user_id].delete()
                    del self.counter_messages[user_id]
                except:
                    pass
            
            # Console output
            console.print(Panel.fit(
                f"[bold gold1]⚡💥 COUNTER ATTACK! 💥⚡[/bold gold1]\n"
                f"[cyan]{message.author.display_name}[/cyan] landed a counter!\n"
                f"[yellow]Damage: {counter_damage} | Enemy stunned for {stun_duration:.1f}s[/yellow]",
                border_style="gold1"
            ))
            
            self.save_all_data()
            
        except Exception as e:
            console.print(f"[red]✗ Error in counter attack handler: {e}[/red]")
            log.error(f"Counter attack error: {e}")


    async def update_player_stats(self, user_id, action, success, response_time):
        """Update player statistics"""
        try:
            if user_id not in self.player_stats:
                self.player_stats[user_id] = {
                    'total_attempts': 0,
                    'successful': 0,
                    'failed': 0,
                    'evades': 0,
                    'parries': 0,
                    'saves': 0,
                    'best_time': float('inf'),
                    'avg_time': 0,
                    'times': [],
                    'current_streak': 0,
                    'best_streak': 0,
                    'parry_streak': 0,
                    'best_parry_streak': 0,
                    'black_flash_chance': self.black_flash_base_chance,
                    'black_flashes': 0
                }

            stats = self.player_stats[user_id]
            stats['total_attempts'] += 1

            if success:
                stats['successful'] += 1
                stats['current_streak'] += 1
                stats['best_streak'] = max(stats['best_streak'], stats['current_streak'])
            else:
                stats['failed'] += 1
                stats['current_streak'] = 0

            if action == 'evade':
                stats['evades'] += 1
                # Reset parry streak on evade
                stats['parry_streak'] = stats.get('parry_streak', 0)
            elif action == 'parry':
                stats['parries'] += 1
                if success:
                    stats['parry_streak'] = stats.get('parry_streak', 0) + 1
                    stats['best_parry_streak'] = max(stats.get('best_parry_streak', 0), stats['parry_streak'])
                else:
                    stats['parry_streak'] = 0
            elif action == 'save':
                stats['saves'] += 1

            stats['times'].append(response_time)
            stats['best_time'] = min(stats['best_time'], response_time)
            stats['avg_time'] = sum(stats['times']) / len(stats['times'])

        except Exception as e:
            console.print(f"[red]✗ Error updating player stats: {e}[/red]")

    def setup_hotkeys(self):
        """Setup keyboard hotkeys from config (requires keyboard library and root on Linux)"""
        if not KEYBOARD_AVAILABLE:
            console.print("[yellow]⚠️  Cannot setup hotkeys - keyboard library not available[/yellow]")
            return
        # Load keybinds from config
        config_path = 'config.json'
        keybinds = {
            "single_easy": "f9",
            "single_medium": "f10",
            "single_hard": "f11",
            "single_impossible": "f12",
            "group_easy": "shift+f9",
            "group_medium": "shift+f10",
            "group_hard": "shift+f11",
            "group_impossible": "shift+f12",
            "checkpoint": "f8",
            "sync_commands": "f7"
        }
        
        # Try to load from config file
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if 'keybinds' in config:
                        keybinds.update(config['keybinds'])
                        console.print("[green]✓ Loaded keybinds from config.json[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠️ Could not load keybinds from config: {e}[/yellow]")
        
        def trigger_single_easy():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_single_qte('easy'), self.bot.loop)

        def trigger_single_medium():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_single_qte('medium'), self.bot.loop)

        def trigger_single_hard():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_single_qte('hard'), self.bot.loop)

        def trigger_single_impossible():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_single_qte('impossible'), self.bot.loop)

        def trigger_group_easy():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_group_qte('easy'), self.bot.loop)

        def trigger_group_medium():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_group_qte('medium'), self.bot.loop)

        def trigger_group_hard():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_group_qte('hard'), self.bot.loop)

        def trigger_group_impossible():
            if self.enemy_stunned and self.stun_end_time and time.time() < self.stun_end_time:
                console.print("[yellow]⚠️  Enemy is stunned! Wait...[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self.trigger_group_qte('impossible'), self.bot.loop)

        def trigger_checkpoint():
            checkpoint_name = f"Checkpoint {len(self.regen_checkpoints) + 1}"
            self.regen_checkpoints.append(checkpoint_name)
            asyncio.run_coroutine_threadsafe(self.trigger_checkpoint_heal(checkpoint_name), self.bot.loop)

        def sync_commands():
            asyncio.run_coroutine_threadsafe(self.force_sync_commands(), self.bot.loop)

        # Batch mode handlers (Ctrl+F9-F12 toggle batch collection)
        def toggle_batch_easy():
            if self.batch_mode_active:
                # Stop batch and process
                asyncio.run_coroutine_threadsafe(self.process_batch_qtes(), self.bot.loop)
            else:
                # Start batch mode
                self.batch_mode_active = True
                self.pending_qte_batch = []
                console.print(Panel.fit(
                    "[bold yellow]📦 BATCH MODE STARTED[/bold yellow]\n"
                    "[cyan]Press F9-F12 to queue QTEs, then Alt+F9 again to send[/cyan]",
                    border_style="yellow"
                ))
        
        def add_batch_easy():
            if self.batch_mode_active:
                self.pending_qte_batch.append({'difficulty': 'easy'})
                console.print(f"[green]+ Added EASY QTE to batch ({len(self.pending_qte_batch)} total)[/green]")
            else:
                trigger_single_easy()
        
        def add_batch_medium():
            if self.batch_mode_active:
                self.pending_qte_batch.append({'difficulty': 'medium'})
                console.print(f"[yellow]+ Added MEDIUM QTE to batch ({len(self.pending_qte_batch)} total)[/yellow]")
            else:
                trigger_single_medium()
        
        def add_batch_hard():
            if self.batch_mode_active:
                self.pending_qte_batch.append({'difficulty': 'hard'})
                console.print(f"[red]+ Added HARD QTE to batch ({len(self.pending_qte_batch)} total)[/red]")
            else:
                trigger_single_hard()
        
        def add_batch_impossible():
            if self.batch_mode_active:
                self.pending_qte_batch.append({'difficulty': 'impossible'})
                console.print(f"[magenta]+ Added IMPOSSIBLE QTE to batch ({len(self.pending_qte_batch)} total)[/magenta]")
            else:
                trigger_single_impossible()

        # Register hotkeys using config
        keyboard.add_hotkey(keybinds['single_easy'], add_batch_easy)
        keyboard.add_hotkey(keybinds['single_medium'], add_batch_medium)
        keyboard.add_hotkey(keybinds['single_hard'], add_batch_hard)
        keyboard.add_hotkey(keybinds['single_impossible'], add_batch_impossible)
        
        # Batch mode toggle (Alt+F9)
        keyboard.add_hotkey('alt+f9', toggle_batch_easy)

        keyboard.add_hotkey(keybinds['group_easy'], trigger_group_easy)
        keyboard.add_hotkey(keybinds['group_medium'], trigger_group_medium)
        keyboard.add_hotkey(keybinds['group_hard'], trigger_group_hard)
        keyboard.add_hotkey(keybinds['group_impossible'], trigger_group_impossible)
        
        keyboard.add_hotkey(keybinds['checkpoint'], trigger_checkpoint)
        keyboard.add_hotkey(keybinds['sync_commands'], sync_commands)

        # Display hotkeys in Rich format
        hotkey_table = Table(title="⌨ Hotkey Bindings", box=box.DOUBLE_EDGE, border_style="green")
        hotkey_table.add_column("Type", style="cyan")
        hotkey_table.add_column("Easy", style="green")
        hotkey_table.add_column("Medium", style="yellow")
        hotkey_table.add_column("Hard", style="red")
        hotkey_table.add_column("Impossible", style="magenta")

        hotkey_table.add_row("Single", keybinds['single_easy'], keybinds['single_medium'],
                            keybinds['single_hard'], keybinds['single_impossible'])
        hotkey_table.add_row("Group", keybinds['group_easy'], keybinds['group_medium'],
                            keybinds['group_hard'], keybinds['group_impossible'])
        hotkey_table.add_row("", "", "", "", "")
        hotkey_table.add_row("Batch Mode", "alt+f9 (Toggle batch on/off)", "", "", "")
        hotkey_table.add_row("Checkpoint", f"{keybinds['checkpoint']} (Heal all +30 HP)", "", "", "")
        hotkey_table.add_row("Sync Cmds", f"{keybinds['sync_commands']} (Force sync slash commands)", "", "", "")

        console.print(hotkey_table)

    async def force_sync_commands(self):
        """Force sync all slash commands"""
        try:
            synced_count = 0
            for guild in self.bot.guilds:
                self.bot.tree.clear_commands(guild=guild)
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
                synced_count += 1
                console.print(f"[green]✓ Force synced commands to {guild.name}[/green]")
            
            total = len(self.bot.tree.get_commands())
            console.print(Panel.fit(
                f"[bold green]✅ COMMANDS SYNCED[/bold green]\n"
                f"[cyan]{total} commands synced to {synced_count} guilds[/cyan]",
                border_style="green"
            ))
        except Exception as e:
            console.print(f"[red]✗ Error syncing commands: {e}[/red]")
            log.error(f"Force sync error: {e}")

    def run(self):
        """Start the bot"""
        try:
            console.print(Panel.fit(
                "[red bold]🚀 Starting Advanced QTE Bot...[/red bold]",
                border_style="cyan"
            ))
            self.bot.run(self.bot_token, log_handler=None)
        except Exception as e:
            console.print(f"[red]✗ Fatal error running bot: {e}[/red]")
        finally:
            self.save_all_data()
            console.print("[yellow]Bot shutdown complete[/yellow]")

if __name__ == "__main__":
    try:
        bot = AdvancedQTEBot()
        bot.run()
    except KeyboardInterrupt:
        console.print("[yellow]\nBot stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Fatal error: {e}[/red]")
