"""
Eventos App - Main FastAPI Application
Fast-track implementation for December deadline
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import json
import time
from typing import Dict, List, Set
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import game engine
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.game_engine import GameSession
from core.event_orchestrator import EventOrchestrator

# Import routes (we'll create these next)
# from api.routes import auth, campaigns, characters, combat
# from api.bridge.discord_bridge import DiscordBridge

# Global game state with game engine
class GameState:
    def __init__(self):
        self.active_campaigns: Dict[str, GameSession] = {}
        self.connected_players: Dict[str, WebSocket] = {}
        self.event_orchestrators: Dict[str, EventOrchestrator] = {}
        
game_state = GameState()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.campaign_connections: Dict[str, Set[str]] = {}  # campaign_id -> set of user_ids

    async def connect(self, websocket: WebSocket, user_id: str, campaign_id: str = None):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        if campaign_id:
            if campaign_id not in self.campaign_connections:
                self.campaign_connections[campaign_id] = set()
            self.campaign_connections[campaign_id].add(user_id)
        logger.info(f"Player {user_id} connected to campaign {campaign_id}")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        # Remove from all campaigns
        for campaign_id in self.campaign_connections:
            self.campaign_connections[campaign_id].discard(user_id)
        logger.info(f"Player {user_id} disconnected")

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def broadcast_to_campaign(self, message: str, campaign_id: str):
        if campaign_id in self.campaign_connections:
            for user_id in self.campaign_connections[campaign_id]:
                if user_id in self.active_connections:
                    try:
                        await self.active_connections[user_id].send_text(message)
                    except:
                        pass

manager = ConnectionManager()

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Eventos App starting...")
    # Initialize game systems here
    yield
    # Shutdown
    logger.info("🛑 Eventos App shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Eventos App",
    description="Real-time RPG campaign system with QTE mechanics",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development (including file://)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic health check
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Eventos App Backend Running",
        "version": "1.0.0",
        "active_campaigns": len(game_state.active_campaigns),
        "connected_players": len(manager.active_connections)
    }

# Health endpoint (for API bridge)
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

# Simple damage calculation endpoint (no campaigns, no WebSocket needed)
@app.post("/api/calculate_damage")
async def calculate_damage(payload: dict):
    """
    Simple damage calculation for Discord bot - no campaign needed
    Just calculates damage using the corrected formula
    
    Payload: {
        "user_id": str,
        "text": str
    }
    
    Returns: {
        "damage": int,
        "base_damage": int,
        "combo_multiplier": float,
        "combo_count": int,
        "quality_bonus": int,
        "action": str,
        "nlp_confidence": float
    }
    """
    user_id = payload.get("user_id")
    text = payload.get("text", "")
    
    if not user_id or not text:
        raise HTTPException(status_code=400, detail="Missing user_id or text")
    
    # Use a temporary session just for calculation
    # This keeps combo tracking per user in memory
    campaign_id = "_discord_temp"
    
    if campaign_id not in game_state.active_campaigns:
        game_state.active_campaigns[campaign_id] = GameSession()
    
    session = game_state.active_campaigns[campaign_id]
    
    # Add player if they don't exist
    if user_id not in session.players:
        session.add_player(user_id)
    
    # Calculate damage using corrected formula
    result = session.process_free_attack(user_id, text)
    
    if result:
        return result
    else:
        raise HTTPException(status_code=500, detail="Damage calculation failed")

# WebSocket endpoint for real-time game communication
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            await handle_websocket_message(user_id, message)
            
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        manager.disconnect(user_id)

async def handle_websocket_message(user_id: str, message: dict):
    """Handle incoming WebSocket messages"""
    msg_type = message.get("type")
    
    if msg_type == "join_campaign":
        campaign_id = message.get("campaign_id")
        await handle_join_campaign(user_id, campaign_id)
        
    elif msg_type == "qte_response":
        await handle_qte_response(user_id, message)
        
    elif msg_type == "action":
        await handle_player_action(user_id, message)
        
    elif msg_type == "ping":
        await manager.send_personal_message(json.dumps({"type": "pong"}), user_id)

# Game event handlers
async def handle_join_campaign(user_id: str, campaign_id: str):
    """Handle player joining a campaign"""
    if not campaign_id:
        logger.warning("join_campaign failed: campaign_id is missing.")
        return

    if campaign_id not in manager.campaign_connections:
        manager.campaign_connections[campaign_id] = set()
    manager.campaign_connections[campaign_id].add(user_id)
    
    # Create campaign session if it doesn't exist
    if campaign_id not in game_state.active_campaigns:
        game_state.active_campaigns[campaign_id] = GameSession()
    
    # Add player to game session
    session = game_state.active_campaigns[campaign_id]
    player = session.add_player(user_id)
    
    # Notify campaign
    await manager.broadcast_to_campaign(
        json.dumps({
            "type": "player_joined",
            "user_id": user_id,
            "campaign_id": campaign_id,
            "hp": player["hp"]
        }),
        campaign_id
    )

async def handle_qte_response(user_id: str, message: dict):
    """Handle QTE response from player"""
    qte_id = message.get("qte_id")
    action = message.get("action")  # evade, parry, save
    response_time_str = message.get("response_time")
    campaign_id = message.get("campaign_id")

    if not all([qte_id, action, response_time_str, campaign_id]):
        logger.warning(f"QTE response from {user_id} missing required fields.")
        return

    # Asserting types to satisfy linter after the check
    assert isinstance(qte_id, str)
    assert isinstance(action, str)
    assert isinstance(campaign_id, str)

    if campaign_id not in game_state.active_campaigns:
        logger.warning(f"Campaign {campaign_id} not found for QTE response from {user_id}.")
        return

    try:
        response_time = float(response_time_str)
    except (ValueError, TypeError):
        logger.warning(f"Invalid response_time format from {user_id}: {response_time_str}")
        return

    # Process with game engine
    session = game_state.active_campaigns[campaign_id]
    result = session.process_qte_response(user_id, qte_id, action, response_time)
    
    # Broadcast result
    await manager.broadcast_to_campaign(json.dumps({
        "type": "qte_result",
        "user_id": user_id,
        "qte_id": qte_id,
        "action": action,
        "success": result.get("success", False),
        "response_time": response_time,
        "special": result.get("special")
    }), campaign_id)
    
    # Send HP update if damaged
    if result.get("damage", 0) > 0:
        player = session.players.get(user_id)
        if player:
            await manager.broadcast_to_campaign(json.dumps({
                "type": "hp_update",
                "user_id": user_id,
                "hp": player["hp"]
            }), campaign_id)
            
    # Send stats and power update
    player = session.players.get(user_id)
    if player:
        await manager.broadcast_to_campaign(json.dumps({
            "type": "stats_update",
            "user_id": user_id,
            "stats": player["stats"]
        }), campaign_id)
        
        await manager.broadcast_to_campaign(json.dumps({
            "type": "power_update",
            "user_id": user_id,
            "power": player["power"]
        }), campaign_id)
        
    # Send boss HP update
    if session.boss_system.active_boss:
        await manager.broadcast_to_campaign(json.dumps({
            "type": "boss_hp_update",
            "boss_hp": session.boss_system.active_boss["hp_current"],
            "boss_max_hp": session.boss_system.active_boss["hp_max"]
        }), campaign_id)

async def handle_player_action(user_id: str, message: dict):
    """Handle general player actions"""
    action_type = message.get("action_type")
    campaign_id = message.get("campaign_id")
    
    if not all([action_type, campaign_id]):
        return
        
    if campaign_id not in game_state.active_campaigns:
        return
        
    session = game_state.active_campaigns[campaign_id]
    player = session.players.get(user_id)
    
    if not player:
        return
        
    # Process different action types
    if action_type == "attack":
        text = message.get("text", "")
        result = session.process_free_attack(user_id, text)
        
        if result:
            # Broadcast attack result
            await manager.broadcast_to_campaign(
                json.dumps({
                    "type": "attack_result",
                    "user_id": user_id,
                    "damage": result["damage"],
                    "combo_multiplier": result["combo_multiplier"],
                    "quality_bonus": result["quality_bonus"],
                    "action": result["action"]
                }),
                campaign_id
            )
            
            # Send boss HP update
            if session.boss_system.active_boss:
                await manager.broadcast_to_campaign(json.dumps({
                    "type": "boss_hp_update",
                    "boss_hp": session.boss_system.active_boss["hp_current"],
                    "boss_max_hp": session.boss_system.active_boss["hp_max"]
                }), campaign_id)
        
    elif action_type == "heal":
        # Handle heal action
        pass
    elif action_type == "power":
        # Handle power activation
        pass

# QTE trigger endpoint (for testing)
@app.post("/api/trigger_qte")
async def trigger_qte(campaign_id: str, difficulty: str = "medium"):
    """Trigger a QTE event for a campaign"""
    if campaign_id not in game_state.active_campaigns:
        game_state.active_campaigns[campaign_id] = GameSession()
    
    session = game_state.active_campaigns[campaign_id]
    qte_data = session.trigger_qte(difficulty)
    
    # Broadcast to campaign
    await manager.broadcast_to_campaign(json.dumps({
        "type": "qte_triggered",
        "qte_id": qte_data["id"],
        "difficulty": difficulty,
        "timestamp": qte_data["start_time"],
        "window": qte_data["window"]
    }), campaign_id)
    
    # Set timeout to clear QTE
    asyncio.create_task(clear_qte_after_timeout(qte_data["id"], qte_data["window"], session))
    
    return {"success": True, "qte_id": qte_data["id"]}

async def clear_qte_after_timeout(qte_id: str, timeout: float, session: GameSession):
    """Clear QTE after timeout"""
    await asyncio.sleep(timeout + 1)
    if qte_id in session.active_qtes:
        del session.active_qtes[qte_id]

# Endpoint to create a boss
@app.post("/api/boss/create")
async def create_boss(campaign_id: str, name: str = "Test Boss", hp: int = 1000):
    """Create a boss for a campaign"""
    if campaign_id not in game_state.active_campaigns:
        return {"error": "Campaign not found"}
    
    session = game_state.active_campaigns[campaign_id]
    session.boss_system.active_boss = session.boss_system.create_boss(name, hp)
    
    # Notify campaign
    await manager.broadcast_to_campaign(
        json.dumps({
            "type": "boss_created",
            "boss_name": name,
            "boss_hp": hp,
            "boss_max_hp": hp
        }),
        campaign_id
    )
    
    return {"success": True, "boss": session.boss_system.active_boss}

# Quick campaign creation for testing
@app.post("/api/campaigns/quick_create")
async def quick_create_campaign(name: str = "Test Campaign"):
    """Quick campaign creation for rapid testing"""
    campaign_id = f"campaign_{int(time.time() * 1000)}"
    
    # Create new game session
    game_state.active_campaigns[campaign_id] = GameSession()
    
    return {
        "success": True,
        "campaign_id": campaign_id,
        "name": name,
        "join_url": f"ws://localhost:8000/ws/USER_ID?campaign={campaign_id}"
    }

# Player action endpoint (for Discord bot integration)
@app.post("/api/players/{user_id}/action")
async def process_player_action(user_id: str, payload: dict):
    """Process a player action (attack, heal, power, etc.)"""
    campaign_id = payload.get("campaign_id", "discord_campaign")
    action_type = payload.get("action_type")
    
    # Create campaign if it doesn't exist
    if campaign_id not in game_state.active_campaigns:
        game_state.active_campaigns[campaign_id] = GameSession()
    
    session = game_state.active_campaigns[campaign_id]
    
    # Add player if they don't exist
    if user_id not in session.players:
        session.add_player(user_id)
    
    if action_type == "attack":
        text = payload.get("text", "")
        result = session.process_free_attack(user_id, text)
        
        if result:
            # Broadcast to connected WebSocket clients if any
            if campaign_id in manager.campaign_connections:
                await manager.broadcast_to_campaign(
                    json.dumps({
                        "type": "attack_result",
                        "user_id": user_id,
                        "damage": result["damage"],
                        "combo_multiplier": result["combo_multiplier"],
                        "quality_bonus": result["quality_bonus"],
                        "action": result["action"]
                    }),
                    campaign_id
                )
            
            # Update boss HP if there is one
            if session.boss_system.active_boss and campaign_id in manager.campaign_connections:
                await manager.broadcast_to_campaign(json.dumps({
                    "type": "boss_hp_update",
                    "boss_hp": session.boss_system.active_boss["hp_current"],
                    "boss_max_hp": session.boss_system.active_boss["hp_max"]
                }), campaign_id)
            
            return result
        else:
            return {"error": "Attack failed"}
    
    return {"error": "Unknown action type"}

# Player stats endpoint
@app.get("/api/players/{user_id}/stats")
async def get_player_stats(user_id: str, campaign_id: str = "default"):
    """Get player statistics"""
    if campaign_id not in game_state.active_campaigns:
        return {"error": "Campaign not found"}
    
    session = game_state.active_campaigns[campaign_id]
    if user_id in session.players:
        return session.players[user_id]["stats"]
    else:
        return {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "best_time": float('inf'),
            "black_flashes": 0
        }

# HP update endpoint
@app.post("/api/players/{user_id}/hp")
async def update_player_hp(user_id: str, hp_change: int, campaign_id: str = "default"):
    """Update player HP (damage or heal)"""
    if campaign_id not in game_state.active_campaigns:
        return {"error": "Campaign not found"}
    
    session = game_state.active_campaigns[campaign_id]
    if user_id not in session.players:
        session.add_player(user_id)
    
    player = session.players[user_id]
    if hp_change > 0:
        player["hp"] = session.hp_system.heal_player(player["hp"], hp_change)
    else:
        player["hp"] = session.hp_system.apply_damage(player["hp"], abs(hp_change))
    
    # Broadcast HP update
    update = {
        "type": "hp_update",
        "user_id": user_id,
        "hp": player["hp"]
    }
    
    await manager.broadcast_to_campaign(json.dumps(update), campaign_id)
    
    return player["hp"]

# Endpoint to start a scripted event
@app.post("/api/events/start")
async def start_event(campaign_id: str, event_script: str = "event3_script.json"):
    """Starts a scripted event for a campaign using the orchestrator."""
    if campaign_id not in game_state.active_campaigns:
        return {"error": "Campaign not found. Create one first."}

    if campaign_id in game_state.event_orchestrators and game_state.event_orchestrators[campaign_id].is_running:
        return {"error": "Event is already running for this campaign."}

    # Path to the event script in the 'data' directory
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', event_script)

    session = game_state.active_campaigns[campaign_id]
    orchestrator = EventOrchestrator(campaign_id, script_path, session, manager)
    orchestrator.load_event_script()

    if not orchestrator.event_data:
        return {"error": f"Failed to load event script: {event_script}"}

    game_state.event_orchestrators[campaign_id] = orchestrator
    
    # Start the event in the background
    asyncio.create_task(orchestrator.start_event())
    
    return {"success": True, "message": f"Event '{event_script}' started for campaign '{campaign_id}'."}


if __name__ == "__main__":
    import uvicorn
    # Run with: python main.py
    uvicorn.run(app, host="0.0.0.0", port=7000, reload=True)
