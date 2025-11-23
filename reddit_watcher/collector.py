from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from reddit_watcher.omniconf import config
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import asyncio


import json
import re

YOUTUBE_REGEX = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=[A-Za-z0-9_-]+|youtu\.be/[A-Za-z0-9_-]+))"
)
URL_REGEX = re.compile(r"(https?://[^\s)]+)")


def extract_media_urls(post):
    """
    Safest and most complete media extractor for Reddit posts.
    Returns *all* media URLs:
      - Galleries
      - Reddit-hosted videos
      - Reddit images
      - External videos (YT, Vimeo, Streamable, Instagram, etc.)
      - Links inside selftext
      - Link posts
    """

    final_urls = set()

    # ------------------------------------------------------------
    # 0. Helper: normalize HTML-escaped URLs (&amp;)
    # ------------------------------------------------------------
    def clean(url):
        return url.replace("&amp;", "&")

    # ------------------------------------------------------------
    # 1. Galleries (multiple images)
    # ------------------------------------------------------------
    if getattr(post, "is_gallery", False) and post.media_metadata:
        for item in post.media_metadata.values():
            if item.get("status") != "valid":
                continue
            if "s" in item and "u" in item["s"]:
                final_urls.add(clean(item["s"]["u"]))

    # ------------------------------------------------------------
    # 2. Reddit-hosted videos (v.redd.it)
    # ------------------------------------------------------------
    if getattr(post, "media", None):
        rv = post.media.get("reddit_video") if post.media else None
        if rv:
            if rv.get("fallback_url"):
                final_urls.add(clean(rv["fallback_url"]))

            # Optional audio track (if needed)
            if rv.get("dash_url"):
                final_urls.add(clean(rv["dash_url"]))

    # ------------------------------------------------------------
    # 3. Preview images (non-gallery posts)
    # ------------------------------------------------------------
    # if getattr(post, "preview", None):
    #     for img in post.preview.get("images", []):
    #         source = img.get("source", {})
    #         if "url" in source:
    #             final_urls.add(clean(source["url"]))

    # ------------------------------------------------------------
    # 4. Link post: external video/img/etc.
    # ------------------------------------------------------------
    if post.url:
        ext = post.url.lower()
        # Raw direct media
        if any(
            ext.endswith(x)
            for x in [".mp4", ".mov", ".webm", ".gif", ".png", ".jpg", ".jpeg"]
        ):
            final_urls.add(clean(post.url))
        else:
            # Could be YouTube, Vimeo, Streamable, etc.
            final_urls.add(clean(post.url))

    # ------------------------------------------------------------
    # 5. Extract links inside selftext (YouTube etc.)
    # ------------------------------------------------------------
    if post.selftext:
        for url in URL_REGEX.findall(post.selftext):
            final_urls.add(clean(url))

    # ------------------------------------------------------------
    # 6. Crossposts (often contain original media)
    # ------------------------------------------------------------
    if getattr(post, "crosspost_parent_list", None):
        for parent in post.crosspost_parent_list:
            # parent media metadata is structured like a post
            if "media_metadata" in parent:
                for item in parent["media_metadata"].values():
                    if item.get("status") == "valid":
                        if "s" in item and "u" in item["s"]:
                            final_urls.add(clean(item["s"]["u"]))

            # parent preview
            # if "preview" in parent:
            #     for img in parent["preview"].get("images", []):
            #         src = img.get("source", {})
            #         if "url" in src:
            #             final_urls.add(clean(src["url"]))

            # parent reddit video
            if "media" in parent and parent["media"]:
                pv = parent["media"].get("reddit_video")
                if pv and pv.get("fallback_url"):
                    final_urls.add(clean(pv["fallback_url"]))

            # parent link
            if parent.get("url"):
                final_urls.add(clean(parent["url"]))

    # ------------------------------------------------------------
    # Return sorted list for determinism
    # ------------------------------------------------------------
    return sorted(list(final_urls))


def get_op_first_comment(post):
    """Return the first top-level comment made by the post author."""
    try:
        # Load  **only top-level** comments, avoid deep trees
        post.comments.replace_more(limit=0)

        author_name = str(post.author) if post.author else None
        if not author_name:
            return None

        for c in post.comments:
            if str(c.author) == author_name:
                return c.body or ""
        return None
    except Exception:
        return None


