## 🧠 reddit_watcher Project Summary

### Core Modules
| File | Purpose | Key Links |
|------|----------|-----------|
| **collector.py** | Modular class `SubredditCollector` to fetch subreddit static data, weekly metadata, and short-term activity metrics using PRAW. Includes caching for efficiency. | Uses `reddit_api`, `omniconf.config`. Feeds data to ORM models. |
| **reddit_api.py** | Authenticates and returns a configured `praw.Reddit` instance. | Depends on `omniconf.config.reddit_auth`. |
| **omniconf.py** | Central configuration and logging hub using `Dynaconf`. Loads all `.toml` configs, initializes global `config` and `logger`. | Drives settings for all modules. |
| **slack_messenger.py** | Sends formatted pipeline updates to Slack using Web API. | Uses `config.slack` + `logger`. |
| **xml_parser.py** | Lightweight regex-based XML parser for simple tag extraction. | Utility — likely used in video/YT parsing. |

---

### Database Layer
| File | Purpose | Key Links |
|------|----------|-----------|
| **database/config.py** | Sets up SQLAlchemy `Base`, engine, and session from config. | Depends on `omniconf.config.DB_FILE`. |
| **database/models.py** | Defines ORM models: `Subreddit`, `SubredditMeta`, `SubredditTopNewPostsSnapshot`, `VideoSubredditMap`. | Data consumers of `collector.py`. |
| **database/manager.py** | CRUD and DB management via `DBManager` (create, query, drop, DataFrame exports). | Uses `database.config`. |

---

### Configuration Files (`settings_file/`)
| File | Scope | Key Variables |
|------|--------|----------------|
| **settings.toml** | Global defaults | `base_data_path`, `logger_name`, `tz`, runtime timestamps |
| **database.toml** | Database config | `DB_FILE` path for SQLite |
| **youtube_watcher.toml** | YouTube & LLM ingestion | `kw_extraction_model_name`, `max_subreddits_to_fetch`, `yt_ingest_slack_channel_id` |
| **subreddit_snapshot.toml** | Subreddit snapshot pipeline config | `subreddit_batch_size`, `subreddit_batch_file`, `subreddit_lock_file`, `subreddit_snapshot_slack_channel_id` |

---

### 🕒 Crons/
| File | Purpose | Key Components |
|------|----------|----------------|
| **subreddit_snapshot_pipeline.py** | Async Reddit snapshot pipeline using asyncpraw. Collects subreddit post snapshots in batches with rate limiting and Slack reporting. | Uses `AsyncRateLimiter`, `AsyncSubredditCollector`, `ExclusiveFileLock`, `DBManager`. |
| **video_ingestion_pipeline.py** | Video-to-subreddit marketing pipeline. Extracts keywords via LLM, finds relevant subreddits, and maps videos using ORM models. | Uses `SubredditCollector`, `SimpleXMLParser`, `LLMFallbackCaller`, `DBManager`, Slack notifications. |
| **subreddit_meta_update_pipeline.py** | Async cron that refreshes `SubredditMeta` data for all tracked subreddits with rate limiting and DB upserts. | Uses `AsyncRateLimiter`, `DBManager`, `reddit_api`, `SubredditMeta` ORM. |

---

### 🧩 Programming Methodology
- **Architecture:** Modular, layered — Config → Collector → Database → Notifier.  
- **Config Management:** Centralized in `omniconf.py` using `Dynaconf`, merging `.toml` layers dynamically.  
- **Persistence:** SQLAlchemy ORM with consistent model hierarchy and session manager.  
- **External I/O:** Reddit API (via PRAW), Slack Web API for alerts, regex-based XML parsing for feeds.  
- **Design Pattern:** Separation of concerns; composable utilities for automation and cron-based ingestion.

---

### 🛠 Utilities
| File | Purpose | Key Features |
|------|----------|---------------|
| **file_lock.py** | Provides an exclusive file lock context manager for preventing concurrent access to shared resources. | Uses `fcntl` for process-safe locking with optional fail-fast exit. |
| **rate_limiter.py** | Async token-bucket based rate limiter for controlling API request rates. | Supports strict/smooth modes; integrates with async tasks in Reddit collectors. |

---

### 🤖 Agent Augmentation Instructions
Whenever the AI agent **creates**, **updates**, or **deletes** a file inside the `reddit_watcher` directory:

1. **File Creation:**  
   - Append a new entry under the appropriate section in this summary.  
   - Include filename, short description (1–2 lines), dependencies, and purpose.

2. **File Update:**  
   - Locate the corresponding file’s summary in this document.  
   - Replace the old summary block with updated functionality notes.  
   - Preserve markdown table consistency.

3. **File Deletion:**  
   - Remove the file’s entry from its respective section.  
   - Add a brief note in a `Changelog` section (create one if absent) indicating file removal.

4. **New Directories:**  
   - Create a new markdown subsection (`### <directory_name>/`) with similar table structure.

All modifications to this file must be atomic and self-contained so it always remains a valid, up-to-date **project map** for downstream autonomous agents.