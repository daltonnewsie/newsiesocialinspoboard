"""Instagram Graph API client (official API, free).

Uses the Business Discovery endpoint to read public Business/Creator accounts,
and hashtag search for the Discover tab.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

GRAPH = "https://graph.facebook.com/v25.0"

# Preferred media fields, then fallbacks in case the API rejects one of them.
MEDIA_FIELD_SETS = [
    "id,caption,media_type,media_product_type,like_count,comments_count,view_count,"
    "permalink,timestamp,thumbnail_url,media_url",
    "id,caption,media_type,like_count,comments_count,view_count,permalink,timestamp,"
    "thumbnail_url,media_url",
    "id,caption,media_type,like_count,comments_count,permalink,timestamp,media_url",
]

PROFILE_FIELDS = "username,name,followers_count,media_count,profile_picture_url"


class GraphError(Exception):
    def __init__(self, err: dict):
        self.code = err.get("code")
        self.subcode = err.get("error_subcode")
        self.message = err.get("error_user_msg") or err.get("message") or str(err)
        super().__init__(f"[{self.code}/{self.subcode}] {self.message}")

    @property
    def is_rate_limit(self) -> bool:
        return self.code in (4, 17, 32, 613)

    @property
    def is_auth(self) -> bool:
        return self.code == 190


class Instagram:
    def __init__(self, ig_user_id: str, token: str):
        self.ig_user_id = ig_user_id
        self.token = token
        self._field_set = 0
        self.calls = 0

    # ------------------------------------------------------------------ core
    def _get(self, path: str, params: dict, retries: int = 2) -> dict:
        params = {**params, "access_token": self.token}
        for attempt in range(retries + 1):
            self.calls += 1
            resp = requests.get(f"{GRAPH}/{path}", params=params, timeout=45)
            data = resp.json()
            if "error" not in data:
                return data
            err = GraphError(data["error"])
            if err.is_rate_limit and attempt < retries:
                time.sleep(60 * (attempt + 1))
                continue
            raise err
        raise RuntimeError("unreachable")

    # ------------------------------------------------------- creator lookup
    def fetch_creator(self, handle: str, max_posts: int = 50, page_size: int = 25):
        """Return (profile_dict, [post_dict, ...]) for a public business/creator account."""
        posts: list[dict] = []
        profile: dict | None = None
        after: str | None = None

        while len(posts) < max_posts:
            limit = min(page_size, max_posts - len(posts))
            media_edge = f"media.limit({limit})" + (f".after({after})" if after else "")
            try:
                bd = self._discovery(handle, media_edge)
            except GraphError as e:
                # A rejected field -> fall back to a smaller field set and retry.
                if e.code == 100 and self._field_set < len(MEDIA_FIELD_SETS) - 1 and "field" in e.message.lower():
                    self._field_set += 1
                    continue
                raise

            if profile is None:
                profile = {k: bd.get(k) for k in PROFILE_FIELDS.split(",")}

            media = bd.get("media", {})
            batch = media.get("data", [])
            posts.extend(batch)
            after = media.get("paging", {}).get("cursors", {}).get("after")
            if not batch or not after:
                break

        return profile, posts

    def _discovery(self, handle: str, media_edge: str) -> dict:
        fields = (
            f"business_discovery.username({handle})"
            f"{{{PROFILE_FIELDS},{media_edge}{{{MEDIA_FIELD_SETS[self._field_set]}}}}}"
        )
        data = self._get(self.ig_user_id, {"fields": fields})
        return data["business_discovery"]

    # ------------------------------------------------------ hashtag discover
    def hashtag_id(self, tag: str) -> str | None:
        data = self._get("ig_hashtag_search", {"user_id": self.ig_user_id, "q": tag})
        items = data.get("data", [])
        return items[0]["id"] if items else None

    def hashtag_top_media(self, hashtag_id: str, limit: int = 25) -> list[dict]:
        data = self._get(
            f"{hashtag_id}/top_media",
            {
                "user_id": self.ig_user_id,
                "fields": "id,caption,media_type,comments_count,like_count,permalink,timestamp",
                "limit": limit,
            },
        )
        return data.get("data", [])

    # ---------------------------------------------------------- token health
    def token_status(self) -> dict:
        """Returns {'valid': bool, 'expires_at': iso|None, 'days_left': int|None}."""
        try:
            data = self._get("debug_token", {"input_token": self.token}).get("data", {})
        except GraphError as e:
            return {"valid": False, "expires_at": None, "days_left": None, "error": e.message}
        exp = data.get("expires_at") or 0
        if not exp:  # 0 means the token doesn't expire (e.g. a Page token)
            return {"valid": bool(data.get("is_valid", True)), "expires_at": None, "days_left": None}
        expires = datetime.fromtimestamp(exp, tz=timezone.utc)
        days = (expires - datetime.now(timezone.utc)).days
        return {"valid": bool(data.get("is_valid", True)), "expires_at": expires.isoformat(), "days_left": days}
