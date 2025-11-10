# Project Overview

This project is an auto-initialized Python template managed by Poetry.
It provides a clean structure for configuration management using Dynaconf, along with support libraries like Jinja2 and pytz.

## 📁 Project Structure

```
project_root/
│
├── pyproject.toml               # Poetry configuration & dependencies
├── README.md                    # Documentation for humans & LLM agents
│
├── reddit_watcher/              # Main Python package
│   ├── __init__.py
│   ├── omniconf.py              # Base configuration loader using Dynaconf
│   └── settings_file/           # Directory holding main Dynaconf settings
│       └── settings.toml        # Default settings loaded by omniconf
│
└── tests/                       # Pytest test directory
```

## ✅ What Each File Does

### `omniconf.py`
- Central config loader for the entire project
- Loads `settings.toml`
- Injects useful Jinja variables (`now`, timezone helpers)
- Sets base paths and timestamp values
- ✅ Initializes a global logger available across the project

To log messages:

```python
from reddit_watcher.omniconf import logger
logger.info("This is a log message")
```

### `settings_file/settings.toml`
- Contains default configuration values
- Uses Jinja2 templating inside Dynaconf
- Includes logger_name which is set to the project root name

Example:
```
[default]
now_iso = "@jinja {{this._get_now_iso(this.tz)}}"
start_ts = "@jinja {{this._get_start_ts(this.tz)}}"
tz = "Asia/Kolkata"
logger_name = "reddit_watcher"
```

If an AI agent needs to modify configuration behavior, it should edit:
- `omniconf.py` for logic or environment variable handling
- `settings.toml` for changing configuration defaults

## 🔧 Extending the Project
- Add new settings in `settings_file/settings.toml`
- Add new Python modules inside `reddit_watcher/`
- Add tests inside `tests/`
