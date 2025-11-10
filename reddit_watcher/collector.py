from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from reddit_watcher.omniconf import config
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


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
        self._cache = {}  # internal lightweight cache for reused data

    # ---------- UTILITIES ----------

    async def _get_cached(self, key: str, fetch_func) -> Any:
        """Get attribute with temporary caching."""
        if key not in self._cache:
            try:
                self._cache[key] = await fetch_func()
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
        """Fetch subreddit rules asynchronously."""
        try:
            rules = []
            async for rule in self.sub.rules():
                rules.append(
                    {
                        "short_name": rule.short_name,
                        "description": rule.description,
                        "kind": rule.kind,
                    }
                )
            return rules
        except Exception as e:
            return [{"error": str(e)}]

    async def _fetch_flairs(self) -> List[Dict[str, Any]]:
        """Fetch subreddit flairs asynchronously."""
        try:
            flairs = []
            async for flair in self.sub.flair.link_templates():
                flairs.append(
                    {
                        "flair_text": flair.get("text"),
                        "flair_css_class": flair.get("css_class"),
                    }
                )
            return flairs
        except Exception as e:
            return [{"error": str(e)}]

    # ---------- MODEL 3: SubredditDailyMetrics ----------

    async def collect_new_posts_snapshot(
        self, limit: int = 100, window_minutes: int = 5
    ) -> Dict[str, Any]:
        """
        Fetch subreddit activity snapshot for the last N minutes.
        """
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

    async def collect_for_video_mapping(self) -> Dict[str, Any]:
        """
        Return subreddit data needed for video ingestion.
        """
        static_data = await self.collect_static()
        return static_data, {"subreddit_name": static_data["name"]}

    # ---------- MAINTENANCE ----------

    def clear_cache(self):
        """Clear cached values (to force fresh API pulls next time)."""
        self._cache.clear()
