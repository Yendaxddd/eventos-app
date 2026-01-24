"""
Simple Discord Bot <-> Eventos App API Bridge
Just calculates damage - no campaigns, no WebSocket, no complexity
"""

import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("SimpleAPIBridge")

class SimpleEventosAPI:
    """Simplified bridge for Discord bot - just damage calculations"""
    
    def __init__(self, api_base_url: str = "http://localhost:7001"):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Test connection
        try:
            response = self.session.get(f"{self.api_base_url}/", timeout=3)
            if response.status_code == 200:
                logger.info(f"✓ Connected to Eventos API at {api_base_url}")
            else:
                logger.warning(f"⚠ API connection status: {response.status_code}")
        except Exception as e:
            logger.error(f"✗ Failed to connect to API: {e}")
    
    def calculate_attack_damage(self, user_id: str, attack_text: str) -> Optional[Dict[str, Any]]:
        """
        Calculate attack damage using the API's corrected formula
        No campaign needed - just pure calculation
        
        Returns:
            dict with: {
                'damage': int,
                'base_damage': int,
                'combo_multiplier': float,
                'combo_count': int,
                'quality_bonus': int,
                'action': str,
                'nlp_confidence': float
            }
        """
        try:
            payload = {
                "user_id": user_id,
                "text": attack_text
            }
            
            response = self.session.post(
                f"{self.api_base_url}/api/calculate_damage",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Damage calculated: {result.get('damage', 0)} for user {user_id}")
                return result
            else:
                logger.error(f"Damage calculation failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calculating damage: {e}")
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
from simple_api_bridge import SimpleEventosAPI

api = SimpleEventosAPI("http://localhost:7000")

# Check if API is available
if api.health_check():
    print("✓ API connected - using corrected damage formula")
else:
    print("⚠ API unavailable - using fallback calculations")

# When processing NLP attack:
result = api.calculate_attack_damage(str(user_id), attack_text)
if result:
    damage = result['damage']
    combo_multiplier = result['combo_multiplier']
    quality_bonus = result['quality_bonus']
    
    # Apply damage to boss and display in Discord
    await damage_boss(boss_name, damage)
    await ctx.send(f"💥 {damage} damage! (x{combo_multiplier} combo, +{quality_bonus} quality)")
else:
    # Fallback to original bot calculation
    damage = calculate_damage_locally(attack_text)
    await damage_boss(boss_name, damage)
"""
