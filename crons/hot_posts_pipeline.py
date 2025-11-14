import sys
import json
import asyncio
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from reddit_watcher.file_lock import ExclusiveFileLock
from reddit_watcher.reddit_api import (
    get_reddit_instance_async,
    sanitize_subreddit_name,
)
from reddit_watcher.database.manager import DBManager
from reddit_watcher.database.models import (
    Subreddit,
    VideoSubredditAssessment,
    SubredditPost,
)
from reddit_watcher.collector import AsyncSubredditCollector
from reddit_watcher.omniconf import config, logger
from reddit_watcher.slack_messenger import send_slack_message as send_slack_message_base
from reddit_watcher.rate_limiter import AsyncRateLimiter


# --- CONFIGURATION ---
# Use dedicated config variables for the hot posts pipeline
BATCH_FILE = Path(config.hot_posts_batch_file)
LOCK_FILE = Path(config.hot_posts_lock_file)
BATCH_SIZE = config.hot_posts_batch_size
HOT_POST_FETCH_LIMIT = config.hot_posts_fetch_limit

# Ensure directories exist
BATCH_FILE.parent.mkdir(exist_ok=True, parents=True)
LOCK_FILE.parent.mkdir(exist_ok=True, parents=True)


def now():
    return datetime.utcnow()


START_TIME = now()


def send_slack_message(message: str) -> None:
    send_slack_message_base(
        message + f"\n\nlogfile: `/tmp/hot_posts.cron.log`\n",
        slack_channel_id=getattr(config, "hot_posts_slack_channel_id", None)
        or config.yt_ingest_slack_channel_id,
        header="Reddit: Hot Posts Pipeline",
    )


# Batch generation logic - exact mirror of snapshot pipeline
def generate_subreddit_batches():
    logger.info("📦 Generating hot posts subreddit batches")

    db = DBManager()

    # Fetch only marketable subreddits for batching
    marketable_subreddits = (
        db.session.query(VideoSubredditAssessment.subreddit_id, Subreddit.name)
        .join(Subreddit, VideoSubredditAssessment.subreddit_id == Subreddit.id)
        .filter(VideoSubredditAssessment.is_marketable == "yes")
        .group_by(VideoSubredditAssessment.subreddit_id, Subreddit.name)
        .order_by(VideoSubredditAssessment.subreddit_id)
        .all()
    )

    total = len(marketable_subreddits)
    total_batches = math.ceil(total / BATCH_SIZE)
    batches = {}

    for i in range(total_batches):
        start = i * BATCH_SIZE
        end = start + BATCH_SIZE
        batches[str(i)] = [s.name for s in marketable_subreddits[start:end]]

    snapshot = {
        "batch_size": BATCH_SIZE,
        "total_batches": total_batches,
        "batches": batches,
        "current_batch_index": 0,
    }

    BATCH_FILE.write_text(json.dumps(snapshot, indent=2))
    logger.info(
        f"Saved {total_batches} batches ({BATCH_SIZE} per batch) to {BATCH_FILE}"
    )

    db.close()


# ---------------- ASYNC WORKER ---------------- #


async def collect_hot_posts_snapshot(name: str, limiter: AsyncRateLimiter, reddit):
    """
    Collect hot posts metadata for a single subreddit asynchronously with rate limiting.
    """
    try:
        await limiter.acquire()
        sub = await reddit.subreddit(sanitize_subreddit_name(name), fetch=True)
        collector = AsyncSubredditCollector(sub)
        # Use the new collector method
        hot_posts_data = await collector.collect_hot_posts_metadata(
            limit=HOT_POST_FETCH_LIMIT
        )
        return name, hot_posts_data, None
    except Exception as e:
        return name, None, str(e)


