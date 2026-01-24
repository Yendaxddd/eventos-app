"""
Event Orchestrator - Automated Game Master
Manages the narrative flow, scenarios, and custom mechanics for scripted events.
"""

import json
import asyncio
import logging
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .game_engine import GameSession
    from ..api.main import ConnectionManager

logger = logging.getLogger(__name__)

class EventOrchestrator:
    """
    Automated Game Master to run scripted events like 'Event 3'.
    """
    def __init__(self, campaign_id: str, event_script_path: str, session: 'GameSession', manager: 'ConnectionManager'):
        self.campaign_id = campaign_id
        self.event_script_path = event_script_path
        self.session = session
        self.manager = manager
        
        self.event_data: Dict[str, Any] = {}
        self.current_arc_index = 0
        self.current_scenario_index = 0
        self.is_running = False

    def load_event_script(self):
        """Loads the event script from a JSON file."""
        try:
            with open(self.event_script_path, 'r') as f:
                self.event_data = json.load(f)
            logger.info(f"Successfully loaded event script: {self.event_script_path}")
        except FileNotFoundError:
            logger.error(f"Event script not found at: {self.event_script_path}")
            self.event_data = {}
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON from: {self.event_script_path}")
            self.event_data = {}

    async def start_event(self):
        """Starts the event orchestration."""
        if not self.event_data:
            logger.error("Cannot start event without loaded event data.")
            return

        self.is_running = True
        logger.info(f"Starting event orchestration for campaign: {self.campaign_id}")
        await self.run_next_scenario()

    async def run_next_scenario(self):
        """Runs the next scenario in the event script."""
        if not self.is_running:
            return

        arcs = self.event_data.get('arcs', [])
        if self.current_arc_index >= len(arcs):
            logger.info("Event finished.")
            self.is_running = False
            await self._broadcast_event_update("Event Finished", "The story has concluded.")
            return

        current_arc = arcs[self.current_arc_index]
        scenarios = current_arc.get('scenarios', [])
        if self.current_scenario_index >= len(scenarios):
            # Move to the next arc
            self.current_arc_index += 1
            self.current_scenario_index = 0
            await self.run_next_scenario()
            return

        scenario = scenarios[self.current_scenario_index]
        logger.info(f"Running Arc {self.current_arc_index + 1}, Scenario {self.current_scenario_index + 1}: {scenario.get('title')}")
        
        # Execute scenario based on type
        scenario_type = scenario.get('type')
        payload = scenario.get('payload', {})
        
        if scenario_type == 'dialogue':
            await self._handle_dialogue(scenario['title'], payload)
        elif scenario_type == 'qte_sequence':
            await self._handle_qte_sequence(scenario['title'], payload)
        elif scenario_type == 'boss_fight':
            await self._handle_boss_fight(scenario['title'], payload)
        
        # Simulate time for the scenario to play out before moving to the next
        await asyncio.sleep(payload.get("duration", 10))

        # Move to the next scenario
        self.current_scenario_index += 1
        await self.run_next_scenario()

    async def _handle_dialogue(self, title: str, payload: Dict):
        """Handles a dialogue scenario."""
        await self._broadcast_event_update(title, payload.get('text', ''))

    async def _handle_qte_sequence(self, title: str, payload: Dict):
        """Handles a QTE sequence scenario."""
        await self._broadcast_event_update(title, payload.get('text', 'A series of challenges appear!'))
        
        for qte in payload.get('qtes', []):
            qte_data = self.session.trigger_qte(qte['difficulty'])
            await self.manager.broadcast_to_campaign(
                json.dumps({
                    "type": "qte_triggered",
                    "qte_id": qte_data["id"],
                    "difficulty": qte['difficulty'],
                    "timestamp": qte_data["start_time"],
                    "window": qte_data["window"]
                }),
                self.campaign_id
            )
            # Wait for QTE to resolve before starting the next
            await asyncio.sleep(qte_data["window"] + 1)

    async def _handle_boss_fight(self, title: str, payload: Dict):
        """Handles a boss fight scenario."""
        boss_name = payload.get('boss_name', 'Unknown Boss')
        hp = payload.get('hp', 1000)
        description = payload.get('description', '')
        
        self.session.boss_system.active_boss = self.session.boss_system.create_boss(boss_name, hp)
        await self._broadcast_event_update(title, description)
        await self.manager.broadcast_to_campaign(
            json.dumps({
                "type": "boss_created",
                "boss_name": boss_name,
                "boss_hp": hp,
                "boss_max_hp": hp
            }),
            self.campaign_id
        )
        # Here you would typically wait for the boss to be defeated
        # For now, we'll just simulate a fight duration
        
    async def _broadcast_event_update(self, title: str, text: str):
        """Broadcasts a narrative update to all players in the campaign."""
        await self.manager.broadcast_to_campaign(
            json.dumps({
                "type": "narrative_update",
                "title": title,
                "text": text
            }),
            self.campaign_id
        )

    def stop_event(self):
        """Stops the event orchestration."""
        self.is_running = False
        logger.info(f"Stopping event orchestration for campaign: {self.campaign_id}")
