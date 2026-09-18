"""
VIDEOCU v1 - Ken Burns Effect
Photo animations with zoom/pan effects
"""

import logging
from typing import Dict, List
import random

logger = logging.getLogger(__name__)


class KenBurnsEffect:
    """Ken Burns effect for photo animations"""

    ZOOM_IN = 'zoom_in'
    ZOOM_OUT = 'zoom_out'
    PAN_LEFT = 'pan_left'
    PAN_RIGHT = 'pan_right'
    ZOOM_PAN = 'zoom_pan'

    def __init__(self):
        logger.info("🎬 Ken Burns Effect initialized")

    def get_random_effect(self) -> str:
        """Get random effect type"""
        effects = [self.ZOOM_IN, self.ZOOM_OUT, self.PAN_LEFT, self.PAN_RIGHT, self.ZOOM_PAN]
        return random.choice(effects)

    def calculate_params(self, effect_type: str, duration: float, intensity: float = 0.2) -> Dict:
        """Calculate zoom/pan parameters"""
        intensity = max(0.1, min(0.5, intensity))

        params = {'duration': duration, 'effect_type': effect_type}

        if effect_type == self.ZOOM_IN:
            params['start_scale'] = 1.0
            params['end_scale'] = 1.0 + intensity
        elif effect_type == self.ZOOM_OUT:
            params['start_scale'] = 1.0 + intensity
            params['end_scale'] = 1.0
        elif effect_type == self.ZOOM_PAN:
            params['start_scale'] = 1.0
            params['end_scale'] = 1.0 + intensity

        return params

    def create_sequence(self, num_photos: int, duration_per_photo: float) -> List[Dict]:
        """Create effect sequence for multiple photos"""
        effects = []
        for i in range(num_photos):
            effect_type = self.get_random_effect()
            params = self.calculate_params(effect_type, duration_per_photo)
            effects.append(params)
        return effects
