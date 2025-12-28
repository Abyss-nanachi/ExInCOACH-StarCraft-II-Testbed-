import sys
import os
import json
import time
import math
import traceback
import numpy as np
import torch
from absl import app, flags
from pysc2.env import sc2_env
from pysc2.lib import actions, features, units

# Add paths to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "mini-AlphaStar"))
sys.path.append(os.path.join(os.path.dirname(__file__), "LLM-PySC2"))

# Mini-AlphaStar imports
from alphastarmini.core.rl.alphastar_agent import AlphaStarAgent
from alphastarmini.core.arch.agent import Agent as ArchAgent
import param as P

# LLM-PySC2 imports
# We will implement a simplified observation processor based on llm_observation ideas
# to avoid complex dependency on LLMAgent configuration

from visual_cues import action_to_cues

FLAGS = flags.FLAGS
flags.DEFINE_string("map", "Simple64", "Name of a map to use.")
flags.DEFINE_string("agent_race", "P", "Agent race.")
flags.DEFINE_string("bot_race", "T", "Bot race.")
flags.DEFINE_string("difficulty", "1", "Bot difficulty.")

OVERLAY_FILE = "overlay_data.json"
MODEL_FILE = "models/alphastar_model.pth"

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

class VisualCue:
    def __init__(self, type, **kwargs):
        self.type = type
        self.data = kwargs

    def to_dict(self):
        d = {"type": self.type}
        d.update(self.data)
        return d

