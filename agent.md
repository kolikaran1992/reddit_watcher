# 🧠 Agent Guide — reddit_watcher

This document provides a clean operational guide for AI agents working inside the **reddit_watcher** project.  
It explains **how the project is structured**, **what each component does**, and **where agents should read or write** when extending system behavior.

---

# 1. 📦 Project Structure (High-Level)

```
project_root/
│
├── pyproject.toml               # Poetry dependencies & project metadata
├── README.md                    # Human + agent-facing documentation
├── agent.md                     # Agent operations guide (this file)
├── summary.md                   # Full system architecture map (auto-updated)
│
├── reddit_watcher/              # Main Python package
│   ├── omniconf.py              # Dynaconf config loader + logger
│   ├── collector.py             # Sync + async Reddit collectors
│   ├── reddit_api.py            # PRAW/asyncpraw clients + sanitization
│   ├── slack_messenger.py       # Slack Web API notifier
│   ├── rate_limiter.py          # Async token bucket limiter
│   ├── file_lock.py             # OS-level exclusive cron locks
│   ├── xml_parser.py            # Regex XML helper
│   ├── database/                # SQLAlchemy engine, models, utils
│   └── settings_file/           # All Dynaconf TOML configs
│
└── crons/                       # Async ingestion & pipeline scripts
```

---

# 2. 🧬 Core Concepts For Agents

### ✔ Centralized Configuration — `omniconf.py`
- All project settings originate from Dynaconf.
- All TOML files under `settings_file/` are auto-merged.
- Jinja helpers (`_get_now_iso`, `_get_start_ts`) provide timestamps.
- Global logger is initialized here.

Agents should **never duplicate configuration logic** — always modify TOML files or `omniconf.py`.

---

### ✔ Data Collection Layer — `collector.py`
Includes two major collectors:

| Collector | Mode | Purpose |
|----------|------|----------|
| `SubredditCollector` | Sync | Basic metadata + new-post snapshot + video mapping helper |
| `AsyncSubredditCollector` | Async | AsyncPRAW rules/flairs/meta + hot posts + snapshots |

Agents implementing new pipelines should **use the async collector** unless strictly necessary.

---

### ✔ Database Layer — `database/`
Agents interact with data via models defined in:

- `models.py`
- `manager.py` (DBManager)
- `config.py` (Session + Engine)

Never write raw SQL unless needed. Prefer ORM.

---

### ✔ Pipelines — `crons/`
Four main cron scripts:

1. **subreddit_snapshot_pipeline.py**  
2. **subreddit_meta_update_pipeline.py**  
3. **hot_posts_pipeline.py**  
4. **video_ingestion_pipeline.py**

These handle:
- batching  
- async concurrency  
- rate limiting  
- Slack summaries  
- DB insertions  

Agents modifying pipeline logic must update:
- code in `crons/`
- corresponding TOML entries
- associated section in `summary.md`

---

# 3. 🛠️ How Agents Should Modify the Project

### When adding or editing **Python code**
- Place new modules under `reddit_watcher/` unless they are cron-only.
- Keep imports consistent with existing patterns (`from reddit_watcher.X import Y`).
- Update `summary.md` automatically after any new file or major functionality change.

---

### When adding or editing **configuration**
Edit TOML files under:

```
reddit_watcher/settings_file/
```

Examples:
- `subreddit_snapshot.toml` for snapshot pipeline config.
- `hot_posts.toml` for hot post pipeline.
- `database.toml` for DB path changes.

Always keep `summary.md` in sync.

---

### When writing to the **database layer**
Use `DBManager` helpers:

```python
db.insert_record(obj)
db.query_to_df("SELECT ...")
db.delete_record(Model, id)
```

Avoid direct engine operations.

---

### When sending **Slack notifications**
Use:

```python
from reddit_watcher.slack_messenger import send_slack_message
```

Provide:
- message
- header
- Slack channel (auto-loaded from config)

The formatter will wrap the message in a decorative box.

---

# 4. 🧩 Agent Workflow Recommendations

### Step 1 — Understand Context  
Consult `summary.md` for system-wide architecture.

### Step 2 — Modify Safely  
When altering:
- models  
- cron pipelines  
- collectors  
- config files  

Update `summary.md` automatically.

### Step 3 — Validate  
Confirm:
- imports correct  
- no duplication  
- batch & concurrency logic preserved  
- DB relationships consistent  

### Step 4 — Document  
Each modification must update:
- relevant sections in `summary.md`

---

# 5. 📐 Patterns Agents Should Follow

### ✔ Consistent Prefixing  
Always import from `reddit_watcher.*`

### ✔ Separation of Concerns  
- Collectors → data  
- Pipelines → orchestration  
- Database → persistence  
- Slack → notification  
- Config → Dynaconf TOML

### ✔ Immutable Pipeline Contracts  
When modifying a pipeline, preserve:
- batch rotation semantics  
- rate limiter behavior  
- error handling and Slack reporting  

---

# 6. 🔒 What Agents Should **Avoid**

- ❌ Writing absolute paths  
- ❌ Creating files outside project root  
- ❌ Duplicating config already in `.toml`  
- ❌ Hardcoding credentials  
- ❌ Making API calls outside collector modules  
- ❌ Running expensive loops without rate limiting  

---

# 7. 🧾 Changelog  
(Automatically appended when agent makes structural changes.)