class SubredditCollector:
    """Efficient modular collector for a given PRAW Subreddit object."""

    def __init__(self, subreddit):
        """
        Parameters
        ----------
        subreddit : praw.models.Subreddit
            A PRAW subreddit object (already fetched).
        """
        self.sub = subreddit
        self._cache = {}  # internal lightweight cache for re-used attributes

    # ---------- UTILITIES ----------

    def _get_cached(self, key: str, fetch_func) -> Any:
        """Get attribute with temporary caching."""
        if key not in self._cache:
            try:
                self._cache[key] = fetch_func()
            except Exception as e:
                self._cache[key] = {"error": str(e)}
        return self._cache[key]

    # ---------- MODEL 1: Subreddit (Static Metadata) ----------

    def collect_static(self) -> Dict[str, Any]:
        """Fetch static subreddit metadata — rarely changes."""
        return {
            "name": f"r/{self.sub.display_name}",
            "title": self.sub.title,
            "created_utc": datetime.utcfromtimestamp(self.sub.created_utc),
            "is_nsfw": self.sub.over18,
            "subreddit_type": self.sub.subreddit_type,
            "lang": getattr(self.sub, "lang", None),
        }

    # ---------- MODEL 2: SubredditWeeklyMeta ----------

    def collect_meta(self) -> Dict[str, Any]:
        """Fetch subreddit weekly metadata — description, rules, flairs."""
        description = self._get_cached(
            "description", lambda: self.sub.public_description or self.sub.description
        )
        rules = self._get_cached("rules", self._fetch_rules)
        flairs = self._get_cached("flairs", self._fetch_flairs)

        return {
            "description": description,
            "rules_json": rules,
            "flairs_json": flairs,
            "allow_videos": self.sub.allow_videos,
            "allow_images": self.sub.allow_images,
            "allow_links": self.sub.allow_discovery,
        }

    def _fetch_rules(self):
        rules = []
        try:
            for rule in self.sub.rules:
                rules.append(
                    {
                        "short_name": rule.short_name,
                        "description": rule.description,
                        "kind": rule.kind,
                    }
                )
        except Exception as e:
            rules = [{"error": str(e)}]
        return rules

    def _fetch_flairs(self):
        flairs = []
        try:
            for flair in self.sub.flair.link_templates:
                flairs.append(
                    {
                        "flair_text": flair.get("text"),
                        "flair_css_class": flair.get("css_class"),
                    }
                )
        except Exception as e:
            flairs = [{"error": str(e)}]
        return flairs

    # ---------- MODEL 3: SubredditDailyMetrics ----------

    def collect_new_posts_snapshot(
        self, limit: int = 100, window_minutes: int = 5
    ) -> Dict[str, Any]:
        """
        Fetch subreddit activity snapshot for the last N minutes.

        Parameters
        ----------
        limit : int
            Maximum number of recent posts to fetch (default=100).
        window_minutes : int
            Time window (in minutes) to include posts for metric computation.

        Returns
        -------
        Dict[str, Any]
            Snapshot metrics including posts, comments, upvotes, etc.
        """
        # Fetch latest submissions (1–2 API calls depending on limit)
        posts = list(self.sub.new(limit=limit))

        # Use timezone-aware current UTC time
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(minutes=window_minutes)

        # Filter posts newer than cutoff
        recent_posts = [
            p
            for p in posts
            if datetime.fromtimestamp(p.created_utc, tz=timezone.utc) > cutoff
        ]

        # Compute dependent metrics
        comments_count = sum(getattr(p, "num_comments", 0) for p in recent_posts)
        scores = [getattr(p, "score", 0) for p in recent_posts]

        avg_upvotes = sum(scores) / len(scores) if scores else 0
        top_post_score = max(scores) if scores else 0

        return {
            "subscribers": getattr(self.sub, "subscribers", None),
            "num_posts_in_window": len(recent_posts),
            "num_comments_in_window": comments_count,
            "average_upvotes_in_window": avg_upvotes,
            "top_post_score_in_window": top_post_score,
        }

    def collect_for_video_mapping(self) -> Dict[str, Any]:
        """
        Return subreddit data needed for video ingestion:
        static model fields only (lightweight, cached).
        """
        static_data = self.collect_static()
        return static_data, {
            "subreddit_name": static_data["name"],
        }

    # ---------- MAINTENANCE ----------

    def clear_cache(self):
        """Clear cached values (to force fresh API pulls next time)."""
        self._cache.clear()


