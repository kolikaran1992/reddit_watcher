# 📘 reddit_watcher

This document is the single authoritative overview of the system


# 1. Repository Layout

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

# 2. Configuration System

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

# 3. Extending the System

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
