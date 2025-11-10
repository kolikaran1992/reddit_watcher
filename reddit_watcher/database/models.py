from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from reddit_watcher.database.config import Base
from reddit_watcher.omniconf import config
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)


class Subreddit(Base):
    """
    Core static metadata for a subreddit.
    Populated by SubredditCollector.collect_static().
    """

    __tablename__ = "subreddits"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    title = Column(String)
    created_utc = Column(DateTime)
    is_nsfw = Column(Boolean)
    subreddit_type = Column(String)
    lang = Column(String)

    meta = relationship("SubredditMeta", back_populates="subreddit")
    top_new_snapshots = relationship(
        "SubredditTopNewPostsSnapshot", back_populates="subreddit"
    )
    video_mappings = relationship("VideoSubredditMap", back_populates="subreddit")


class SubredditMeta(Base):
    """
    Descriptive metadata that changes infrequently.
    Populated by SubredditCollector.collect_meta().
    """

    __tablename__ = "subreddit_meta"

    id = Column(Integer, primary_key=True)
    subreddit_id = Column(Integer, ForeignKey("subreddits.id"))
    description = Column(Text)
    rules_json = Column(JSON)
    flairs_json = Column(JSON)
    allow_videos = Column(Boolean)
    allow_images = Column(Boolean)
    allow_links = Column(Boolean)
    updated_at = Column(DateTime, default=now)

    subreddit = relationship("Subreddit", back_populates="meta")


class SubredditTopNewPostsSnapshot(Base):
    """
    Snapshot of subreddit activity from the top 100 newest posts.
    Created by SubredditCollector.collect_new_posts_snapshot().
    """

    __tablename__ = "subreddit_top_new_posts_snapshots"

    id = Column(Integer, primary_key=True)
    subreddit_id = Column(Integer, ForeignKey("subreddits.id"), nullable=False)

    # Snapshot timestamp
    timestamp = Column(DateTime, default=now, nullable=False)

    # Parameters & metrics
    subscribers = Column(Integer)
    num_posts_in_window = Column(Integer)
    num_comments_in_window = Column(Integer)
    average_upvotes_in_window = Column(Float)
    top_post_score_in_window = Column(Integer)

    subreddit = relationship("Subreddit", back_populates="top_new_snapshots")


class VideoSubredditMap(Base):
    """
    Mapping between YouTube videos and recommended subreddits
    extracted by the LLM pipeline.
    """

    __tablename__ = "video_subreddit_map"

    id = Column(Integer, primary_key=True)
    video_id = Column(String, nullable=False, index=True)
    subreddit_id = Column(Integer, ForeignKey("subreddits.id"), nullable=False)
    subreddit_name = Column(String, nullable=False)
    keywords_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=now)

    subreddit = relationship("Subreddit", back_populates="video_mappings")

    __table_args__ = (
        UniqueConstraint("video_id", "subreddit_id", name="uq_video_sub_map"),
    )
