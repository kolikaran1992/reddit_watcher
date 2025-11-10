import praw
import asyncpraw
from reddit_watcher.omniconf import config

# Configuration is expected to come from the 'config' object for PRAW credentials


def get_reddit_instance():
    """Initializes and returns a PRAW Reddit instance using project configuration."""
    # Assuming PRAW config keys are available in a standard location, e.g., config.reddit
    reddit_config = config.reddit_auth
    reddit = praw.Reddit(
        client_id=reddit_config.client_id,
        client_secret=reddit_config.client_secret,
        user_agent=f"script:{reddit_config.user_agent}: v0.1 by (u/{reddit_config.user_name})",
        username=reddit_config.user_name,
        password=reddit_config.user_password,
    )
    return reddit


async def get_reddit_instance_async():
    """
    Initializes and returns an asyncpraw Reddit instance using project configuration.
    """
    reddit_config = config.reddit_auth
    reddit = asyncpraw.Reddit(
        client_id=reddit_config.client_id,
        client_secret=reddit_config.client_secret,
        user_agent=f"script:{reddit_config.user_agent}:v0.1 by (u/{reddit_config.user_name})",
        username=reddit_config.user_name,
        password=reddit_config.user_password,
    )
    return reddit


def sanitize_subreddit_name(name: str) -> str:
    """
    Sanitize subreddit names for use with PRAW/asyncpraw.

    Handles:
    - Removes 'r/' or '/r/' prefixes
    - Trims whitespace
    - Ensures lowercase normalization (optional)
    - Removes trailing slashes or accidental prefixes

    Examples
    --------
    >>> sanitize_subreddit_name("r/shittyfoodporn")
    'shittyfoodporn'

    >>> sanitize_subreddit_name("/r/FoodPorn/")
    'foodporn'
    """
    if not name:
        return ""

    # Trim spaces
    name = name.strip()

    # Remove leading "/r/" or "r/" prefixes
    if name.lower().startswith("/r/"):
        name = name[3:]
    elif name.lower().startswith("r/"):
        name = name[2:]

    # Remove any trailing slash
    name = name.rstrip("/")

    # Normalize case — optional but safe
    name = name.lower()

    return name
