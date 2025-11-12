import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from reddit_watcher.file_lock import ExclusiveFileLock
from reddit_watcher.reddit_api import get_reddit_instance_async, sanitize_subreddit_name
from reddit_watcher.database.manager import DBManager
from reddit_watcher.database.models import Subreddit, SubredditMeta
from reddit_watcher.omniconf import config, logger
from reddit_watcher.slack_messenger import send_slack_message as send_slack_message_base
from reddit_watcher.rate_limiter import AsyncRateLimiter
from reddit_watcher.collector import AsyncSubredditCollector


LOCK_FILE = Path(config.subreddit_lock_file)
LOCK_FILE.parent.mkdir(exist_ok=True, parents=True)


def now():
    return datetime.utcnow()


def send_slack_message(message: str) -> None:
    send_slack_message_base(
        message + "\n log_file: `/tmp/sub_meta_ext.cron.log`\n",
        slack_channel_id=getattr(config, "subreddit_snapshot_slack_channel_id", None)
        or getattr(config, "yt_ingest_slack_channel_id", None),
        header="Reddit: Subreddit Meta Update",
    )


async def update_subreddit_meta(
    subreddit_row, limiter: AsyncRateLimiter, reddit, db: DBManager
):
    """Fetch and update subreddit metadata using AsyncSubredditCollector and subreddit_id FK."""
    try:
        await limiter.acquire()
        name = subreddit_row.get("name", "")
        subreddit_id = subreddit_row.get("id", "")

        try:
            sub = await reddit.subreddit(sanitize_subreddit_name(name), fetch=True)
            collector = AsyncSubredditCollector(sub)
            meta_data = await collector.collect_meta()
            meta_data["subreddit_id"] = subreddit_id

        except Exception as e:
            # Handle 403 Forbidden (e.g., private/banned subreddits)
            if "403" in str(e) or "Forbidden" in str(e):
                logger.warning(f"⚠️ 403 Forbidden for {name} — inserting null metadata.")
                meta_data = {"subreddit_id": subreddit_id}
                # Set all nullable fields to None explicitly (except subreddit_id)
                for col in SubredditMeta.__table__.columns.keys():
                    if col != "subreddit_id":
                        meta_data[col] = None
            else:
                raise  # re-raise other errors

        existing = (
            db.session.query(SubredditMeta).filter_by(subreddit_id=subreddit_id).first()
        )
        if existing:
            for k, v in meta_data.items():
                setattr(existing, k, v)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise e
            logger.info(f"🔄 Updated meta for {name}")
        else:
            try:
                record = SubredditMeta(**meta_data)
                db.insert_record(record)
                logger.info(f"✅ Inserted meta for {name}")
            except Exception as e:
                db.session.rollback()
                raise e

        return name, None

    except Exception as e:
        db.session.rollback()
        name = subreddit_row.get("name", "")
        logger.exception(f"Failed to update meta for {name}: {e}")
        return name, str(e)


async def process_batch_async(subreddit_rows, db: DBManager):
    max_calls = getattr(config, "subreddit_meta_rate_limit_calls", 20)
    period = getattr(config, "subreddit_meta_rate_limit_period", 60)
    concurrency = getattr(config, "subreddit_meta_concurrency", 5)

    limiter = AsyncRateLimiter(max_calls=max_calls, period=period)
    semaphore = asyncio.Semaphore(concurrency)
    reddit = await get_reddit_instance_async()

    async def _worker(row):
        async with semaphore:
            return await update_subreddit_meta(row, limiter, reddit, db)

    tasks = [asyncio.create_task(_worker(row)) for row in subreddit_rows]
    successful, failed = 0, 0

    for coro in asyncio.as_completed(tasks):
        name, error = await coro
        if error:
            failed += 1
            logger.error(f"❌ {name}: {error}")
        else:
            successful += 1

    await reddit.close()
    return successful, failed


def process_subreddit_meta_updates():
    logger.info(
        "🚀 Starting subreddit meta update pipeline (AsyncSubredditCollector version)"
    )
    start_time = now()
    db = DBManager()

    try:
        batch_size = getattr(config, "subreddit_meta_batch_size", 50)

        query = f"""
        select 
            *
        from
            subreddits
        where
            id not in (
                select subreddit_id from subreddit_meta
            )
        limit {batch_size}
        """
        missing_rows = db.query_to_df(query).to_dict(orient="records")
        # subquery = select(SubredditMeta.subreddit_id).scalar_subquery()

        # missing_rows = (
        #     db.session.query(Subreddit)
        #     .filter(Subreddit.id.notin_(subquery))
        #     .limit(batch_size)
        #     .all()
        # )
        if not missing_rows:
            logger.info("✅ All subreddits already have metadata. Nothing to update.")
            return 0

        logger.info(
            f"Processing {len(missing_rows)} missing subreddit metadata entries..."
        )
        successful, failed = asyncio.run(process_batch_async(missing_rows, db))

        duration = (now() - start_time).total_seconds()
        message = (
            f"*🧩 Subreddit Meta Update Summary*\n"
            f"> *Run Time:* {duration:.1f}s | *Processed:* {len(missing_rows)}\n\n"
            f"• ✅ Successful: `{successful}`\n"
            f"• ❌ Failed: `{failed}`\n\n"
            f"_{'🎉 All metadata updated successfully!' if failed == 0 else '⚠️ Some updates failed — check logs.'}_"
        )
        send_slack_message(message)
        logger.info(
            f"🎯 Completed subreddit meta update pipeline — {successful}/{len(missing_rows)} succeeded."
        )
        return 0
    finally:
        db.close()
        logger.info("🧹 Database connection closed.")


if __name__ == "__main__":
    with ExclusiveFileLock(LOCK_FILE.as_posix()):
        exit_code = process_subreddit_meta_updates()
        sys.exit(exit_code)
