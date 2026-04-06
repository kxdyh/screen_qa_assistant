# Screen QA Assistant

A Windows desktop tool for screenshot-based AI question answering.

Press a global hotkey, capture any region on screen, type your question immediately, and receive a streamed answer in a floating window at the top-right corner. The app also supports pure text mode, follow-up questions, multiple OpenAI-compatible providers, local model backends, and optional screenshot saving.

## Features

- Global hotkey to launch capture overlay
- Ask with screenshot or plain text
- Floating answer window with streamed output
- Follow-up questions on the same screenshot or text session
- Multiple OpenAI-compatible provider profiles
- Vision models, text-only models, and local models
- Optional default reasoning mode
- Optional screenshot saving and cleanup
- System tray integration and iconified compact mode

## Tech Stack

- Python 3.10+
- PySide6
- httpx
- mss
- keyring
- pydantic
- pytest

## Quick Start

### Install

```powershell
pip install -e .
```

### Run

```powershell
python -m screen_qa_assistant
```

### Configure a Model

Add at least one OpenAI-compatible model endpoint in settings:

- Display name
- Base URL
- Model name
- API key
- Vision support flag
- Default reasoning mode flag

## Usage

### Vision Flow

1. Press the capture hotkey
2. Drag to select a region, or press `Enter` for text-only mode
3. Type your question
4. Press `Enter` to submit
5. Read the streamed answer in the floating window

### Text-Only Flow

1. Press the capture hotkey
2. Press `Enter`
3. Type your question
4. Press `Enter` to submit

## Saving Screenshots

If screenshot saving is enabled, the app writes captured images to disk with timestamped filenames such as:

```text
screen-qa-20260405-012953.png
```

If saving is disabled, the screenshot remains in memory only for the current request.

## Project Layout

```text
src/
  screen_qa_assistant/
tests/
pyproject.toml
README.md
README.zh-CN.md
LICENSE
```

## Test

```powershell
pytest -q
```

## Build a Windows Executable

The publish directory includes packaging assets and release outputs. To build locally:

```powershell
python -m pip install pyinstaller
```

Then run the provided PowerShell packaging script.

## License

This project is released under the `MIT License`.

## API Key Security

- Plain-text API keys are not written into the project directory
- Regular settings are stored in `%LOCALAPPDATA%\\ScreenQAAssistant\\settings.json`
- API keys are stored in `Windows Credential Manager` by default
- Each provider can also be switched to `session-only` mode

In session-only mode:

- the key stays in memory only
- it is not written to `settings.json`
- it is not written to the project directory
- it is not persisted to `Windows Credential Manager`
- it disappears after the app exits
