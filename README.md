# claude-glasses

TUI monitor for Claude Code sessions with real-time status and notifications.

![demo](https://github.com/user-attachments/assets/placeholder.png)

## Install

```bash
pip install -e .
```

## Usage

```bash
claude-glasses
```

## Features

- **Live session monitoring** - See all running Claude Code sessions
- **Animated status** - Spinner for working sessions, pulsing dot for ready
- **macOS notifications** - Get notified when Claude needs your input
- **Keyboard shortcuts** - `q` quit, `n` toggle notifications, `r` refresh, `t` test

## Status indicators

```
⠋ project-name     5h 2m   Processing...        (green, animated)
● project-name     2h 3m   ← ready              (magenta, pulsing)
○ project-name     1h 5m   Waiting              (yellow)
```

## Requirements

- Python 3.10+
- macOS (for notifications via `terminal-notifier`)
- Claude Code CLI
