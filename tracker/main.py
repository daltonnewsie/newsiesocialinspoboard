"""Run the full pipeline.

    python -m tracker.main            # real run (needs IG_USER_ID + IG_ACCESS_TOKEN)
    python -m tracker.main --demo     # fake data, to preview the dashboard
    python -m tracker.main --no-ai    # skip Claude for this run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import scoring
from .scoring import now_utc, parse_ts

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"


# --------------------------------------------------------------------- io
def load_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path: Path, obj, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=None if compact else 1))


def load_config():
    settings = yaml.safe_load((ROOT / "config/settings.yaml").read_text()) or {}
    creators = (yaml.safe_load((ROOT / "config/creators.yaml").read_text()) or {}).get("creators") or []
    creators = [c for c in creators if c and str(c.get("handle", "")).strip()]
    for c in creators:
        c["handle"] = str(c["handle"]).strip().lstrip("@").lower()
    return settings, creators


# ------------------------------------------------------------------ fetch
def fetch_all(ig, creator_cfg, settings, posts, creators, errors):
    today = datetime.now(timezone.utc).date().isoformat()
    for c in creator_cfg:
        h = c["handle"]
        print(f"→ @{h}")
        try:
            profile, raw_posts = ig.fetch_creator(h, max_posts=settings.get("posts_per_creator", 50))
        except Exception as e:
            msg = getattr(e, "message", str(e))
            print(f"  ! {msg}")
            errors.append({"handle": h, "error": _friendly_error(e)})
            if getattr(e, "is_auth", False):
                raise  # bad token: no point continuing
            continue

        rec = creators.setdefault(h, {"history": []})
        rec.update({
            "name": c.get("name") or profile.get("name") or h,
            "display_name": profile.get("name"),
            "group": c.get("group", "core"),
            "followers": profile.get("followers_count"),
            "media_count": profile.get("media_count"),
            "avatar": profile.get("profile_picture_url"),
        })
        hist = rec["history"]
        if hist and hist[-1]["date"] == today:
            hist[-1]["followers"] = rec["followers"]
        else:
            hist.append({"date": today, "followers": rec["followers"]})
        rec["history"] = hist[-400:]

        for raw in raw_posts:
            new = scoring.normalize(raw, h)
            old = posts.get(new["id"])
            if old:
                # keep tags + first_seen, refresh metrics
                if "tags" in old:
                    new["tags"] = old["tags"]
                new["first_seen"] = old.get("first_seen", today)
            else:
                new["first_seen"] = today
            posts[new["id"]] = new
        print(f"  {len(raw_posts)} posts, {profile.get('followers_count')} followers")


def _friendly_error(e) -> str:
    code = getattr(e, "code", None)
    msg = getattr(e, "message", str(e))
    if code == 110 or "cannot be found" in msg.lower() or "not a business" in msg.lower():
        return "Handle not found, or it isn't a Business/Creator account. Check the spelling in creators.yaml."
    if code == 190:
        return "Access token is invalid or expired. Generate a new Page token and update the IG_ACCESS_TOKEN secret."
    if getattr(e, "is_rate_limit", False):
        return "Instagram rate limit reached. This creator will be retried next run."
    return msg


def discover(ig, settings, errors):
    dcfg = settings.get("discovery") or {}
    if not dcfg.get("enabled"):
        return None
    cache = load_json(DATA / "hashtag_ids.json", {})
    results = []
    for tag in dcfg.get("hashtags", [])[:30]:
        tag = tag.lstrip("#").lower()
        try:
            if tag not in cache:
                cache[tag] = ig.hashtag_id(tag)
            if not cache[tag]:
                continue
            for m in ig.hashtag_top_media(cache[tag]):
                results.append({
                    "id": m["id"], "hashtag": tag, "format": scoring.post_format(m),
                    "caption": (m.get("caption") or "")[:500], "permalink": m.get("permalink"),
                    "timestamp": m.get("timestamp"), "likes": m.get("like_count"),
                    "comments": m.get("comments_count"),
                })
        except Exception as e:
            errors.append({"handle": f"#{tag}", "error": "Hashtag lookup failed: " + _friendly_error(e)})
    save_json(DATA / "hashtag_ids.json", cache)
    # de-dupe (same post can top several hashtags), rank by interactions
    seen, uniq = set(), []
    for r in sorted(results, key=lambda r: -((r["likes"] or 0) + 2 * (r["comments"] or 0))):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        r["hashtags"] = sorted({x["hashtag"] for x in results if x["id"] == r["id"]})
        uniq.append(r)
    return {"updated_at": now_utc().isoformat(), "posts": uniq[:80]}


# --------------------------------------------------------------- publish
def build_site_data(posts, creators, settings, summary, discovery, status):
    cutoff = now_utc() - timedelta(days=90)
    recent = [p for p in posts.values() if parse_ts(p["timestamp"]) >= cutoff]
    slim = []
    for p in recent:
        slim.append({k: p.get(k) for k in (
            "id", "handle", "format", "permalink", "timestamp", "thumb", "views", "likes",
            "comments", "comment_cta", "age_hours", "mature", "metric", "baseline", "outlier",
            "engagement_rate", "view_engagement", "tags",
        )} | {"caption": (p.get("caption") or "")[:700]})
    return {
        "generated_at": now_utc().isoformat(),
        "settings": {
            "hit_threshold": settings.get("hit_threshold", 2.0),
            "mature_after_hours": settings.get("mature_after_hours", 48),
        },
        "status": status,
        "summary": summary,
        "creators": scoring.creator_stats(posts, creators, settings),
        "posts": slim,
        "discovery": discovery,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="generate fake data to preview the dashboard")
    ap.add_argument("--no-ai", action="store_true", help="skip Claude tagging/brief this run")
    ap.add_argument("--force-brief", action="store_true", help="write a new weekly brief now")
    args = ap.parse_args()

    settings, creator_cfg = load_config()

    if args.demo:
        from .demo import make_demo
        posts, creators, summary, discovery = make_demo()
        scoring.score_posts(posts, creators, settings)
        status = {"last_run": now_utc().isoformat(), "demo": True, "errors": [], "token": None,
                  "ai_enabled": False, "creators_tracked": len(creators)}
        save_json(SITE / "data.json", build_site_data(posts, creators, settings, summary, discovery, status), compact=True)
        print(f"Demo data written to site/data.json ({len(posts)} posts).")
        return

    ig_user_id = os.environ.get("IG_USER_ID")
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not ig_user_id or not token:
        sys.exit("Set IG_USER_ID and IG_ACCESS_TOKEN (see README).")
    if not creator_cfg:
        sys.exit("No creators in config/creators.yaml yet — add at least one handle.")

    from .instagram import Instagram
    ig = Instagram(ig_user_id, token)

    posts = load_json(DATA / "posts.json", {})
    creators = load_json(DATA / "creators.json", {})
    summaries = load_json(DATA / "summaries.json", [])
    errors: list[dict] = []

    token_info = ig.token_status()
    fetch_all(ig, creator_cfg, settings, posts, creators, errors)

    # forget creators removed from the config (their posts too)
    active = {c["handle"] for c in creator_cfg}
    creators = {h: v for h, v in creators.items() if h in active}
    keep_after = now_utc() - timedelta(days=settings.get("keep_days", 180))
    posts = {k: p for k, p in posts.items() if p["handle"] in active and parse_ts(p["timestamp"]) >= keep_after}

    scoring.score_posts(posts, creators, settings)

    # ---- optional AI layer
    ai_cfg = settings.get("ai") or {}
    ai_on = ai_cfg.get("enabled") and not args.no_ai and os.environ.get("ANTHROPIC_API_KEY")
    if ai_on:
        try:
            from . import ai
            n = ai.tag_posts(posts, ai_cfg.get("tag_model"))
            print(f"Tagged {n} new posts")
            last = summaries[-1]["generated_at"] if summaries else None
            due = args.force_brief or not last or (
                now_utc() - datetime.fromisoformat(last) >= timedelta(days=ai_cfg.get("summary_every_days", 7))
            )
            if due:
                brief = ai.weekly_brief(posts, ai_cfg.get("summary_model"), ai_cfg.get("your_context", ""))
                if brief:
                    summaries.append(brief)
                    summaries = summaries[-26:]
                    print("Wrote weekly brief")
        except Exception as e:
            errors.append({"handle": "AI", "error": f"Claude step failed: {e}"})

    discovery = discover(ig, settings, errors)
    if discovery is None:
        discovery = load_json(DATA / "discovery.json", None)
    else:
        save_json(DATA / "discovery.json", discovery)

    save_json(DATA / "posts.json", posts)
    save_json(DATA / "creators.json", creators)
    save_json(DATA / "summaries.json", summaries)

    status = {
        "last_run": now_utc().isoformat(),
        "errors": errors,
        "token": token_info,
        "ai_enabled": bool(ai_on),
        "creators_tracked": len(creators),
        "api_calls": ig.calls,
    }
    site = build_site_data(posts, creators, settings, summaries[-1] if summaries else None, discovery, status)
    save_json(SITE / "data.json", site, compact=True)
    print(f"Done: {len(site['posts'])} posts on the dashboard, {len(errors)} issue(s), {ig.calls} API calls.")


if __name__ == "__main__":
    main()
