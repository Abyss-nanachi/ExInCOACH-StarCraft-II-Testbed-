# ExInCOACH (StarCraft II Testbed)

本 repository 从属于论文 **“ExInCOACH: Strategic Exploration Meets Interactive Tutoring for Context-Aware Game Onboarding”** 的工作。

## 简介

本项目是一个 **ExInCOACH 框架** 的星际争霸II (StarCraft II) 新手教程实例。它实现了：

*   **RL 模型决策**：利用强化学习模型进行游戏决策。
*   **LLM 解释**：使用大语言模型为决策提供解释。
*   **可视化 Overlay**：实现了对窗口化星际争霸II游戏环境的追踪与遮罩，并将 RL 模型的决策实时映射到游戏画面中。

本项目包含以下两个核心组件的修改版本，感谢原作者的开源贡献：
*   `mini-AlphaStar`: 原始仓库 [https://github.com/liuruoze/mini-AlphaStar](https://github.com/liuruoze/mini-AlphaStar)
*   `LLM-PySC2`: 原始仓库 [https://github.com/NKAI-Decision-Team/LLM-PySC2](https://github.com/NKAI-Decision-Team/LLM-PySC2)

## 快速开始

### 1. 配置环境
复制 `config_template.json` 文件并重命名为 `config.json`。
根据需要填入相关配置信息（如 LLM API Key 等）。

### 2. 准备模型
使用 `mini-AlphaStar` 提供的训练代码训练强化学习 (RL) 模型。
将训练好的模型文件重命名为 `alphastar_model.pth`。
将该文件放置在 `models` 文件夹中 (路径: `models/alphastar_model.pth`)。

### 3. 运行 Agent
运行以下命令启动 Agent 和游戏环境：
```bash
python main_agent.py
```

### 4. 设置和运行 Overlay
Overlay 用于在游戏中显示辅助信息。

**编译 Overlay:**
运行 `compile_overlay.bat` 脚本来编译 `SC2Overlay.cs`。
```cmd
compile_overlay.bat
```
编译成功后会生成 `SC2Overlay.exe`。

**启动 Overlay:**
双击运行 `SC2Overlay.exe`。

## 高级功能：动作翻译
项目包含动作名称的翻译映射文件 `action_mapping.json`。
如果发现操作提醒的翻译不够准确，您可以：
1.  **手动修改**: 直接编辑 `action_mapping.json` 文件。
2.  **自动生成**: 运行 `generate_action_mapping.py` 重新生成翻译映射。
    ```bash
    python generate_action_mapping.py
    ```
