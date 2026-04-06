# 截图问答助手

一个面向 Windows 10/11 的桌面截图问答工具。

按下全局快捷键后，可以像截图工具一样快速框选屏幕区域，随后直接输入你想问 AI 的问题。应用会在右上角弹出悬浮回答窗，基于截图和提问内容进行即时回复，并支持继续追问。

## 功能特性

- 全局快捷键唤起截图蒙版
- 直接文本提问，或截图后再提问
- 右上角悬浮回答窗，支持流式输出
- 连续追问同一张截图或同一轮问题
- 可配置多个 OpenAI 兼容服务端点
- 支持视觉模型、纯文本模型、本地模型服务
- 支持默认思考模式
- 支持截图保存到本地目录并按周期清理
- 支持系统托盘、图标化收起、窗口字体档位切换

## 技术栈

- Python 3.10+
- PySide6
- httpx
- mss
- keyring
- pydantic
- pytest

## 快速开始

### 1. 安装依赖

```powershell
pip install -e .
```

### 2. 启动应用

```powershell
python -m screen_qa_assistant
```

### 3. 配置模型

首次启动后，至少配置一个 OpenAI 兼容模型：

- 显示名称
- Base URL
- 模型名
- API Key
- 是否支持视觉输入
- 是否默认开启思考模式

## 基本使用流程

### 多模态模型

1. 按下截图快捷键
2. 拖拽框选截图，或直接按 `Enter` 进入纯文本提问
3. 输入问题
4. 按 `Enter` 提交
5. 在右上角回答窗查看结果并继续追问

### 纯文本模型

1. 按下截图快捷键
2. 直接按 `Enter`
3. 输入问题
4. 按 `Enter` 提交

## 本地保存截图

当设置中开启“截图落盘”后，应用会把截图保存到配置目录中，文件名格式类似：

```text
screen-qa-20260405-012953.png
```

如果未开启“截图落盘”，截图只会暂存在内存中供当前提问使用，不会写入磁盘。

## 项目结构

```text
src/
  screen_qa_assistant/
tests/
pyproject.toml
README.md
README.zh-CN.md
LICENSE
```

## 测试

```powershell
pytest -q
```

## 打包 Windows EXE

仓库外的发布目录中已经提供打包脚本和发行物说明。若要自行构建：

```powershell
python -m pip install pyinstaller
```

然后执行对应的 PowerShell 构建脚本。

## 开源协议

本项目采用 `MIT License`。