class SimpleObserver:
    def __init__(self):
        pass

    def get_text_observation(self, obs):
        """Generates a natural language description of the current game state."""
        try:
            observation = obs.observation
            
            # 1. Game Info (Time, Resources)
            game_loop = observation.game_loop
            if hasattr(game_loop, 'item'):
                game_loop = game_loop.item()
            
            game_m = int(game_loop / 22.4 // 60)
            game_s = int(game_loop / 22.4 % 60)
            
            # Get race info
            race_map = {'P': 'Protoss', 'T': 'Terran', 'Z': 'Zerg', 'R': 'Random'}
            current_race = race_map.get(FLAGS.agent_race, FLAGS.agent_race)
            
            player = observation.player
            # Player info: [player_id, minerals, vespene, food_used, food_cap, food_army, food_workers, idle_worker_count, army_count, warp_gate_count, larva_count]
            minerals = int(player[1])
            vespene = int(player[2])
            supply_used = int(player[3])
            supply_cap = int(player[4])
            
            text = f"Time: {game_m:02d}:{game_s:02d}\n"
            text += f"Race: {current_race}\n"
            text += f"Resources: {minerals} M, {vespene} G\n"
            text += f"Supply: {supply_used}/{supply_cap}\n"
            
            # 2. Units on Screen
            if 'feature_units' in observation:
                feature_units = observation.feature_units
                # Count visible units
                my_units = {}
                enemy_units = {}
                
                for unit in feature_units:
                    if unit.alliance == features.PlayerRelative.SELF:
                        u_type = unit.unit_type
                        my_units[u_type] = my_units.get(u_type, 0) + 1
                    elif unit.alliance == features.PlayerRelative.ENEMY:
                        u_type = unit.unit_type
                        enemy_units[u_type] = enemy_units.get(u_type, 0) + 1
                
                if my_units:
                    text += "My Units on Screen:\n"
                    for ut, count in my_units.items():
                        # We would need a unit type ID to name mapping here
                        # For now, just show ID or simple name if possible
                        text += f"  Type {ut}: {count}\n"
                        
                if enemy_units:
                    text += "Enemy Units on Screen:\n"
                    for ut, count in enemy_units.items():
                        text += f"  Type {ut}: {count}\n"
            
            return text
        except Exception as e:
            return f"Error generating observation: {str(e)}"


def main(unused_argv):
    # Initialize Mini-AlphaStar Agent
    # Note: AlphaStarAgent needs specific setup. 
    # For this prototype, we'll try to use it as simply as possible.
    # If it fails, we fall back to a RandomAgent for testing the pipeline.
    
    initial_weights = None
    model_path = os.path.join(os.path.dirname(__file__), MODEL_FILE)
    if os.path.exists(model_path):
        print(f"Found model file at {model_path}, loading...")
        try:
            initial_weights = torch.load(model_path, map_location='cpu')
            print("Model weights loaded successfully.")
        except Exception as e:
            print(f"Failed to load model weights: {e}")
            print("Falling back to random initialization.")
    else:
        print(f"No model file found at {model_path}. Using random initialization.")

    agent = AlphaStarAgent(name="AlphaStar", initial_weights=initial_weights)
    
    # Setup Agent (normally done by Coordinator)
    # We need to define observation and action specs.
    # SC2Env will provide these.
    
    try:
        with sc2_env.SC2Env(
            map_name=FLAGS.map,
            players=[sc2_env.Agent(sc2_env.Race.protoss),
                     sc2_env.Bot(sc2_env.Race.terran, sc2_env.Difficulty.very_easy)],
            agent_interface_format=features.AgentInterfaceFormat(
                feature_dimensions=features.Dimensions(screen=64, minimap=64),
                raw_resolution=64,
                use_feature_units=True,
                use_raw_units=True,
                use_unit_counts=True),
            step_mul=8,
            game_steps_per_episode=0,
            visualize=False,
            realtime=True,
            random_seed=1) as env:
            
            agent.setup(env.observation_spec(), env.action_spec())
            
            # Fix: Unpack specs if they are lists/tuples (PySC2 behavior)
            obs_spec = env.observation_spec()
            action_spec = env.action_spec()
            if isinstance(obs_spec, (list, tuple)):
                obs_spec = obs_spec[0]
            if isinstance(action_spec, (list, tuple)):
                action_spec = action_spec[0]
            agent.setup(obs_spec, action_spec)
            
            observer = SimpleObserver()
            
            timesteps = env.reset()
            agent.reset()
            
            print("Starting Main Loop...")
            
            last_overlay_update = 0
            virtual_selected_tags = set()
            
            while True:
                step_start = time.time()
                
                # 1. Get Observation
                obs = timesteps[0]
                
                # 2. Get Action from Agent
                internal_action = None
                try:
                    action_result = agent.step(obs)
                    if isinstance(action_result, tuple):
                        action, internal_action = action_result
                    else:
                        action = action_result
                except ValueError as e:
                    # Catch PySC2 ValueError for unavailable actions
                    # "Function X is currently not available"
                    print(f"Warning: Agent attempted unavailable action. Fallback to no-op. Error: {e}")
                    action = actions.FunctionCall(actions.FUNCTIONS.no_op.id, [])
                
                # --- Virtual Selection Tracking ---
                # Since we send no-op to the real env, the game state selection never updates.
                # We must track what the agent *thinks* it selected to visualize subsequent moves correctly.
                if internal_action and 'raw_units' in obs.observation:
                    raw_units = obs.observation['raw_units']
                    tag_to_idx = {u.tag: i for i, u in enumerate(raw_units)}
                    
                    func_id = action.function
                    func_name = actions.FUNCTIONS[func_id].name
                    is_selection_action = "select" in func_name.lower()
                    
                    if is_selection_action:
                        # Update virtual selection based on agent's intended selection
                        if hasattr(internal_action, 'units') and internal_action.units is not None:
                            units_idx = internal_action.units
                            # Handle Tensor/Array/Scalar
                            if isinstance(units_idx, torch.Tensor):
                                units_idx = units_idx.cpu().detach().numpy().flatten()
                            elif isinstance(units_idx, np.ndarray):
                                units_idx = units_idx.flatten()
                            elif not isinstance(units_idx, (list, tuple)):
                                units_idx = [units_idx]
                                
                            new_tags = []
                            invalid_selection_count = 0
                            for idx in units_idx:
                                # Ensure index is valid integer
                                idx = int(idx)
                                if idx < len(raw_units):
                                    u = raw_units[idx]
                                    # Filter: Only allow selecting own units (Alliance 1 = Self)
                                    if u.alliance == features.PlayerRelative.SELF:
                                        new_tags.append(u.tag)
                                    else:
                                        invalid_selection_count += 1
                            
                            if invalid_selection_count > 0:
                                print(f"Debug: Filtered out {invalid_selection_count} invalid units (not self) from selection.")
                            
                            # Check for Shift (Queue) - usually queue=1 means add to selection
                            is_queue = False
                            if hasattr(internal_action, 'queue') and internal_action.queue is not None:
                                q = internal_action.queue
                                if isinstance(q, torch.Tensor): q = q.item()
                                if q == 1: is_queue = True
                                
                            if is_queue:
                                virtual_selected_tags.update(new_tags)
                            else:
                                if new_tags: # Only replace if we actually selected something
                                    virtual_selected_tags = set(new_tags)
                            
                            print(f"Debug: Virtual Selection Updated. Tags: {virtual_selected_tags}")
                    else:
                        # Command Action (Move, Attack, Smart, etc.)
                        # If internal_action.units is empty, inject virtual selection so visual_cues knows the source
                        has_units = hasattr(internal_action, 'units') and internal_action.units is not None
                        if has_units:
                            # Check if it's empty list/array
                            u = internal_action.units
                            if isinstance(u, (list, tuple, np.ndarray)) and len(u) == 0:
                                has_units = False
                        
                        if not has_units:
                            # Find indices for virtual tags in current frame
                            current_indices = []
                            found_tags = []
                            for tag in virtual_selected_tags:
                                if tag in tag_to_idx:
                                    current_indices.append(tag_to_idx[tag])
                                    found_tags.append(tag)
                            
                            if current_indices:
                                internal_action.units = current_indices
                                print(f"Debug: Injected {len(current_indices)} units into action {func_name} from virtual selection.")
                            else:
                                print(f"Debug: Action {func_name} but no virtual units found in current frame! Virtual Tags: {virtual_selected_tags}")
                # ----------------------------------

                # 3. Get Text Observation
                text_obs = observer.get_text_observation(obs)
                
                # 4. Generate Visual Cues
                # We use the 'action' object directly, which is the one suggested by AlphaStar
                cues, debug_info = action_to_cues(action, obs, internal_action)
                
                # 5. Write to JSON
                # Log the suggested action
                # No throttle, update every frame
                if True:
                    action_name = actions.FUNCTIONS[action.function].name
                    
                    # Ensure cues is a list
                    if cues is None: cues = []
                    
                    # Debug: Force add a test cue if empty (to verify visualization pipeline)
                    if not cues and action_name != "no_op":
                         cues.append({
                            "type": "text",
                            "pos": [32, 10],
                            "color": "cyan",
                            "text": f"Action: {action_name}",
                            "coordinate": "screen"
                        })
                    
                    # Load LLM config from config.json
                    llm_config_data = {}
                    try:
                        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
                        with open(config_path, 'r', encoding='utf-8') as f:
                            full_config = json.load(f)
                            llm_config_data = full_config.get('decision_llm', {})
                    except Exception as e:
                        print(f"Warning: Could not load config.json: {e}")

                    data = {
                        "cues": cues,
                        "debug": debug_info,
                        "observation": text_obs,
                        "decision": action_name, 
                        "llm_config": llm_config_data
                    }
                    
                    # Atomic write
                    try:
                        temp_file = OVERLAY_FILE + ".tmp"
                        with open(temp_file, 'w') as f:
                            json.dump(data, f, cls=NumpyEncoder)
                        os.replace(temp_file, OVERLAY_FILE)
                        last_overlay_update = time.time()
                    except Exception as e:
                        print(f"Error writing overlay data: {e}")
                
                # 6. Step Environment with No-Op
                # User wants the Agent to only suggest, not act.
                # We always send no_op to the environment so the player can control it.
                # Note: In a real "player vs AI" scenario where this script is the player's assistant,
                # we need to ensure the environment is stepping forward.
                # If PySC2 is controlling the player slot, sending no_op means "do nothing this frame".
                try:
                    no_op_action = actions.FunctionCall(actions.FUNCTIONS.no_op.id, [])
                    timesteps = env.step([no_op_action])
                except ValueError as e:
                     print(f"Warning: Environment rejected no-op action. Error: {e}")
                     # Should rarely happen for no-op
                     pass
                
                step_end = time.time()
                # print(f"Loop time: {(step_end - step_start)*1000:.2f}ms")

                
                # Optional: Sleep to slow down for debugging/visualization
                # time.sleep(0.1)
                
                if obs.last():
                    break
                    
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    app.run(main)
