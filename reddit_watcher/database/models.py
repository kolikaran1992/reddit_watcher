from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
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

    post_generation_rules = relationship(
        "SubredditPostGenerationRules",
        back_populates="subreddit",
    )


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


class SubredditPostGenerationRules(Base):
    """
    Data model for storing generation rules extracted from analysing
    hot posts of a subreddit
    """

    __tablename__ = "subreddit_post_generation_rules"

    id = Column(Integer, primary_key=True)
    subreddit_id = Column(Integer, ForeignKey("subreddits.id"))
    post_generation_rules = Column(Text)
    updated_at = Column(DateTime, default=now)

    subreddit = relationship("Subreddit", back_populates="post_generation_rules")


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


class VideoSubredditAssessment(Base):
    """
    Stores detailed marketing assessment results for a specific video-subreddit pair.
    Extracted from the XML structure produced by the Reddit marketing assessment pipeline.
    """

    __tablename__ = "video_subreddit_assessments"

    id = Column(Integer, primary_key=True)

    # Core relationships
    video_id = Column(String, nullable=False, index=True)
    subreddit_id = Column(Integer, ForeignKey("subreddits.id"), nullable=False)

    # Extracted tags from the <reddit_marketing_assessment> XML
    is_marketable = Column(String, nullable=True)  # e.g. "yes" / "no"
    relevance_level = Column(String, nullable=True)  # e.g. "high" / "moderate" / "none"
    complexity_level = Column(
        String, nullable=True
    )  # e.g. "simple" / "moderate" / "difficult"

    posting_requirements = Column(Text, nullable=True)
    recommended_post_format = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    risk_of_ban = Column(String, nullable=True)  # e.g. "low" / "medium" / "high"
    additional_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=now)

    # Relationships
    subreddit = relationship("Subreddit")

    __table_args__ = (
        UniqueConstraint("video_id", "subreddit_id", name="uq_video_sub_assessment"),
    )


class VideoSubredditGeneratedPost(Base):
    """
    Stores finalized Reddit post generation output for a specific video–subreddit pair.
    Created by the post-generation LLM (step_1_postgen).

    This table represents the *final synthesized output* ready for submission,
    including title, post body, and comment body in a structured form.
    """

    __tablename__ = "video_subreddit_generated_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False, index=True)
    subreddit_id = Column(Integer, ForeignKey("subreddits.id"), nullable=False)

    post_title = Column(String, nullable=False)
    post_content = Column(Text, nullable=False)
    comment_content = Column(Text, nullable=True)
    requires_mod_approval = Column(String, nullable=False)

    upload_video_directly = Column(String(10), nullable=False, default="no")
    upload_photo_directly = Column(String(10), nullable=False, default="no")

    subreddit = relationship("Subreddit")

    __table_args__ = (
        UniqueConstraint(
            "video_id", "subreddit_id", name="uq_video_sub_generated_post"
        ),
    )

    def __repr__(self):
        return f"<VideoSubredditGeneratedPost(video_id={self.video_id}, subreddit_id={self.subreddit_id})>"


class ProcessedVideoRegistry(Base):
    """
    Registry table for all processed videos.
    Used for duplicate-checking in video ingestion pipeline.
    """

    __tablename__ = "processed_video_registry"

    video_id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=now)


class SubredditPost(Base):
    """
    Stores post metadata
    """

    __tablename__ = "subreddit_post"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subreddit_id = Column(
        Integer,
        ForeignKey(Subreddit.id),
        nullable=False,
        index=True,
    )
    post_id = Column(String(10), unique=True, nullable=False, index=True)
    post_url = Column(String(512), nullable=False)
    post_title = Column(String(512), nullable=False)
    # Use Text for description in case it's long
    post_description = Column(Text)

    # Optional relationship for easy joining
    subreddit = relationship("Subreddit")

    def __repr__(self):
        return f"<SubredditPost(id={self.id}, post_id='{self.post_id}', subreddit_id={self.subreddit_id})>"


######################
# Mom Slack App Models
######################
class PostMeta(Base):
    """
    Minimal Reddit post metadata.
    - Sub list is in config, not here.
    """

    __tablename__ = "mom_post_meta"

    id = Column(Integer, primary_key=True)
    subreddit = Column(String(255), nullable=False)
    reddit_post_id = Column(String(32), nullable=False)  # e.g. 'abc123'
    reddit_url = Column(String(500), nullable=False)

    first_seen_at = Column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint("subreddit", "reddit_post_id", name="uq_sub_post"),
    )

    comments = relationship("SlackComment", back_populates="mom_post_meta")


class SlackComment(Base):
    """
    One row per mom-comment on Slack.
    Multiple comments per post allowed.
    """

    __tablename__ = "mom_slack_comments"

    id = Column(Integer, primary_key=True)

    # Composite FK to PostMeta
    subreddit = Column(String(255), nullable=False)
    reddit_post_id = Column(String(32), nullable=False)

    comment_text = Column(Text, nullable=False)

    slack_ts = Column(String(64), nullable=False)  # Slack message ts
    slack_channel = Column(String(255), nullable=False)
    slack_user = Column(String(255), nullable=True)  # for sanity check it's mom

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["subreddit", "reddit_post_id"],
            ["post_meta.subreddit", "post_meta.reddit_post_id"],
            name="fk_comment_post",
        ),
    )

    post = relationship("PostMeta", back_populates="mom_slack_comments")
