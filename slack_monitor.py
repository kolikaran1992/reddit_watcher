import os, json, datetime
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from reddit_watcher.omniconf import config, logger

from reddit_watcher.database.manager import DBManager
from reddit_watcher.database.models import SlackThreadComment


app = App(token=config.slack.bot_token)

TARGET_CHANNEL = config.hot_post_full_slack_channel_id


# -----------------------------
# Helper: Resolve user name
# -----------------------------


def slack_ts_to_datetime(slack_ts):
    return datetime.datetime.fromtimestamp(float(slack_ts), tz=datetime.timezone.utc)


def get_user_name(client, user_id):
    if not user_id:
        return None

    try:
        info = client.users_info(user=user_id)
        user = info.get("user", {})

        return (
            user.get("name")
            or user.get("real_name")
            or user.get("profile", {}).get("display_name")
            or user.get("profile", {}).get("real_name")
            or user.get("profile", {}).get("name")
        )
    except Exception:
        return None


# -----------------------------
# Extract hidden metadata from block_id="reddit::<sub|post>"
# -----------------------------
def extract_hidden_meta_from_blocks(blocks):
    if not blocks:
        return None

    for block in blocks:
        block_id = block.get("block_id") or ""
        if block_id.startswith("reddit::"):
            try:
                payload = block_id.replace("reddit::", "")
                subreddit_id, post_id = payload.split("|", 1)
                return {
                    "subreddit_id": subreddit_id,
                    "post_id": post_id,
                }
            except Exception:
                pass

    return None


# -----------------------------
# Convert raw Slack thread → structured list
# -----------------------------
def extract_thread_items(thread, client):
    thread = sorted(thread, key=lambda m: float(m["ts"]))

    items = []
    for msg in thread:
        user_id = msg.get("user")
        user_name = get_user_name(client, user_id)
        text = msg.get("text")
        blocks = msg.get("blocks")

        hidden_meta = extract_hidden_meta_from_blocks(blocks)

        items.append(
            {
                "user_name": user_name,
                "user_id": user_id,
                "text": text,
                "metadata": hidden_meta,
                "ts": msg.get("ts"),
                "thread_ts": msg.get("thread_ts"),
            }
        )
    return items


# -----------------------------
# Slack Event Handler
# -----------------------------
@app.event("message")
def handle_message_events(body, logger, client):
    event = body["event"]

    # ---- Filter ONLY human thread replies ----
    if "bot_id" in event or event.get("subtype") is not None:
        return
    if event.get("thread_ts") is None:
        return
    if event["ts"] == event["thread_ts"]:
        return
    if event["channel"] != TARGET_CHANNEL:
        return
    # -----------------------------------------

    channel = event["channel"]
    thread_ts = event["thread_ts"]

    # Fetch entire thread for context
    thread_res = client.conversations_replies(channel=channel, ts=thread_ts)
    thread = thread_res["messages"]
    thread_items = extract_thread_items(thread, client)

    # Root of the thread (metadata lives here)
    root_item = thread_items[0]

    # Build triggering item from event itself (ground truth)
    triggering_item = {
        "user_id": event["user"],
        "user_name": get_user_name(client, event["user"]),
        "text": event.get("text"),
        "metadata": None,
        "ts": event["ts"],
        "thread_ts": event["thread_ts"],
        "event_id": event.get("client_msg_id") or event.get("event_ts") or event["ts"],
    }

    # Pass event + items to custom logic
    run_custom_logic(
        triggering_item=triggering_item,
        root_item=root_item,
    )


# -----------------------------
# Your Custom Logic
# -----------------------------
def run_custom_logic(triggering_item, root_item):
    """
    triggering_item → the message that triggered this event (canonical)
    root_item → contains hidden metadata (reddit::<sub|post>)
    """

    if triggering_item["user_id"] == config.slack.bot_user_id:
        logger.info("Skipping bot comment")
        return

    meta = root_item.get("metadata") or {}

    subreddit_id = meta.get("subreddit_id")
    post_id = meta.get("post_id")

    if subreddit_id is None or post_id is None:
        logger.info("No metadata on root message; cannot log comment.")
        return

    try:
        subreddit_id = int(subreddit_id)
    except:
        logger.exception(f"Invalid subreddit_id: {subreddit_id}")
        return

    comment_text = triggering_item["text"]

    # NEW: event_id + slack ts stored here
    slack_ts_dt = slack_ts_to_datetime(triggering_item["ts"])
    event_id = triggering_item.get("event_id")  # must be added below

    db = DBManager()
    insert_dict = {
        "subreddit_id": subreddit_id,
        "post_id": post_id,
        "comment_text": comment_text,
        "user_id": triggering_item["user_id"],
        "user_name": triggering_item["user_name"],
        "event_id": event_id,
        "slack_ts": slack_ts_dt,
    }

    record = SlackThreadComment(**insert_dict)

    db.insert_record(
        record, unique_keys=["subreddit_id", "post_id", "comment_text", "user_id"]
    )

    logger.info(
        f"Processed slack comment for post_id={post_id}, subreddit_id={subreddit_id}, triggering_user={triggering_item['user_name']}"
    )


# -----------------------------
# Start Socket Mode
# -----------------------------
if __name__ == "__main__":
    handler = SocketModeHandler(app, config.slack.socket_mode_token)
    handler.start()
