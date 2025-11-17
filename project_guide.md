# 📘 reddit_watcher — Unified Project Guide

This document is the single authoritative overview of the system: its architecture, modules, pipelines, database schema, and the operational expectations for any agent working inside this project.

# 1. High-Level Purpose

The project automates:
- Reddit data collection (snapshots, metadata, hot posts)
- Video → subreddit discovery via LLM
- Reddit post generation for marketing
- Slack-based monitoring and mom-assistant integrations

All behavior is configuration-driven through TOML and thin pipelines.

# 2. Repository Layout

reddit_watcher/
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
    settings_file/
        settings.toml
        *.toml

crons/
    subreddit_snapshot_pipeline.py
    subreddit_meta_update_pipeline.py
    hot_posts_pipeline.py
    video_ingestion_pipeline.py

# 3. Configuration System

Configuration is managed via Dynaconf (`omniconf.py`):
- Loads base settings + all TOML modules in `settings_file/`
- Provides:
  - Global `config` object
  - Date/time helpers
  - Standardized project paths
  - Global logger

Rules:
- Agents modify only TOML files for tunables.
- Code may read config but must not hard-code pipeline parameters.
- All logging must use the project logger.

# 4. Core Components

## 4.1 Collectors

AsyncSubredditCollector
- Primary component for pipelines
- Provides:
  - Static metadata
  - Weekly metadata (rules, flairs, description)
  - Activity snapshot (recent posts)
  - Hot posts metadata

SubredditCollector
- Used for the video ingestion pipeline
- Lightweight static-only collector

## 4.2 Database Layer

Located in `database/models.py`:
- Subreddits
- SubredditMeta
- SubredditTopNewPostsSnapshot
- SubredditPost (hot posts)
- VideoSubredditMap
- VideoSubredditAssessment
- VideoSubredditGeneratedPost
- ProcessedVideoRegistry
- Mom Slack App tables (PostMeta, SlackComment)

Database access is performed exclusively through DBManager:
- insert_record
- delete
- query_to_df
- session management

# 5. Pipeline Architecture

Every cron task follows this structure:
1. Acquire ExclusiveFileLock
2. Load or rotate batch file (if applicable)
3. Initialize:
   - Async Reddit client (asyncpraw)
   - DBManager
   - AsyncRateLimiter
4. Concurrent subreddit processing
5. DB writes via inserts or upserts
6. Slack summary notification

## Available Pipelines

subreddit_snapshot_pipeline
- Collects activity snapshots (top new posts window).

subreddit_meta_update_pipeline
- Updates weekly subreddit metadata.

hot_posts_pipeline
- Collects hot post metadata for rule extraction and analytics.

video_ingestion_pipeline
- Processes queued YouTube videos → generates keyword list via LLM → identifies relevant subreddits → writes mappings.

# 6. Slack Messaging

`slack_messenger.py`:
- Structured formatting via `format_message_in_box`
- Safe Slack API interaction
- Pipeline-specific channel routing via config

Agents must not call Slack APIs manually.

# 7. Agent Operational Rules

1. Always read configuration from `omniconf.config`.
2. Modify parameters only via TOML files.
3. When extending or creating pipelines, follow established patterns:
   - batch files
   - lock files
   - AsyncSubredditCollector
   - AsyncRateLimiter
   - Slack summary
4. All DB writes go through DBManager.
5. Maintain async-safe behavior in collectors and pipelines.
6. Avoid rewriting large files unless explicitly instructed.
7. Use the project logger consistently.
8. When adding new tables:
   - define models in `models.py`
   - ensure compatibility with existing pipelines
9. Do not bypass collectors when interacting with Reddit.

# 8. Extending the System

When creating a new pipeline:
- Add a dedicated TOML configuration file
- Use the same architecture as existing pipelines
- Reuse AsyncSubredditCollector + DBManager

When adding new models:
- Place definitions in `models.py`
- Ensure relationships are declared
- Use DBManager for interactions

When adjusting Reddit behavior:
- Modify `collector.py`
- Keep async/sync variants consistent

# 9. Decision Matrix

| Task | Modify | Avoid |
|------|--------|-------|
| Change pipeline parameters | TOML | Python constants |
| Add Reddit features | collector.py | omniconf internals |
| Add new DB model | models.py | DBManager logic |
| Modify logging | omniconf logger | pipeline-level prints |
| Slack formatting | slack_messenger.py | direct Slack API use |

# 10. Summary

This unified guide contains the essential architectural knowledge and operational constraints required for agents to safely update, debug, or extend the reddit_watcher project.