class AsyncSubredditCollector:
    """
    Efficient modular collector for an asyncpraw Subreddit object.
    """

    def __init__(self, subreddit):
        """
        Parameters
        ----------
        subreddit : asyncpraw.models.Subreddit
            An asyncpraw subreddit object (already fetched).
        """
        self.sub = subreddit
        self._cache = {}

    # ---------- UTILITIES ----------

    async def _get_cached(self, key: str, fetch_func) -> Any:
        """Get attribute with temporary caching. Works for sync + async funcs."""
        if key in self._cache:
            return self._cache[key]

        try:
            result = fetch_func()  # may return coroutine or value
            if asyncio.iscoroutine(result):
                result = await result
            self._cache[key] = result
        except Exception as e:
            self._cache[key] = {"error": str(e)}

        return self._cache[key]

    # ---------- MODEL 1: Subreddit (Static Metadata) ----------

    async def collect_static(self) -> Dict[str, Any]:
        """Fetch static subreddit metadata — rarely changes."""
        return {
            "name": f"r/{self.sub.display_name}",
            "title": self.sub.title,
            "created_utc": datetime.utcfromtimestamp(self.sub.created_utc),
            "is_nsfw": self.sub.over18,
            "subreddit_type": self.sub.subreddit_type,
            "lang": getattr(self.sub, "lang", None),
        }

    # ---------- MODEL 2: SubredditWeeklyMeta ----------

    async def collect_meta(self) -> Dict[str, Any]:
        """Fetch subreddit weekly metadata — description, rules, flairs."""
        description = await self._get_cached(
            "description",
            lambda: self.sub.public_description or self.sub.description,
        )

        rules = await self._get_cached("rules", self._fetch_rules)
        flairs = await self._get_cached("flairs", self._fetch_flairs)

        return {
            "description": description,
            "rules_json": rules,
            "flairs_json": flairs,
            "allow_videos": self.sub.allow_videos,
            "allow_images": self.sub.allow_images,
            "allow_links": self.sub.allow_discovery,
        }

    async def _fetch_rules(self) -> List[Dict[str, Any]]:
        """Fetch subreddit rules asynchronously (fixed, non-awaitable)."""
        try:
            rules_obj = (
                await self.sub.rules() if callable(self.sub.rules) else self.sub.rules
            )
            # asyncpraw SubredditRules supports iteration
            rules = []
            async for rule in rules_obj:
                rules.append(
                    {
                        "short_name": getattr(rule, "short_name", None),
                        "description": getattr(rule, "description", None),
                        "kind": getattr(rule, "kind", None),
                    }
                )
            return rules
        except TypeError:
            # Fallback if rules() is a direct iterable
            try:
                return [
                    {
                        "short_name": getattr(rule, "short_name", None),
                        "description": getattr(rule, "description", None),
                        "kind": getattr(rule, "kind", None),
                    }
                    async for rule in self.sub.rules
                ]
            except Exception as e:
                return [{"error": str(e)}]
        except Exception as e:
            return [{"error": str(e)}]

    async def _fetch_flairs(self) -> List[Dict[str, Any]]:
        """Fetch subreddit flairs asynchronously — final corrected version."""
        try:
            flairs = []

            # asyncpraw exposes link_templates as async iterable, not callable
            async for flair in self.sub.flair.link_templates:
                flairs.append(
                    {
                        "flair_text": flair.get("text"),
                        "flair_css_class": flair.get("css_class"),
                        "flair_background_color": flair.get("background_color"),
                        "flair_text_color": flair.get("text_color"),
                    }
                )

            return flairs

        except TypeError:
            # fallback for older or experimental asyncpraw versions
            try:
                flair_iterable = getattr(self.sub.flair, "link_templates", None)
                if flair_iterable is None:
                    return []
                # if it's a coroutine (rare), await it
                if callable(flair_iterable):
                    flair_list = await flair_iterable()
                    return [
                        {
                            "flair_text": f.get("text"),
                            "flair_css_class": f.get("css_class"),
                        }
                        for f in flair_list or []
                    ]
                # otherwise, it's iterable
                else:
                    return [
                        {
                            "flair_text": f.get("text"),
                            "flair_css_class": f.get("css_class"),
                        }
                        async for f in flair_iterable
                    ]
            except Exception as e:
                return [{"error": str(e)}]

        except Exception as e:
            return [{"error": str(e)}]

    # ---------- MODEL 3: SubredditDailyMetrics ----------

    async def collect_new_posts_snapshot(
        self, limit: int = 100, window_minutes: int = 5
    ) -> Dict[str, Any]:
        """Fetch subreddit activity snapshot for the last N minutes."""
        posts = []
        async for post in self.sub.new(limit=limit):
            posts.append(post)

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(minutes=window_minutes)

        recent_posts = [
            p
            for p in posts
            if datetime.fromtimestamp(p.created_utc, tz=timezone.utc) > cutoff
        ]

        comments_count = sum(getattr(p, "num_comments", 0) for p in recent_posts)
        scores = [getattr(p, "score", 0) for p in recent_posts]
        avg_upvotes = sum(scores) / len(scores) if scores else 0
        top_post_score = max(scores) if scores else 0

        return {
            "subscribers": getattr(self.sub, "subscribers", None),
            "num_posts_in_window": len(recent_posts),
            "num_comments_in_window": comments_count,
            "average_upvotes_in_window": avg_upvotes,
            "top_post_score_in_window": top_post_score,
        }

    async def collect_hot_posts_metadata(self, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Fetch the hottest posts metadata for the subreddit, including extended
        fields useful for Slack rendering and downstream mapping.

        Parameters
        ----------
        limit : int
            Maximum number of hot posts to fetch (default=25).

        Returns
        -------
        List[Dict[str, Any]]
            A list of post metadata dictionaries ready for DB insertion and Slack delivery.
        """
        hot_posts_data = []

        async for post in self.sub.hot(limit=limit):
            # Skip deleted/removed posts
            if not getattr(post, "author", None):
                continue

            # Extract media URLs
            # media_urls = []
            # try:
            #     if hasattr(post, "preview") and post.preview:
            #         images = post.preview.get("images", [])
            #         for img in images:
            #             source = img.get("source")
            #             if source and source.get("url"):
            #                 media_urls.append(source["url"].replace("&amp;", "&"))
            # except Exception:
            #     pass

            # try:
            #     if hasattr(post, "media") and post.media:
            #         reddit_video = post.media.get("reddit_video")
            #         if reddit_video and reddit_video.get("fallback_url"):
            #             media_urls.append(reddit_video["fallback_url"])
            # except Exception:
            #     pass

            media_urls = extract_media_urls(post)

            hot_posts_data.append(
                {
                    "post_id": post.id,
                    "post_url": post.url,
                    "post_title": post.title,
                    "post_description": post.selftext or "",
                    "post_media_urls": media_urls,
                    "post_created_utc": post.created_utc,
                    "post_score": getattr(post, "score", None),
                    "post_num_comments": getattr(post, "num_comments", None),
                    # "post_is_self": getattr(post, "is_self", None),
                    "post_author": str(post.author) if post.author else None,
                    # NEW FIELDS
                    "post_subreddit_name": str(post.subreddit.display_name),
                    "post_subreddit_permalink": f"https://www.reddit.com/r/{post.subreddit.display_name}/comments/{post.id}/",
                    "post_op_first_comment": get_op_first_comment(post),
                }
            )

        return hot_posts_data

    async def fetch_post_top_comments(
        self, post, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch the top N comments for a specific post.

        Parameters
        ----------
        post : asyncpraw.models.Submission
            The asyncpraw Submission object for the post.
        limit : int
            The maximum number of top comments to fetch (default=50).

        Returns
        -------
        List[Dict[str, Any]]
            A list of comment metadata dictionaries.
        """
        comments_data = []
        try:
            # Explicitly set the comment sort to 'top' for certainty.
            post.comment_sort = "top"
            # Asynchronously load top-level comments and skip loading 'more' links for efficiency.
            await post.comments.replace_more(limit=0)

            # Iterate through the resulting comments, which are now top-level comments (sorted by 'top')
            for comment in post.comments.list():
                if len(comments_data) >= limit:
                    break

                # Skip deleted/removed comments
                if not getattr(comment, "author", None):
                    continue

                comments_data.append(
                    {
                        "comment_id": comment.id,
                        "author": (
                            str(comment.author) if comment.author else "[deleted]"
                        ),
                        "body": comment.body,
                        "score": getattr(comment, "score", 0),
                        "created_utc": comment.created_utc,
                        "permalink": comment.permalink,
                        # Enhanced fields for analysis
                        "is_op": comment.is_submitter,
                        "parent_id": getattr(comment, "parent_id", None),
                        "distinguished": getattr(comment, "distinguished", None),
                        "is_locked": getattr(comment, "locked", False),
                    }
                )

            return comments_data

        except Exception as e:
            return [{"error": f"Failed to fetch comments: {e}"}]

    async def collect_for_video_mapping(self) -> Dict[str, Any]:
        """Return subreddit data needed for video ingestion."""
        static_data = await self.collect_static()
        return static_data, {"subreddit_name": static_data["name"]}

    def clear_cache(self):
        """Clear cached values (to force fresh API pulls next time)."""
        self._cache.clear()
