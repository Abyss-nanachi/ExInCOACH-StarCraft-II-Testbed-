# AlphaStar Project (AlphaStar 项目)

[English Version below](#english-version)

## 中文版本

### 简介
本项目运行一个 AlphaStar 代理与星际争霸II (StarCraft II) 环境交互，并提供一个可视化的 Overlay 工具。

### 快速开始

#### 1. 配置环境
复制 `config_template.json` 文件并重命名为 `config.json`。
根据需要填入相关配置信息（如 LLM API Key 等）。

#### 2. 准备模型
使用 `mini-alphastar` 提供的训练代码训练强化学习 (RL) 模型。
将训练好的模型文件重命名为 `alphastar_model.pth`。
将该文件放置在 `models` 文件夹中 (路径: `models/alphastar_model.pth`)。

#### 3. 运行 Agent
运行以下命令启动 Agent 和游戏环境：
```bash
python main_agent.py
```

#### 4. 设置和运行 Overlay
Overlay 用于在游戏中显示辅助信息。

**编译 Overlay:**
运行 `compile_overlay.bat` 脚本来编译 `SC2Overlay.cs`。
```cmd
compile_overlay.bat
```
编译成功后会生成 `SC2Overlay.exe`。

**启动 Overlay:**
双击运行 `SC2Overlay.exe`。

### 高级功能：动作翻译
项目包含动作名称的翻译映射文件 `action_mapping.json`。
如果发现操作提醒的翻译不够准确，您可以：
1.  **手动修改**: 直接编辑 `action_mapping.json` 文件。
2.  **自动生成**: 运行 `generate_action_mapping.py` 重新生成翻译映射。
    ```bash
    python generate_action_mapping.py
    ```

---

<a id="english-version"></a>
## English Version

### Introduction
This project runs an AlphaStar agent interacting with the StarCraft II environment and provides a visual Overlay tool.

### Quick Start

#### 1. Configuration
Copy `config_template.json` and rename it to `config.json`.
Fill in the configuration details (e.g., LLM API Key) as needed.

#### 2. Prepare Model
Train a Reinforcement Learning (RL) model using the training code provided in `mini-alphastar`.
Rename the trained model file to `alphastar_model.pth`.
Place the file in the `models` directory (Path: `models/alphastar_model.pth`).

#### 3. Run Agent
Run the following command to start the Agent and the game environment:
```bash
python main_agent.py
```

#### 4. Setup and Run Overlay
The Overlay is used to display auxiliary information in the game.

**Compile Overlay:**
Run the `compile_overlay.bat` script to compile `SC2Overlay.cs`.
```cmd
compile_overlay.bat
```
Upon successful compilation, `SC2Overlay.exe` will be generated.

**Start Overlay:**
Double-click to run `SC2Overlay.exe`.

### Advanced Feature: Action Translation
The project includes an action name translation mapping file `action_mapping.json`.
If you find the action translation inaccurate, you can:
1.  **Manually Edit**: Edit the `action_mapping.json` file directly.
2.  **Regenerate**: Run `generate_action_mapping.py` to regenerate the translation mapping.
    ```bash
    python generate_action_mapping.py
    ```
