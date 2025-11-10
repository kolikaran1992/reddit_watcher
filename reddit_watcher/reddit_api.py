import praw
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
