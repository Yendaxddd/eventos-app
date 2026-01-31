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
from typing import List
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

# Import Special Objects Manager
from special_objects_manager import SpecialObjectsManager, get_manager

# Ollama/AI imports
import aiohttp

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

# Setup logging with session rotation - each bot start gets a new log file
def setup_logging():
    """Setup logging with timestamped log file per session in central logs folder"""
    session_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Centralize logs under eventos-app/logs regardless of cwd
    project_root = pathlib.Path(__file__).resolve().parents[1]
    logs_dir = project_root / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fallback: write next to script if creation fails
        logs_dir = pathlib.Path(__file__).resolve().parent
    
    log_filename = logs_dir / f"qte_bot_{session_time}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        handlers=[
            logging.FileHandler(str(log_filename), encoding="utf-8", mode="w")
        ],
    )
    
    # Try to create/update symlink to latest log for convenience
    try:
        latest_link = logs_dir / "qte_bot.log"
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(log_filename.name)
    except Exception:
        pass  # Symlinks may fail on some systems
    
    return logging.getLogger("QTE_Bot"), str(log_filename)

log, LOG_FILENAME = setup_logging()
console.print(f"[cyan]📝 Logging to: {LOG_FILENAME}[/cyan]")

# Timing profiler for performance diagnostics
class TimingProfiler:
    """Track timing of operations for performance diagnostics"""
    def __init__(self):
        self.timings = {}  # {operation: [durations]}
        self.enabled = True
        self._start_times = {}  # {operation: start_time}
    
    def start(self, operation: str):
        if self.enabled:
            self._start_times[operation] = time.perf_counter()
    
    def stop(self, operation: str):
        if self.enabled and operation in self._start_times:
            duration = time.perf_counter() - self._start_times.pop(operation)
            if operation not in self.timings:
                self.timings[operation] = []
            self.timings[operation].append(duration)
            # Log slow operations (>500ms)
            if duration > 0.5:
                log.warning(f"SLOW: {operation} took {duration:.3f}s")
            return duration
        return 0
    
    def get_stats(self, operation: str = None):
        """Get timing statistics"""
        if operation:
            if operation in self.timings and self.timings[operation]:
                times = self.timings[operation]
                return {
                    'count': len(times),
                    'avg': sum(times) / len(times),
                    'min': min(times),
                    'max': max(times),
                    'total': sum(times)
                }
            return None
        return {op: self.get_stats(op) for op in self.timings}
    
    def clear(self):
        self.timings.clear()
        self._start_times.clear()
    
    def format_report(self):
        """Format a human-readable timing report"""
        lines = ["=== Timing Report ==="]
        stats = self.get_stats()
        for op, s in sorted(stats.items(), key=lambda x: x[1]['total'] if x[1] else 0, reverse=True):
            if s:
                lines.append(f"{op}: avg={s['avg']*1000:.1f}ms, max={s['max']*1000:.1f}ms, count={s['count']}, total={s['total']:.2f}s")
        return "\n".join(lines)

profiler = TimingProfiler()

# Persistence helpers
def resolve_data_dir():
    """Pick a writable data directory with a home fallback."""
    candidates = [
        pathlib.Path(__file__).parent / "data",
        pathlib.Path.home() / ".eventos-bot" / "data",
    ]

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".perm_check"
            test_file.write_text("ok", encoding="utf-8")
            try:
                test_file.unlink()
            except FileNotFoundError:
                pass
            log.info(f"Using data directory: {path}")
            return path
        except Exception as e:
            log.warning(f"Data directory not writable at {path}: {e}")
            continue

    # Fallback to last candidate even if unwritable so code still runs (will log errors on save)
    return candidates[-1]

