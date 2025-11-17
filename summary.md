# 🧠 reddit_watcher Project Summary (Rewritten & Consolidated)

A complete, agent-friendly overview of all modules, pipelines, ORM models, and configuration files within the **reddit_watcher** system.

---

# 1. 📦 Core Architecture Overview

```
Config → Collectors → Database Layer → Pipelines (Crons) → Slack Notifications
```

The project centralizes configuration with **Dynaconf**, performs Reddit API ingestion (sync + async), stores processed data in **SQLAlchemy ORM models**, and runs automated pipelines under the `crons/` directory.

---

# 2. 🧩 Core Modules (`reddit_watcher/`)

### **collector.py**
| Capability | Description |
|-----------|-------------|
| **SubredditCollector (sync)** | Fetch static metadata, meta (rules/flairs), and activity snapshots from PRAW objects. |
| **AsyncSubredditCollector** | AsyncPRAW version with caching, async rules/flairs handling, hot-posts collection (`collect_hot_posts_metadata`). |
| **Snapshot collector** | Computes recent posts window stats (comments, upvotes, counts). |
| **Video-mapping collector** | Lightweight static metadata extraction for video → subreddit mapping. |

---

### **reddit_api.py**
| Component | Description |
|-----------|-------------|
| `get_reddit_instance()` | Creates authenticated PRAW client. |
| `get_reddit_instance_async()` | AsyncPRAW client for async pipelines. |
| `sanitize_subreddit_name()` | Normalizes names (`r/foo` → `foo`). |

---

### **omniconf.py**
| Capability | Description |
|-----------|-------------|
| Dynaconf loader | Loads all `settings_file/*.toml` including secrets. |
| Jinja variables | `now`, `partition_date`, timezone helpers. |
| Logger | Central logger with ISO timestamps & formatted console output. |

---

### **slack_messenger.py**
| Capability | Description |
|-----------|-------------|
| Formatting | Decorative message box around pipeline output. |
| Transport | Posts via Slack Web API using configured bot token + channel. |

---

### **rate_limiter.py**
| Capability | Description |
|-----------|-------------|
| `AsyncRateLimiter` | Token-bucket limiter with jittered refill rate used in async pipelines. |

---

### **file_lock.py**
| Purpose | Description |
|---------|-------------|
| ExclusiveFileLock | Prevents concurrent pipeline execution via OS-level file locks. |

---

### **xml_parser.py**
| Purpose | Description |
|---------|-------------|
| SimpleXMLParser | Regex-based XML tag extractor used in LLM keyword processing. |

---

# 3. 🗄️ Database Layer (`reddit_watcher/database/`)

### **ORM Models Summary**
| Model | Purpose |
|-------|---------|
| **Subreddit** | Canonical list of subreddits with basic profile fields. |
| **SubredditMeta** | Infrequently changing metadata (description, rules, flairs). |
| **SubredditTopNewPostsSnapshot** | Rolling activity snapshots (post counts, scores) from async pipeline. |
| **SubredditPostGenerationRules** | Stores rules extracted from analysis of hot posts for training/guidance. |
| **SubredditPost** | Raw hot post metadata stored by hot-posts pipeline. |
| **VideoSubredditMap** | Mapping between videos and recommended subreddits. |
| **VideoSubredditAssessment** | Rich assessment metadata extracted from XML-based LLM pipeline. |
| **VideoSubredditGeneratedPost** | Final generated Reddit post (title, body, comments). |
| **ProcessedVideoRegistry** | Registry of already processed video IDs (prevents duplicates). |
| **PostMeta** | Mom Slack App — lightweight storage of Reddit post IDs. |
| **SlackComment** | Mom Slack App — stores individual Slack comments per post. |

---

### **DB Utilities**
| File | Description |
|------|-------------|
| **config.py** | SQLite engine + base declarative class. |
| **manager.py** | DBManager with create/drop/query/export helpers. |

---

# 4. ⚙️ Configuration Files (`reddit_watcher/settings_file/`)

### **settings.toml (default global configuration)**
- Base paths
- Logger name
- Timezone (`tz`)
- Utility Jinja timestamps

---

### **database.toml**
| Key | Description |
|-----|-------------|
| `DB_FILE` | Path to SQLite database file (prod + test variants). |

---

### **hot_posts.toml**
| Key | Description |
|-----|-------------|
| `hot_posts_batch_file` | JSON file containing subreddit batches. |
| `hot_posts_batch_size` | Number of subs per batch. |
| `hot_posts_fetch_limit` | Max hot posts fetched per subreddit. |
| `hot_posts_lock_file` | Lock file for ensuring exclusive cron run. |
| `hot_posts_limiter_*` | Rate limiting & workers. |
| `hot_posts_slack_channel_id` | Slack channel for reporting. |

---

### **subreddit_meta.toml**
| Key | Description |
|-----|-------------|
| `subreddit_meta_batch_size` | Rows fetched per batch. |
| `subreddit_meta_concurrency` | Async concurrency. |
| `subreddit_meta_rate_limit_*` | Rate limiter config. |
| `subreddit_meta_lock_file` | Lock file. |

---

### **subreddit_snapshot.toml**
| Key | Description |
|-----|-------------|
| `subreddit_batch_file` | Batch file for snapshot collector. |
| `subreddit_batch_size` | # subs processed per batch. |
| `limiter_*` | Rate limiting & workers. |
| `single_batch_wait_period` | Window for snapshot metrics. |
| `subreddit_snapshot_slack_channel_id` | Slack channel for pipeline results. |

---

### **youtube_watcher.toml**
| Key | Description |
|-----|-------------|
| `base_youtube_watcher_directory` | Directory where raw video JSON files are queued. |
| `kw_extraction_model_name` | Model used for LLM keyword extraction. |
| `max_subreddits_to_fetch` | Max subreddits fetched from Reddit search. |
| `video_processing_batch_size` | Number of videos processed per cycle. |
| `yt_ingest_slack_channel_id` | Notification channel ID. |

---

# 5. 🕒 Cron Pipelines (`crons/`)

| File | Purpose | Key Components |
|------|----------|----------------|
| **subreddit_snapshot_pipeline.py** | AsyncPRAW snapshot pipeline generating activity snapshots. | `AsyncSubredditCollector`, `AsyncRateLimiter`, `ExclusiveFileLock`, `DBManager`, Slack reports. |
| **subreddit_meta_update_pipeline.py** | Refreshes SubredditMeta for subs missing metadata. | Async meta collector, concurrency + rate limiter, Slack summary. |
| **hot_posts_pipeline.py** | Fetches HOT posts for marketable subreddits; inserts into `SubredditPost`. | Async collector, duplicate skipping, batch rotation, Slack reporting. |
| **video_ingestion_pipeline.py** | Extracts keywords via LLM, searches for subreddits, maps videos → subs. | `SubredditCollector`, `SimpleXMLParser`, `LLMFallbackCaller`, ORM mapping, Slack summary. |

---

# 6. 🤖 Agent Augmentation Rules

Whenever an agent **creates / updates / deletes** any file under `reddit_watcher/`:

### **File Creation**
- Add new entry under correct section & table.
- Include: filename, purpose, dependencies, inputs/outputs.

### **File Update**
- Replace the corresponding block in this summary.
- Keep tables valid and aligned.

### **File Deletion**
- Remove entry + add note under **Changelog** (auto-create if missing).

### **New Directories**
- Add a new subsection mirroring the existing layout.

---

# 7. 🧾 Changelog
(Add entries here automatically as the project evolves.)