async def process_batch_async(current_batch: List[str], db: DBManager):
    """
    Process a single subreddit batch concurrently, yielding results as each finishes.
    """
    # Rate limiter setup uses general config keys
    limiter = AsyncRateLimiter(
        max_calls=BATCH_SIZE, period=config.hot_posts_limiter_period_seconds
    )
    semaphore = asyncio.Semaphore(
        config.hot_posts_limiter_num_workers
    )  # Concurrency cap

    # Create a single shared reddit instance
    reddit = await get_reddit_instance_async()

    async def _worker(name):
        async with semaphore:
            return await collect_hot_posts_snapshot(name, limiter, reddit)

    tasks = [asyncio.create_task(_worker(name)) for name in current_batch]
    subreddits_processed, posts_inserted, failed_subreddits = 0, 0, 0

    async for finished in _as_completed(tasks):
        name, posts_data, error = finished
        subreddits_processed += 1

        if error:
            failed_subreddits += 1
            logger.error(f"❌ {name}: {error}")
            continue

        if not posts_data:
            logger.info(f"⚠️ {name}: No posts returned.")
            continue

        try:
            # Get existing Subreddit ID once
            existing_sub = db.session.query(Subreddit).filter_by(name=name).first()
            if not existing_sub:
                logger.warning(f"Skipping {name}: Subreddit not found in DB.")
                failed_subreddits += 1
                continue

            successful_inserts = 0
            skipped_existing = 0

            # Preload existing post_ids for efficiency
            existing_post_ids = {
                pid
                for (pid,) in db.session.query(SubredditPost.post_id)
                .filter_by(subreddit_id=existing_sub.id)
                .all()
            }

            # Insert each post individually, skipping duplicates
            for post in posts_data:
                try:
                    post_id = post.get("post_id")
                    if post_id in existing_post_ids:
                        skipped_existing += 1
                        continue  # skip duplicates

                    record = SubredditPost(subreddit_id=existing_sub.id, **post)
                    db.insert_record(record)
                    successful_inserts += 1

                except Exception as post_err:
                    logger.error(f"⚠️ Failed to insert post in {name}: {post_err}")

            posts_inserted += successful_inserts

            logger.info(
                f"✅ {name}: {successful_inserts}/{len(posts_data)} posts inserted "
                f"(⏭️ {skipped_existing} skipped as duplicates)."
            )

        except Exception as db_err:
            failed_subreddits += 1
            db.session.rollback()
            logger.exception(f"Failed DB insert for {name}: {db_err}")

    # Cleanup Reddit session
    await reddit.close()

    return subreddits_processed, posts_inserted, failed_subreddits


async def _as_completed(tasks):
    """Async generator that yields results as tasks complete."""
    for task in asyncio.as_completed(tasks):
        yield await task


# ---------------- ENTRYPOINT ---------------- #


def process_hot_posts_pipeline():
    logger.info("🚀 Starting Hot Posts Pipeline (asyncpraw version)")
    start_time = now()
    db = DBManager()

    if not BATCH_FILE.exists():
        logger.error("Batch file not found. Please run batch generation script first.")
        return 1

    try:
        with open(BATCH_FILE, "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception(f"Failed to load batch file: {e}")
        return 1

    batches = data["batches"]
    batch_index = data["current_batch_index"]
    current_batch = batches.get(str(batch_index))

    if not current_batch:
        logger.error(f"Batch index {batch_index} not found in file.")
        # Reset index to 0 to restart the cycle
        data["current_batch_index"] = 0
        try:
            with open(BATCH_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass
        return 1

    batch_size = len(current_batch)

    logger.info(
        f'Processing batch {batch_index + 1}/{data["total_batches"]} ({batch_size} subreddits)'
    )

    # Run the async processing
    subreddits_processed, posts_inserted, failed_subreddits = asyncio.run(
        process_batch_async(current_batch, db)
    )

    duration = (now() - start_time).total_seconds()
    message = (
        f"*📊 Hot Posts Pipeline Summary*\n"
        f'> *Run Time:* {duration:.1f}s  |  *Batch:* {batch_index + 1}/{data["total_batches"]}\n\n'
        f"*Subreddits Processed:* `{subreddits_processed}`\n"
        f"*Total Posts Inserted:* `{posts_inserted}`\n"
        f"• ✅ Successful Subreddits: `{subreddits_processed - failed_subreddits}`\n"
        f"• ❌ Failed Subreddits: `{failed_subreddits}`\n\n"
        f"_{'🎉 All good!' if failed_subreddits == 0 else '🚨 Some errors occurred. Check logs.'}_"
    )
    send_slack_message(message)

    # Rotate to next batch safely
    data["current_batch_index"] = (batch_index + 1) % data["total_batches"]
    try:
        with open(BATCH_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.exception(f"Failed to write batch file: {e}")
        # Do not return 1 here, as the main work was completed.

    db.close()
    logger.info("🧹 Database connection closed.")
    logger.info(
        f"🎯 Completed Hot Posts Pipeline — {subreddits_processed - failed_subreddits}/{subreddits_processed} succeeded."
    )
    return 0


if __name__ == "__main__":
    # Use a unique lock file for this pipeline
    with ExclusiveFileLock(LOCK_FILE.as_posix()):
        if not BATCH_FILE.exists():
            logger.info("Hot Posts batch file does not exist. Generating batches.")
            generate_subreddit_batches()
        exit_code = process_hot_posts_pipeline()
        sys.exit(exit_code)
