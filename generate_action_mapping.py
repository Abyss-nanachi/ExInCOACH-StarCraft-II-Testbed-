import sys
import os
import json
import re
import requests
import concurrent.futures
from loguru import logger

# Add the project root to sys.path so we can import pysc2
sys.path.append(os.getcwd())

from pysc2.lib import actions

class SimpleConfig:
    def __init__(self):
        self.model_name = "glm-4.6"
        self.api_base = ""
        self.api_key = ""

    def load_from_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Regex to find api_base and api_key
            base_match = re.search(r"self\.api_base\s*=\s*['\"]([^'\"]+)['\"]", content)
            key_match = re.search(r"self\.api_key\s*=\s*['\"]([^'\"]+)['\"]", content)
            
            if base_match:
                self.api_base = base_match.group(1)
            if key_match:
                self.api_key = key_match.group(1)
                
            logger.info(f"Loaded config: API Base={self.api_base}, Model={self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")

# Initialize Config
config = SimpleConfig()
config_path = os.path.join(os.getcwd(), 'LLM-PySC2', 'llm_pysc2', 'agents', 'configs', 'config.py')
config.load_from_file(config_path)

def clean_action_name(name):
    """Removes standard suffixes from action name to get the core action."""
    clean_name = name
    # Common suffixes in PySC2
    suffixes = ["_quick", "_pt", "_screen", "_minimap", "_unit", "_autocast"]
    for suffix in suffixes:
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)]
    return clean_name

def format_english_name(name):
    """Formats raw name to readable English."""
    clean = clean_action_name(name)
    clean = clean.replace("_", " ")
    clean = re.sub(r'(?<!^)(?=[A-Z])', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def json_post_process(text):
    """Extracts valid JSON object from text."""
    try:
        # Remove markdown code blocks if present
        text = text.replace("```json", "").replace("```", "")
        
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            return json.loads(json_str)
        else:
            logger.warning(f"No JSON object found in response: {text[:100]}...")
    except Exception as e:
        logger.error(f"JSON parsing error: {e}. Text snippet: {text[:100]}...")
    return {}

def llm_translate_batch(names_chunk):
    """Translates a batch of names using the LLM."""
    if not names_chunk:
        return {}
        
    system_prompt = """You are a professional translator for StarCraft II (PySC2). 
Your task is to translate action names from English to Chinese.
Rules:
1. Output ONLY valid JSON.
2. NO markdown formatting, NO code blocks, NO explanations.
3. The JSON must be a single object where keys are the English names and values are Chinese translations.
4. Use standard StarCraft II terminology (e.g., "Barracks" -> "兵营")."""

    user_prompt = f"""Translate these actions:
{json.dumps(names_chunk)}"""
    
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1
    }
    
    url = f"{config.api_base.rstrip('/')}/chat/completions"
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        content = res_json['choices'][0]['message']['content']
        return json_post_process(content)
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        return {}

def main():
    logger.info("Starting LLM-based action mapping generation...")
    
    # 1. Collect all unique core names to translate
    unique_core_names = set()
    raw_to_core = {}
    
    for func_spec in actions.FUNCTIONS:
        raw_name = func_spec.name
        core_name = clean_action_name(raw_name)
        unique_core_names.add(core_name)
        raw_to_core[raw_name] = core_name
        
    sorted_names = sorted(list(unique_core_names))
    logger.info(f"Found {len(sorted_names)} unique core actions to translate.")
    
    # 2. Batch processing with ThreadPoolExecutor
    batch_size = 20
    batches = [sorted_names[i:i + batch_size] for i in range(0, len(sorted_names), batch_size)]
    
    translations = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_batch = {executor.submit(llm_translate_batch, batch): batch for batch in batches}
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_batch)):
            batch = future_to_batch[future]
            try:
                result = future.result()
                if result:
                    translations.update(result)
                else:
                    logger.warning(f"Empty result for batch starting with {batch[0]}")
                
                logger.info(f"Progress: {len(translations)}/{len(sorted_names)} translated.")
            except Exception as exc:
                logger.error(f"Batch generated an exception: {exc}")

    # 3. Generate final mapping
    mapping = {}
    
    for func_spec in actions.FUNCTIONS:
        raw_name = func_spec.name
        core_name = raw_to_core[raw_name]
        
        # Get translation or fallback to English format
        zh_name = translations.get(core_name)
        
        # If missing, try to construct a fallback but log it
        if not zh_name:
             zh_name = format_english_name(core_name)
             # logger.warning(f"Missing translation for {core_name}, using fallback.")

        en_name = format_english_name(raw_name)
        
        entry = {
            "id": func_spec.id,
            "en": en_name,
            "zh": zh_name
        }
        
        # Add by Raw Name
        mapping[raw_name] = entry
        
        # Add by VisualCues Clean Name (compatibility)
        vc_clean_name = raw_name
        for suffix in ["_quick", "_pt", "_screen", "_minimap", "_unit"]:
            vc_clean_name = vc_clean_name.replace(suffix, "")
        vc_clean_name = vc_clean_name.replace("_", " ")
        
        if vc_clean_name not in mapping:
            mapping[vc_clean_name] = entry

    # 4. Save to file
    output_path = os.path.join(os.getcwd(), 'action_mapping.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
            
    logger.info(f"Successfully generated action_mapping.json with {len(mapping)} entries.")

if __name__ == "__main__":
    main()
