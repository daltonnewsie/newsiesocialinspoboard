"""Turns raw posts into scored posts.

The key idea: "outperforming" is measured against each creator's OWN baseline,
so a 15k-follower account's 5x breakout ranks above a big account's average post.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from statistics import median


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(ts: str) -> datetime:
    # Graph API format: 2026-09-20T14:03:11+0000
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def post_format(p: dict) -> str:
    if p.get("media_product_type") == "REELS" or p.get("media_type") == "VIDEO":
        return "reel"
    if p.get("media_type") == "CAROUSEL_ALBUM":
        return "carousel"
    return "image"


def has_comment_cta(caption: str) -> bool:
    """Detects 'Comment FLOWS and I'll send it' style CTAs, which inflate comments."""
    if not caption:
        return False
    for m in re.finditer(r"\bcomment\b\s+[\"'“”‘’]?([A-Za-z0-9]+)", caption, re.IGNORECASE):
        word = m.group(1)
        if word.isupper() and len(word) >= 3:
            return True
    return False


def normalize(raw: dict, handle: str) -> dict:
    """Map a Graph API media object to our stored post shape."""
    caption = raw.get("caption") or ""
    return {
        "id": raw["id"],
        "handle": handle,
        "format": post_format(raw),
        "caption": caption,
        "permalink": raw.get("permalink"),
        "timestamp": raw.get("timestamp"),
        "thumb": raw.get("thumbnail_url") or raw.get("media_url"),
        "views": raw.get("view_count"),
        "likes": raw.get("like_count"),  # None when the creator hides likes
        "comments": raw.get("comments_count"),
        "comment_cta": has_comment_cta(caption),
    }


def _metric(p: dict) -> tuple[str, float | None]:
    """Which number judges this post: views for Reels, interactions otherwise."""
    if p["format"] == "reel" and p.get("views") is not None:
        return "views", float(p["views"])
    if p.get("likes") is not None:
        return "interactions", float(p["likes"] + 2 * (p.get("comments") or 0))
    if p.get("comments") is not None:
        return "comments", float(p["comments"])
    return "none", None


def score_posts(posts: dict[str, dict], creators: dict[str, dict], cfg: dict) -> None:
    """Adds outlier / engagement fields to every post in place."""
    mature_after = timedelta(hours=cfg.get("mature_after_hours", 48))
    window = cfg.get("baseline_window", 30)
    min_n = cfg.get("min_baseline_posts", 5)
    now = now_utc()

    by_creator: dict[str, list[dict]] = {}
    for p in posts.values():
        by_creator.setdefault(p["handle"], []).append(p)

    for handle, plist in by_creator.items():
        followers = (creators.get(handle) or {}).get("followers") or 0
        plist.sort(key=lambda p: p["timestamp"], reverse=True)

        for p in plist:
            age = now - parse_ts(p["timestamp"])
            p["age_hours"] = round(age.total_seconds() / 3600, 1)
            p["mature"] = age >= mature_after
            p["metric"], p["metric_value"] = _metric(p)
            interactions = (p.get("likes") or 0) + (p.get("comments") or 0)
            p["engagement_rate"] = round(interactions / followers, 5) if followers else None
            p["view_engagement"] = (
                round(interactions / p["views"], 4) if p.get("views") else None
            )

        # Baselines per (bucket, metric) — Reels and static posts behave differently.
        for p in plist:
            bucket = "reel" if p["format"] == "reel" else "static"
            peers = [
                q["metric_value"]
                for q in plist
                if q["mature"]
                and q["metric"] == p["metric"]
                and ("reel" if q["format"] == "reel" else "static") == bucket
                and q["metric_value"] is not None
            ][:window]
            if p["metric_value"] is None or len(peers) < min_n:
                p["baseline"] = None
                p["outlier"] = None
                continue
            base = median(peers)
            p["baseline"] = base
            p["outlier"] = round(p["metric_value"] / base, 2) if base > 0 else None


def creator_stats(posts: dict[str, dict], creators: dict[str, dict], cfg: dict) -> list[dict]:
    hit = cfg.get("hit_threshold", 2.0)
    now = now_utc()
    cutoff = now - timedelta(days=30)
    out = []
    for handle, c in creators.items():
        mine = [p for p in posts.values() if p["handle"] == handle]
        recent = [p for p in mine if parse_ts(p["timestamp"]) >= cutoff]
        scored = [p for p in recent if p.get("outlier") is not None and p["mature"]]
        reel_views = [p["views"] for p in mine if p["format"] == "reel" and p.get("views") is not None][:30]
        best = max(scored, key=lambda p: p["outlier"], default=None)

        hist = c.get("history", [])
        growth = None
        if hist:
            cutoff_naive = (now - timedelta(days=30)).replace(tzinfo=None)
            old = next((h for h in hist if datetime.fromisoformat(h["date"]) >= cutoff_naive), hist[0])
            if old.get("followers") and c.get("followers"):
                growth = c["followers"] - old["followers"]

        out.append({
            "handle": handle,
            "name": c.get("name") or c.get("display_name") or handle,
            "group": c.get("group", "core"),
            "followers": c.get("followers"),
            "follower_growth_30d": growth,
            "posts_30d": len(recent),
            "median_reel_views": int(median(reel_views)) if reel_views else None,
            "hit_rate_30d": round(sum(1 for p in scored if p["outlier"] >= hit) / len(scored), 3) if scored else None,
            "best_post": {"id": best["id"], "permalink": best["permalink"], "outlier": best["outlier"]} if best else None,
            "reels_share_30d": round(sum(1 for p in recent if p["format"] == "reel") / len(recent), 2) if recent else None,
        })
    out.sort(key=lambda c: c["followers"] or 0, reverse=True)
    return out
