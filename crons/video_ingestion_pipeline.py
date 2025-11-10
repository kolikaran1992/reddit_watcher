import json
import sys
from pathlib import Path
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

from reddit_watcher.reddit_api import get_reddit_instance
from reddit_watcher.database.manager import DBManager
from reddit_watcher.database.models import Subreddit, VideoSubredditMap
from reddit_watcher.collector import SubredditCollector
from reddit_watcher.omniconf import config, logger
from reddit_watcher.xml_parser import SimpleXMLParser
from reddit_watcher.slack_messenger import send_slack_message as send_slack_message_base

from meter_call import LLMFallbackCaller


# ---------- Utility ----------
def now():
    """Centralized UTC timestamp."""
    return datetime.utcnow()


def send_slack_message(message: str) -> None:
    send_slack_message_base(
        message,
        slack_channel_id=config.yt_ingest_slack_channel_id,
        header="Marketing: Video Ingestion",
    )


SYSTEM_PROMPT = """
You are a Reddit marketing keyword generator that understands Indian cooking, Hinglish, and food culture.

Your job:
Given a YouTube recipe title and description (which may be written in Hinglish or imperfect English),
generate precise Reddit search keywords that will help find relevant subreddits
for marketing the video.

Guidelines:
1. Understand the actual dish — use real culinary meaning. For example:
   - "seeta phal ki sabji" → "pumpkin curry", "Indian cooking", "vegetarian food".
   - "aloo fry" → "potato fry", "Indian snacks".
2. Exclude misleading or wrong interpretations (like confusing “sitaphal” with “custard apple”).
3. Prefer 1–3 word phrases that real Reddit users might search as community topics.
4. Use normal spacing (e.g., “Food Videos”, not “FoodVideos”).
5. Focus on dish name, cuisine, ingredients, diet type, and cooking context.
6. Avoid redundant or vague words like “recipe”, “video”, “tasty”, “delicious”.

Output:
Return **only** one XML block in this format:

<keywords>
comma-separated list of meaningful, space-separated keywords
</keywords>
"""

USER_PROMPT = """
Now, generate the output for the following video:
Title: "{title}"
Description: "{description}"
"""


# ---------- LLM Keyword Extraction ----------
def extract_keywords_from_llm(
    title: str, description: str, llm_caller: LLMFallbackCaller
) -> list[str]:
    """Use LLM to generate keyword list from YouTube title + description."""

    try:
        model_output = llm_caller.call(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "system",
                    "content": USER_PROMPT.format(title=title, description=description),
                },
            ]
        )
        xml_content = model_output.choices[0].message.content
        kws_text = SimpleXMLParser.extract_tag_content(xml_content, "keywords")
        kws_list = [kw.strip().lower() for kw in kws_text.split(",") if kw.strip()]
        logger.info(f"Extracted {len(kws_list)} keywords: {kws_list}")
        return kws_list

    except Exception as e:
        logger.exception(f"LLM keyword extraction failed: {e}")
        return []


# ---------- Video Discovery ----------
def load_unprocessed_videos(base_dir: Path, db: DBManager) -> list[Path]:
    """Return paths to unprocessed video JSON files."""
    paths = list(base_dir.glob("*.json"))
    unprocessed = []
    for p in paths:
        video_id = p.stem  # filename = video_id
        exists = (
            db.session.query(VideoSubredditMap).filter_by(video_id=video_id).first()
        )
        if not exists:
            unprocessed.append(p)

    bs = min(len(unprocessed), config.video_processing_batch_size)
    logger.info(
        f"Found {len(unprocessed)} unprocessed video files. Processing {bs} videos"
    )
    return unprocessed[: config.video_processing_batch_size]


# ---------- Slack Summary Helper ----------
def send_pipeline_summary(stats: dict):
    """Prepare and send a summary message to Slack."""
    duration = stats["duration"]
    message = (
        f"*📊 Reddit Marketing Pipeline Summary*\n"
        f"> *Run Time:* {duration:.1f}s  |  *Start:* {stats['start_time'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        f"*Videos Processed:* `{stats['total_videos']}`\n"
        f"• ✅ Successful: `{stats['successful']}`\n"
        f"• ⚠️ Skipped: `{stats['skipped']}`\n"
        f"• ❌ Failed: `{stats['failed']}`\n\n"
        f"*Total Subreddits Collected:* `{stats['total_subreddits']}`\n\n"
        f"_{'🎉 All good!' if stats['failed'] == 0 else '🚨 Some failures occurred, please check logs.'}_"
    )
    send_slack_message(message)


