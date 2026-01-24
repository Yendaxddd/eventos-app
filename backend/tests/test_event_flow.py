"""
Automated Test for Event 3 Flow
- Connects a test player via WebSocket
- Starts the scripted event
- Listens for and validates incoming events
- Automatically responds to QTEs
"""

import asyncio
import websockets
import json
import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Test Configuration ---
BASE_URL = "http://localhost:8000"
WEBSOCKET_URL = "ws://localhost:8000/ws"
TEST_PLAYER_ID = "EventTestPlayer"
CAMPAIGN_ID = f"test_campaign_{int(time.time())}"

async def run_test():
    """Main function to run the automated event test."""
    logger.info("--- Starting Automated Event Flow Test ---")

    # 1. Create a test campaign
    try:
        response = requests.post(f"{BASE_URL}/api/campaigns/quick_create", params={"name": CAMPAIGN_ID})
        response.raise_for_status()
        campaign_id = response.json().get("campaign_id")
        if not campaign_id:
            logger.error("Failed to create campaign.")
            return
        logger.info(f"Successfully created campaign: {campaign_id}")
    except requests.RequestException as e:
        logger.error(f"Failed to create campaign: {e}")
        return

    # 2. Connect to WebSocket and join campaign
    websocket_uri = f"{WEBSOCKET_URL}/{TEST_PLAYER_ID}"
    async with websockets.connect(websocket_uri) as websocket:
        logger.info(f"Connected to WebSocket at {websocket_uri}")

        # Join the campaign
        await websocket.send(json.dumps({
            "type": "join_campaign",
            "campaign_id": campaign_id
        }))
        logger.info(f"Sent 'join_campaign' message for campaign: {campaign_id}")
        
        # Listen for join confirmation
        join_confirmation = await websocket.recv()
        logger.info(f"Received: {join_confirmation}")

        # 3. Start the event
        try:
            logger.info("Triggering event start...")
            start_response = requests.post(
                f"{BASE_URL}/api/events/start",
                params={"campaign_id": campaign_id, "event_script": "event3_script.json"}
            )
            start_response.raise_for_status()
            logger.info(f"Event start response: {start_response.json()}")
        except requests.RequestException as e:
            logger.error(f"Failed to start event: {e}")
            return

        # 4. Listen for and handle events
        try:
            while True:
                message_str = await asyncio.wait_for(websocket.recv(), timeout=20.0)
                message = json.loads(message_str)
                event_type = message.get("type")
                logger.info(f"Received event: {event_type}")
                
                if event_type == "narrative_update":
                    logger.info(f"  > Narrative: {message.get('title')} - {message.get('text')}")
                
                elif event_type == "qte_triggered":
                    qte_id = message.get("qte_id")
                    logger.info(f"  > QTE Triggered: {qte_id}. Responding 'evade'...")
                    # Respond to QTE automatically
                    await websocket.send(json.dumps({
                        "type": "qte_response",
                        "qte_id": qte_id,
                        "action": "evade",
                        "response_time": 1.0,
                        "campaign_id": campaign_id
                    }))

                elif event_type == "boss_created":
                    logger.info(f"  > Boss Created: {message.get('boss_name')}")

                elif event_type == "event_finished":
                    logger.info("--- Event Finished Successfully ---")
                    break

        except asyncio.TimeoutError:
            logger.error("Test failed: Timed out waiting for event.")
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed.")
            
    logger.info("--- Automated Test Finished ---")

if __name__ == "__main__":
    # Ensure the server is running before executing this test
    # You can run it with: python -m backend.tests.test_event_flow
    asyncio.run(run_test())
