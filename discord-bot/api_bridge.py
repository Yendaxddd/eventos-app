"""
Discord Bot <-> Eventos App API Bridge
Connects the legacy Discord bot to the new FastAPI backend
"""

import requests
import logging
from typing import Optional, Dict, Any
import json

logger = logging.getLogger("API_Bridge")

class EventosAPIBridge:
    """Bridge to connect Discord bot to Eventos App backend"""
    
    def __init__(self, api_base_url: str = "http://localhost:7000"):
        self.api_base_url = api_base_url
        self.campaign_id = "discord_campaign"  # Default campaign for Discord bot
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Test connection
        try:
            response = self.session.get(f"{self.api_base_url}/")
            if response.status_code == 200:
                logger.info(f"✓ Connected to Eventos API at {api_base_url}")
            else:
                logger.warning(f"⚠ API connection status: {response.status_code}")
        except Exception as e:
            logger.error(f"✗ Failed to connect to API: {e}")
    
    def ensure_campaign(self) -> bool:
        """Ensure the Discord campaign exists"""
        try:
            # The campaign will be auto-created when players join
            return True
        except Exception as e:
            logger.error(f"Error ensuring campaign: {e}")
            return False
    
    def process_free_attack(self, user_id: str, attack_text: str) -> Optional[Dict[str, Any]]:
        """
        Process a free attack using the API's corrected damage formula
        
        Returns:
            dict with: {
                'damage': int,
                'base_damage': int,
                'combo_multiplier': float,
                'combo_count': int,
                'quality_bonus': int,
                'nlp_confidence': float,
                'action': str
            }
        """
        try:
            # Use the internal game session directly via HTTP
            # We'll need to add an endpoint for this
            payload = {
                "campaign_id": self.campaign_id,
                "action_type": "attack",
                "text": attack_text
            }
            
            response = self.session.post(
                f"{self.api_base_url}/api/players/{user_id}/action",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Attack processed: {result.get('damage', 0)} damage")
                return result
            else:
                logger.error(f"Attack failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing attack: {e}")
            return None
    
    def trigger_qte(self, difficulty: str = "medium") -> Optional[Dict[str, Any]]:
        """Trigger a QTE event via API"""
        try:
            response = self.session.post(
                f"{self.api_base_url}/api/trigger_qte",
                params={"campaign_id": self.campaign_id, "difficulty": difficulty},
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            logger.error(f"Error triggering QTE: {e}")
            return None
    
    def process_qte_response(self, user_id: str, qte_id: str, action: str, response_time: float) -> Optional[Dict[str, Any]]:
        """Process QTE response via API"""
        try:
            payload = {
                "campaign_id": self.campaign_id,
                "qte_id": qte_id,
                "action": action,
                "response_time": response_time
            }
            
            response = self.session.post(
                f"{self.api_base_url}/api/players/{user_id}/qte_response",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            logger.error(f"Error processing QTE response: {e}")
            return None
    
    def create_boss(self, name: str, hp: int) -> Optional[Dict[str, Any]]:
        """Create a boss via API"""
        try:
            response = self.session.post(
                f"{self.api_base_url}/api/boss/create",
                params={
                    "campaign_id": self.campaign_id,
                    "name": name,
                    "hp": hp
                },
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            logger.error(f"Error creating boss: {e}")
            return None
    
    def get_player_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get player statistics via API"""
        try:
            response = self.session.get(
                f"{self.api_base_url}/api/players/{user_id}/stats",
                params={"campaign_id": self.campaign_id},
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            logger.error(f"Error getting player stats: {e}")
            return None
    
    def update_player_hp(self, user_id: str, hp_change: int) -> Optional[Dict[str, Any]]:
        """Update player HP via API (positive = heal, negative = damage)"""
        try:
            response = self.session.post(
                f"{self.api_base_url}/api/players/{user_id}/hp",
                params={
                    "campaign_id": self.campaign_id,
                    "hp_change": hp_change
                },
                timeout=5
            )
            
            if response.status_code == 200:
                return response.json()
            return None
            
        except Exception as e:
            logger.error(f"Error updating player HP: {e}")
            return None
    
    def health_check(self) -> bool:
        """Check if API is accessible"""
        try:
            response = self.session.get(f"{self.api_base_url}/", timeout=3)
            return response.status_code == 200
        except:
            return False


# Example usage in Discord bot:
"""
# In your Discord bot initialization:
from api_bridge import EventosAPIBridge

api_bridge = EventosAPIBridge("http://localhost:7000")

# When processing NLP attack:
result = api_bridge.process_free_attack(user_id, attack_text)
if result:
    damage = result['damage']
    combo = result['combo_multiplier']
    # Use the damage value in Discord messages
"""
