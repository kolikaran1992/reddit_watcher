import json
import math
from pathlib import Path

from reddit_watcher.database.manager import DBManager
from reddit_watcher.database.models import Subreddit
from reddit_watcher.omniconf import config, logger

BATCH_SIZE = config.subreddit_batch_size
BATCH_FILE = config.subreddit_batch_file


def generate_subreddit_batches():
    logger.info("📦 Generating subreddit batches snapshot")

    db = DBManager()
    subs = db.session.query(Subreddit).order_by(Subreddit.id).all()

    total = len(subs)
    total_batches = math.ceil(total / BATCH_SIZE)
    batches = {}

    for i in range(total_batches):
        start = i * BATCH_SIZE
        end = start + BATCH_SIZE
        batches[str(i)] = [s.name for s in subs[start:end]]

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


if __name__ == "__main__":
    generate_subreddit_batches()