# ---------- Main Pipeline ----------
def process_new_videos():
    """End-to-end ingestion pipeline. Safe for cron execution."""
    logger.info("🚀 Starting video ingestion pipeline")
    start_time = now()

    reddit = get_reddit_instance()
    db = DBManager()

    providers = [
        {"model": config.kw_extraction_model_name, "api_key": config.llm_api_key.groq}
    ]
    llm_caller = LLMFallbackCaller(providers=providers)

    base_dir = Path(config.base_youtube_watcher_directory)
    video_files = load_unprocessed_videos(base_dir, db)

    # --- Tracking stats ---
    total_videos = len(video_files)
    successful, skipped, failed, total_subreddits = 0, 0, 0, 0

    for file_path in video_files:
        video_id = file_path.stem
        try:
            obj = json.loads(file_path.read_text())
            title = obj.get("title", "").strip()
            description = obj.get("description", "") or ""
            logger.info(f"🎥 Processing video {video_id}: {title}")

            # Step 1️⃣ — Extract keywords
            keywords = extract_keywords_from_llm(title, description, llm_caller)
            if not keywords:
                skipped += 1
                logger.warning(f"No keywords generated for video {video_id}. Skipping.")
                continue

            # Step 2️⃣ — Find relevant subreddits
            subs = list(
                reddit.subreddits.search(keywords, limit=config.max_subreddits_to_fetch)
            )
            logger.info(f"Collected {len(subs)} subreddits")
            total_subreddits += len(subs)
            if not subs:
                skipped += 1
                logger.warning(f"No subreddits found for {video_id}. Skipping.")
                continue

            # Step 3️⃣ — Process each subreddit
            for sub in subs:
                collector = SubredditCollector(sub)
                static_data, video_data = collector.collect_for_video_mapping()
                existing_sub = (
                    db.session.query(Subreddit)
                    .filter_by(name=static_data["name"])
                    .first()
                )
                if not existing_sub:
                    db.insert_record(Subreddit(**static_data))
                    sub_id = (
                        db.session.query(Subreddit)
                        .filter_by(name=static_data["name"])
                        .first()
                        .id
                    )
                else:
                    sub_id = existing_sub.id

                # Insert VideoSubredditMap
                mapping_data = video_data
                mapping = VideoSubredditMap(
                    video_id=video_id,
                    subreddit_id=sub_id,
                    subreddit_name=mapping_data["subreddit_name"],
                    keywords_json=keywords,
                )
                db.insert_record(mapping)

            successful += 1
            logger.info(f"✅ Ingested {len(subs)} mappings for video {video_id}")

        except SQLAlchemyError as e:
            db.session.rollback()
            failed += 1
            error_msg = f"Database error while processing {video_id}: {e}"
            logger.exception(error_msg)
            send_slack_message(f"🚨 *Database Error* in pipeline:\n```{error_msg}```")

        except Exception as e:
            failed += 1
            error_msg = f"Unexpected error while processing {video_id}: {e}"
            logger.exception(error_msg)
            send_slack_message(f"🚨 *Unexpected Error*:\n```{error_msg}```")

    db.close()
    duration = (now() - start_time).total_seconds()

    # Prepare and send final summary
    stats = {
        "start_time": start_time,
        "duration": duration,
        "total_videos": total_videos,
        "successful": successful,
        "skipped": skipped,
        "failed": failed,
        "total_subreddits": total_subreddits,
    }
    send_pipeline_summary(stats)

    logger.info(
        f"🎉 Ingestion complete in {duration:.1f}s. "
        f"Processed {total_videos} videos: {successful} ok, {skipped} skipped, {failed} failed."
    )
    return 0


# ---------- CLI Entry ----------
if __name__ == "__main__":
    exit_code = process_new_videos()
    sys.exit(exit_code)
