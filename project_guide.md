# 📘 reddit_watcher — Unified Project Guide (Paths Root-Relative)

This document is the single authoritative overview of the system: its
architecture, modules, pipelines, Slack logic, and the operational expectations
for any agent working inside this project.

# 1. High-Level Purpose

The project automates:

* Reddit data collection (snapshots, metadata, hot posts)
* Video → subreddit discovery via LLM
* Reddit post generation for marketing
* Slack-based monitoring, moderation helpers, and mom-assistant integrations

All behavior is configuration-driven through TOML and thin pipelines.

# 2. Repository Layout

```
./reddit_watcher/
    omniconf.py
    reddit_api.py
    collector.py
    slack_messenger.py
    rate_limiter.py
    file_lock.py
    xml_parser.py
    database/
        config.py
        manager.py
        models.py
        agent.md   ← Reference for all DB/model interaction rules
    settings_file/
        settings.toml
        *.toml

./crons/
    subreddit_snapshot_pipeline.py
    subreddit_meta_update_pipeline.py
    hot_posts_pipeline.py
    video_ingestion_pipeline.py

./slack_monitor.py  ← Slack thread monitoring & comment logging
```

# 3. Configuration System

Configuration is managed via Dynaconf (`./reddit_watcher/omniconf.py`):

* Loads base settings + all TOML modules in `./reddit_watcher/settings_file/`
* Provides:
  * Global `config` object
  * Date/time helpers
  * Standardized project paths
  * Global logger

Rules:

* Agents modify only TOML files for tunables.
* Code may read config but must not hard-code pipeline parameters.
* All logging must use the project logger.

# 4. Core Components

## 4.1 Collectors

From `./reddit_watcher/collector.py`:

The **AsyncSubredditCollector** is the primary component used by all asynchronous pipelines to interact with Reddit. It encapsulates all required logic for fetching static metadata, weekly metadata, and post activity snapshots, ensuring compliance with operational and rate-limiting rules.

For a detailed breakdown of all available collector methods and the specific data they extract, consult:

```
./COLLECTOR_METADATA_GUIDE.md
```

**Note:** Only reference `COLLECTOR_METADATA_GUIDE.md` when planning or debugging a component that involves fetching data from the Reddit API. For all other tasks, refer to the other sections of this guide.

## 4.2 Database Layer

All details regarding:

* Available data models
* How data flows between them
* Required patterns for insertion, updates, deletion, and querying
* Duplicate-safe interactions
* Valid and invalid DB usage patterns

…are documented in:

```
./reddit_watcher/database/agent.md
```

**Whenever your task requires interacting with the database or its models,
consult `agent.md` first.** Do not interact directly with the models or
SQLAlchemy session unless explicitly permitted there.

All DB writes must use:

```
./reddit_watcher/database/manager.py   (DBManager)
```

# 5. Pipeline Architecture

Every cron task follows this structure:

1. Acquire `ExclusiveFileLock` (`./reddit_watcher/file_lock.py`)
2. Load or rotate batch file (if applicable)
3. Initialize:
   * Async Reddit client (`asyncpraw`)
   * `DBManager`
   * `AsyncRateLimiter` (`./reddit_watcher/rate_limiter.py`)
4. Concurrent subreddit processing
5. DB writes via inserts or upserts
6. Slack summary notification (`./reddit_watcher/slack_messenger.py`)

## Available Pipelines (`crons/`)

* `crons/subreddit_snapshot_pipeline.py`
* `crons/subreddit_meta_update_pipeline.py`
* `crons/hot_posts_pipeline.py`
* `crons/video_ingestion_pipeline.py`

# 6. Slack Messaging (Outbound)

Located in `./reddit_watcher/slack_messenger.py`:

* Structured formatting via `format_message_in_box`
* Safe Slack API interaction
* Pipeline-specific channel routing via config

Agents must **never** call Slack APIs manually.

# 7. Slack Monitoring & Logging (Inbound)

Located in `./slack_monitor.py`.

### Purpose
Monitors Slack threads where Reddit posts were shared, and logs every human
reply into the database.

### Behavior

* Listens only for **human** replies in the configured Slack channel.
* Extracts metadata from the root message:
  * `subreddit_id`
  * `post_id`
* Stores each reply using the new model `SlackThreadComment`.
* Uses `DBManager.insert_record` for persistence.
* Ensures safe handling of inconsistent metadata or malformed messages.

This allows Slack-side human discussion to be archived and joined with Reddit
side activity.

# 8. Agent Operational Rules

1. Always read configuration from `omniconf.config`.
2. Modify parameters only via TOML files.
3. Follow existing pipeline structure when extending:
   * Batch files
   * Lock files
   * `AsyncSubredditCollector`
   * `AsyncRateLimiter`
   * Slack summaries
4. All DB writes go through `DBManager`.
5. Maintain async-safe behavior in collectors.
6. Avoid rewriting large files unless explicitly instructed.
7. Use the project logger consistently.
8. When adding new tables:
   * Define models in `./reddit_watcher/database/models.py`
   * Ensure compatibility with existing structures
9. Do not bypass collectors when interacting with Reddit.
10. For Slack monitoring:
   * Use only `slack_monitor.py`
   * Use `DBManager` for all writes
   * Maintain metadata decoding from root message blocks

# 9. Extending the System

When creating a new pipeline:

* Add a dedicated TOML file in `./reddit_watcher/settings_file/`
* Follow the same architecture as existing pipelines
* Reuse `AsyncSubredditCollector` + `DBManager`

When adding new models:

* Add them in `./reddit_watcher/database/models.py`
* Add them to this guide under *Database Layer*
* Follow the pattern: timestamps via `now()`, simple table names, consistent
  field naming

When adjusting Reddit behavior:

* Modify `./reddit_watcher/collector.py`
* Keep async/sync variants consistent

# 10. Decision Matrix

| Task                       | Modify                                | Avoid                   |
| -------------------------- | ------------------------------------- | ----------------------- |
| Change pipeline parameters | TOML                                  | Python constants        |
| Add Reddit features        | `./reddit_watcher/collector.py`       | `omniconf` internals    |
| Add new DB model           | `./reddit_watcher/database/models.py` | DBManager logic         |
| Modify logging             | logger in `omniconf`                  | prints inside pipelines |
| Slack formatting           | `./reddit_watcher/slack_messenger.py` | direct Slack API use    |
| Slack monitoring           | `./slack_monitor.py`                  | editing pipelines       |

# 11. Summary

This unified guide contains the essential architectural knowledge and
operational constraints required for agents to safely update, debug, or extend
the reddit_watcher project.

As of the latest update, Slack inbound comment logging is fully supported
through the `SlackThreadComment` model and the monitoring logic in
`slack_monitor.py`.