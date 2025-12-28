import numpy as np
import torch
import json
import os
from pysc2.lib import actions

# Load Translation Mapping
MAPPING_FILE = os.path.join(os.path.dirname(__file__), 'action_mapping.json')
ACTION_MAPPING = {}
if os.path.exists(MAPPING_FILE):
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            ACTION_MAPPING = json.load(f)
    except Exception as e:
        print(f"Error loading action_mapping.json: {e}")

def get_translation(name):
    """Translates action name using loaded mapping."""
    # 1. Try Exact Match (Raw Name)
    if name in ACTION_MAPPING:
        return ACTION_MAPPING[name]['zh']
    
    # 2. Try Clean Name (Remove Suffixes)
    clean = name
    for suffix in ["_quick", "_pt", "_screen", "_minimap", "_unit", "_autocast"]:
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)]
    clean = clean.replace("_", " ")
    
    if clean in ACTION_MAPPING:
        return ACTION_MAPPING[clean]['zh']
        
    # 3. Fallback: Return Clean Name
    return clean

def action_to_cues(action_func_call, obs, internal_action=None):
    """Converts a PySC2 FunctionCall to visual cues."""
    cues = []
    debug_info = {}
    
    # Debug: Add Minimap Boundary and Center to verify alignment
    # Removed per user request - only show during calibration in C# Overlay


    try:
        func_id = action_func_call.function
        args = action_func_call.arguments
        func_spec = actions.FUNCTIONS[func_id]
        func_name = func_spec.name
        
        # Action Type Name (Text) - Clean up name (for mapping lookup in Overlay)
        clean_name = func_name
        for suffix in ["_quick", "_pt", "_screen", "_minimap", "_unit", "_autocast"]:
            clean_name = clean_name.replace(suffix, "")
        clean_name = clean_name.replace("_", " ")

        # Prepare for coordinate mapping
        camera = None
        raw_units = []
        tag_to_unit = {}
        
        # 1. Try to get camera position
        # Strategy A: obs.observation['camera'] (Feature Layer)
        if 'camera' in obs.observation:
             camera = obs.observation['camera']
        
        # Strategy B: From feature_minimap (More robust for PySC2)
        camera_mm_rect = None # [min_x, max_x, min_y, max_y] in Minimap Coords
        camera_mm_center = None
        
        if 'feature_minimap' in obs.observation:
            # Camera channel is index 3
            f_mm = obs.observation['feature_minimap']
            if len(f_mm) > 3:
                cam_layer = f_mm[3]
                ys, xs = cam_layer.nonzero()
                if len(xs) > 0:
                    min_x, max_x = xs.min(), xs.max()
                    min_y, max_y = ys.min(), ys.max()
                    camera_mm_rect = [min_x, max_x, min_y, max_y]
                    camera_mm_center = [xs.mean(), ys.mean()]
                    
                    # If camera (World) is missing, infer it from Minimap assuming Simple64 (64x64)
                    # or just use it for screen mapping logic.
                    if camera is None:
                        # Assuming 1:1 mapping for Simple64
                        # World X = Minimap X
                        # World Y = 64 - Minimap Y (Flip)
                        camera = [camera_mm_center[0], 64.0 - camera_mm_center[1]]

        # 2. Get Raw Units and Screen Units
        # Screen units (feature_units) are more accurate for screen overlay
        screen_units = [] # List of feature_units
        if 'feature_units' in obs.observation:
            screen_units = obs.observation['feature_units']
            
        if 'raw_units' in obs.observation:
            raw_units = obs.observation['raw_units']
            # Create tag lookup
            for u in raw_units:
                tag_to_unit[u.tag] = u
        
        # Debug: Capture camera and units count
        debug_info['camera_found'] = (camera is not None)
        debug_info['camera_mm_found'] = (camera_mm_rect is not None)
        debug_info['camera_val'] = camera.tolist() if isinstance(camera, np.ndarray) else camera
        debug_info['raw_units_count'] = len(raw_units)
        if len(raw_units) > 0:
            # Log first unit as sample
            u = raw_units[0]
            debug_info['sample_unit'] = {'tag': u.tag, 'x': u.x, 'y': u.y}

        if camera is None or len(raw_units) == 0:
             pass

        # Define Screen Dimensions (in World Units)
        # Based on Log: Camera ~16.5, Unit ~46 is far away.
        # Assuming Feature Screen 64x64 corresponds to World 24x24 (Standard PySC2)
        # Screen Radius = 12
        SCREEN_WORLD_RADIUS = 12.0
        
        def get_screen_pos(wx, wy):
            # Check if in camera view using Minimap Rect if available (More Accurate)
            in_view = False
            
            # Method A: Use Minimap Camera Rect (Best for "current view")
            if camera_mm_rect is not None:
                # Map World to Minimap
                # Assumption: Simple64 Scale. For other maps, this needs map size.
                mx = int(wx)
                my = int(64.0 - wy)
                
                # Check bounds with slight margin
                margin = 4
                if (camera_mm_rect[0] - margin <= mx <= camera_mm_rect[1] + margin and
                    camera_mm_rect[2] - margin <= my <= camera_mm_rect[3] + margin):
                    in_view = True
                    
                    # Map to Screen
                    # Calculate relative position within camera rect
                    cam_w = camera_mm_rect[1] - camera_mm_rect[0]
                    cam_h = camera_mm_rect[3] - camera_mm_rect[2]
                    
                    # Debug camera rect for alignment
                    if 'camera_mm_rect' not in debug_info:
                         debug_info['camera_mm_rect'] = [int(x) for x in camera_mm_rect]
                    
                    if cam_w > 0 and cam_h > 0:
                        rel_x = (mx - camera_mm_rect[0]) / cam_w
                        rel_y = (my - camera_mm_rect[2]) / cam_h
                        
                        # Screen is 64x64
                        sx = rel_x * 64.0
                        sy = rel_y * 64.0
                        return [int(sx), int(sy)], "screen"

            # Method B: Use World Distance (Fallback)
            if not in_view and camera is not None:
                dist_x = abs(wx - camera[0])
                dist_y = abs(wy - camera[1])
                
                # If within screen radius, map to screen
                if dist_x <= SCREEN_WORLD_RADIUS and dist_y <= SCREEN_WORLD_RADIUS:
                    # Inside Screen
                    rel_x = wx - camera[0]
                    rel_y = wy - camera[1]
                    # Map [-12, 12] to [0, 64]
                    scale = 64.0 / (SCREEN_WORLD_RADIUS * 2)
                    sx = 32 + rel_x * scale
                    sy = 32 - rel_y * scale # Y-flip
                    return [int(sx), int(sy)], "screen"
                else:
                    # Outside screen - Map to edge or just return minimap
                    # For arrows, we might want "off-screen" indicator, but "minimap" is safer for now.
                    # Returning minimap allows add_dual_cues to handle it.
                    pass

            # Fallback or Outside Screen -> Minimap
            # World Coordinates: (0,0) is Bottom-Left
            # Overlay/Screen Coordinates: (0,0) is Top-Left
            # Update: User feedback suggests removing flip for Minimap consistency with Overlay
            return [int(wx), int(wy)], "minimap"

        def world_to_screen(wx, wy):
            # Deprecated, use get_screen_pos
            pos, coord = get_screen_pos(wx, wy)
            if coord == "screen": return pos
            return None # Return None if not on screen for legacy calls

        # Find specific arguments in the function spec
        unit_tags_arg_index = -1
        target_unit_tag_arg_index = -1
        target_point_arg_index = -1
        target_point_type = None # 'screen' or 'minimap'
        
        # Initialize internal variables
        internal_target_location = None
        internal_target_unit_idx = None
        
        for i, arg_spec in enumerate(func_spec.args):
            if arg_spec.name == 'unit_tags':
                unit_tags_arg_index = i
            elif arg_spec.name == 'target_unit_tag':
                target_unit_tag_arg_index = i
            elif arg_spec.name in ['screen', 'minimap', 'screen2']:
                target_point_arg_index = i
                target_point_type = arg_spec.name

        # --- 1. Selected Units (Box Selection) ---
        # Represents SelectedUnitsHead
        selected_positions = []
        selected_positions_minimap = [] # Add minimap positions
        selected_world_positions = [] # Store world coords for center calculation
        
        # Check real selection status (independent of agent intent)
        real_selection_empty = True
        if screen_units is not None:
             for u in screen_units:
                 if u.is_selected:
                     real_selection_empty = False
                     break
        if real_selection_empty and len(raw_units) > 0:
             for u in raw_units:
                 if u.is_selected:
                     real_selection_empty = False
                     break

        # Priority 1: Internal Action (Agent's Intent)
        if internal_action is not None:
            # 1.1 Selected Units
            if hasattr(internal_action, 'units'):
                # Convert Tensor to list if needed
                units_idx = internal_action.units
                if isinstance(units_idx, torch.Tensor):
                    units_idx = units_idx.cpu().detach().numpy().flatten().tolist()
                elif isinstance(units_idx, np.ndarray):
                    units_idx = units_idx.flatten().tolist()
                
                # Debug
                debug_info['internal_units_idx'] = units_idx

                # Map indices to raw_units
                # Note: This assumes raw_units order matches the Agent's entity list order.
                # This is a simplification but better than nothing.
                if units_idx:
                    for idx in units_idx:
                        if idx < len(raw_units):
                            u = raw_units[idx]
                            # PySC2 units have radius
                            r = getattr(u, 'radius', 1.0)
                            
                            selected_world_positions.append([u.x, u.y, r]) # Store radius
                            pos, coord = get_screen_pos(u.x, u.y)
                            
                            if pos: 
                                # Separate screen and minimap selections
                                # For simplicity, we only draw box for screen cues
                                if coord == "screen":
                                    selected_positions.append(pos)
                                elif coord == "minimap":
                                    selected_positions_minimap.append(pos)
                            
                            # Debug logic for selection
                            if 'selected_units_debug' not in debug_info: debug_info['selected_units_debug'] = []
                            debug_info['selected_units_debug'].append({
                                'idx': idx, 
                                'unit_x': u.x, 'unit_y': u.y, 
                                'screen_pos': pos,
                                'coord_sys': coord
                            })
            
            # 1.2 Target Location
            if hasattr(internal_action, 'target_location'):
                loc = internal_action.target_location
                # Handle Tensor/Array
                if isinstance(loc, torch.Tensor):
                    loc = loc.cpu().detach().numpy().flatten()
                elif isinstance(loc, np.ndarray):
                    loc = loc.flatten()
                
                if len(loc) >= 2:
                    internal_target_location = [float(loc[0]), float(loc[1])]
                    debug_info['internal_target_location'] = internal_target_location
                    
                    # Debug: Check if target is on screen
                    t_pos, t_coord = get_screen_pos(internal_target_location[0], internal_target_location[1])
                    debug_info['target_location_debug'] = {'loc': internal_target_location, 'mapped': t_pos, 'coord': t_coord}

            # 1.3 Target Unit Index
            if hasattr(internal_action, 'target_unit'):
                 t_idx = internal_action.target_unit
                 # Convert to scalar
                 if isinstance(t_idx, torch.Tensor):
                     t_idx = t_idx.item()
                 elif isinstance(t_idx, np.ndarray):
                     if t_idx.size == 1:
                         t_idx = t_idx.item()
                     elif t_idx.size > 0:
                         t_idx = t_idx.flatten()[0]
                 
                 if isinstance(t_idx, (int, np.integer, float, np.floating)):
                     internal_target_unit_idx = int(t_idx)

        # Priority 2: Explicit unit_tags from FunctionCall
        if not selected_positions and unit_tags_arg_index != -1 and unit_tags_arg_index < len(args):
            tags = args[unit_tags_arg_index]
            if isinstance(tags, int): tags = [tags]
            
            for tag in tags:
                if tag in tag_to_unit:
                    u = tag_to_unit[tag]
                    selected_world_positions.append([u.x, u.y])
                    pos, coord = get_screen_pos(u.x, u.y)
                    if pos and coord == "screen": 
                        selected_positions.append(pos)
        
        # Priority 3: Fallback to currently selected units
        if not selected_positions:
             # Strategy 3A: Use feature_units (Screen Units) - High Precision for Screen
                if screen_units is not None:
                    # Debug screen units availability
                    debug_info['screen_units_count'] = len(screen_units)
                    
                    for u in screen_units:
                        if u.is_selected:
                            # feature_units are already in screen coords (0-64? or pixels?)
                            # PySC2 feature_units x,y are usually 0-ScreenSize
                            # We assume screen size is 64x64 based on env config
                            sx, sy = u.x, u.y
                            selected_positions.append([sx, sy])
                            
                            debug_info['selected_unit_screen'] = {'x': int(sx), 'y': int(sy), 'tag': int(u.tag)}
                     
                     # Try to estimate world pos if needed (reverse map)
                     # But for screen box, we just need screen pos
            
             # Strategy 3B: Use raw_units (World Units) - For Minimap or Off-screen
                for u in raw_units:
                    if u.is_selected:
                        # PySC2 units have radius
                        r = getattr(u, 'radius', 1.0)
                        
                        selected_world_positions.append([u.x, u.y, r]) # Store radius too
                        pos, coord = get_screen_pos(u.x, u.y)
                        
                        debug_info.setdefault('selected_units_raw', []).append({
                            'x': float(u.x), 
                            'y': float(u.y), 
                            'radius': float(r),
                            'tag': int(u.tag),
                            'mapped_pos': pos,
                            'mapped_coord': coord
                        })

                        # Only add to selected_positions if NOT already covered by feature_units
                # Actually, if we found screen units, we probably have the screen box covered.
                # But let's add just in case (dedup logic might be needed if mixed)
                if not selected_positions and pos and coord == "screen": 
                    selected_positions.append(pos)

        # Calculate Selection Center (World Coordinates)
        selection_center_world = None
        selection_radius_avg = 1.0
        
        if selected_world_positions:
            # Filter for screen units first
            screen_world_units = []
            for p in selected_world_positions:
                _, coord = get_screen_pos(p[0], p[1])
                if coord == "screen":
                    screen_world_units.append(p)
            
            # If we have units on screen, use ONLY them for the center/arrow origin
            # This prevents the "Void Center" issue when units are scattered across the map
            target_group = screen_world_units if screen_world_units else selected_world_positions
            
            # Calculate dispersion to avoid "Void Center" even if all on minimap
            if not screen_world_units and len(target_group) > 1:
                 # Simple bounding box check
                 xs = [p[0] for p in target_group]
                 ys = [p[1] for p in target_group]
                 max_dist = max(max(xs)-min(xs), max(ys)-min(ys))
                 
                 # If units are too scattered (> 20 world units), just pick the first one
                 # This usually happens when selecting all larvae or bases
                 if max_dist > 20:
                     target_group = [target_group[0]]
            
            wx = [p[0] for p in target_group]
            wy = [p[1] for p in target_group]
            # Handle potential missing radius by defaulting to 1.0 if len < 3
            wr = [(p[2] if len(p) > 2 else 1.0) for p in target_group]
            
            selection_center_world = [sum(wx)/len(wx), sum(wy)/len(wy)]
            selection_radius_avg = sum(wr)/len(wr)
            
        elif camera is not None:
             selection_center_world = [camera[0], camera[1]]
        
        # Default screen center if all else fails
        selection_center_screen = [32, 32] 
        selection_center_coord = "minimap" # Default to minimap if no screen pos found
        
        if selection_center_world:
            pos, coord = get_screen_pos(selection_center_world[0], selection_center_world[1])
            if pos:
                selection_center_screen = pos
                selection_center_coord = coord

        if selected_positions:
            # Draw bounding box for all selected units
            xs = [p[0] for p in selected_positions]
            ys = [p[1] for p in selected_positions]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            # Note: We update selection_center_screen based on bounding box only if it's "screen"
            # But the world-based calculation above is more robust for arrows.
            # selection_center = [(min_x + max_x) // 2, (min_y + max_y) // 2]
            
            cues.append({
                "type": "box",
                "start": [min_x - 10, min_y - 10],
                "end": [max_x + 10, max_y + 10],
                "color": "lime", # Green for self/selection
                "text": clean_name, # Show action name on selection
                "coordinate": "screen"
            })
            
            # If no unit is actually selected, but we have an intended selection, 
            # add ripples to guide the user to select these units.
            # Update: Always show ripples for recommended units (from world positions)
            if selected_world_positions:
                for item in selected_world_positions:
                    wx, wy = item[0], item[1]
                    radius = item[2] if len(item) > 2 else 1.0
                    
                    pos, coord = get_screen_pos(wx, wy)
                    if pos and coord == "screen":
                        cues.append({
                            "type": "ripple",
                            "pos": pos,
                            "color": "cyan",
                            "radius": max(15, int(radius * 15)),
                            "coordinate": "screen"
                        })
            
            # Fallback for Priority 3A (Screen Units only, no world pos)
            elif real_selection_empty:
                for p in selected_positions:
                    cues.append({
                        "type": "ripple",
                        "pos": p,
                        "color": "cyan", 
                        "radius": 15,
                        "coordinate": "screen"
                    })
        
            debug_info['box_cue'] = {'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}

        if selected_positions_minimap and real_selection_empty:
             for p in selected_positions_minimap:
                 cues.append({
                     "type": "ripple",
                     "pos": p,
                     "color": "cyan",
                     "radius": 5, # Smaller radius for minimap
                     "coordinate": "minimap"
                 })
            
        # Helper to generate dual cues (Screen + Minimap)
        def add_dual_cues(cue_type, start_world, end_world, color, text, radius=None):
            # 1. Minimap Cue (Always)
            # Force Minimap mapping logic manually to ensure we get minimap coords even if on screen
            def to_mm(wx, wy):
                 # Overlay/PySC2 Y-axis issue:
                 # PySC2 World: Y=0 (Bottom-Left), Y=64 (Top-Right)
                 # Overlay Minimap: Y=0 (Top), Y=64 (Bottom)
                 # BUT, based on user feedback/visuals, the previous flip (64-y) caused arrows to start at Bottom-Left (Y~60->4?)
                 # and point to Top-Right.
                 # Actually, if PySC2 world coords match the Overlay's expected input (where 0 is Top?),
                 # we should NOT flip. Or if the Overlay draws Upwards?
                 # Let's try removing the flip as requested by user observation.
                 return [int(wx), int(wy)]
            
            s_mm = to_mm(start_world[0], start_world[1])
            e_mm = to_mm(end_world[0], end_world[1])
            
            cues.append({
                "type": cue_type,
                "start": s_mm,
                "end": e_mm,
                "color": color,
                "text": text,
                "coordinate": "minimap"
            })
            
            # 2. Screen Cue (If both in view)
            s_scr, s_coord = get_screen_pos(start_world[0], start_world[1])
            e_scr, e_coord = get_screen_pos(end_world[0], end_world[1])
            
            if s_coord == "screen" and e_coord == "screen":
                cues.append({
                    "type": cue_type,
                    "start": s_scr,
                    "end": e_scr,
                    "color": color,
                    "text": text,
                    "coordinate": "screen",
                    "radius": radius # Pass radius for ripple/circle
                })
                # Add Circle at target
                cues.append({
                    "type": "circle",
                    "center": e_scr,
                    "radius": 15 if cue_type == "arrow" else 10,
                    "color": color,
                    "coordinate": "screen"
                })

        if internal_action:
            # Parse action name
            act_name = internal_action[0] if isinstance(internal_action, (list, tuple)) else str(internal_action)
            
            # If we have a target location
            if internal_target_location:
                # Use refined selection center
                start_pos = selection_center_world
                end_pos = internal_target_location
                
                # Only draw arrow if we have valid start/end AND the action actually requires a target point
                if start_pos and end_pos and target_point_type is not None:
                    add_dual_cues("arrow", start_pos, end_pos, "Lime", get_translation(act_name))
                    
            # Debug: Log raw action name for mapping
            debug_info['raw_action_name'] = func_spec.name
            
            # If we have a target unit (Attack/Follow unit)
            if internal_target_unit_idx is not None:
                 # Find target unit position
                 # ... (existing logic) ...
                 pass # Handled below if we implemented target unit lookup
            
            # If it's just a selection or self-cast (no target loc)
            # Draw a RIPPLE on the selection center
            else:
                 if selection_center_world:
                     # Use ripple instead of box for self-cast/selection
                     # Scale ripple radius by unit radius (approx 1 world unit ~ 10-20 screen pixels?)
                     # Let's say 1 radius = 20 pixels
                     ripple_r = selection_radius_avg * 20.0
                     if ripple_r < 20: ripple_r = 20
                     
                     # We want the ripple at the START (Selection Center)
                     # So we treat start and end as the same
                     add_dual_cues("ripple", selection_center_world, selection_center_world, "Cyan", act_name, radius=ripple_r)

        # --- 2. Target Unit (Arrow + Circle) ---
        # Represents TargetUnitHead
        target_found = False
        target_unit_pos_world = None
        
        # Priority 1: Internal Action
        if internal_action is not None and hasattr(internal_action, 'target_unit'):
             t_idx = internal_action.target_unit
             # Convert to scalar if it's a Tensor or NumPy array
             if isinstance(t_idx, torch.Tensor):
                 t_idx = t_idx.item()
             elif isinstance(t_idx, np.ndarray):
                 # Handle 0-d array or 1-d array with 1 element
                 if t_idx.size == 1:
                     t_idx = t_idx.item()
                 elif t_idx.size > 0:
                     t_idx = t_idx.flatten()[0] # Take first element if multiple?
             
             # Ensure t_idx is a simple integer before comparison
             if isinstance(t_idx, (int, np.integer, float, np.floating)):
                 t_idx = int(t_idx)
                 debug_info['internal_target_unit_idx'] = t_idx
                 
                 if t_idx < len(raw_units):
                    u = raw_units[t_idx]
                    target_unit_pos_world = [u.x, u.y]
                    target_found = True
                    debug_info['target_unit_debug'] = {'idx': t_idx, 'x': u.x, 'y': u.y}

        # Priority 2: FunctionCall arguments
        if not target_found and target_unit_tag_arg_index != -1 and target_unit_tag_arg_index < len(args):
            t_tag = args[target_unit_tag_arg_index]
            if isinstance(t_tag, list): t_tag = t_tag[0] 
            
            if t_tag in tag_to_unit:
                u = tag_to_unit[t_tag]
                target_unit_pos_world = [u.x, u.y]
                target_found = True

        if target_found and selection_center_world:
             # Use add_dual_cues to handle both screen and minimap arrows
             add_dual_cues("arrow", selection_center_world, target_unit_pos_world, "red", "Target")

        # --- 3. Target Location (Arrow + Circle) ---
        # Represents LocationHead
        location_found = False
        target_loc_world = None
        
        # Priority 1: Internal Action
        if internal_action is not None and hasattr(internal_action, 'target_location'):
            loc = internal_action.target_location
            if isinstance(loc, torch.Tensor):
                loc = loc.cpu().detach().numpy().flatten().tolist()
            elif isinstance(loc, np.ndarray):
                loc = loc.flatten().tolist()
            
            debug_info['internal_target_location'] = loc

            # loc might be [x, y] or empty
            # Ensure loc is a list and check length safely
            if isinstance(loc, list) and len(loc) >= 2:
                target_loc_world = [loc[0], loc[1]]
                location_found = True
                debug_info['target_location_debug'] = {'loc': loc}

        # Priority 2: FunctionCall arguments
        if not location_found and target_point_arg_index != -1 and target_point_arg_index < len(args):
            raw_loc = args[target_point_arg_index] # [x, y] screen or minimap coords
            
            if target_point_type == 'screen':
                # Convert Screen to World (if camera is known)
                if camera is not None:
                    # World = Camera + (Screen - Center) * Scale_Inverse
                    # Center = 32, Scale = 64 / (12 * 2) = 2.666
                    # Scale_Inverse = 24 / 64 = 0.375
                    scale_inv = (SCREEN_WORLD_RADIUS * 2) / 64.0
                    
                    # Screen Y is flipped relative to World Y?
                    # get_screen_pos: sy = 32 - rel_y * scale
                    # => rel_y * scale = 32 - sy
                    # => rel_y = (32 - sy) / scale
                    
                    sx = raw_loc[0]
                    sy = raw_loc[1]
                    
                    rel_x = (sx - 32.0) * scale_inv
                    rel_y = (32.0 - sy) * scale_inv # Flip back
                    
                    wx = camera[0] + rel_x
                    wy = camera[1] + rel_y
                    
                    target_loc_world = [wx, wy]
                    location_found = True
                    debug_info['target_loc_from_screen'] = {'raw': raw_loc, 'world': target_loc_world}
            
            elif target_point_type == 'minimap':
                # Convert Minimap to World
                # World X = Minimap X
                # World Y = 64 - Minimap Y
                mx = raw_loc[0]
                my = raw_loc[1]
                
                wx = mx
                wy = 64.0 - my
                
                target_loc_world = [wx, wy]
                location_found = True
                debug_info['target_loc_from_minimap'] = {'raw': raw_loc, 'world': target_loc_world}

        if location_found and selection_center_world:
             add_dual_cues("arrow", selection_center_world, target_loc_world, "yellow", clean_name)

        return cues, debug_info

    except Exception as e:
        print(f"Error in action_to_cues: {e}")
        # traceback.print_exc()
        return [], {}
