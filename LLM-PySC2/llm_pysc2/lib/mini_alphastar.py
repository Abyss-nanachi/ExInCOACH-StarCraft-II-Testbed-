
import sys
import os
import random
import traceback
from loguru import logger

# Add mini-AlphaStar to path
# Assuming this file is at .../LLM-PySC2/llm_pysc2/lib/mini_alphastar.py
# We need to point to .../mini-AlphaStar
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MINI_ALPHASTAR_PATH = os.path.abspath(os.path.join(CURRENT_DIR, "../../../mini-AlphaStar"))
sys.path.append(MINI_ALPHASTAR_PATH)

try:
    from alphastarmini.core.rl.alphastar_agent import AlphaStarAgent
    from pysc2.lib import actions, features
    from pysc2.env import sc2_env
except ImportError as e:
    logger.error(f"Failed to import mini-AlphaStar: {e}")
    AlphaStarAgent = None

class MiniAlphaStar:
    def __init__(self):
        self.agent = None
        if AlphaStarAgent:
            try:
                self.agent = AlphaStarAgent(name='MiniAlphaStar', race=sc2_env.Race.protoss)
                logger.success("MiniAlphaStar Agent initialized successfully.")
            except Exception as e:
                logger.error(f"Error initializing AlphaStarAgent: {e}")
        
        self.last_action = None
        self.last_decision_text = "Initializing..."

    def get_decision(self, obs):
        if not self.agent:
            return "MiniAlphaStar Agent not loaded."

        try:
            # AlphaStarAgent expects observation.
            # obs passed here is likely the one from LLMAgent.update(obs) which is a TimeStep
            
            # The agent.step() returns a FunctionCall
            func_call = self.agent.step(obs)
            self.last_action = func_call
            
            # Convert FunctionCall to readable text
            func_id = func_call.function
            func_name = actions.FUNCTIONS[func_id].name
            args = func_call.arguments
            
            decision_text = f"Action: {func_name} Args: {args}"
            self.last_decision_text = decision_text
            return decision_text

        except Exception as e:
            err_msg = f"Error in decision: {str(e)}"
            # logger.error(err_msg)
            # traceback.print_exc()
            return err_msg

    def get_visual_cues(self, obs):
        cues = []
        if not self.last_action:
            return cues

        try:
            func_id = self.last_action.function
            args = self.last_action.arguments
            func_name = actions.FUNCTIONS[func_id].name

            # Helper to get screen center
            screen_w = 640 # Default?
            screen_h = 480
            center_x = screen_w // 2
            center_y = screen_h // 2
            
            # 1. Attack Actions (Arrow)
            if 'Attack' in func_name:
                target = None
                if 'screen' in func_name and len(args) > 0:
                    target = args[0] # [x, y]
                elif 'minimap' in func_name and len(args) > 0:
                    # Map minimap to screen roughly or just show direction
                    target = [args[0][0] * (screen_w / 64), args[0][1] * (screen_h / 64)] # Approx scaling
                
                if target:
                    cues.append({
                        'type': 'arrow',
                        'start': [center_x, center_y],
                        'end': [int(target[0]), int(target[1])],
                        'color': 'red',
                        'text': 'Attack'
                    })

            # 2. Build Actions (Box)
            elif 'Build' in func_name and 'screen' in func_name:
                if len(args) > 0:
                    target = args[0]
                    cues.append({
                        'type': 'box',
                        'start': [int(target[0]) - 20, int(target[1]) - 20],
                        'end': [int(target[0]) + 20, int(target[1]) + 20],
                        'color': 'green',
                        'text': func_name.split('_')[1] if '_' in func_name else 'Build'
                    })

            # 3. Move Actions (Arrow)
            elif 'Move' in func_name:
                if len(args) > 0:
                    target = args[0]
                    cues.append({
                        'type': 'arrow',
                        'start': [center_x, center_y],
                        'end': [int(target[0]), int(target[1])],
                        'color': 'blue',
                        'text': 'Move'
                    })

            # 4. Selection (Circle)
            elif 'select' in func_name:
                if len(args) > 0:
                    # Some select actions take point, some rect
                    if 'rect' in func_name and len(args) >= 2:
                        p1 = args[0]
                        p2 = args[1]
                        cues.append({
                            'type': 'box',
                            'start': [int(p1[0]), int(p1[1])],
                            'end': [int(p2[0]), int(p2[1])],
                            'color': 'yellow',
                            'text': 'Select'
                        })
                    elif 'point' in func_name:
                        target = args[0]
                        cues.append({
                            'type': 'circle',
                            'center': [int(target[0]), int(target[1])],
                            'radius': 20,
                            'color': 'yellow',
                            'text': 'Select'
                        })

        except Exception as e:
            logger.error(f"Error generating cues: {e}")

        return cues
