# ExInCOACH (StarCraft II Testbed)

[中文版本 (Chinese Version)](README_cn.md)

This repository is part of the work for the paper **"ExInCOACH: Strategic Exploration Meets Interactive Tutoring for Context-Aware Game Onboarding"**.

## Introduction

This project is an instance of the **ExInCOACH framework** applied to a StarCraft II tutorial. It implements:

*   **RL Decision Making**: Utilizing Reinforcement Learning models for game decisions.
*   **LLM Explanation**: Leveraging Large Language Models to explain decisions.
*   **Visual Overlay**: Tracks and masks the windowed StarCraft II game environment, mapping RL model decisions directly onto the game screen.

This project incorporates modified versions of the following repositories. We thank the original authors for their open-source contributions:
*   `mini-AlphaStar`: Original Repository [https://github.com/liuruoze/mini-AlphaStar](https://github.com/liuruoze/mini-AlphaStar)
*   `LLM-PySC2`: Original Repository [https://github.com/NKAI-Decision-Team/LLM-PySC2](https://github.com/NKAI-Decision-Team/LLM-PySC2)

## Quick Start

### 1. Configuration
Copy `config_template.json` and rename it to `config.json`.
Fill in the configuration details (e.g., LLM API Key) as needed.

### 2. Prepare Model
Train a Reinforcement Learning (RL) model using the training code provided in `mini-AlphaStar`.
Rename the trained model file to `alphastar_model.pth`.
Place the file in the `models` directory (Path: `models/alphastar_model.pth`).

### 3. Run Agent
Run the following command to start the Agent and the game environment:
```bash
python main_agent.py
```

### 4. Setup and Run Overlay
The Overlay is used to display auxiliary information in the game.

**Compile Overlay:**
Run the `compile_overlay.bat` script to compile `SC2Overlay.cs`.
```cmd
compile_overlay.bat
```
Upon successful compilation, `SC2Overlay.exe` will be generated.

**Start Overlay:**
Double-click to run `SC2Overlay.exe`.

## Advanced Feature: Action Translation
The project includes an action name translation mapping file `action_mapping.json`.
If you find the action translation inaccurate, you can:
1.  **Manually Edit**: Edit the `action_mapping.json` file directly.
2.  **Regenerate**: Run `generate_action_mapping.py` to regenerate the translation mapping.
    ```bash
    python generate_action_mapping.py
    ```