DATA_DIR = resolve_data_dir()

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

        # Create assets directory for persistent storage
        self.assets_dir = "assets"
        if not os.path.exists(self.assets_dir):
            os.makedirs(self.assets_dir)
            console.print(f"[green]✓ Created assets directory[/green]")
        
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
        self.boss_defeat_gifs = load_data("boss_defeat_gifs", [])  # Boss defeat celebration GIFs (list)
        self.player_buffs = load_data("player_buffs", {})  # Active buffs: {user_id: {buff_type: {value, expires}}}

        console.print(f"[yellow]✓ Loaded {len(self.character_registry)} character registrations[/yellow]")
        console.print(f"[yellow]✓ Loaded stats for {len(self.player_stats)} players[/yellow]")
        console.print(f"[purple]✓ Loaded powers for {len(self.character_powers)} characters[/purple]")
        console.print(f"[purple]✓ Loaded charges for {len(self.power_charges)} players[/purple]")
        console.print(f"[purple]✓ Loaded counter GIFs for {len(self.user_counter_gifs)} players[/purple]")
        console.print(f"[gold1]✓ Loaded {len(self.boss_defeat_gifs)} boss defeat GIFs[/gold1]")

        # QTE State Management - Support multiple concurrent QTEs
        self.active_qtes = {}  # Dictionary: qte_id -> qte_data
        self.qte_counter = 0   # Counter for unique QTE IDs
        self.afk_users = set()
        self.last_qte_completion = {}  # {user_id: timestamp} for anti-spam
        self.hp_cleanup_needed = False  # If true, clear HP thread messages on startup
        self.reset_choice = None
        self.save_timestamps = {}  # {user_id: [list of timestamps]} - for save rate limiting
        self.save_limit = 2  # Max 2 saves per minute
        self.save_time_window = 60  # Per 60 seconds
        
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
        self.ultimate_max_damage = 500  # Cap: Maximum damage an ultimate can deal
        self.ultimate_base_cooldown = 600  # 10 minutes base cooldown (fight-time only)
        # =================================================
        
        # ========== FIGHT STATE SYSTEM ==========
        # Ultimate cooldowns only tick down during active boss fights!
        self.fight_active = False  # True when boss fight is in progress
        self.fight_start_time = None  # When the current fight started
        self.ultimate_fight_cooldowns = {}  # {user_id: {power_key: remaining_seconds}}
        # =========================================
        
        # ========== COUNTER MECHANIC ==========
        self.counter_enabled_players = {}  # {user_id: qte_id}
        self.counter_context = {}  # {user_id: {"qte_id": qte_id, "difficulty": difficulty}}
        self.counter_window = 1.5  # LOWERED: 1.5 seconds from QTE start (was 2.0)
        self.enemy_stunned = False
        self.stun_end_time = None
        self.counter_gif_dir = pathlib.Path("assets/counter_gifs")
        self.counter_streaks = {}  # {user_id: streak_count} - for stun scaling
        # ======================================
        
        # ========== BOSS DEFEAT ANIMATION ==========
        self.default_boss_defeat_gif = "https://media1.tenor.com/m/DQZQ0cXHkjgAAAAd/one-punch-man-saitama.gif"  # Default fallback
        # boss_defeat_gifs is loaded from file - list of custom GIFs
        # ===========================================
        
        # ========== BLACK FLASH CHAIN SYSTEM ==========
        self.bf_chain_active = {}  # {user_id: chain_count} - tracks active BF chains (max 4)
        self.bf_chain_damage = {1: 25, 2: 50, 3: 100, 4: 200}  # Damage per chain level
        self.bf_parry_cooldowns = {1: 10, 2: 30, 3: 60, 4: 120}  # Cooldowns in seconds after each BF
        self.bf_timing_window = 0.2  # First BF timing tolerance (tighter - 0.2s)
        self.bf_chain_timing_window = 0.15  # Subsequent chain BFs even tighter (0.15s)
        self.player_parry_cooldown = {}  # {user_id: timestamp} - parry locked until this time
        # ===============================================
        
        # ========== BATCHED HP UPDATE SYSTEM ==========
        # Instead of updating HP bar immediately on every damage event,
        # we batch updates and flush them periodically to reduce rate limits
        self._pending_hp_updates = {}  # {cache_key: embed} - pending updates
        self._hp_update_task = None  # Background task for flushing
        self._hp_update_interval = 2.0  # Flush every 2 seconds (reduced from 0.5s for rate limits)
        # ===============================================
        
        # ========== GLOBAL MESSAGE QUEUE SYSTEM ==========
        # Throttle all outgoing messages to prevent rate limits
        self._message_queue = asyncio.Queue()  # Global message queue
        self._message_processor_task = None  # Background task for processing
        self._min_message_interval = 0.15  # Minimum 150ms between messages per channel
        self._channel_last_send = {}  # {channel_id: timestamp} - track last send per channel
        self._rate_limit_backoff = {}  # {channel_id: backoff_multiplier} - exponential backoff
        # =================================================
        
        # ========== QTE BATCH MODE ==========
        self.batch_mode_active = False
        self.pending_qte_batch = []  # List of {'difficulty': str} during batch collection
        self.player_qte_queues = {}  # {user_id: [list of qte dicts]} - sequential processing
        self.player_current_qte = {}  # {user_id: qte_data} - currently active QTE per player
        
        # ========== AI/OLLAMA INTEGRATION ==========
        self.ai_enabled = False  # Master toggle
        self.ai_endpoint = "http://localhost:11434/api/generate"
        self.ai_model = "dolphin-phi:2.7b"
        self.ai_channel_id = None  # If set, only respond in this channel
        self.ai_message_counter = {}  # {channel_id: count} - tracks messages since last AI response
        self.ai_trigger_count = 10  # Respond after this many messages
        self.ai_respond_to_pins = True  # Respond when message is pinned
        self.ai_system_prompt = "You are a helpful assistant in a Discord server focused on roleplaying and QTE combat. Keep responses brief and engaging."
        self.ai_last_response = {}  # {channel_id: timestamp} - cooldown per channel
        self.ai_cooldown = 30  # Seconds between auto-responses
        # =============================================
        # ====================================
        
        # ========== MAX ADAPTATION WARNING TRACKING ==========
        # Track users who have been warned about max adaptation (prevent spam)
        self.max_adaptation_warned = {}  # {user_id: {obj_id: {difficulty: bool}}}
        # ======================================================
        
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
        
        # ========== SPECIAL OBJECTS SYSTEM (Data-Driven Mechanics) ==========
        # Replaces hardcoded adaptation mechanics with JSON-defined objects
        self.special_objects_manager = get_manager()
        obj_count, obj_errors = self.special_objects_manager.load_all()
        self.special_objects_manager.load_tracking()
        console.print(f"[purple]✓ Loaded {obj_count} special objects[/purple]")
        if obj_errors:
            for err in obj_errors:
                console.print(f"[red]  ✗ {err}[/red]")
        # ====================================================================
        
        # ========== BLOCK MECHANIC ==========
        # *block* reduces damage but doesn't negate it completely
        self.block_damage_reduction = 0.50  # 50% damage reduction on successful block
        self.block_window_multiplier = 1.5  # Block window is 50% wider than evade
        self.block_cooldown = {}  # {user_id: timestamp} - block cooldown per player
        self.block_cooldown_duration = 3.0  # 3 seconds between blocks
        # =====================================
        
        # ========== BOSS DEFEAT SYSTEM ==========
        self.boss_defeat_gifs = [
            "https://media.tenor.com/your-boss-defeat-gif-1.gif",  # Placeholder
            "https://media.tenor.com/your-boss-defeat-gif-2.gif"   # Placeholder
        ]
        self.boss_defeat_messages = [
            "The tyrant falls... their reign ends here.",
            "Victory! The darkness recedes...",
            "Against all odds, the hero prevails!",
            "The beast is slain. Rest now, warrior."
        ]
        # =========================================

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

        # Load custom QTE settings if they exist
        self.load_qte_settings()

        # Prompt once on startup: keep or reset HP/charges
        self.reset_choice = self.prompt_reset_hp_and_charges()
        if self.reset_choice == "reset":
            console.print("[yellow]⚠️  Resetting HP, power charges, and buffs on startup[/yellow]")
            self.player_hp = {}
            self.power_charges = {}
            self.player_buffs = {}
            self.hp_cleanup_needed = True
            self.save_all_data(force=True)
        else:
            console.print("[green]Keeping existing HP and charges[/green]")

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
        save_data("boss_defeat_gifs", self.boss_defeat_gifs)  # Boss defeat celebration GIFs
        save_data("player_buffs", self.player_buffs)  # Active buffs
        
        # Save special objects tracking data
        self.special_objects_manager.save_tracking()
        
        self._last_save_time = current_time
        self._pending_save = False
        console.print("[green]💾 Data saved to disk[/green]")
    
    async def periodic_save(self):
        """Periodically save pending data - call from event loop"""
        if self._pending_save:
            self.save_all_data(force=True)

    # ========== AI/OLLAMA INTEGRATION METHODS ==========
    
    async def ollama_list_models(self) -> list:
        """Get list of available models from Ollama"""
        try:
            # Ollama API endpoint for listing models
            list_url = self.ai_endpoint.replace("/api/generate", "/api/tags")
            async with aiohttp.ClientSession() as session:
                async with session.get(list_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get('models', [])
                        return [m.get('name', 'unknown') for m in models]
                    else:
                        console.print(f"[red]❌ Failed to list models: {resp.status}[/red]")
                        return []
        except Exception as e:
            console.print(f"[red]❌ Error listing models: {e}[/red]")
            return []
    
    async def ollama_load_model(self, model_name: str) -> bool:
        """Load/pull a model in Ollama (makes it ready for use)"""
        try:
            # Send a simple request to load the model into memory
            payload = {
                "model": model_name,
                "prompt": "",  # Empty prompt just loads the model
                "stream": False,
                "options": {"num_predict": 1}  # Minimal generation
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.ai_endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        console.print(f"[green]✅ Model {model_name} loaded[/green]")
                        return True
                    else:
                        error_text = await resp.text()
                        console.print(f"[red]❌ Failed to load model: {error_text}[/red]")
                        return False
        except Exception as e:
            console.print(f"[red]❌ Error loading model: {e}[/red]")
            return False
    
    async def ollama_unload_model(self, model_name: str) -> bool:
        """Unload a model from Ollama memory"""
        try:
            # Ollama uses keep_alive: 0 to unload immediately
            payload = {
                "model": model_name,
                "keep_alive": 0
            }
            unload_url = self.ai_endpoint.replace("/api/generate", "/api/generate")
            async with aiohttp.ClientSession() as session:
                async with session.post(unload_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        console.print(f"[yellow]📤 Model {model_name} unloaded from memory[/yellow]")
                        return True
                    else:
                        # Model might not be loaded, that's fine
                        return True
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not unload model (may not be loaded): {e}[/yellow]")
            return True  # Not critical if unload fails
    
    async def call_ollama(self, prompt: str, system_prompt: str = None) -> str:
        """Call Ollama API and return response text"""
        if system_prompt is None:
            system_prompt = self.ai_system_prompt
        
        payload = {
            "model": self.ai_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 300  # Limit response length
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.ai_endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('response', '').strip()
                    else:
                        error_text = await resp.text()
                        console.print(f"[red]❌ Ollama API error: {resp.status} - {error_text}[/red]")
                        return None
        except asyncio.TimeoutError:
            console.print("[red]❌ Ollama request timed out[/red]")
            return None
        except aiohttp.ClientError as e:
            console.print(f"[red]❌ Ollama connection error: {e}[/red]")
            return None
        except Exception as e:
            console.print(f"[red]❌ Ollama error: {e}[/red]")
            return None
    
    async def handle_ai_prompt(self, message, prompt: str):
        """Handle direct AI prompt (-- prefix)"""
        async with message.channel.typing():
            console.print(f"[cyan]🤖 AI prompt from {message.author.name}: {prompt[:50]}...[/cyan]")
            
            response = await self.call_ollama(prompt)
            
            if response:
                # Truncate if too long for Discord
                if len(response) > 1900:
                    response = response[:1900] + "..."
                
                await message.reply(response, mention_author=False)
                console.print(f"[green]✓ AI responded ({len(response)} chars)[/green]")
            else:
                await message.reply("❌ Sorry, I couldn't generate a response. Is Ollama running?", mention_author=False)
    
    async def get_channel_context(self, channel, limit: int = 5) -> str:
        """Get recent messages from channel as context"""
        messages = []
        async for msg in channel.history(limit=limit):
            if not msg.author.bot:
                messages.append(f"{msg.author.display_name}: {msg.content[:100]}")
        messages.reverse()  # Oldest first
        return "\n".join(messages)
    
    async def handle_ai_auto_response(self, channel, context: str):
        """Generate automatic AI response based on channel context"""
        try:
            prompt = f"""Based on this recent conversation in a Discord server, provide a brief, natural response or comment. Don't repeat what others said. Be engaging but concise.

Recent messages:
{context}

Your response (1-2 sentences max):"""
            
            async with channel.typing():
                response = await self.call_ollama(prompt)
                
                if response:
                    if len(response) > 500:
                        response = response[:500] + "..."
                    
                    await channel.send(f"🤖 {response}")
                    self.ai_last_response[channel.id] = time.time()
                    console.print(f"[cyan]🤖 AI auto-response in #{channel.name}[/cyan]")
        except Exception as e:
            console.print(f"[red]❌ AI auto-response error: {e}[/red]")
    
    # ========== END AI INTEGRATION ==========

    async def cleanup_hp_thread_messages(self):
        """Delete all messages in the HP bar thread when resetting data"""
        if not self.hp_bar_thread_id:
            return
        channel = self.bot.get_channel(self.hp_bar_thread_id)
        if not channel:
            return
        try:
            await channel.purge(limit=None)
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not purge HP thread: {e}[/yellow]")

    # ========== RATE-LIMITED MESSAGING ==========
    
    def save_qte_settings(self):
        """Save QTE timing and damage settings to JSON"""
        settings = {
            'qte_times': self.qte_times,
            'damage_ranges': self.damage_ranges
        }
        save_data("qte_settings", settings)
        console.print("[green]💾 QTE settings saved[/green]")
    
    def load_qte_settings(self):
        """Load QTE timing and damage settings from JSON"""
        settings = load_data("qte_settings", {})
        if settings:
            if 'qte_times' in settings:
                # Merge with defaults (in case new difficulties added)
                for diff, timing in settings['qte_times'].items():
                    if diff in self.qte_times:
                        self.qte_times[diff] = timing
                        # Convert parry_window list to tuple if needed
                        if isinstance(self.qte_times[diff]['parry_window'], list):
                            self.qte_times[diff]['parry_window'] = tuple(self.qte_times[diff]['parry_window'])
            if 'damage_ranges' in settings:
                for diff, dmg in settings['damage_ranges'].items():
                    if diff in self.damage_ranges:
                        # Convert list to tuple if needed
                        self.damage_ranges[diff] = tuple(dmg) if isinstance(dmg, list) else dmg
            console.print("[cyan]✓ Loaded custom QTE settings[/cyan]")

    def prompt_reset_hp_and_charges(self):
        """Ask operator whether to keep HP/charges or reset on startup"""
        try:
            choice = input("Keep existing HP/charges? (Y/n): ").strip().lower()
            if choice in ("n", "no"):  # reset
                return "reset"
        except Exception:
            pass
        return "keep"
    
    async def download_and_store_asset(self, url, asset_type, identifier):
        """Download image from URL and store locally. Returns local file path or URL if download fails"""
        try:
            import aiohttp
            import hashlib
            
            # Create type subdirectory
            type_dir = os.path.join(self.assets_dir, asset_type)
            if not os.path.exists(type_dir):
                os.makedirs(type_dir)
            
            # Generate filename from URL hash + identifier
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            file_ext = '.gif' if 'gif' in url.lower() else '.png'
            filename = f"{identifier}_{url_hash}{file_ext}"
            filepath = os.path.join(type_dir, filename)
            
            # If already downloaded, return local path
            if os.path.exists(filepath):
                return filepath
            
            # Download the file
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        with open(filepath, 'wb') as f:
                            f.write(await resp.read())
                        console.print(f"[green]✓ Downloaded asset: {filename}[/green]")
                        return filepath
        except Exception as e:
            console.print(f"[yellow]⚠ Failed to download asset from {url}: {e}[/yellow]")
        
        # Return original URL if download fails
        return url
    
    def get_local_asset_url(self, filepath):
        """Convert local file path to Discord-compatible URL path"""
        # For now, just return the filepath - in production, you'd host these or embed them
        return filepath
    
    async def webhook_send(self, content=None, embed=None, file=None):
        """Send message to QTE channel with rate limit protection"""
        profiler.start('webhook_send')
        try:
            channel = self.bot.get_channel(self.qte_channel_id)
            if channel:
                # Use safe_send for rate limit protection (but pass file separately if needed)
                if file:
                    # Direct send for files (safe_send doesn't handle files)
                    result = await channel.send(content=content, embed=embed, file=file)
                else:
                    result = await self.safe_send(channel, content=content, embed=embed)
                profiler.stop('webhook_send')
                return result
            profiler.stop('webhook_send')
            return None
        except Exception as e:
            profiler.stop('webhook_send')
            console.print(f"[red]✗ Error sending message: {e}[/red]")
            return None

    async def safe_send(self, channel, content=None, embed=None, priority=False, use_webhook=True):
        """Send a message with rate limit protection and exponential backoff."""
        if channel is None:
            return None
        
        profiler.start('safe_send')
        channel_id = channel.id
        
        # Check minimum interval between sends to this channel
        now = time.time()
        last_send = self._channel_last_send.get(channel_id, 0)
        backoff = self._rate_limit_backoff.get(channel_id, 1.0)
        min_wait = self._min_message_interval * backoff
        
        if now - last_send < min_wait:
            await asyncio.sleep(min_wait - (now - last_send))
        
        max_retries = 4
        for attempt in range(max_retries):
            try:
                result = await channel.send(content=content, embed=embed)
                self._channel_last_send[channel_id] = time.time()
                # Reduce backoff on success (slowly return to normal)
                if channel_id in self._rate_limit_backoff:
                    self._rate_limit_backoff[channel_id] = max(1.0, self._rate_limit_backoff[channel_id] * 0.9)
                profiler.stop('safe_send')
                return result
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 1.0 * (2 ** attempt))
                    # Increase backoff for this channel
                    self._rate_limit_backoff[channel_id] = min(8.0, backoff * 2)
                    log.warning(f"Rate limited (attempt {attempt+1}/{max_retries}), waiting {retry_after:.1f}s, backoff now {self._rate_limit_backoff[channel_id]}x")
                    await asyncio.sleep(retry_after)
                else:
                    profiler.stop('safe_send')
                    return None
            except Exception as e:
                profiler.stop('safe_send')
                log.error(f"Error sending message: {e}")
                return None
        
        profiler.stop('safe_send')
        log.error(f"Failed to send message after {max_retries} retries")
        return None
    
    async def safe_add_reaction(self, message, emoji):
        """Add a reaction with rate limit protection and exponential backoff"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await message.add_reaction(emoji)
                return True
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 0.5 * (2 ** attempt))
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_after)
                else:
                    return False
            except:
                return False
        return False
    
    async def safe_edit_message(self, message, content=None, embed=None):
        """Edit a message with rate limit protection and exponential backoff"""
        if message is None:
            return None
        
        channel_id = message.channel.id
        backoff = self._rate_limit_backoff.get(channel_id, 1.0)
        
        max_retries = 4
        for attempt in range(max_retries):
            try:
                result = await message.edit(content=content, embed=embed)
                # Reduce backoff on success
                if channel_id in self._rate_limit_backoff:
                    self._rate_limit_backoff[channel_id] = max(1.0, self._rate_limit_backoff[channel_id] * 0.9)
                return result
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 1.0 * (2 ** attempt))
                    self._rate_limit_backoff[channel_id] = min(8.0, backoff * 2)
                    log.warning(f"Rate limited on edit (attempt {attempt+1}/{max_retries}), waiting {retry_after:.1f}s")
                    await asyncio.sleep(retry_after)
                else:
                    return None
            except Exception as e:
                log.error(f"Error editing message: {e}")
                return None
        return None
    
    async def safe_delete_message(self, message):
        """Delete a message with rate limit protection"""
        if message is None:
            return False
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await message.delete()
                return True
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, 'retry_after', 0.5 * (2 ** attempt))
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_after)
                elif e.status == 404:
                    return True  # Already deleted
                else:
                    return False
            except:
                return False
        return False
    # =============================================

    async def persist_attachment(self, attachment: discord.Attachment) -> str:
        """
        Re-upload an attachment to get a permanent Discord CDN URL AND download locally for persistence.
        Discord slash command attachment URLs expire, but message attachment URLs are permanent.
        We also store locally as backup.
        
        Returns the permanent URL or the original URL if re-upload fails.
        """
        try:
            # Download the attachment data
            image_data = await attachment.read()
            
            # Get the QTE channel to upload to
            channel = self.bot.get_channel(self.qte_channel_id)
            if not channel:
                console.print("[yellow]⚠️ Could not get channel for image persistence, using temporary URL[/yellow]")
                return attachment.url
            
            # Create a discord.File from the data
            import io
            file = discord.File(io.BytesIO(image_data), filename=attachment.filename)
            
            # Also save locally as backup
            local_path = await self.download_and_store_asset(
                attachment.url, 
                "counter_gifs",
                attachment.filename.split('.')[0]
            )
            console.print(f"[green]✓ Asset backed up locally: {local_path}[/green]")
            
            # Send a message with the file for persistence (direct send, no webhook)
            try:
                msg = await channel.send(
                    content="📁 (Image storage - ignore)",
                    file=file
                )
                
                # Get the permanent URL from the attachment
                if msg.attachments:
                    permanent_url = msg.attachments[0].url
                    
                    # DON'T delete the storage message - Discord CDN URLs expire when the message is deleted!
                    # The message will stay in the channel but be hidden among normal messages
                    console.print(f"[green]✓ Image persisted: {attachment.filename}[/green]")
                    return permanent_url
            except:
                pass
            
            # Fallback: return original URL
            console.print("[yellow]⚠️ Could not persist image, using temporary URL[/yellow]")
            return attachment.url
            
        except Exception as e:
            log.error(f"Error persisting attachment: {e}")
            return attachment.url

    def check_black_flash(self, user_id, response_time, difficulty, is_chain=False):
        """Check if a black flash occurred - TIMING + RNG based (harder to get)"""
        # Get player's current stats
        if user_id not in self.player_stats:
            return False

        stats = self.player_stats[user_id]
        if 'black_flashes' not in stats:
            stats['black_flashes'] = 0

        # Get adjusted perfect timing if in REVENGE mode
        perfect_timing = self.get_adjusted_parry_center(difficulty, user_id)
        timing_deviation = abs(response_time - perfect_timing)

        # Use tighter timing for first BF (0.2s), even tighter for chains (0.15s base)
        base_window = self.bf_chain_timing_window if is_chain else self.bf_timing_window
        
        # REVENGE mode widens the window slightly
        timing_window = base_window
        if user_id in self.player_hp and self.player_hp[user_id].get("revenge_mode", False):
            timing_window += 0.05  # +0.05s forgiveness in revenge mode (reduced from 0.1)
        
        # STEP 1: Check if within timing window (MUST be close to perfect)
        if timing_deviation > timing_window:
            return False  # Not even close enough to roll
        
        # STEP 2: RNG roll using player's luck modifier (timing qualifies, now roll for it!)
        bf_chance = stats.get('black_flash_chance', self.black_flash_base_chance)
        
        # Add REVENGE bonus to chance
        if user_id in self.player_hp and self.player_hp[user_id].get("revenge_mode", False):
            bf_chance += self.revenge_bf_bonus
        
        # Add buff bonus
        bf_chance += self.get_bf_boost(user_id)
        
        # Roll the dice!
        if random.random() < bf_chance:
            # BLACK FLASH! Timing + Luck aligned!
            stats['black_flashes'] += 1
            self.session_stats['black_flashes_today'] += 1
            
            # Increase luck for next time (capped)
            if stats.get('black_flash_chance', 0) < self.black_flash_cap:
                stats['black_flash_chance'] = min(
                    stats.get('black_flash_chance', self.black_flash_base_chance) + self.black_flash_increment,
                    self.black_flash_cap
                )
            
            console.print(f"[bold magenta]⚡ BLACK FLASH! Timing: {timing_deviation:.3f}s, Chance: {bf_chance:.1%}[/bold magenta]")
            return True

        console.print(f"[dim]BF roll failed - Timing: {timing_deviation:.3f}s (good!), Chance: {bf_chance:.1%} (bad luck)[/dim]")
        return False

    def can_save_qte(self, user_id):
        """Check if player can perform a save (rate limited to 2 per minute)"""
        current_time = time.time()
        
        # Initialize timestamps list if first time
        if user_id not in self.save_timestamps:
            self.save_timestamps[user_id] = []
        
        # Remove timestamps older than the time window
        self.save_timestamps[user_id] = [
            ts for ts in self.save_timestamps[user_id] 
            if current_time - ts < self.save_time_window
        ]
        
        # Check if at limit
        if len(self.save_timestamps[user_id]) >= self.save_limit:
            return False
        
        # Add current timestamp and return True
        self.save_timestamps[user_id].append(current_time)
        return True
    
    async def trigger_bf_chain_qte(self, user_id, channel, member, difficulty, chain_level, origin_message=None):
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
            # Calculate perfect timing for display
            perfect_timing = self.get_adjusted_parry_center(difficulty, user_id)
            parry_min, parry_max = self.get_adjusted_parry_window(difficulty, user_id)
            
            embed = discord.Embed(
                title=f"⚡🔥 {chain_name} BLACK FLASH CHAIN! 🔥⚡",
                description=f"**{member.mention}** is in the zone!\n\n"
                           f"🎯 Land another `*parry*` for **{damage} DAMAGE!**\n"
                           f"⏱️ You have **3 seconds!**\n\n"
                           f"⭐ **AIM FOR {perfect_timing:.2f}s** ⭐\n"
                           f"📍 Window: {parry_min:.2f}s - {parry_max:.2f}s\n\n"
                           f"*No damage on miss - just chain ends!*",
                color=discord.Color.from_rgb(255, 0, 255)  # Hot pink
            )
            embed.set_image(url=self.black_flash_gif)  # Add BF GIF to chain announcement
            embed.set_footer(text=f"Chain {chain_level}/4 | ⭐=BF Window | Perfect ~{perfect_timing:.1f}s")
            await self.safe_send(channel, embed=embed)

            # React on the player's successful parry message to signal the new window
            if origin_message:
                asyncio.create_task(self.add_reaction_to_response(channel, user_id, origin_message, "⭐"))
            
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
                        await self.trigger_bf_chain_qte(user_id, channel, target, difficulty, chain_level + 1, origin_message=message)
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
                    # Show how close they were to the BF window
                    parry_indicator = self.get_parry_visual_indicator(response_time, difficulty, user_id)
                    timing_feedback = self.get_parry_timing_feedback(response_time, difficulty, user_id)
                    
                    cooldown_seconds = self.bf_parry_cooldowns.get(chain_level, 10)
                    self.player_parry_cooldown[user_id] = time.time() + cooldown_seconds
                    
                    if user_id in self.bf_chain_active:
                        del self.bf_chain_active[user_id]
                    
                    self.active_qtes.pop(qte_id, None)
                    
                    await self.webhook_send(
                        content=f"{parry_indicator} {message.author.mention} **parried [{timing_feedback}] but no Black Flash!** Chain ends.\n"
                        f"Parry cooldown: **{cooldown_seconds}s**"
                    )
                    console.print(f"[yellow]⚔ BF Chain ended (no flash, {timing_feedback}) - {message.author.name}[/yellow]")
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

            # If reset was requested, clear HP thread messages once
            if self.hp_cleanup_needed:
                await self.cleanup_hp_thread_messages()
                console.print("[yellow]✓ HP thread cleared and data reset[/yellow]")
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
            
            content = message.content
            content_lower = content.lower()
            
            # ========== AI PROMPT HANDLING (-- prefix) ==========
            if content.startswith('--') and len(content) > 2:
                prompt = content[2:].strip()
                if prompt and self.ai_enabled:
                    await self.handle_ai_prompt(message, prompt)
                    return
                elif prompt and not self.ai_enabled:
                    await message.reply("❌ AI is currently disabled. Use `/ai enable:True` to enable it.", mention_author=False)
                    return
            
            # ========== AI MESSAGE COUNTER (auto-respond) ==========
            if self.ai_enabled and message.channel.id:
                channel_id = message.channel.id
                # Only track in AI channel if set, otherwise track everywhere
                if self.ai_channel_id is None or channel_id == self.ai_channel_id:
                    self.ai_message_counter[channel_id] = self.ai_message_counter.get(channel_id, 0) + 1
                    
                    # Check if we should auto-respond
                    if self.ai_message_counter[channel_id] >= self.ai_trigger_count:
                        # Check cooldown
                        last_response = self.ai_last_response.get(channel_id, 0)
                        if time.time() - last_response >= self.ai_cooldown:
                            # Get recent context
                            context = await self.get_channel_context(message.channel, limit=5)
                            await self.handle_ai_auto_response(message.channel, context)
                            self.ai_message_counter[channel_id] = 0

            # Handle *attack* counter command
            if '*attack*' in content_lower:
                await self.handle_counter_attack(message)
                return
            
            # Handle *adapt* during counter window (allows adapt while counter is enabled)
            if '*adapt*' in content_lower:
                await self.handle_adapt_command(message)
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
        # ========== AI CONFIGURATION COMMAND ==========
        @self.bot.tree.command(
            name="ai",
            description="[ADMIN] Configure AI/Ollama integration"
        )
        @app_commands.describe(
            enable="Enable or disable AI features",
            channel="Restrict AI to this channel only (leave empty for all channels)",
            trigger_count="Number of messages before auto-response (0 to disable)",
            cooldown="Seconds between auto-responses",
            model="Ollama model name (default: dolphin-phi:2.7b)"
        )
        async def ai_config_command(
            interaction: discord.Interaction,
            enable: bool = None,
            channel: discord.TextChannel = None,
            trigger_count: int = None,
            cooldown: int = None,
            model: str = None
        ):
            # Check admin role
            if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            changes = []
            
            if enable is not None:
                self.ai_enabled = enable
                changes.append(f"**Enabled**: {enable}")
            
            if channel is not None:
                self.ai_channel_id = channel.id
                changes.append(f"**Channel**: {channel.mention}")
            elif channel == "":
                self.ai_channel_id = None
                changes.append("**Channel**: All channels")
            
            if trigger_count is not None:
                self.ai_trigger_count = max(0, trigger_count)
                changes.append(f"**Auto-trigger**: Every {trigger_count} messages" if trigger_count > 0 else "**Auto-trigger**: Disabled")
            
            if cooldown is not None:
                self.ai_cooldown = max(5, cooldown)
                changes.append(f"**Cooldown**: {cooldown}s")
            
            if model is not None:
                self.ai_model = model
                changes.append(f"**Model**: {model}")
            
            if not changes:
                # Show current settings
                embed = discord.Embed(
                    title="🤖 AI Configuration",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Enabled", value="✅ Yes" if self.ai_enabled else "❌ No", inline=True)
                embed.add_field(name="Model", value=f"`{self.ai_model}`", inline=True)
                embed.add_field(name="Endpoint", value=f"`{self.ai_endpoint}`", inline=True)
                embed.add_field(name="Channel", value=f"<#{self.ai_channel_id}>" if self.ai_channel_id else "All channels", inline=True)
                embed.add_field(name="Auto-trigger", value=f"Every {self.ai_trigger_count} messages" if self.ai_trigger_count > 0 else "Disabled", inline=True)
                embed.add_field(name="Cooldown", value=f"{self.ai_cooldown}s", inline=True)
                embed.set_footer(text="Use --your message to prompt the AI directly")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="🤖 AI Settings Updated",
                    description="\n".join(changes),
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                console.print(f"[cyan]🤖 AI config updated by {interaction.user.name}: {', '.join(changes)}[/cyan]")
        
        @self.bot.tree.command(
            name="aitest",
            description="Test AI connection with a simple prompt"
        )
        @app_commands.describe(prompt="Test prompt to send to the AI")
        async def aitest_command(interaction: discord.Interaction, prompt: str = "Hello, respond with a brief greeting."):
            await interaction.response.defer(ephemeral=True)
            
            response = await self.call_ollama(prompt)
            
            if response:
                embed = discord.Embed(
                    title="🤖 AI Test Successful!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Prompt", value=prompt[:200], inline=False)
                embed.add_field(name="Response", value=response[:1000] if len(response) <= 1000 else response[:1000] + "...", inline=False)
                embed.add_field(name="Model", value=self.ai_model, inline=True)
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ AI Test Failed",
                    description="Could not connect to Ollama.\n\nMake sure:\n• Ollama is running (`ollama serve`)\n• Model is loaded (`ollama run dolphin-phi:2.7b`)\n• Endpoint is correct",
                    color=discord.Color.red()
                )
                embed.add_field(name="Endpoint", value=f"`{self.ai_endpoint}`", inline=True)
                embed.add_field(name="Model", value=f"`{self.ai_model}`", inline=True)
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="aimodel",
            description="[ADMIN] List available AI models or switch to a different one"
        )
        @app_commands.describe(
            action="Action to perform",
            model_name="Model name to switch to (for 'switch' action)"
        )
        @app_commands.choices(action=[
            app_commands.Choice(name="List available models", value="list"),
            app_commands.Choice(name="Switch model", value="switch"),
            app_commands.Choice(name="Reload current model", value="reload"),
        ])
        async def aimodel_command(
            interaction: discord.Interaction, 
            action: str = "list",
            model_name: str = None
        ):
            # Check admin role
            if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            
            if action == "list":
                # List all available models
                models = await self.ollama_list_models()
                
                if not models:
                    embed = discord.Embed(
                        title="❌ No Models Found",
                        description="Could not retrieve model list.\n\nMake sure Ollama is running.",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Endpoint", value=f"`{self.ai_endpoint}`", inline=False)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="🤖 Available AI Models",
                    description=f"**{len(models)}** model(s) installed",
                    color=discord.Color.blue()
                )
                
                model_list = ""
                for m in models:
                    is_active = "✅ " if m == self.ai_model else "   "
                    model_list += f"{is_active}`{m}`\n"
                
                embed.add_field(name="Models", value=model_list or "None", inline=False)
                embed.add_field(name="Current Model", value=f"`{self.ai_model}`", inline=True)
                embed.set_footer(text="Use /aimodel action:Switch model_name:<name> to change")
                await interaction.followup.send(embed=embed, ephemeral=True)
            
            elif action == "switch":
                if not model_name:
                    await interaction.followup.send("❌ Please specify a model name to switch to!", ephemeral=True)
                    return
                
                # Check if model exists
                models = await self.ollama_list_models()
                if model_name not in models:
                    embed = discord.Embed(
                        title="❌ Model Not Found",
                        description=f"Model `{model_name}` is not installed.\n\nAvailable models:\n" + 
                                   "\n".join([f"• `{m}`" for m in models[:10]]),
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Install models with: ollama pull <model_name>")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                old_model = self.ai_model
                
                # Unload old model
                await interaction.followup.send(f"📤 Unloading `{old_model}`...", ephemeral=True)
                await self.ollama_unload_model(old_model)
                
                # Update model name
                self.ai_model = model_name
                
                # Load new model
                await interaction.edit_original_response(content=f"📥 Loading `{model_name}`...")
                success = await self.ollama_load_model(model_name)
                
                if success:
                    embed = discord.Embed(
                        title="✅ Model Switched!",
                        description=f"Successfully switched from `{old_model}` to `{model_name}`",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Previous", value=f"`{old_model}`", inline=True)
                    embed.add_field(name="Current", value=f"`{model_name}`", inline=True)
                    await interaction.edit_original_response(content=None, embed=embed)
                    console.print(f"[green]🤖 AI model switched: {old_model} → {model_name} by {interaction.user.name}[/green]")
                else:
                    # Revert on failure
                    self.ai_model = old_model
                    embed = discord.Embed(
                        title="❌ Model Switch Failed",
                        description=f"Could not load `{model_name}`. Reverted to `{old_model}`.",
                        color=discord.Color.red()
                    )
                    await interaction.edit_original_response(content=None, embed=embed)
            
            elif action == "reload":
                # Reload current model (unload then load)
                current = self.ai_model
                
                await interaction.followup.send(f"🔄 Reloading `{current}`...", ephemeral=True)
                await self.ollama_unload_model(current)
                
                await interaction.edit_original_response(content=f"📥 Loading `{current}`...")
                success = await self.ollama_load_model(current)
                
                if success:
                    embed = discord.Embed(
                        title="✅ Model Reloaded!",
                        description=f"Successfully reloaded `{current}`",
                        color=discord.Color.green()
                    )
                    await interaction.edit_original_response(content=None, embed=embed)
                    console.print(f"[green]🤖 AI model reloaded: {current} by {interaction.user.name}[/green]")
                else:
                    embed = discord.Embed(
                        title="⚠️ Reload May Have Failed",
                        description=f"Model `{current}` may not have loaded correctly. Try testing with `/aitest`.",
                        color=discord.Color.orange()
                    )
                    await interaction.edit_original_response(content=None, embed=embed)
        
        # ========== END AI COMMANDS ==========
        
        @self.bot.tree.command(
            name="timing",
            description="[ADMIN] Show performance timing report"
        )
        async def timing_command(interaction: discord.Interaction, clear: bool = False):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                    return
                
                if clear:
                    profiler.clear()
                    await interaction.response.send_message("🧹 Timing data cleared!", ephemeral=True)
                    return
                
                report = profiler.format_report()
                if len(report) > 1900:
                    # Split into chunks if too long
                    report = report[:1900] + "\n... (truncated)"
                
                embed = discord.Embed(
                    title="⏱️ Performance Timing Report",
                    description=f"```\n{report}\n```",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Log File", value=LOG_FILENAME, inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                log.error(f"Error in timing command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
        
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

        # ========== OBJECT CHARGES VIEW & MODAL ==========
        class ObjectChargesView(discord.ui.View):
            def __init__(self, bot_instance, target_user_id):
                super().__init__(timeout=300)
                self.bot_instance = bot_instance
                self.target_user_id = target_user_id
            
            def build_embed(self):
                """Build the embed showing object spins"""
                # Start with inventory-listed objects (use int key)
                inventory = list(self.bot_instance.special_objects_manager.player_inventory.get(self.target_user_id, []))
                # Include unique objects owned by this user
                owners_map = getattr(self.bot_instance.special_objects_manager, 'unique_object_owners', {})
                for obj_id, owner_id in owners_map.items():
                    if owner_id == self.target_user_id and obj_id not in inventory:
                        inventory.append(obj_id)
                
                embed = discord.Embed(
                    title="🔮 Object Charges (Adaptation Spins)",
                    description="Track your special object adaptation progress per difficulty.",
                    color=discord.Color.purple()
                )
                
                if not inventory:
                    embed.description = "No special objects found."
                    return embed
                
                for obj_id in inventory:
                    obj = self.bot_instance.special_objects_manager.objects.get(obj_id)
                    if not obj:
                        continue
                    
                    obj_name = obj.get('name', obj_id)
                    emoji = obj.get('display', {}).get('emoji', '🔮')
                    
                    # Check tracking type
                    tracking_config = obj.get('tracking', {})
                    tracking_type = tracking_config.get('type', 'per_difficulty') if isinstance(tracking_config, dict) else 'per_difficulty'
                    
                    spin_text = []
                    thresholds = obj.get('thresholds', [])
                    
                    if tracking_type == 'total':
                        # Total tracking - single counter
                        spins = self.bot_instance.special_objects_manager.get_tracking(self.target_user_id, obj_id, 'total')
                        if isinstance(thresholds, list) and thresholds:
                            max_threshold = max(t['spins'] for t in thresholds)
                            status = "✅ MAXED" if spins >= max_threshold else f"{spins}/{max_threshold}"
                            spin_text.append(f"**Total Spins**: {status}")
                        else:
                            spin_text.append(f"**Total Spins**: {spins}")
                    else:
                        # Per-difficulty tracking
                        for difficulty in ['easy', 'medium', 'hard', 'impossible']:
                            spins = self.bot_instance.special_objects_manager.get_tracking(self.target_user_id, obj_id, difficulty)
                            diff_thresholds = thresholds.get(difficulty, []) if isinstance(thresholds, dict) else []
                            
                            if diff_thresholds:
                                max_threshold = max(t['spins'] for t in diff_thresholds)
                                status = "✅" if spins >= max_threshold else f"{spins}/{max_threshold}"
                                spin_text.append(f"**{difficulty.capitalize()}**: {status}")
                            elif spins > 0:
                                spin_text.append(f"**{difficulty.capitalize()}**: {spins}")
                    
                    field_value = "\n".join(spin_text) if spin_text else "*No adaptation tracking*"
                    embed.add_field(name=f"{emoji} {obj_name}", value=field_value, inline=False)
                
                embed.set_footer(text="GMs can edit spins using the button below")
                return embed
            
            @discord.ui.button(label="✏️ Edit Spins (GM Only)", style=discord.ButtonStyle.danger, row=0)
            async def edit_spins_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Check if user is GM/admin
                if not interaction.user.guild_permissions.administrator:
                    await interaction.response.send_message("❌ Only GMs/Admins can edit object spins!", ephemeral=True)
                    return
                
                # Get inventory (use int key)
                inventory = self.bot_instance.special_objects_manager.player_inventory.get(self.target_user_id, [])
                
                if not inventory:
                    await interaction.response.send_message("❌ This user has no special objects!", ephemeral=True)
                    return
                
                # For now, open modal for first object (TODO: add object selector)
                obj_id = inventory[0]
                modal = ObjectSpinsModal(self.bot_instance, self.target_user_id, obj_id)
                await interaction.response.send_modal(modal)
        
        class ObjectSpinsModal(discord.ui.Modal):
            def __init__(self, bot_instance, target_user_id, obj_id):
                super().__init__(title="Edit Object Spins")
                self.bot_instance = bot_instance
                self.target_user_id = target_user_id
                self.obj_id = obj_id
                
                obj = self.bot_instance.special_objects_manager.objects.get(obj_id)
                obj_name = obj.get('name', obj_id) if obj else obj_id
                
                # Check tracking type
                tracking_config = obj.get('tracking', {}) if obj else {}
                self.tracking_type = tracking_config.get('type', 'per_difficulty') if isinstance(tracking_config, dict) else 'per_difficulty'
                
                if self.tracking_type == 'total':
                    # Total tracking - single input
                    total_spins = self.bot_instance.special_objects_manager.get_tracking(
                        target_user_id, obj_id, 'total'
                    )
                    self.total_input = discord.ui.TextInput(
                        label=f"{obj_name} - Total Spins",
                        placeholder="Enter total number of spins",
                        default=str(total_spins),
                        required=True,
                        max_length=5
                    )
                    self.add_item(self.total_input)
                    self.easy_input = None
                    self.medium_input = None
                    self.hard_input = None
                    self.impossible_input = None
                else:
                    # Per-difficulty tracking
                    self.total_input = None
                    current_spins = {}
                    for difficulty in ['easy', 'medium', 'hard', 'impossible']:
                        current_spins[difficulty] = self.bot_instance.special_objects_manager.get_tracking(
                            target_user_id, obj_id, difficulty
                        )
                    
                    self.easy_input = discord.ui.TextInput(
                        label=f"{obj_name} - Easy Spins",
                        placeholder="Enter number of easy spins",
                        default=str(current_spins.get('easy', 0)),
                        required=True,
                        max_length=5
                    )
                    self.add_item(self.easy_input)
                    
                    self.medium_input = discord.ui.TextInput(
                        label=f"{obj_name} - Medium Spins",
                        placeholder="Enter number of medium spins",
                        default=str(current_spins.get('medium', 0)),
                        required=True,
                        max_length=5
                    )
                    self.add_item(self.medium_input)
                    
                    self.hard_input = discord.ui.TextInput(
                        label=f"{obj_name} - Hard Spins",
                        placeholder="Enter number of hard spins",
                        default=str(current_spins.get('hard', 0)),
                        required=True,
                        max_length=5
                    )
                    self.add_item(self.hard_input)
                    
                    self.impossible_input = discord.ui.TextInput(
                        label=f"{obj_name} - Impossible Spins",
                        placeholder="Enter number of impossible spins",
                        default=str(current_spins.get('impossible', 0)),
                        required=True,
                        max_length=5
                    )
                    self.add_item(self.impossible_input)
            
            async def on_submit(self, interaction: discord.Interaction):
                try:
                    obj = self.bot_instance.special_objects_manager.objects.get(self.obj_id)
                    obj_name = obj.get('name', self.obj_id) if obj else self.obj_id
                    
                    # Get target user
                    target_user = await interaction.guild.fetch_member(self.target_user_id)
                    target_name = target_user.display_name if target_user else f"User {self.target_user_id}"
                    
                    if self.tracking_type == 'total':
                        # Total tracking - single value
                        total_spins = int(self.total_input.value)
                        if total_spins < 0:
                            await interaction.response.send_message("❌ Spins must be non-negative!", ephemeral=True)
                            return
                        
                        self.bot_instance.special_objects_manager.set_tracking(
                            self.target_user_id, self.obj_id, 'total', total_spins
                        )
                        
                        # Save to file
                        self.bot_instance.special_objects_manager.save_tracking()
                        
                        embed = discord.Embed(
                            title="✅ Object Spins Updated",
                            description=f"Updated **{obj_name}** spins for **{target_name}**",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Total Spins", value=total_spins, inline=True)
                        
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        # Per-difficulty tracking
                        new_spins = {
                            'easy': int(self.easy_input.value),
                            'medium': int(self.medium_input.value),
                            'hard': int(self.hard_input.value),
                            'impossible': int(self.impossible_input.value)
                        }
                        
                        # Validate non-negative
                        for difficulty, spins in new_spins.items():
                            if spins < 0:
                                await interaction.response.send_message(f"❌ Spins must be non-negative! ({difficulty})", ephemeral=True)
                                return
                        
                        # Update tracking data
                        for difficulty, spins in new_spins.items():
                            self.bot_instance.special_objects_manager.set_tracking(
                                self.target_user_id, self.obj_id, difficulty, spins
                            )
                        
                        # Save to file
                        self.bot_instance.special_objects_manager.save_tracking()
                        
                        embed = discord.Embed(
                            title="✅ Object Spins Updated",
                            description=f"Updated **{obj_name}** spins for **{target_name}**",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Easy", value=new_spins['easy'], inline=True)
                        embed.add_field(name="Medium", value=new_spins['medium'], inline=True)
                        embed.add_field(name="Hard", value=new_spins['hard'], inline=True)
                        embed.add_field(name="Impossible", value=new_spins['impossible'], inline=True)
                        
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                except ValueError:
                    await interaction.response.send_message("❌ Invalid input! Please enter numbers only.", ephemeral=True)
                except Exception as e:
                    log.error(f"Error updating object spins: {e}")
                    await interaction.response.send_message(f"❌ Error updating spins: {e}", ephemeral=True)

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
            
            @discord.ui.button(label="🔮 Object Charges", style=discord.ButtonStyle.primary, row=0)
            async def object_charges_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                user_id = interaction.user.id
                
                # Get player's special objects from inventory (use int key)
                inventory = self.bot_instance.special_objects_manager.player_inventory.get(user_id, [])
                
                if not inventory:
                    embed = discord.Embed(
                        title="🔮 Object Charges",
                        description="You don't have any special objects yet!\n\nAsk a GM to grant you items with `/giveobject`.",
                        color=discord.Color.purple()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Show objects view with edit button for GMs
                view = ObjectChargesView(self.bot_instance, user_id)
                embed = view.build_embed()
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            @discord.ui.button(label="🎨 Counter Images", style=discord.ButtonStyle.secondary, row=1)
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
            app_commands.Choice(name="Saves", value="saves"),
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
                    elif category == "saves":
                        value = stats.get('saves', 0)
                        display = str(value)
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
                    "best_time": "⏱️ Best Response Time",
                    "saves": "🛡️ Total Saves"
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
                
                # ========== AUTO-START FIGHT ==========
                # Automatically start the fight when a boss is registered!
                self.fight_active = True
                self.fight_start_time = time.time()
                
                # Resume any paused ultimate cooldowns
                self._resume_ultimate_cooldowns()
                console.print(f"[green]⚔️ FIGHT STARTED - Ultimate cooldowns now ticking![/green]")
                # ======================================
                
                # Create boss embed
                embed = discord.Embed(
                    title=f"⚔️ BOSS FIGHT STARTED: {name}",
                    description=f"**HP**: {hp}\n**Status**: ⚔️ **FIGHT IN PROGRESS!**\n\n"
                               f"🔥 Ultimate cooldowns are now active!",
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
            name="targetqte",
            description="[ADMIN] Target a specific player with a QTE"
        )
        @app_commands.describe(
            player="The player to target",
            difficulty="QTE difficulty level"
        )
        @app_commands.choices(difficulty=[
            app_commands.Choice(name="Easy", value="easy"),
            app_commands.Choice(name="Medium", value="medium"),
            app_commands.Choice(name="Hard", value="hard"),
            app_commands.Choice(name="Impossible", value="impossible"),
        ])
        async def targetqte_command(interaction: discord.Interaction, player: discord.Member, difficulty: str):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                    return
                
                # Check if QTE channel is set
                channel = self.bot.get_channel(self.qte_channel_id)
                if not channel:
                    await interaction.response.send_message("❌ QTE channel not found!", ephemeral=True)
                    return
                
                # Trigger the QTE
                await interaction.response.send_message(
                    f"⚡ Targeting **{player.display_name}** with **{difficulty.upper()}** QTE!",
                    ephemeral=True
                )
                
                # Trigger targeted QTE for this specific player
                await self.trigger_single_qte(difficulty, target_member=player, is_targeted=True)
                
            except Exception as e:
                log.error(f"Error in targetqte command: {e}")
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        @self.bot.tree.command(
            name="editqte",
            description="[ADMIN] Edit QTE timing and damage values"
        )
        @app_commands.describe(
            difficulty="Which difficulty to edit",
            evade_window="Evade time window in seconds",
            parry_start="Parry window start time in seconds",
            parry_end="Parry window end time in seconds",
            perfect_parry="Perfect parry timing (for Black Flash)",
            damage_min="Minimum damage",
            damage_max="Maximum damage"
        )
        @app_commands.choices(difficulty=[
            app_commands.Choice(name="Easy", value="easy"),
            app_commands.Choice(name="Medium", value="medium"),
            app_commands.Choice(name="Hard", value="hard"),
            app_commands.Choice(name="Impossible", value="impossible"),
        ])
        async def editqte_command(
            interaction: discord.Interaction,
            difficulty: str,
            evade_window: float = None,
            parry_start: float = None,
            parry_end: float = None,
            perfect_parry: float = None,
            damage_min: int = None,
            damage_max: int = None
        ):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                    return
                
                changes = []
                
                # Update evade window
                if evade_window is not None and evade_window > 0:
                    old = self.qte_times[difficulty]['evade_window']
                    self.qte_times[difficulty]['evade_window'] = evade_window
                    changes.append(f"Evade window: {old}s → {evade_window}s")
                
                # Update parry window
                if parry_start is not None and parry_end is not None:
                    if parry_start >= parry_end:
                        await interaction.response.send_message("❌ Parry start must be less than parry end!", ephemeral=True)
                        return
                    old = self.qte_times[difficulty]['parry_window']
                    self.qte_times[difficulty]['parry_window'] = (parry_start, parry_end)
                    changes.append(f"Parry window: {old} → ({parry_start}, {parry_end})")
                elif parry_start is not None or parry_end is not None:
                    await interaction.response.send_message("❌ Must provide both parry_start and parry_end!", ephemeral=True)
                    return
                
                # Update perfect parry
                if perfect_parry is not None:
                    old = self.qte_times[difficulty]['perfect_parry']
                    self.qte_times[difficulty]['perfect_parry'] = perfect_parry
                    changes.append(f"Perfect parry: {old}s → {perfect_parry}s")
                
                # Update damage range
                if damage_min is not None and damage_max is not None:
                    if damage_min > damage_max:
                        await interaction.response.send_message("❌ Min damage must be ≤ max damage!", ephemeral=True)
                        return
                    old = self.damage_ranges[difficulty]
                    self.damage_ranges[difficulty] = (damage_min, damage_max)
                    changes.append(f"Damage: {old} → ({damage_min}, {damage_max})")
                elif damage_min is not None or damage_max is not None:
                    await interaction.response.send_message("❌ Must provide both damage_min and damage_max!", ephemeral=True)
                    return
                
                if changes:
                    # Save to JSON file
                    self.save_qte_settings()
                    
                    embed = discord.Embed(
                        title=f"⚡ QTE Settings Updated: {difficulty.upper()}",
                        description="\n".join(f"• {c}" for c in changes),
                        color=discord.Color.blue()
                    )
                    # Show current values
                    embed.add_field(
                        name="Current Settings",
                        value=f"**Evade Window:** {self.qte_times[difficulty]['evade_window']}s\n"
                              f"**Parry Window:** {self.qte_times[difficulty]['parry_window']}\n"
                              f"**Perfect Parry:** {self.qte_times[difficulty]['perfect_parry']}s\n"
                              f"**Damage:** {self.damage_ranges[difficulty]}",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed)
                else:
                    # Just show current values
                    embed = discord.Embed(
                        title=f"⚡ QTE Settings: {difficulty.upper()}",
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name="Timing",
                        value=f"**Evade Window:** {self.qte_times[difficulty]['evade_window']}s\n"
                              f"**Parry Window:** {self.qte_times[difficulty]['parry_window']}\n"
                              f"**Perfect Parry:** {self.qte_times[difficulty]['perfect_parry']}s",
                        inline=True
                    )
                    embed.add_field(
                        name="Damage",
                        value=f"**Range:** {self.damage_ranges[difficulty]}",
                        inline=True
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
            except Exception as e:
                log.error(f"Error in editqte command: {e}")
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
                # GM ONLY - command not finished
                if not self.is_admin(interaction.user):
                    await interaction.response.send_message("❌ This command is for GMs only (still in development).", ephemeral=True)
                    return
                
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

                # Acknowledge early to avoid unknown interaction errors
                deferred = False
                try:
                    await interaction.response.defer(ephemeral=True, thinking=True)
                    deferred = True
                except discord.NotFound:
                    log.error("setcountergif interaction expired before defer")
                    return
                except Exception as e:
                    log.warning(f"setcountergif defer failed: {e}")

                async def respond(**kwargs):
                    if deferred or interaction.response.is_done():
                        return await interaction.followup.send(**kwargs)
                    return await interaction.response.send_message(**kwargs)
                
                if action == "add":
                    if not image:
                        await respond(content="⚠️ Please upload an image to add!", ephemeral=True)
                        return
                    
                    # Validate it's an image/gif
                    if not image.content_type or not image.content_type.startswith(('image/', 'video/')):
                        await respond(content="⚠️ Please upload an image or GIF file!", ephemeral=True)
                        return
                    
                    # Persist the image to get a permanent URL
                    image_url = await self.persist_attachment(image)
                    
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
                    await respond(embed=embed)
                    console.print(f"[orange1]⚡ Counter image added for {interaction.user.display_name} (total: {count})[/orange1]")
                
                elif action == "clear":
                    if user_id in self.user_counter_gifs:
                        del self.user_counter_gifs[user_id]
                        self.save_all_data()
                    await respond(content="✅ All counter images cleared! Using default now.", ephemeral=True)
                
                elif action == "view":
                    gifs = self.user_counter_gifs.get(user_id, [])
                    if isinstance(gifs, str):
                        gifs = [gifs]
                    
                    if not gifs:
                        await respond(content="📭 No custom counter images set. Using default.", ephemeral=True)
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
                    await respond(embed=embed, ephemeral=True)
                    
            except Exception as e:
                log.error(f"Error in setcountergif command: {e}")
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send("❌ An error occurred.", ephemeral=True)
                    else:
                        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
                except Exception:
                    pass

        @self.bot.tree.command(
            name="bossdefeatgif",
            description="[ADMIN] Manage boss defeat celebration GIFs. Multiple GIFs will be randomized!"
        )
        @app_commands.describe(
            image="Upload a victory GIF/image to ADD to the collection.",
            action="Action to perform"
        )
        @app_commands.choices(action=[
            app_commands.Choice(name="Add GIF", value="add"),
            app_commands.Choice(name="Clear All", value="clear"),
            app_commands.Choice(name="View Collection", value="view"),
        ])
        async def bossdefeatgif_command(interaction: discord.Interaction, action: str = "add", image: discord.Attachment = None):
            try:
                # Check admin role
                if self.admin_role_id and self.admin_role_id not in [role.id for role in interaction.user.roles]:
                    await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
                    return
                
                if action == "add":
                    if not image:
                        await interaction.response.send_message("⚠️ Please attach an image or GIF to add!", ephemeral=True)
                        return
                    
                    # Validate it's an image/gif
                    if not image.content_type or not image.content_type.startswith(('image/', 'video/')):
                        await interaction.response.send_message("⚠️ Please upload an image or GIF file!", ephemeral=True)
                        return
                    
                    # Defer response since persisting might take a moment
                    await interaction.response.defer()
                    
                    # Persist the image to get a permanent URL
                    image_url = await self.persist_attachment(image)
                    
                    # Add to list
                    self.boss_defeat_gifs.append(image_url)
                    self.save_all_data()
                    
                    count = len(self.boss_defeat_gifs)
                    embed = discord.Embed(
                        title="🎉 Boss Defeat GIF Added!",
                        description=f"Collection now has **{count}** GIF(s)!\nThey will be randomized on boss defeat.",
                        color=discord.Color.gold()
                    )
                    embed.set_image(url=image_url)
                    await interaction.followup.send(embed=embed)
                    console.print(f"[gold1]🎉 Boss defeat GIF added (total: {count})[/gold1]")
                
                elif action == "clear":
                    self.boss_defeat_gifs.clear()
                    self.save_all_data()
                    await interaction.response.send_message("✅ All boss defeat GIFs cleared! Using default now.", ephemeral=True)
                    console.print("[yellow]Boss defeat GIFs cleared[/yellow]")
                
                elif action == "view":
                    gifs = self.boss_defeat_gifs
                    
                    if not gifs:
                        await interaction.response.send_message(
                            f"📭 No custom boss defeat GIFs set.\nUsing default: {self.default_boss_defeat_gif}", 
                            ephemeral=True
                        )
                        return
                    
                    embed = discord.Embed(
                        title="🏆 Boss Defeat GIF Collection",
                        description=f"**{len(gifs)}** GIF(s) in rotation",
                        color=discord.Color.gold()
                    )
                    for i, url in enumerate(gifs[:5], 1):  # Show first 5
                        embed.add_field(name=f"GIF {i}", value=f"[Link]({url})", inline=True)
                    if len(gifs) > 5:
                        embed.set_footer(text=f"... and {len(gifs) - 5} more")
                    embed.set_thumbnail(url=gifs[0])
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
            except Exception as e:
                log.error(f"Error in bossdefeatgif command: {e}")
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
        
        # ========== SPECIAL OBJECTS MANAGEMENT COMMANDS ==========
        
        @self.bot.tree.command(
            name="debuginventory",
            description="[ADMIN] Debug: Show raw inventory data for a player"
        )
        @app_commands.describe(player="Player to check (leave empty for self)")
        async def debuginventory_command(interaction: discord.Interaction, player: discord.Member = None):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            target = player or interaction.user
            user_id = target.id
            
            # Get raw inventory data
            raw_inv = self.special_objects_manager.player_inventory
            user_inv = raw_inv.get(user_id, None)
            
            # Get all keys to show type info
            all_keys = list(raw_inv.keys())[:10]  # First 10 keys
            
            embed = discord.Embed(
                title=f"🔧 Debug: Inventory for {target.display_name}",
                description=f"User ID: `{user_id}` (type: {type(user_id).__name__})",
                color=discord.Color.dark_grey()
            )
            
            embed.add_field(
                name="Raw Inventory Keys (first 10)",
                value="\n".join([f"`{k}` (type: {type(k).__name__})" for k in all_keys]) or "*Empty*",
                inline=False
            )
            
            embed.add_field(
                name=f"Lookup Result for user_id={user_id}",
                value=f"`{user_inv}`" if user_inv is not None else "*Not found / None*",
                inline=False
            )
            
            # Also check with str key
            str_inv = raw_inv.get(str(user_id), None)
            embed.add_field(
                name=f"Lookup Result for str({user_id})",
                value=f"`{str_inv}`" if str_inv is not None else "*Not found / None*",
                inline=False
            )
            
            # Show loaded objects count
            embed.add_field(
                name="Loaded Objects",
                value=f"{len(self.special_objects_manager.objects)} objects",
                inline=True
            )
            
            embed.add_field(
                name="Total Inventories",
                value=f"{len(raw_inv)} players",
                inline=True
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="listobjects",
            description="[ADMIN] List all approved special objects"
        )
        async def listobjects_command(interaction: discord.Interaction):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            objects = self.special_objects_manager.objects
            
            if not objects:
                await interaction.response.send_message("📦 No special objects loaded.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📦 Special Objects",
                description=f"**{len(objects)}** objects loaded",
                color=discord.Color.purple()
            )
            
            rarity_colors = {
                'common': '⬜', 'uncommon': '🟩', 'rare': '🟦',
                'epic': '🟪', 'legendary': '🟧', 'mythic': '🟥'
            }
            
            for obj_id, obj in objects.items():
                rarity = obj.get('rarity', 'common')
                emoji = obj.get('display', {}).get('emoji', rarity_colors.get(rarity, '📦'))
                unique_text = "👤 UNIQUE" if obj.get('unique', False) else ""
                owner_id = self.special_objects_manager.unique_object_owners.get(obj_id)
                owner_text = f"\nOwner: <@{owner_id}>" if owner_id else ""
                
                embed.add_field(
                    name=f"{emoji} {obj['name']}",
                    value=f"ID: `{obj_id}`\nType: {obj['type']} | {rarity.upper()} {unique_text}{owner_text}",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="listpending",
            description="[ADMIN] List special objects awaiting approval"
        )
        async def listpending_command(interaction: discord.Interaction):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            pending_files = list(self.special_objects_manager.pending_path.glob("*.json"))
            
            if not pending_files:
                await interaction.response.send_message("✅ No pending objects!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="⏳ Pending Special Objects",
                description=f"**{len(pending_files)}** objects awaiting review",
                color=discord.Color.orange()
            )
            
            for filepath in pending_files[:10]:  # Limit to 10
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    embed.add_field(
                        name=f"📄 {filepath.name}",
                        value=f"Name: {data.get('name', 'Unknown')}\nType: {data.get('type', 'Unknown')}",
                        inline=True
                    )
                except:
                    embed.add_field(name=f"📄 {filepath.name}", value="⚠️ Error reading file", inline=True)
            
            if len(pending_files) > 10:
                embed.set_footer(text=f"...and {len(pending_files) - 10} more")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="approveobject",
            description="[ADMIN] Approve a pending special object"
        )
        @app_commands.describe(filename="Filename of the object to approve (e.g., my_object.json)")
        async def approveobject_command(interaction: discord.Interaction, filename: str):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            success, message = self.special_objects_manager.approve_object(filename)
            
            if success:
                await interaction.response.send_message(f"✅ {message}")
                console.print(f"[green]✓ Special object approved: {filename}[/green]")
            else:
                await interaction.response.send_message(f"❌ {message}", ephemeral=True)
        
        @self.bot.tree.command(
            name="rejectobject",
            description="[ADMIN] Reject a pending special object"
        )
        @app_commands.describe(
            filename="Filename to reject",
            reason="Optional reason for rejection"
        )
        async def rejectobject_command(interaction: discord.Interaction, filename: str, reason: str = ""):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            success, message = self.special_objects_manager.reject_object(filename, reason)
            
            if success:
                await interaction.response.send_message(f"🗑️ {message}")
            else:
                await interaction.response.send_message(f"❌ {message}", ephemeral=True)
        
        @self.bot.tree.command(
            name="reloadobjects",
            description="[ADMIN] Hot-reload all special objects"
        )
        async def reloadobjects_command(interaction: discord.Interaction):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            count, errors = self.special_objects_manager.load_all()
            
            embed = discord.Embed(
                title="🔄 Special Objects Reloaded",
                description=f"Loaded **{count}** objects",
                color=discord.Color.green() if not errors else discord.Color.orange()
            )
            
            if errors:
                embed.add_field(
                    name="⚠️ Errors",
                    value="\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else ""),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            console.print(f"[cyan]🔄 Special objects reloaded: {count} loaded, {len(errors)} errors[/cyan]")
        
        @self.bot.tree.command(
            name="testobject",
            description="[ADMIN] Validate a pending object without approving"
        )
        @app_commands.describe(filename="Filename to test")
        async def testobject_command(interaction: discord.Interaction, filename: str):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            filepath = self.special_objects_manager.pending_path / filename
            if not filepath.exists():
                filepath = self.special_objects_manager.approved_path / filename
            
            if not filepath.exists():
                await interaction.response.send_message(f"❌ File not found: {filename}", ephemeral=True)
                return
            
            valid, errors, warnings = self.special_objects_manager.test_object(filepath)
            
            embed = discord.Embed(
                title=f"🧪 Test Results: {filename}",
                color=discord.Color.green() if valid else discord.Color.red()
            )
            embed.add_field(name="Status", value="✅ Valid" if valid else "❌ Invalid", inline=False)
            
            if errors:
                embed.add_field(name="❌ Errors", value="\n".join(f"• {e}" for e in errors[:5]), inline=False)
            
            if warnings:
                embed.add_field(name="⚠️ Warnings", value="\n".join(f"• {w}" for w in warnings[:5]), inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="checkadaptation",
            description="Check your or another player's adaptation progress"
        )
        @app_commands.describe(player="Player to check (leave empty for self)")
        async def checkadaptation_command(interaction: discord.Interaction, player: discord.Member = None):
            target = player or interaction.user
            user_id = target.id
            
            # Get objects from player's INVENTORY
            objects = self.special_objects_manager.get_player_inventory(user_id)
            adaptation_objects = [o for o in objects if o['type'] == 'adaptation']
            
            if not adaptation_objects:
                await interaction.response.send_message(
                    f"❌ {target.display_name} has no adaptation objects equipped.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title=f"🔄 Adaptation Progress: {target.display_name}",
                description=f"Objects with adaptation in inventory",
                color=discord.Color.purple()
            )
            
            for obj in adaptation_objects:
                obj_id = obj['id']
                tracking = self.special_objects_manager.get_all_tracking(user_id, obj_id)
                
                field_value = ""
                for difficulty in ['easy', 'medium', 'hard', 'impossible']:
                    spins = tracking.get(difficulty, 0)
                    # Pass empty list for character names since we use inventory now
                    reduction = self.special_objects_manager.get_damage_reduction(user_id, [], difficulty)
                    
                    # Find next threshold
                    thresholds = obj.get('thresholds', {}).get(difficulty, [])
                    next_threshold = None
                    for t in thresholds:
                        if t['spins'] > spins:
                            next_threshold = t['spins']
                            break
                    
                    next_text = f" (next: {next_threshold})" if next_threshold else " ✅"
                    field_value += f"**{difficulty.capitalize()}**: {spins} spins → {reduction:.0f}% reduction{next_text}\n"
                
                embed.add_field(
                    name=f"{obj.get('display', {}).get('emoji', '📦')} {obj['name']}",
                    value=field_value,
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # ========== INVENTORY MANAGEMENT COMMANDS ==========
        
        @self.bot.tree.command(
            name="gmobjects",
            description="[ADMIN] View and manage any player's object spins"
        )
        @app_commands.describe(player="The player to view/edit")
        async def gmobjects_command(interaction: discord.Interaction, player: discord.Member):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            user_id = player.id
            
            # Get inventory from both sources
            inventory = list(self.special_objects_manager.player_inventory.get(user_id, []))
            
            # Also check unique owners
            for obj_id, owner_id in self.special_objects_manager.unique_object_owners.items():
                if owner_id == user_id and obj_id not in inventory:
                    inventory.append(obj_id)
            
            if not inventory:
                await interaction.response.send_message(
                    f"❌ {player.mention} has no special objects!\n\nUse `/giveobject` to grant them one.",
                    ephemeral=True
                )
                return
            
            # Build embed showing all objects and their spins
            embed = discord.Embed(
                title=f"🔮 {player.display_name}'s Objects (GM View)",
                description=f"**{len(inventory)}** object(s) in inventory",
                color=discord.Color.purple()
            )
            
            for obj_id in inventory:
                obj = self.special_objects_manager.objects.get(obj_id)
                if not obj:
                    embed.add_field(name=f"❓ {obj_id}", value="*Object not found*", inline=False)
                    continue
                
                obj_name = obj.get('name', obj_id)
                emoji = obj.get('display', {}).get('emoji', '🔮')
                
                # Get tracking info
                tracking_config = obj.get('tracking', {})
                tracking_type = tracking_config.get('type', 'per_difficulty') if isinstance(tracking_config, dict) else 'per_difficulty'
                
                spins_info = []
                thresholds = obj.get('thresholds', [])
                
                if tracking_type == 'total':
                    spins = self.special_objects_manager.get_tracking(user_id, obj_id, 'total')
                    if isinstance(thresholds, list) and thresholds:
                        max_t = max(t['spins'] for t in thresholds)
                        status = "✅ MAXED" if spins >= max_t else f"{spins}/{max_t}"
                    else:
                        status = str(spins)
                    spins_info.append(f"**Total**: {status}")
                else:
                    for diff in ['easy', 'medium', 'hard', 'impossible']:
                        spins = self.special_objects_manager.get_tracking(user_id, obj_id, diff)
                        diff_ts = thresholds.get(diff, []) if isinstance(thresholds, dict) else []
                        if diff_ts:
                            max_t = max(t['spins'] for t in diff_ts)
                            status = "✅" if spins >= max_t else f"{spins}/{max_t}"
                        else:
                            status = str(spins)
                        spins_info.append(f"**{diff.capitalize()}**: {status}")
                
                embed.add_field(
                    name=f"{emoji} {obj_name} (`{obj_id}`)",
                    value="\n".join(spins_info),
                    inline=False
                )
            
            embed.set_footer(text="Use /setobjectspins to change values | /resetobjectspins to reset")
            
            # Show with ObjectChargesView for editing
            view = ObjectChargesView(self, user_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # Autocomplete function for object IDs
        async def object_id_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
            objects = self.special_objects_manager.objects
            choices = []
            for obj_id, obj in objects.items():
                if current.lower() in obj_id.lower() or current.lower() in obj['name'].lower():
                    display_name = f"{obj['name']} ({obj_id})"
                    choices.append(app_commands.Choice(name=display_name[:100], value=obj_id))
                if len(choices) >= 25:
                    break
            return choices
        
        @self.bot.tree.command(
            name="giveobject",
            description="[ADMIN] Give a special object to a player"
        )
        @app_commands.describe(
            player="The player to give the object to",
            object_id="The ID of the object (e.g., reactive_core)"
        )
        @app_commands.autocomplete(object_id=object_id_autocomplete)
        async def giveobject_command(interaction: discord.Interaction, player: discord.Member, object_id: str):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            success, message = self.special_objects_manager.give_object(player.id, object_id)
            
            if success:
                obj = self.special_objects_manager.objects.get(object_id, {})
                rarity = obj.get('rarity', 'common').upper()
                rarity_colors = {
                    'COMMON': '⬜', 'UNCOMMON': '🟩', 'RARE': '🟦',
                    'EPIC': '🟪', 'LEGENDARY': '🟧', 'MYTHIC': '🟥'
                }
                emoji = rarity_colors.get(rarity, '📦')
                
                embed = discord.Embed(
                    title=f"{emoji} Object Granted!",
                    description=f"**{obj.get('name', object_id)}** given to {player.mention}",
                    color=discord.Color.green()
                )
                embed.add_field(name="Rarity", value=rarity, inline=True)
                embed.add_field(name="Slots Used", value=str(obj.get('slots_required', 1)), inline=True)
                embed.add_field(
                    name="Player's Inventory",
                    value=f"{self.special_objects_manager.get_used_slots(player.id)}/{self.special_objects_manager.get_player_max_slots(player.id)} slots",
                    inline=True
                )
                
                if obj.get('image_url'):
                    embed.set_thumbnail(url=obj['image_url'])
                
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(f"❌ {message}", ephemeral=True)
        
        @self.bot.tree.command(
            name="takeobject",
            description="[ADMIN] Remove a special object from a player"
        )
        @app_commands.describe(
            player="The player to remove the object from",
            object_id="The ID of the object to remove"
        )
        @app_commands.autocomplete(object_id=object_id_autocomplete)
        async def takeobject_command(interaction: discord.Interaction, player: discord.Member, object_id: str):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            success, message = self.special_objects_manager.take_object(player.id, object_id)
            
            if success:
                await interaction.response.send_message(f"🗑️ {message} from {player.mention}")
            else:
                await interaction.response.send_message(f"❌ {message}", ephemeral=True)
        
        @self.bot.tree.command(
            name="inventory",
            description="View your special objects inventory or another player's"
        )
        @app_commands.describe(player="Player to check (leave empty for self)")
        async def inventory_command(interaction: discord.Interaction, player: discord.Member = None):
            target = player or interaction.user
            user_id = target.id
            
            inventory = self.special_objects_manager.get_player_inventory(user_id)
            used_slots = self.special_objects_manager.get_used_slots(user_id)
            max_slots = self.special_objects_manager.get_player_max_slots(user_id)
            
            embed = discord.Embed(
                title=f"🎒 {target.display_name}'s Inventory",
                description=f"**{used_slots}/{max_slots}** slots used",
                color=discord.Color.blue()
            )
            
            if not inventory:
                embed.add_field(name="Empty!", value="No objects in inventory.", inline=False)
            else:
                rarity_colors = {
                    'common': '⬜', 'uncommon': '🟩', 'rare': '🟦',
                    'epic': '🟪', 'legendary': '🟧', 'mythic': '🟥'
                }
                
                for obj in inventory:
                    rarity = obj.get('rarity', 'common')
                    emoji = obj.get('display', {}).get('emoji', rarity_colors.get(rarity, '📦'))
                    
                    value = f"**Rarity:** {rarity.capitalize()}\n"
                    value += f"**Slots:** {obj.get('slots_required', 1)}\n"
                    value += f"**Type:** {obj.get('type', 'unknown').capitalize()}\n"
                    if obj.get('description'):
                        value += f"*{obj['description'][:100]}...*" if len(obj.get('description', '')) > 100 else f"*{obj['description']}*"
                    
                    embed.add_field(
                        name=f"{emoji} {obj['name']}",
                        value=value,
                        inline=True
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="objectinfo",
            description="View detailed info about a special object"
        )
        @app_commands.describe(object_id="The ID of the object to view")
        @app_commands.autocomplete(object_id=object_id_autocomplete)
        async def objectinfo_command(interaction: discord.Interaction, object_id: str):
            obj = self.special_objects_manager.objects.get(object_id)
            
            if not obj:
                await interaction.response.send_message(f"❌ Object '{object_id}' not found.", ephemeral=True)
                return
            
            rarity = obj.get('rarity', 'common')
            rarity_colors_hex = {
                'common': 0xAAAAAA, 'uncommon': 0x1EFF00, 'rare': 0x0070DD,
                'epic': 0xA335EE, 'legendary': 0xFF8000, 'mythic': 0xFF0000
            }
            
            embed = discord.Embed(
                title=f"{obj.get('display', {}).get('emoji', '📦')} {obj['name']}",
                description=obj.get('description', 'No description'),
                color=rarity_colors_hex.get(rarity, 0x888888)
            )
            
            embed.add_field(name="ID", value=f"`{object_id}`", inline=True)
            embed.add_field(name="Type", value=obj.get('type', 'unknown').capitalize(), inline=True)
            embed.add_field(name="Rarity", value=rarity.upper(), inline=True)
            embed.add_field(name="Slots Required", value=str(obj.get('slots_required', 1)), inline=True)
            embed.add_field(name="Tradeable", value="Yes" if obj.get('tradeable', True) else "No", inline=True)
            embed.add_field(name="Unique", value="Yes" if obj.get('unique', False) else "No", inline=True)
            
            if obj.get('lore'):
                embed.add_field(name="📜 Lore", value=f"*{obj['lore']}*", inline=False)
            
            # Show who owns it if unique
            if obj.get('unique', False):
                owner_id = self.special_objects_manager.unique_object_owners.get(object_id)
                if owner_id:
                    embed.add_field(name="👤 Owner", value=f"<@{owner_id}>", inline=False)
                else:
                    embed.add_field(name="👤 Owner", value="*Unclaimed*", inline=False)
            
            if obj.get('image_url'):
                embed.set_image(url=obj['image_url'])
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="setobjectimage",
            description="[ADMIN] Set the image URL for a special object"
        )
        @app_commands.describe(
            object_id="The ID of the object",
            image_url="The URL of the image (or 'clear' to remove)"
        )
        @app_commands.autocomplete(object_id=object_id_autocomplete)
        async def setobjectimage_command(interaction: discord.Interaction, object_id: str, image_url: str):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            if object_id not in self.special_objects_manager.objects:
                await interaction.response.send_message(f"❌ Object '{object_id}' not found.", ephemeral=True)
                return
            
            # Update in memory
            if image_url.lower() == 'clear':
                self.special_objects_manager.objects[object_id]['image_url'] = None
            else:
                self.special_objects_manager.objects[object_id]['image_url'] = image_url
            
            # Update JSON file
            filepath = self.special_objects_manager.approved_path / f"{object_id}.json"
            if filepath.exists():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data['image_url'] = None if image_url.lower() == 'clear' else image_url
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                except Exception as e:
                    await interaction.response.send_message(f"⚠️ Updated in memory but failed to save: {e}", ephemeral=True)
                    return
            
            if image_url.lower() == 'clear':
                await interaction.response.send_message(f"✅ Cleared image for **{object_id}**", ephemeral=True)
            else:
                embed = discord.Embed(
                    title=f"✅ Image Set!",
                    description=f"Image for **{object_id}** has been updated.",
                    color=discord.Color.green()
                )
                embed.set_image(url=image_url)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        @self.bot.tree.command(
            name="resetobjectspins",
            description="[ADMIN] Reset adaptation spins for a player's special object"
        )
        @app_commands.describe(
            player="The player whose object spins to reset",
            object_id="The ID of the object to reset"
        )
        @app_commands.autocomplete(object_id=object_id_autocomplete)
        async def resetobjectspins_command(interaction: discord.Interaction, player: discord.Member, object_id: str):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            # Check if object exists
            if object_id not in self.special_objects_manager.objects:
                await interaction.response.send_message(f"❌ Object '{object_id}' not found.", ephemeral=True)
                return
            
            # Check if player has the object (either in inventory or as unique owner)
            has_by_inventory = object_id in self.special_objects_manager.player_inventory.get(player.id, [])
            owner_id = self.special_objects_manager.unique_object_owners.get(object_id)
            has_by_ownership = owner_id == player.id
            if not (has_by_inventory or has_by_ownership):
                owner_info = f" (owned by <@{owner_id}>)" if owner_id else ""
                await interaction.response.send_message(
                    f"❌ {player.mention} doesn't have **{object_id}**{owner_info}.",
                    ephemeral=True
                )
                return
            
            obj = self.special_objects_manager.objects.get(object_id, {})
            obj_name = obj.get('name', object_id)
            
            # Check tracking type to reset the correct keys
            tracking_config = obj.get('tracking', {})
            tracking_type = tracking_config.get('type', 'per_difficulty') if isinstance(tracking_config, dict) else 'per_difficulty'
            
            if tracking_type == 'total':
                # Total tracking - reset 'total' key
                self.special_objects_manager.set_tracking(player.id, object_id, 'total', 0)
                reset_info = "Total"
            else:
                # Per-difficulty tracking - reset all difficulty keys
                for difficulty in ['easy', 'medium', 'hard', 'impossible']:
                    self.special_objects_manager.set_tracking(player.id, object_id, difficulty, 0)
                reset_info = "Easy/Medium/Hard/Impossible"
            
            # Clear max adaptation warnings for this object
            if player.id in self.max_adaptation_warned and object_id in self.max_adaptation_warned[player.id]:
                del self.max_adaptation_warned[player.id][object_id]
            
            # Save tracking data
            self.special_objects_manager.save_tracking()
            
            embed = discord.Embed(
                title="🔄 Object Spins Reset",
                description=f"Reset all adaptation spins for **{obj_name}** ({object_id})\n\nPlayer: {player.mention}",
                color=discord.Color.blue()
            )
            
            if tracking_type == 'total':
                embed.add_field(name="Total Spins", value="0", inline=True)
            else:
                embed.add_field(name="Easy", value="0", inline=True)
                embed.add_field(name="Medium", value="0", inline=True)
                embed.add_field(name="Hard", value="0", inline=True)
                embed.add_field(name="Impossible", value="0", inline=True)
            
            await interaction.response.send_message(embed=embed)
            console.print(f"[blue]🔄 {interaction.user.name} reset {obj_name} spins for {player.name}[/blue]")
        
        @self.bot.tree.command(
            name="setobjectspins",
            description="[ADMIN] Set adaptation spins for a player's special object"
        )
        @app_commands.describe(
            player="The player whose object spins to set",
            object_id="The ID of the object",
            spins="Number of spins to set"
        )
        @app_commands.autocomplete(object_id=object_id_autocomplete)
        async def setobjectspins_command(interaction: discord.Interaction, player: discord.Member, object_id: str, spins: int):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            # Check if object exists
            if object_id not in self.special_objects_manager.objects:
                await interaction.response.send_message(f"❌ Object '{object_id}' not found.", ephemeral=True)
                return
            
            # Check if player has the object (either in inventory or as unique owner)
            has_by_inventory = object_id in self.special_objects_manager.player_inventory.get(player.id, [])
            owner_id = self.special_objects_manager.unique_object_owners.get(object_id)
            has_by_ownership = owner_id == player.id
            if not (has_by_inventory or has_by_ownership):
                owner_info = f" (owned by <@{owner_id}>)" if owner_id else ""
                await interaction.response.send_message(
                    f"❌ {player.mention} doesn't have **{object_id}**{owner_info}.",
                    ephemeral=True
                )
                return
            
            if spins < 0:
                await interaction.response.send_message("❌ Spins must be non-negative!", ephemeral=True)
                return
            
            obj = self.special_objects_manager.objects.get(object_id, {})
            obj_name = obj.get('name', object_id)
            
            # Check tracking type to set the correct key
            tracking_config = obj.get('tracking', {})
            tracking_type = tracking_config.get('type', 'per_difficulty') if isinstance(tracking_config, dict) else 'per_difficulty'
            
            if tracking_type == 'total':
                # Total tracking - set 'total' key
                old_spins = self.special_objects_manager.get_tracking(player.id, object_id, 'total')
                self.special_objects_manager.set_tracking(player.id, object_id, 'total', spins)
            else:
                # Per-difficulty - ask for specific difficulty or set all
                await interaction.response.send_message(
                    f"⚠️ **{obj_name}** uses per-difficulty tracking. Use the dashboard Edit Spins button to set individual difficulties.",
                    ephemeral=True
                )
                return
            
            # Save tracking data
            self.special_objects_manager.save_tracking()
            
            embed = discord.Embed(
                title="✅ Object Spins Set",
                description=f"Set spins for **{obj_name}** ({object_id})\n\nPlayer: {player.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Old Spins", value=str(old_spins), inline=True)
            embed.add_field(name="New Spins", value=str(spins), inline=True)
            
            await interaction.response.send_message(embed=embed)
            console.print(f"[blue]✏️ {interaction.user.name} set {obj_name} spins for {player.name}: {old_spins} → {spins}[/blue]")
        
        @self.bot.tree.command(
            name="setplayerslots",
            description="[ADMIN] Set max inventory slots for a player"
        )
        @app_commands.describe(
            player="The player to modify",
            max_slots="Maximum number of inventory slots"
        )
        async def setplayerslots_command(interaction: discord.Interaction, player: discord.Member, max_slots: int):
            # Check admin role
            if self.admin_role_id and not any(role.id == self.admin_role_id for role in interaction.user.roles):
                await interaction.response.send_message("❌ Admin only!", ephemeral=True)
                return
            
            if max_slots < 1:
                await interaction.response.send_message("❌ Slots must be at least 1!", ephemeral=True)
                return
            
            old_slots = self.special_objects_manager.get_player_max_slots(player.id)
            self.special_objects_manager.set_player_max_slots(player.id, max_slots)
            
            await interaction.response.send_message(
                f"✅ Set {player.mention}'s inventory slots: **{old_slots}** → **{max_slots}**",
                ephemeral=True
            )
        
        @self.bot.tree.command(
            name="mirrorinvoke",
            description="Use Mirror Shard to invoke a QTE against the enemy (requires 20 total spins)"
        )
        async def mirrorinvoke_command(interaction: discord.Interaction):
            """Invoke a medium QTE against the boss using Mirror Shard at 20+ spins"""
            user_id = interaction.user.id
            
            # Check if user has Mirror Shard
            inventory = self.special_objects_manager.player_inventory.get(user_id, [])
            has_mirror_shard = 'mirror_shard' in inventory
            
            # Also check unique ownership
            if not has_mirror_shard:
                owner_id = self.special_objects_manager.unique_object_owners.get('mirror_shard')
                has_mirror_shard = owner_id == user_id
            
            if not has_mirror_shard:
                await interaction.response.send_message("❌ You don't have the **Mirror Shard**!", ephemeral=True)
                return
            
            # Check spins
            spins = self.special_objects_manager.get_tracking(user_id, 'mirror_shard', 'total')
            if spins < 20:
                await interaction.response.send_message(
                    f"❌ Mirror Shard needs **20 total spins** to invoke QTE!\n"
                    f"Your current spins: **{spins}/20**",
                    ephemeral=True
                )
                return
            
            # Check if there's an active boss
            if not self.active_boss:
                await interaction.response.send_message(
                    "❌ No active boss to invoke QTE against!\n"
                    "Wait for a boss to appear in combat.",
                    ephemeral=True
                )
                return
            
            # Invoke the medium QTE against the boss!
            await interaction.response.send_message(
                f"🪞⚡ **Mirror Shard Invocation!**\n"
                f"{interaction.user.mention} reflects a **MEDIUM QTE** back at **{self.active_boss['name']}**!",
            )
            
            # Create the boss QTE - the boss must evade
            boss_name = self.active_boss['name']
            
            # For now, auto-resolve: boss takes damage since NPCs can't respond
            # This simulates invoking a QTE that the boss "fails"
            base_damage = 15  # Medium QTE damage
            
            # Apply boss damage
            await self.damage_boss(boss_name, base_damage)
            
            embed = discord.Embed(
                title="🪞💥 Mirror Shard - QTE Reflected!",
                description=f"**{boss_name}** failed to evade the reflected attack!\n\n"
                           f"💢 **{base_damage} damage** dealt!",
                color=discord.Color.purple()
            )
            
            # Check for black flash effect at 20 spins
            mirror_effects = self.special_objects_manager.get_active_effects(user_id, 'medium')
            if mirror_effects.get('on_boss_stunned', {}).get('black_flash', False):
                embed.add_field(
                    name="⚡ Black Flash Ready!",
                    value="Boss stunned! Black Flash opportunity!",
                    inline=False
                )
                # Stun the enemy
                self.enemy_stunned = True
                self.stun_end_time = time.time() + 2.0  # 2 second stun
            
            await self.webhook_send(embed=embed)
            console.print(f"[magenta]🪞 MIRROR INVOKE - {interaction.user.name} reflected QTE at {boss_name} for {base_damage} damage[/magenta]")
        
        # ========== END SPECIAL OBJECTS COMMANDS ==========
        
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
        
        # ========== SPECIAL OBJECTS: DAMAGE REDUCTION ==========
        # Uses INVENTORY-based system now (no character names needed)
        damage_reduction = self.special_objects_manager.get_damage_reduction(user_id, [], difficulty)
        
        if damage_reduction > 0:
            reduced_damage = int(damage * (1 - damage_reduction / 100))
            reduction_amount = damage - reduced_damage
            console.print(f"[cyan]🛡️ Damage reduction {damage_reduction:.0f}%: {damage} → {reduced_damage} (-{reduction_amount})[/cyan]")
            damage = reduced_damage
        # =======================================================
        
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
        """Helper: Queue HP update for batched sending - reduces rate limits"""
        # Queue the update instead of sending immediately
        self._pending_hp_updates[cache_key] = (thread, embed)
        
        # Start flush task if not running
        if self._hp_update_task is None or self._hp_update_task.done():
            self._hp_update_task = asyncio.create_task(self._flush_hp_updates())
    
    async def _flush_hp_updates(self):
        """Flush all pending HP updates after a short delay - batches rapid updates"""
        await asyncio.sleep(self._hp_update_interval)
        
        # Copy and clear pending updates
        updates = dict(self._pending_hp_updates)
        self._pending_hp_updates.clear()
        
        # Process updates with small delays between each to avoid rate limits
        update_delay = 0.3  # 300ms between HP bar edits
        
        for cache_key, (thread, embed) in updates.items():
            try:
                # Try to use cached message ID
                if cache_key in self.hp_bar_messages:
                    try:
                        message = await thread.fetch_message(self.hp_bar_messages[cache_key])
                        await self.safe_edit_message(message, embed=embed)
                        await asyncio.sleep(update_delay)  # Throttle between edits
                        continue
                    except discord.NotFound:
                        # Message was deleted, remove from cache
                        del self.hp_bar_messages[cache_key]
                    except Exception:
                        pass
                
                # No cached message, send new one and cache the ID
                new_message = await self.safe_send(thread, embed=embed)
                if new_message:
                    self.hp_bar_messages[cache_key] = new_message.id
                await asyncio.sleep(update_delay)  # Throttle between sends
                
            except Exception as e:
                log.error(f"Error in HP bar flush: {e}")

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
            await self.safe_send(channel, embed=embed)

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
            # Clear stored counter context
            if user_id in self.counter_context:
                ctx = self.counter_context.get(user_id, {})
                if ctx.get('qte_id') == qte_id:
                    del self.counter_context[user_id]
        
        # Delete the counter window message
        if hasattr(self, 'counter_messages') and user_id in self.counter_messages:
            try:
                await self.safe_delete_message(self.counter_messages[user_id])
                del self.counter_messages[user_id]
            except Exception:
                pass  # Message might already be deleted

    def get_random_counter_gif(self):
        """Get a random counter GIF from local assets directory"""
        try:
            if not self.counter_gif_dir.exists():
                log.warning(f"Counter GIF directory not found: {self.counter_gif_dir}")
                return None
            
            # Get all image files from counter_gifs directory
            gif_files = list(self.counter_gif_dir.glob("*.png")) + \
                       list(self.counter_gif_dir.glob("*.jpg")) + \
                       list(self.counter_gif_dir.glob("*.gif"))
            
            if not gif_files:
                log.warning("No counter GIF files found in assets/counter_gifs/")
                return None
            
            # Pick random file
            chosen_file = random.choice(gif_files)
            
            # Create discord.File object
            return discord.File(chosen_file, filename=chosen_file.name)
            
        except Exception as e:
            log.error(f"Error loading counter GIF: {e}")
            return None

    async def send_success_with_counter(self, channel, author_mention, response_time, user_id, qte_id, difficulty):
        """Send SUCCESS + COUNTER message merged into one - saves rate limit"""
        self.counter_enabled_players[user_id] = qte_id
        # Store difficulty for accurate adaptation tracking during counter
        self.counter_context[user_id] = {"qte_id": qte_id, "difficulty": difficulty}
        
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
    
    def get_parry_visual_indicator(self, response_time: float, difficulty: str, user_id: int) -> str:
        """Get visual indicator for parry timing - shows Black Flash zones (GUARANTEED if in window!)"""
        # Get the center of parry window (perfect timing)
        perfect_timing = self.get_adjusted_parry_center(difficulty, user_id)
        timing_deviation = abs(response_time - perfect_timing)
        
        # BF window check - within bf_timing_window = GUARANTEED BF!
        if timing_deviation <= 0.1:
            return "⭐💫"  # PERFECT - dead center, guaranteed BF
        elif timing_deviation <= 0.25:
            return "⭐"  # Great - guaranteed BF
        elif timing_deviation <= self.bf_timing_window:
            return "✨"  # In BF window - guaranteed BF
        else:
            return "✅"  # Outside BF window - no BF but still success
    
    def get_parry_timing_feedback(self, response_time: float, difficulty: str, user_id: int) -> str:
        """Get detailed timing feedback for parry - shows if BF will trigger"""
        perfect_timing = self.get_adjusted_parry_center(difficulty, user_id)
        timing_deviation = abs(response_time - perfect_timing)
        
        if timing_deviation <= 0.1:
            return "⚡PERFECT⚡"
        elif timing_deviation <= 0.25:
            return "Great!"
        elif timing_deviation <= self.bf_timing_window:
            return "Good"
        else:
            return "OK"

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
                # ========== END FIGHT - PAUSE COOLDOWNS ==========
                self._pause_ultimate_cooldowns()
                self.fight_active = False
                self.fight_start_time = None
                console.print(f"[yellow]⏸️ FIGHT ENDED - Ultimate cooldowns PAUSED![/yellow]")
                # ================================================
                
                # ========== BOSS DEFEAT ANIMATION ==========
                # Select random GIF from user-defined list or use default
                if self.boss_defeat_gifs and len(self.boss_defeat_gifs) > 0:
                    defeat_gif = random.choice(self.boss_defeat_gifs)
                else:
                    defeat_gif = self.default_boss_defeat_gif
                # ===========================================
                
                channel = self.bot.get_channel(self.qte_channel_id)
                if channel:
                    # Dramatic delay before victory announcement
                    await asyncio.sleep(0.5)
                    
                    embed = discord.Embed(
                        title="💀🎉 BOSS DEFEATED! 🎉💀",
                        description=f"**{boss_name}** has been vanquished!\n\n"
                                   f"🏆 **VICTORY!**\n"
                                   f"⏸️ Ultimate cooldowns are now **paused** until next fight!",
                        color=discord.Color.gold()
                    )
                    embed.set_image(url=defeat_gif)
                    embed.set_footer(text="Use /bossdefeatgif to add custom victory GIFs!")
                    await channel.send(embed=embed)
                console.print(f"[gold]👹 Boss {boss_name} DEFEATED![/gold]")
                
                # Clear the boss
                self.active_boss = None
                return False
            
            return True
        except Exception as e:
            log.error(f"Error damaging boss: {e}")
            return False

    # ========== FIGHT-BASED COOLDOWN SYSTEM ==========
    
    def _pause_ultimate_cooldowns(self):
        """Pause ultimate cooldowns when fight ends - save remaining time"""
        current_time = time.time()
        
        for user_id, cooldowns in self.power_cooldowns.items():
            if user_id not in self.ultimate_fight_cooldowns:
                self.ultimate_fight_cooldowns[user_id] = {}
            
            for power_key, cooldown_end in cooldowns.items():
                remaining = max(0, cooldown_end - current_time)
                if remaining > 0:
                    self.ultimate_fight_cooldowns[user_id][power_key] = remaining
                    console.print(f"[yellow]⏸️ Paused {power_key} cooldown for user {user_id}: {remaining:.1f}s remaining[/yellow]")
    
    def _resume_ultimate_cooldowns(self):
        """Resume ultimate cooldowns when fight starts - restore remaining time"""
        current_time = time.time()
        
        for user_id, paused in self.ultimate_fight_cooldowns.items():
            if user_id not in self.power_cooldowns:
                self.power_cooldowns[user_id] = {}
            
            for power_key, remaining in paused.items():
                if remaining > 0:
                    self.power_cooldowns[user_id][power_key] = current_time + remaining
                    console.print(f"[green]▶️ Resumed {power_key} cooldown for user {user_id}: {remaining:.1f}s[/green]")
        
        # Clear paused cooldowns after resuming
        self.ultimate_fight_cooldowns.clear()
    
    def get_ultimate_cooldown_remaining(self, user_id, power_key):
        """Get remaining cooldown for an ultimate, accounting for fight state"""
        # If fight is not active, check paused cooldowns
        if not self.fight_active:
            return self.ultimate_fight_cooldowns.get(user_id, {}).get(power_key, 0)
        
        # Fight is active, check real cooldowns
        if user_id not in self.power_cooldowns:
            return 0
        
        cooldown_end = self.power_cooldowns[user_id].get(power_key, 0)
        remaining = max(0, cooldown_end - time.time())
        return remaining
    
    def is_ultimate_ready(self, user_id, power_key):
        """Check if an ultimate is ready (cooldown complete and fight active for use)"""
        remaining = self.get_ultimate_cooldown_remaining(user_id, power_key)
        return remaining <= 0
    
    # =================================================

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

    async def trigger_single_qte(self, difficulty, target_member=None, is_targeted=False):
        """Trigger a single-target QTE - optionally targeted to specific player"""
        try:
            if self.should_update_cache():
                await self.update_qte_player_cache()

            if not self.qte_players and not target_member:
                console.print("[red]✗ No QTE players available![/red]")
                return

            if not target_member:
                target_member = random.choice(self.qte_players)
            
            # MIRROR SHARD: Check for auto-evade on easy QTEs
            mirror_effects = self.special_objects_manager.get_active_effects(target_member.id, difficulty)
            auto_evade_difficulty = mirror_effects.get('auto_evade')
            
            if auto_evade_difficulty and difficulty == auto_evade_difficulty:
                # Auto-evade this QTE!
                channel = self.bot.get_channel(self.qte_channel_id)
                console.print(f"[green]🪞 AUTO-EVADE (Mirror Shard) - {target_member.name} auto-evades {difficulty.upper()} QTE[/green]")
                
                await self.webhook_send(
                    content=f"🪞✨ **{target_member.mention}** auto-evades the **{difficulty.upper()}** attack!\n"
                           f"_Mirror Shard reflects the technique back!_"
                )
                
                # Still counts as session stat
                self.session_stats['qtes_triggered'] += 1
                
                # Enable counter window for auto-evade too (with guaranteed_counter)
                if mirror_effects.get('guaranteed_counter', False):
                    qte_id = self.qte_counter
                    self.qte_counter += 1
                    await self.send_success_with_counter(channel, target_member.mention, 0.0, target_member.id, qte_id, difficulty)
                    console.print(f"[yellow]⚡🪞 COUNTER ENABLED (auto-evade) for {target_member.name}[/yellow]")
                
                return  # QTE handled, don't actually trigger it

            qte_id = self.qte_counter
            self.qte_counter += 1

            self.active_qtes[qte_id] = {
                'difficulty': difficulty,
                'mode': 'single',
                'start': datetime.now(timezone.utc),
                'target': target_member,
                'participants': {},
                'responses': set(),
                'is_targeted': is_targeted  # Flag: this QTE only accepts evade/adapt, not parry
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
            asyncio.create_task(self.send_parry_and_bf_warning(qte_message, parry_min, bf_window_start, qte_id))

            asyncio.create_task(
                self.qte_timeout_handler(qte_id, difficulty, 'single', target_member)
            )

        except Exception as e:
            console.print(f"[red]✗ Error triggering single QTE: {e}[/red]")

    async def send_parry_and_bf_warning(self, qte_message, parry_start, bf_start, qte_id=None):
        """Add parry warning star, then replace with exclamation when BF window opens"""
        try:
            # Wait until parry window starts
            if parry_start > 0:
                await asyncio.sleep(parry_start)
            
            # Check if QTE is still active before adding star
            if qte_id and qte_id not in self.active_qtes:
                return
            
            await self.safe_add_reaction(qte_message, "⭐")
            
            # Wait until black flash window starts, then replace star with exclamation
            bf_delay = max(0, bf_start - parry_start)
            if bf_delay > 0:
                await asyncio.sleep(bf_delay)
            
            # Check AGAIN if QTE is still active before adding exclamation
            if qte_id and qte_id not in self.active_qtes:
                # QTE ended (player evaded/parried), clean up the star
                try:
                    await qte_message.clear_reaction("⭐")
                except:
                    pass
                return
            
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
            
            channel = self.bot.get_channel(self.qte_channel_id)
            
            # MIRROR SHARD: Check for auto-evade on group QTEs
            auto_evaded_players = []
            remaining_players = []
            
            for member in self.qte_players:
                mirror_effects = self.special_objects_manager.get_active_effects(member.id, difficulty)
                auto_evade_difficulty = mirror_effects.get('auto_evade')
                
                if auto_evade_difficulty and difficulty == auto_evade_difficulty:
                    auto_evaded_players.append((member, mirror_effects))
                else:
                    remaining_players.append(member)
            
            # Announce auto-evades
            for member, effects in auto_evaded_players:
                console.print(f"[green]🪞 AUTO-EVADE (Group) - {member.name} auto-evades {difficulty.upper()} QTE[/green]")
                await self.webhook_send(
                    content=f"🪞✨ **{member.mention}** auto-evades the **{difficulty.upper()}** attack!"
                )
                
                # Enable counter window if has guaranteed_counter
                if effects.get('guaranteed_counter', False):
                    await self.send_success_with_counter(channel, member.mention, 0.0, member.id, qte_id, difficulty)
            
            # If everyone auto-evaded, no QTE needed
            if not remaining_players:
                self.session_stats['qtes_triggered'] += 1
                console.print(f"[green]🪞 All players auto-evaded group {difficulty.upper()} QTE![/green]")
                return

            self.active_qtes[qte_id] = {
                'difficulty': difficulty,
                'mode': 'group',
                'start': datetime.now(timezone.utc),
                'target': None,
                'participants': {member.id: {'responded': False, 'success': False, 'member': member} 
                                for member in remaining_players},
                'responses': set(),
                'auto_evaded': [m.id for m, _ in auto_evaded_players]  # Track who auto-evaded
            }

            self.session_stats['qtes_triggered'] += 1

            role = channel.guild.get_role(self.qte_player_role_id)
            emoji = self.difficulty_emoji.get(difficulty, '⚡')

            await channel.send(f"🚨 **GROUP {difficulty.upper()} QTE** {emoji} | {role.mention}")

            # Rich console output
            table = Table(show_header=False, box=box.ROUNDED, border_style="red")
            table.add_row("[magenta]🚨 GROUP QTE TRIGGERED[/magenta]")
            table.add_row(f"[white]ID:[/white] [red]{qte_id}[/red]")
            table.add_row(f"[white]Difficulty:[/white] [red]{difficulty.upper()}[/red]")
            table.add_row(f"[white]Players:[/white] [cyan]{len(remaining_players)}[/cyan] (auto-evaded: {len(auto_evaded_players)})")
            console.print(table)

            asyncio.create_task(
                self.qte_timeout_handler(qte_id, difficulty, 'group')
            )

        except Exception as e:
            console.print(f"[red]✗ Error triggering group QTE: {e}[/red]")

    async def handle_qte_response(self, message):
        """Handle player responses to QTE events - OPTIMIZED"""
        profiler.start('handle_qte_response')
        try:
            # Early exits for performance
            if not self.active_qtes:
                profiler.stop('handle_qte_response')
                return

            if message.channel.id != self.qte_channel_id:
                profiler.stop('handle_qte_response')
                return
            
            content = message.content.lower()
            
            # Fast check: Only process if message contains a QTE command
            qte_commands = ('*evade*', '*parry*', '*save*', '*adapt*', '*counter*', '*block*')
            if not any(cmd in content for cmd in qte_commands):
                profiler.stop('handle_qte_response')
                return

            user_id = self.resolve_user_id(message)
            now = datetime.now(timezone.utc)

            # Check if user is in active QTE and using slash commands while QTE is active
            # (This auto-fails the QTE if they use slash commands during active QTE)
            user_has_active_qte = any(
                (qte_data.get('target') is not None and qte_data.get('target').id == user_id) or 
                user_id in qte_data.get('participants', {})
                for qte_data in self.active_qtes.values()
            )
            
            # If message doesn't match expected QTE response pattern, it's auto-fail
            if message.content.startswith('/') and user_has_active_qte:
                # User tried to use a slash command during active QTE - auto-fail
                for qte_id in list(self.active_qtes.keys()):
                    qte_data = self.active_qtes.get(qte_id)
                    if not qte_data:
                        continue
                    target = qte_data.get('target')
                    if target and target.id == user_id:
                        await message.channel.send(f"❌ {message.author.mention} **Using commands during QTE = automatic fail!**")
                        await self.damage_player(user_id, qte_data['difficulty'])
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        return

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
        finally:
            profiler.stop('handle_qte_response')

    def resolve_user_id(self, message):
        """Resolve user ID, handling Tupperbox characters"""
        author_name = message.author.display_name
        if author_name in self.character_registry:
            return self.character_registry[author_name]
        return message.author.id

    def get_user_characters(self, user_id: int) -> list:
        """Get all character names registered to a user"""
        return [
            char_name for char_name, owner_id in self.character_registry.items()
            if owner_id == user_id
        ]

    async def process_adaptation(self, user_id: int, difficulty: str, objects: list, message) -> dict:
        """Process adaptation objects for a user during a successful *adapt* command"""
        results = {
            'total_spins': {},
            'new_thresholds': [],
            'effects_applied': [],
            'heals': 0,
            'damage_reduction': 0
        }
        
        channel = message.channel
        # Inventory-based: no longer need character names
        
        for obj in objects:
            # Validate obj is a dict
            if not isinstance(obj, dict):
                log.error(f"process_adaptation: obj is {type(obj)}, not dict")
                continue
            
            obj_id = obj.get('id', 'UNKNOWN')
            obj_name = obj.get('name', 'UNKNOWN')
            
            # Check tracking type - safely handle if tracking config is missing
            tracking_config = obj.get('tracking', {})
            if isinstance(tracking_config, list):
                # Old format where thresholds was stored as tracking config (shouldn't happen)
                tracking_config = {}
            tracking_type = tracking_config.get('type', 'per_difficulty')
            
            if tracking_type == 'total':
                # Total tracking - one unified counter regardless of difficulty
                tracking_key = 'total'
                tracking_display = 'total'
                new_spins = self.special_objects_manager.increment_tracking(user_id, obj_id, tracking_key)
                results['total_spins'][obj_id] = {'total': new_spins}
                
                # Thresholds is a flat list
                thresholds = obj.get('thresholds', [])
                if isinstance(thresholds, dict):
                    # Old format - shouldn't happen but handle it
                    thresholds = thresholds.get(difficulty, [])
            else:
                # Per-difficulty tracking (default)
                tracking_key = difficulty
                tracking_display = difficulty
                new_spins = self.special_objects_manager.increment_tracking(user_id, obj_id, difficulty)
                results['total_spins'][obj_id] = {difficulty: new_spins}
                
                # Thresholds is per-difficulty dict
                thresholds_config = obj.get('thresholds', {})
                if isinstance(thresholds_config, list):
                    # New format but with per-difficulty - shouldn't happen
                    thresholds = thresholds_config
                else:
                    # Old per-difficulty dict format
                    thresholds = thresholds_config.get(difficulty, [])
            
            old_threshold = None
            new_threshold = None
            
            # Find old and new threshold levels
            for t in thresholds:
                if new_spins - 1 >= t['spins']:
                    old_threshold = t
                if new_spins >= t['spins']:
                    new_threshold = t
            
            # If we reached a new threshold, announce it!
            if new_threshold and (not old_threshold or new_threshold['spins'] > old_threshold.get('spins', 0)):
                results['new_thresholds'].append({
                    'object': obj_name,
                    'spins': new_threshold['spins'],
                    'effects': new_threshold['effects']
                })
                
                # Parse and apply effects
                effects = self.special_objects_manager.parse_effects(new_threshold['effects'])
                
                # Check for heal effects on threshold unlock
                if effects.get('heal_percent', 0) > 0:
                    heal_amount = await self.heal_player_percent(user_id, effects['heal_percent'])
                    results['heals'] += heal_amount
                
                if effects.get('heal', 0) > 0:
                    self.player_hp[user_id]['current'] = min(
                        self.player_hp[user_id]['max'],
                        self.player_hp[user_id]['current'] + effects['heal']
                    )
                    results['heals'] += effects['heal']
                
                # Build announcement embed
                threshold_num = thresholds.index(new_threshold) + 1
                max_thresholds = len(thresholds)
                
                # Check if this is the max threshold (first time only warning)
                is_max_threshold = (threshold_num == max_thresholds)
                if is_max_threshold:
                    # Check if we've already warned this user about this object+difficulty/total
                    if user_id not in self.max_adaptation_warned:
                        self.max_adaptation_warned[user_id] = {}
                    if obj_id not in self.max_adaptation_warned[user_id]:
                        self.max_adaptation_warned[user_id][obj_id] = {}
                    
                    already_warned = self.max_adaptation_warned[user_id][obj_id].get(tracking_key, False)
                
                embed = discord.Embed(
                    title=f"🔮 {obj_name} - THRESHOLD {threshold_num}/{max_thresholds}!",
                    description=f"**{message.author.mention}** reached **{new_spins} {tracking_display}** spins!\n\n"
                               f"📈 **New Effects Unlocked:**",
                    color=discord.Color.purple()
                )
                
                # If max threshold and first time, add warning
                if is_max_threshold and not already_warned:
                    if tracking_type == 'total':
                        embed.description += f"\n\n🌟 **MAX ADAPTATION REACHED!**\nFurther adapts provide no additional bonuses."
                    else:
                        embed.description += f"\n\n🌟 **MAX ADAPTATION REACHED!**\nFurther adapts on **{difficulty}** provide no additional bonuses."
                    self.max_adaptation_warned[user_id][obj_id][tracking_key] = True
                
                # List effects in a readable format
                effect_text = []
                for effect in new_threshold['effects']:
                    if 'damage_reduction' in effect:
                        val = effect.split(':')[-1].replace('+', '')
                        effect_text.append(f"🛡️ {val}% damage reduction")
                    elif 'heal_percent' in effect:
                        val = effect.split(':')[-1]
                        effect_text.append(f"💚 Healed {val}% HP!")
                    elif 'heal:' in effect:
                        val = effect.split(':')[-1]
                        effect_text.append(f"💚 Healed {val} HP!")
                    elif 'bf_chance' in effect:
                        val = effect.split(':')[-1]
                        effect_text.append(f"⚡ +{val}% Black Flash chance")
                    elif 'damage_boost' in effect:
                        val = effect.split(':')[-1]
                        effect_text.append(f"💢 +{val} damage boost")
                    else:
                        effect_text.append(f"✨ {effect}")
                
                embed.add_field(name="Effects", value="\n".join(effect_text), inline=False)
                
                # Add GIF if object has one
                if obj.get('visuals', {}).get('threshold_gif'):
                    embed.set_image(url=obj['visuals']['threshold_gif'])
                
                await self.safe_send(channel, embed=embed)
            
            # Check conditionals
            for cond in obj.get('conditionals', []):
                if self.special_objects_manager._evaluate_condition(cond['if'], user_id, obj_id, difficulty):
                    results['effects_applied'].extend(cond['then'])
                    
                    # Special conditional announcements (e.g., impossible@12 bonuses)
                    if 'impossible' in cond['if'] and '>= 12' in cond['if']:
                        effects = self.special_objects_manager.parse_effects(cond['then'])
                        
                        if any('damage_reduction' in e for e in cond['then']):
                            embed = discord.Embed(
                                title=f"🌟 {obj_name} - MASTERY BONUS!",
                                description=f"**{message.author.mention}** achieved **12+ impossible** spins!\n\n"
                                           f"🔥 **Mastery Effect Active!**",
                                color=discord.Color.gold()
                            )
                            
                            # List conditional effects
                            for effect in cond['then']:
                                if 'damage_reduction.easy' in effect:
                                    embed.add_field(name="Easy QTE", value="🚫 100% damage negated!", inline=True)
                                elif 'damage_reduction.medium' in effect:
                                    embed.add_field(name="Medium QTE", value=f"+50% reduction", inline=True)
                                elif 'damage_reduction.hard' in effect:
                                    embed.add_field(name="Hard QTE", value=f"+10% reduction", inline=True)
                            
                            await self.safe_send(channel, embed=embed)
            
            # Calculate current damage reduction for reporting (inventory-based)
            results['damage_reduction'] = self.special_objects_manager.get_damage_reduction(user_id, [], difficulty)
            
            # Console log - show tracking_display (total vs difficulty)
            console.print(f"[magenta]🔮 ADAPT - {message.author.name}: {obj_name} {tracking_display} = {new_spins} spins[/magenta]")
        
        # Save tracking data
        self.special_objects_manager.save_tracking()
        
        return results

    async def heal_player_percent(self, user_id: int, percent: int) -> int:
        """Heal player by a percentage of their max HP, returns amount healed"""
        if user_id not in self.player_hp:
            return 0
        
        hp_data = self.player_hp[user_id]
        max_hp = hp_data['max']
        current_hp = hp_data['current']
        
        heal_amount = int(max_hp * (percent / 100))
        new_hp = min(max_hp, current_hp + heal_amount)
        actual_heal = new_hp - current_hp
        
        self.player_hp[user_id]['current'] = new_hp
        
        return actual_heal

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
            
            # Get active Mirror Shard effects
            mirror_effects = self.special_objects_manager.get_active_effects(user_id, difficulty)

            if user_id == target.id:
                if '*evade*' in content:
                    current_time = time.time()
                    # Note: Spam protection is handled by the responses set - no need to penalize here
                    
                    if response_time <= evade_window:
                        responses.add(user_id)
                        await self.update_player_stats(user_id, 'evade', True, response_time)
                        console.print(f"[green]✓ EVADE SUCCESS - {message.author.name} in {response_time:.2f}s[/green]")
                        
                        # Add success reaction to Tupper message (or original if not using Tupper)
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "✅"))
                        
                        # MIRROR SHARD: Heal on hard evade (15+ spins)
                        if difficulty == 'hard' and mirror_effects.get('on_hard_evade_heal', 0) > 0:
                            heal_amount = mirror_effects['on_hard_evade_heal']
                            if user_id in self.player_hp:
                                old_hp = self.player_hp[user_id]['current']
                                self.player_hp[user_id]['current'] = min(
                                    self.player_hp[user_id]['max'],
                                    self.player_hp[user_id]['current'] + heal_amount
                                )
                                new_hp = self.player_hp[user_id]['current']
                                await self.webhook_send(content=f"🪞✨ **Mirror Shard** healed {message.author.mention}! ({old_hp} → {new_hp} HP)")
                                console.print(f"[green]🪞 Mirror Shard heal: {old_hp} → {new_hp} (+{heal_amount})[/green]")
                        
                        # Enable counter window if evaded fast enough OR has guaranteed_counter
                        has_guaranteed_counter = mirror_effects.get('guaranteed_counter', False)
                        if response_time < self.counter_window or has_guaranteed_counter:
                            await self.send_success_with_counter(channel, message.author.mention, response_time, user_id, qte_id, difficulty)
                            if has_guaranteed_counter:
                                console.print(f"[yellow]⚡🪞 COUNTER ENABLED (Mirror Shard guaranteed) for {message.author.name}[/yellow]")
                            else:
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
                            
                            # MIRROR SHARD BLACK FLASH: If user has 20+ spins, guaranteed 40% boss damage
                            mirror_shard_bf = False
                            mirror_effects = self.special_objects_manager.get_active_effects(user_id, difficulty)
                            if mirror_effects.get('total_spins', 0) >= 20 and self.active_boss:
                                mirror_shard_bf = True
                                # 40% of boss MAX HP as damage
                                boss_max_hp = self.active_boss.get('max_hp', 1000)
                                mirror_damage = int(boss_max_hp * 0.40)
                                
                                # Reset Mirror Shard to 5 spins
                                self.special_objects_manager.set_tracking(user_id, 'mirror_shard', 'total', 5)
                                self.special_objects_manager.save_tracking()
                                
                                # Apply mirror damage (no stun required!)
                                await self.damage_boss(self.active_boss['name'], mirror_damage)
                                
                                # Clear max adaptation warning so they get notified again
                                if user_id in self.max_adaptation_warned:
                                    if 'mirror_shard' in self.max_adaptation_warned[user_id]:
                                        del self.max_adaptation_warned[user_id]['mirror_shard']
                                
                                console.print(f"[bold magenta]🪞⚡ MIRROR SHARD BLACK FLASH! {mirror_damage} damage (40% boss HP), reset to 5 spins[/bold magenta]")
                            else:
                                # Normal BF damage
                                if self.active_boss:
                                    await self.damage_boss(self.active_boss['name'], base_damage)
                            
                            # Stun enemy for 1 second (guaranteed on BF)
                            self.enemy_stunned = True
                            self.stun_end_time = time.time() + 1.0
                            
                            # Add charge
                            self.add_charge_from_damage_dealt(user_id, base_damage)
                            
                            # Build embed based on Mirror Shard or normal BF
                            if mirror_shard_bf:
                                embed = discord.Embed(
                                    title="🪞⚡ MIRROR SHARD BLACK FLASH! ⚡🪞",
                                    description=f"**{message.author.mention}** channeled the Mirror Shard's power!\n\n"
                                               f"💀 **{mirror_damage} DAMAGE!** (40% Boss HP)\n"
                                               f"🪞 Mirror Shard reset to 5 spins!\n"
                                               f"🌀 Enemy stunned for 1s!\n"
                                               f"🔥 **CHAIN OPPORTUNITY INCOMING!**",
                                    color=discord.Color.from_rgb(180, 0, 255)  # Bright Purple
                                )
                                embed.set_footer(text=f"Mirror Shard 20→5 Spins | No Stun Required!")
                            else:
                                embed = discord.Embed(
                                    title="⚡💥 BLACK FLASH! 💥⚡",
                                    description=f"**{message.author.mention}** landed a **PERFECT BLACK FLASH!**\n\n"
                                               f"💢 **{base_damage} DAMAGE!**\n"
                                               f"🌀 Enemy stunned for 1s!\n"
                                               f"🔥 **CHAIN OPPORTUNITY INCOMING!**",
                                    color=discord.Color.from_rgb(138, 43, 226)  # Purple
                                )
                                bf_chance = self.player_stats[user_id]['black_flash_chance'] * 100
                                embed.set_footer(text=f"Black Flash Chance: {bf_chance:.1f}% | Response Time: {response_time:.2f}s")
                            
                            embed.set_image(url=self.black_flash_gif)
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
                            await self.trigger_bf_chain_qte(user_id, channel, target, difficulty, 2, origin_message=message)
                            
                            # Process next batch QTE if applicable (after chain ends naturally)
                            # Don't process here - let chain complete first
                            return True
                        else:
                            # PARRY SUCCESS (no Black Flash) - Show visual with BF timing indicator
                            parry_indicator = self.get_parry_visual_indicator(response_time, difficulty, user_id)
                            timing_feedback = self.get_parry_timing_feedback(response_time, difficulty, user_id)
                            
                            # Only show message if player has BF chance (to indicate timing)
                            bf_chance = self.player_stats.get(user_id, {}).get('black_flash_chance', 0)
                            if bf_chance > 0 and parry_indicator != "✅":
                                # Show visual indicator for BF window
                                await self.webhook_send(
                                    content=f"{parry_indicator} {message.author.mention} **parried!** [{timing_feedback}] ({response_time:.2f}s)"
                                )
                            
                            console.print(f"[cyan]⚔ PARRY SUCCESS - {message.author.name} in {response_time:.2f}s ({timing_feedback})[/cyan]")

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

                # ========== SPECIAL OBJECTS: *adapt* COMMAND ==========
                elif '*adapt*' in content:
                    # Check if user has any adaptation objects IN THEIR INVENTORY
                    adaptation_objects = [
                        obj for obj in self.special_objects_manager.get_player_inventory(user_id)
                        if obj.get('type') == 'adaptation'
                    ]
                    
                    if not adaptation_objects:
                        return False  # No adaptation objects, ignore
                    
                    # Check if within valid window (parry window for adaptation)
                    # Get adjusted parry window for REVENGE mode  
                    adj_parry_min, adj_parry_max = self.get_adjusted_parry_window(difficulty, user_id)
                    
                    # Adaptation uses parry timing
                    if not (adj_parry_min <= response_time <= adj_parry_max):
                        await self.webhook_send(content=f"❌ {message.author.mention} **adapt mistimed!** ({response_time:.2f}s)")
                        await self.damage_player(user_id, difficulty)
                        console.print(f"[red]✗ ADAPT FAILED (mistimed) - {message.author.name} at {response_time:.2f}s[/red]")
                        
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "❌"))
                        
                        current_time = time.time()
                        self.last_qte_completion[user_id] = current_time
                        
                        is_batch = qte_data.get('batch_mode', False)
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        
                        if is_batch:
                            await self.process_next_player_qte(target)
                        return True
                    
                    # ADAPT SUCCESS - Process all adaptation objects
                    responses.add(user_id)
                    results = await self.process_adaptation(user_id, difficulty, adaptation_objects, message)
                    
                    # Track adaptation as successful response
                    await self.update_player_stats(user_id, 'adapt', True, response_time)
                    
                    # Mark success
                    asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "🔮"))
                    
                    # Send success message with spin count (if no threshold was unlocked)
                    if not results.get('new_thresholds'):
                        # Show current spin progress
                        spin_info = []
                        for obj in adaptation_objects:
                            obj_id = obj['id']
                            spins = self.special_objects_manager.get_tracking(user_id, obj_id, difficulty)
                            spin_info.append(f"**{obj['name']}**: {spins} {difficulty} spins")
                        
                        await self.webhook_send(
                            content=f"🔮 {message.author.mention} **adapted!** ({response_time:.2f}s)\n" + "\n".join(spin_info)
                        )
                    
                    console.print(f"[magenta]🔮 ADAPT SUCCESS - {message.author.name}[/magenta]")
                    
                    current_time = time.time()
                    self.last_qte_completion[user_id] = current_time
                    
                    is_batch = qte_data.get('batch_mode', False)
                    self.active_qtes.pop(qte_id, None)
                    self.save_all_data()
                    
                    if is_batch:
                        await self.process_next_player_qte(target)
                    return True

            else:
                if '*save*' in content and target:
                    # Check save rate limit (2 per minute)
                    if not self.can_save_qte(user_id):
                        await self.webhook_send(content=f"⏱️ {message.author.mention} **Save limit exceeded!** Max 2 saves per minute")
                        return False
                    
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
            
            # Get active Mirror Shard effects
            mirror_effects = self.special_objects_manager.get_active_effects(user_id, difficulty)

            if '*evade*' in content:
                action = 'evade'
                current_time = time.time()
                
                if response_time <= evade_window:
                    success = True
                    participant['success'] = True
                    console.print(f"[green]✓ {message.author.name} - EVADE - {response_time:.2f}s[/green]")
                    
                    # MIRROR SHARD: Heal on hard evade (15+ spins)
                    if difficulty == 'hard' and mirror_effects.get('on_hard_evade_heal', 0) > 0:
                        heal_amount = mirror_effects['on_hard_evade_heal']
                        if user_id in self.player_hp:
                            old_hp = self.player_hp[user_id]['current']
                            self.player_hp[user_id]['current'] = min(
                                self.player_hp[user_id]['max'],
                                self.player_hp[user_id]['current'] + heal_amount
                            )
                            new_hp = self.player_hp[user_id]['current']
                            await self.webhook_send(content=f"🪞✨ **Mirror Shard** healed {message.author.mention}! ({old_hp} → {new_hp} HP)")
                            console.print(f"[green]🪞 Mirror Shard heal: {old_hp} → {new_hp} (+{heal_amount})[/green]")
                    
                    # Enable counter window if evaded fast enough OR has guaranteed_counter
                    has_guaranteed_counter = mirror_effects.get('guaranteed_counter', False)
                    if response_time < self.counter_window or has_guaranteed_counter:
                        await self.send_success_with_counter(channel, message.author.mention, response_time, user_id, qte_id, difficulty)
                        if has_guaranteed_counter:
                            console.print(f"[yellow]⚡🪞 COUNTER ENABLED (Mirror Shard guaranteed) for {message.author.name}[/yellow]")
                        else:
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
                # Block parry in GROUP QTEs
                await self.webhook_send(content=f"❌ {message.author.mention} **Cannot parry in group QTEs!** Use *evade* instead")
                return False
                
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
                        asyncio.create_task(self.trigger_bf_chain_qte(user_id, channel, member, difficulty, 2, origin_message=message))
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

            await self.safe_send(channel, content=f"📊 **Group QTE Complete!** {successful}/{total} succeeded")

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
            
            # ========== CHECK IF FIGHT IS ACTIVE ==========
            if not self.fight_active:
                await channel.send(
                    f"{message.author.mention} ⚔️ **No active fight!** "
                    f"Ultimate can only be used during boss fights."
                )
                return
            # ==============================================
            
            # Check cooldown (fight-based)
            current_time = time.time()
            if user_id not in self.power_cooldowns:
                self.power_cooldowns[user_id] = {}
            
            cooldown_remaining = self.get_ultimate_cooldown_remaining(user_id, power_key)
            if cooldown_remaining > 0:
                minutes = int(cooldown_remaining // 60)
                seconds = int(cooldown_remaining % 60)
                await channel.send(
                    f"{message.author.mention} ⏱️ Power on cooldown! **{minutes}m {seconds}s** remaining.\n"
                    f"💡 Cooldowns only tick during active fights!"
                )
                return
            
            # Get power data
            power = self.character_powers[character_name][power_key]
            
            # ===== PHASE 5: CONSUME ULTIMATE CHARGE =====
            self.consume_ultimate_charge(user_id, power_slot)
            # ============================================
            
            # Apply power effect (will set cooldown internally based on damage)
            await self.apply_power_effect(message.author, power, channel, power_key)
            
            console.print(f"[purple]⚡ {message.author.name} used {power['name']}[/purple]")
            
        except Exception as e:
            log.error(f"Error handling power activation: {e}")

    async def apply_power_effect(self, user, power, channel, power_key=None):
        """Apply power effects based on effect string"""
        try:
            effect = power["effect"]
            power_name = power["name"]
            
            # Create activation embed
            embed = discord.Embed(
                title=f"⚡ {power_name.upper()} ⚡",
                description=power["description"],
                color=self.get_power_color(power["type"])
            )
            
            # Parse effect string
            if effect.startswith("damage:"):
                raw_damage = int(effect.split(":")[1])
                
                # ========== CAP DAMAGE AT 500 ==========
                damage = min(raw_damage, self.ultimate_max_damage)
                was_capped = raw_damage > self.ultimate_max_damage
                # ======================================
                
                # Use 10-minute base cooldown for ultimates (fight-time only!)
                total_cooldown = self.ultimate_base_cooldown  # 600 seconds = 10 minutes
                
                if was_capped:
                    embed.add_field(
                        name="Effect", 
                        value=f"💥 **{damage} damage** to enemy! (capped from {raw_damage})", 
                        inline=False
                    )
                else:
                    embed.add_field(name="Effect", value=f"💥 **{damage} damage** to enemy!", inline=False)
                
                # Show cooldown in minutes
                cooldown_minutes = total_cooldown // 60
                embed.add_field(
                    name="Cooldown", 
                    value=f"⏱️ **{cooldown_minutes} minutes** (fight-time only!)", 
                    inline=False
                )
                
                # Set the cooldown for this power
                if power_key and user.id:
                    if user.id not in self.power_cooldowns:
                        self.power_cooldowns[user.id] = {}
                    self.power_cooldowns[user.id][power_key] = time.time() + total_cooldown
                    console.print(f"[yellow]⏱️ Set {power_key} cooldown: {cooldown_minutes}m (fight-time)[/yellow]")
                
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
            embed.set_footer(text=f"Type: {power['type'].capitalize()} | 💡 Cooldowns tick during fights only!")
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
            
            # CRITICAL COUNTER CHECK - Uses luck modifier (formerly BF chance)
            is_critical = False
            crit_chance = self.player_stats.get(user_id, {}).get('black_flash_chance', self.black_flash_base_chance)
            # Add REVENGE bonus
            if user_id in self.player_hp and self.player_hp[user_id].get("revenge_mode", False):
                crit_chance += self.revenge_bf_bonus
            # Add buff bonus
            crit_chance += self.get_bf_boost(user_id)
            
            if random.random() < crit_chance:
                is_critical = True
                counter_damage = int(counter_damage * 2.0)  # Double damage on crit!
                # Increase luck for next time (capped)
                stats = self.player_stats.get(user_id, {})
                if stats.get('black_flash_chance', 0) < self.black_flash_cap:
                    stats['black_flash_chance'] = min(
                        stats.get('black_flash_chance', self.black_flash_base_chance) + self.black_flash_increment,
                        self.black_flash_cap
                    )
            
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
            counter_file = None
            
            # Debug logging for counter GIF lookup
            console.print(f"[dim]Counter GIF lookup for user_id={user_id}: found={user_gifs is not None}[/dim]")
            
            if user_gifs:
                # Support both single URL (string) and multiple URLs (list)
                if isinstance(user_gifs, list) and user_gifs:
                    counter_gif_url = random.choice(user_gifs)
                    console.print(f"[dim]Using random GIF from list ({len(user_gifs)} total)[/dim]")
                else:
                    counter_gif_url = user_gifs
                    console.print(f"[dim]Using single GIF URL[/dim]")
            else:
                # Use random local counter GIF
                counter_file = self.get_random_counter_gif()
                counter_gif_url = f"attachment://{counter_file.filename}" if counter_file else None
            
            # Get ultimate charge for display
            p1_charge = self.get_charge_percentage(user_id, 1)
            p2_charge = self.get_charge_percentage(user_id, 2)
            charge_text = f"⚡ Ult: P1 {p1_charge:.0f}% | P2 {p2_charge:.0f}%"
            
            # Check if this was from a Black Flash chain (add star visual)
            is_bf_chain = user_id in self.bf_chain_active
            
            # Build title based on critical or normal counter
            crit_text = ""
            if is_bf_chain:
                title = "⭐⚡💥 BLACK FLASH COUNTER! 💥⚡⭐"
                title_color = discord.Color.from_rgb(138, 43, 226)
            elif is_critical:
                title = "🎯💥 CRITICAL COUNTER! 💥🎯"
                title_color = discord.Color.from_rgb(255, 215, 0)  # Gold for crit
                crit_text = "\n🍀 **CRITICAL HIT!** (2x Damage)"
            else:
                title = "⚡💥 FEROCIOUS COUNTER! 💥⚡"
                title_color = discord.Color.from_rgb(255, 69, 0)
            
            # Show crit chance in footer
            crit_display = crit_chance * 100
            
            embed = discord.Embed(
                title=title,
                description=f"**{message.author.mention}** unleashes a devastating counterattack!\n\n"
                           f"💢 **{counter_damage} DAMAGE!**{crit_text}\n"
                           f"🌀 Enemy stunned for {stun_text}\n"
                           f"🔥 Counter Streak: **{counter_streak}**\n"
                           f"{charge_text}",
                color=title_color
            )
            
            # Add footer with luck/crit info
            embed.set_footer(text=f"🍀 Luck: {crit_display:.1f}% | {'CRIT!' if is_critical else 'No crit'}")
            
            if counter_gif_url:
                embed.set_image(url=counter_gif_url)
            
            # Send with file attachment if using local image (use safe_send for embeds)
            if counter_file:
                await channel.send(file=counter_file, embed=embed)  # Files need direct send
            else:
                await self.safe_send(channel, embed=embed)
            
            # Add reaction to Tupper message (or original if not using Tupper)
            asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "✅"))
            
            # Delete the counter window message if exists
            if hasattr(self, 'counter_messages') and user_id in self.counter_messages:
                try:
                    await self.safe_delete_message(self.counter_messages[user_id])
                    del self.counter_messages[user_id]
                except:
                    pass
            
            # Console output
            crit_status = "[bold gold1]CRITICAL![/bold gold1] " if is_critical else ""
            console.print(Panel.fit(
                f"[bold gold1]⚡💥 {crit_status}COUNTER ATTACK! 💥⚡[/bold gold1]\n"
                f"[cyan]{message.author.display_name}[/cyan] landed a counter!\n"
                f"[yellow]Damage: {counter_damage} | Stun: {stun_duration:.1f}s | Luck: {crit_display:.1f}%[/yellow]",
                border_style="gold1"
            ))
            
            self.save_all_data()
            
        except Exception as e:
            console.print(f"[red]✗ Error in counter attack handler: {e}[/red]")
            log.error(f"Counter attack error: {e}")

    async def handle_adapt_command(self, message):
        """Handle *adapt* command - works during active QTE or counter window"""
        try:
            if message.channel.id != self.qte_channel_id:
                return
            
            user_id = self.resolve_user_id(message)
            channel = message.channel
            
            # Check if user has any adaptation objects IN THEIR INVENTORY
            adaptation_objects = [
                obj for obj in self.special_objects_manager.get_player_inventory(user_id)
                if obj.get('type') == 'adaptation'
            ]
            
            if not adaptation_objects:
                return  # No adaptation objects, ignore
            
            # TWO POSSIBLE SCENARIOS:
            # 1. During active QTE - use QTE timing window
            # 2. During counter window - no timing requirement, just execute
            
            user_has_active_qte = any(
                qte_data.get('target', {}).id == user_id or 
                user_id in [p for qte_data in self.active_qtes.values() for p in qte_data.get('participants', {})]
                for qte_data in self.active_qtes.values()
            )
            
            user_in_counter = user_id in self.counter_enabled_players
            
            # If neither active QTE nor counter, ignore
            if not user_has_active_qte and not user_in_counter:
                return
            
            # SCENARIO 1: Adapt during active QTE - must use QTE timing
            if user_has_active_qte:
                # Find the active QTE for this user
                for qte_id in list(self.active_qtes.keys()):
                    qte_data = self.active_qtes.get(qte_id)
                    if not qte_data:
                        continue
                    
                    target = qte_data.get('target')
                    if not target or target.id != user_id:
                        continue
                    
                    # Calculate response time
                    now = datetime.now(timezone.utc)
                    response_time = (now - qte_data['start']).total_seconds() - self.latency_offset
                    difficulty = qte_data['difficulty']
                    
                    # Check if within valid window (parry window for adaptation)
                    adj_parry_min, adj_parry_max = self.get_adjusted_parry_window(difficulty, user_id)
                    
                    # Adaptation uses parry timing
                    if not (adj_parry_min <= response_time <= adj_parry_max):
                        await self.webhook_send(content=f"❌ {message.author.mention} **adapt mistimed!** ({response_time:.2f}s)")
                        await self.damage_player(user_id, difficulty)
                        console.print(f"[red]✗ ADAPT FAILED (mistimed) - {message.author.name} at {response_time:.2f}s[/red]")
                        
                        asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "❌"))
                        
                        current_time = time.time()
                        self.last_qte_completion[user_id] = current_time
                        
                        is_batch = qte_data.get('batch_mode', False)
                        self.active_qtes.pop(qte_id, None)
                        self.save_all_data()
                        
                        if is_batch:
                            await self.process_next_player_qte(target)
                        return
                    
                    # ADAPT SUCCESS - Process all adaptation objects
                    results = await self.process_adaptation(user_id, difficulty, adaptation_objects, message)
                    
                    # Track adaptation as successful response
                    await self.update_player_stats(user_id, 'adapt', True, response_time)
                    
                    # Mark success
                    asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "🔮"))
                    
                    # Send success message with spin count (if no threshold was unlocked)
                    if not results.get('new_thresholds'):
                        # Show current spin progress
                        spin_info = []
                        for obj in adaptation_objects:
                            obj_id = obj['id']
                            tracking_config = obj.get('tracking', {})
                            tracking_type = tracking_config.get('type', 'per_difficulty')
                            
                            if tracking_type == 'total':
                                spins = self.special_objects_manager.get_tracking(user_id, obj_id, 'total')
                                spin_info.append(f"**{obj['name']}**: {spins} total spins")
                            else:
                                spins = self.special_objects_manager.get_tracking(user_id, obj_id, difficulty)
                                spin_info.append(f"**{obj['name']}**: {spins} {difficulty} spins")
                        
                        await self.webhook_send(
                            content=f"🔮 {message.author.mention} **adapted!** ({response_time:.2f}s)\n" + "\n".join(spin_info)
                        )
                    
                    console.print(f"[magenta]🔮 ADAPT SUCCESS (during QTE) - {message.author.name}[/magenta]")
                    
                    current_time = time.time()
                    self.last_qte_completion[user_id] = current_time
                    
                    is_batch = qte_data.get('batch_mode', False)
                    self.active_qtes.pop(qte_id, None)
                    self.save_all_data()
                    
                    if is_batch:
                        await self.process_next_player_qte(target)
                    return
            
            # SCENARIO 2: Adapt during counter window - instant success, no timing check needed
            elif user_in_counter:
                # Get the counter QTE ID to find difficulty
                counter_qte_id = self.counter_enabled_players[user_id]
                # Prefer stored counter context difficulty
                ctx = self.counter_context.get(user_id, {})
                difficulty = ctx.get('difficulty') or 'medium'
                
                # ADAPT SUCCESS - instant, no timing requirement during counter
                results = await self.process_adaptation(user_id, difficulty, adaptation_objects, message)
                
                # Track adaptation as successful response
                await self.update_player_stats(user_id, 'adapt', True, 0.0)
                
                # Mark success
                asyncio.create_task(self.add_reaction_to_response(channel, user_id, message, "🔮"))
                
                # Send success message
                if not results.get('new_thresholds'):
                    spin_info = []
                    for obj in adaptation_objects:
                        obj_id = obj['id']
                        tracking_config = obj.get('tracking', {})
                        tracking_type = tracking_config.get('type', 'per_difficulty')
                        
                        if tracking_type == 'total':
                            spins = self.special_objects_manager.get_tracking(user_id, obj_id, 'total')
                            spin_info.append(f"**{obj['name']}**: {spins} total spins")
                        else:
                            spins = self.special_objects_manager.get_tracking(user_id, obj_id, difficulty)
                            spin_info.append(f"**{obj['name']}**: {spins} {difficulty} spins")
                    
                    await self.webhook_send(
                        content=f"🔮 {message.author.mention} **adapted during counter!**\n" + "\n".join(spin_info)
                    )
                
                console.print(f"[magenta]🔮 ADAPT SUCCESS (during counter) - {message.author.name}[/magenta]")
                
                # Remove counter window
                del self.counter_enabled_players[user_id]
                # Clear stored counter context
                if user_id in self.counter_context:
                    del self.counter_context[user_id]
                
                # Delete counter window message if exists
                if hasattr(self, 'counter_messages') and user_id in self.counter_messages:
                    try:
                        await self.safe_delete_message(self.counter_messages[user_id])
                        del self.counter_messages[user_id]
                    except:
                        pass
                
                self.save_all_data()
                return
                
        except Exception as e:
            import traceback
            console.print(f"[red]✗ Error in adapt handler: {e}[/red]")
            console.print(f"[red]{traceback.format_exc()}[/red]")
            log.error(f"Adapt command error: {e}\n{traceback.format_exc()}")

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
                    'adapts': 0,
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
            elif action == 'adapt':
                stats['adapts'] = stats.get('adapts', 0) + 1

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
