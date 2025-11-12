import sys
import json
import asyncio
import math
from datetime import datetime
from pathlib import Path

from reddit_watcher.file_lock import ExclusiveFileLock
from reddit_watcher.reddit_api import (
    get_reddit_instance,
    get_reddit_instance_async,
    sanitize_subreddit_name,
)  # now asyncpraw
from reddit_watcher.database.manager import DBManager
from reddit_watcher.database.models import (
    SubredditTopNewPostsSnapshot,
    Subreddit,
    VideoSubredditAssessment,
)
from reddit_watcher.collector import AsyncSubredditCollector  # async collector
from reddit_watcher.omniconf import config, logger
from reddit_watcher.slack_messenger import send_slack_message as send_slack_message_base
from reddit_watcher.rate_limiter import AsyncRateLimiter


BATCH_FILE = Path(config.subreddit_batch_file)
LOCK_FILE = Path(config.subreddit_lock_file)
BATCH_SIZE = config.subreddit_batch_size

# Ensure directories exist
BATCH_FILE.parent.mkdir(exist_ok=True, parents=True)
LOCK_FILE.parent.mkdir(exist_ok=True, parents=True)


def now():
    return datetime.utcnow()


START_TIME = now()


def send_slack_message(message: str) -> None:
    send_slack_message_base(
        message + f"\n\nlogfile: `/tmp/sub_snapshot.cron.log`\n",
        slack_channel_id=getattr(config, "subreddit_snapshot_slack_channel_id", None)
        or config.yt_ingest_slack_channel_id,
        header="Reddit: Subreddit Snapshot",
    )


# Batch generation if not already exists


def generate_subreddit_batches():
    logger.info("📦 Generating subreddit batches snapshot")

    db = DBManager()
    # marketable_subreddit_ids = db.session.query(Subreddit).order_by(Subreddit.id).all()

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

    BATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    BATCH_FILE.write_text(json.dumps(snapshot, indent=2))
    logger.info(
        f"Saved {total_batches} batches ({BATCH_SIZE} per batch) to {BATCH_FILE}"
    )

    db.close()


# ---------------- ASYNC WORKER ---------------- #


async def collect_subreddit_snapshot(name: str, limiter: AsyncRateLimiter, reddit):
    """
    Collect snapshot for a single subreddit asynchronously with rate limiting.
    """
    try:
        await limiter.acquire()
        sub = await reddit.subreddit(sanitize_subreddit_name(name), fetch=True)
        collector = AsyncSubredditCollector(sub)
        snapshot_data = await collector.collect_new_posts_snapshot(
            window_minutes=config.single_batch_wait_period
        )
        return name, snapshot_data, None
    except Exception as e:
        return name, None, str(e)


async def process_batch_async(current_batch, db: DBManager):
    """
    Process a single subreddit batch concurrently, yielding results as each finishes.
    """
    limiter = AsyncRateLimiter(
        max_calls=config.subreddit_batch_size, period=config.limiter_period_seconds
    )  # Adjust as per quota
    semaphore = asyncio.Semaphore(config.limiter_num_workers)  # Concurrency cap

    # Create a single shared reddit instance
    reddit = await get_reddit_instance_async()

    async def _worker(name):
        async with semaphore:
            return await collect_subreddit_snapshot(name, limiter, reddit)

    tasks = [asyncio.create_task(_worker(name)) for name in current_batch]
    successful, failed = 0, 0

    async for finished in _as_completed(tasks):
        name, snapshot, error = finished
        if error:
            failed += 1
            logger.error(f"❌ {name}: {error}")
        else:
            try:
                existing_sub = db.session.query(Subreddit).filter_by(name=name).first()
                record = SubredditTopNewPostsSnapshot(
                    subreddit_id=existing_sub.id, timestamp=START_TIME, **snapshot
                )
                db.insert_record(record)
                successful += 1
                logger.info(f"✅ {name} snapshot inserted.")
            except Exception as db_err:
                failed += 1
                logger.exception(f"Failed DB insert for {name}: {db_err}")

    # Cleanup Reddit session
    await reddit.close()

    return successful, failed


async def _as_completed(tasks):
    """Async generator that yields results as tasks complete."""
    for task in asyncio.as_completed(tasks):
        yield await task


# ---------------- ENTRYPOINT ---------------- #


def process_subreddit_snapshots():
    logger.info("🚀 Starting subreddit snapshot pipeline (asyncpraw version)")
    start_time = now()
    db = DBManager()

    if not BATCH_FILE.exists():
        logger.error(
            "Batch file not found. Please run generate_subreddit_batches.py first."
        )
        return 1

    with open(BATCH_FILE, "r") as f:
        data = json.load(f)

    batches = data["batches"]
    batch_index = data["current_batch_index"]
    current_batch = batches[str(batch_index)]
    batch_size = len(current_batch)

    logger.info(
        f'Processing batch {batch_index + 1}/{data["total_batches"]} ({batch_size} subreddits)'
    )

    successful, failed = asyncio.run(process_batch_async(current_batch, db))

    duration = (now() - start_time).total_seconds()
    message = (
        f"*📊 Subreddit Snapshot Pipeline Summary*\n"
        f'> *Run Time:* {duration:.1f}s  |  *Batch:* {batch_index + 1}/{data["total_batches"]}\n\n'
        f"*Subreddits Processed:* `{batch_size}`\n"
        f"• ✅ Successful: `{successful}`\n"
        f"• ❌ Failed: `{failed}`\n\n"
        f"_{'🎉 All good!' if failed == 0 else '🚨 Some errors occurred. Check logs.'}_"
    )
    send_slack_message(message)

    # Rotate to next batch safely
    data["current_batch_index"] = (batch_index + 1) % data["total_batches"]
    with open(BATCH_FILE, "w") as f:
        json.dump(data, f)

    db.close()
    logger.info("🧹 Database connection closed.")
    logger.info(
        f"🎯 Completed subreddit snapshot pipeline — {successful}/{batch_size} succeeded."
    )


if __name__ == "__main__":
    with ExclusiveFileLock(LOCK_FILE.as_posix()):
        if not BATCH_FILE.exists():
            logger.info("Snapshot batch file does not exist")
            generate_subreddit_batches()
        exit_code = process_subreddit_snapshots()
        sys.exit(exit_code)
