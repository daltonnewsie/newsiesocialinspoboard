"""Optional Claude layer.

1. Tags each post's hook type, topic, and a short hook paraphrase (cheap model,
   each post tagged once and cached).
2. Writes a weekly brief: what's working, what's cooling off, and content ideas.

Everything here is skipped when ai.enabled is false or ANTHROPIC_API_KEY is unset.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

HOOK_TYPES = [
    "how_to", "listicle", "contrarian", "results_case_study", "teardown_audit",
    "mistake_warning", "personal_story", "freebie_template", "news_trend",
    "question_poll", "promo", "other",
]
TOPICS = [
    "flows_automation", "campaigns", "copywriting", "subject_lines", "email_design",
    "deliverability", "sms", "list_growth", "segmentation", "seasonal_bfcm",
    "metrics_strategy", "agency_business", "ai_tools", "ecommerce_general", "other",
]

TAG_PROMPT = """You label Instagram posts from creators in the ecommerce email & SMS marketing niche.
For each post, read the caption and return:
- hook_type: one of {hook_types}
- topic: one of {topics}
- hook: the post's opening hook, paraphrased in 12 words or fewer (plain text, no quotes)

Return ONLY a JSON array like [{{"id": "...", "hook_type": "...", "topic": "...", "hook": "..."}}], no other text.

Posts:
{posts}"""

BRIEF_PROMPT = """You're a content strategist helping a creator decide what to post next.

About the creator you're advising:
{context}

Below is last {days} days of performance data from Instagram creators in the ecommerce email marketing
niche. "outlier" = the post's views (Reels) or likes+2×comments (other posts) divided by that creator's own
median, so 3.0 means 3× their normal performance. Pattern rows show median outlier score and post count per tag.
Where a prior-period value is given, compare to spot what's rising or cooling.

TOP OUTLIER POSTS
{top_posts}

PATTERNS (this period vs. prior period)
{patterns}

Write a short, concrete brief. Base every claim on the data above; if a pattern has few posts, say it's early.
Return ONLY JSON with this shape, no other text:
{{
  "headline": "one sentence: the single most useful takeaway",
  "trends": [{{"title": "...", "detail": "1-2 sentences citing the numbers"}}],   // 3-5 items
  "cooling": [{{"title": "...", "detail": "..."}}],                               // 0-3 items
  "ideas": [{{"title": "a post idea for the creator", "angle": "hook + format", "why": "which outlier/pattern it borrows from"}}]  // 4-6 items
}}"""


def _client():
    import anthropic  # imported lazily so the pipeline runs without it installed
    return anthropic.Anthropic()


def _json_from(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = min([i for i in (text.find("["), text.find("{")) if i != -1], default=0)
    return json.loads(text[start:])


def tag_posts(posts: dict[str, dict], model: str, batch_size: int = 15, max_new: int = 300) -> int:
    """Tag posts that don't have tags yet. Returns number tagged."""
    todo = [p for p in posts.values() if "tags" not in p]
    todo.sort(key=lambda p: p["timestamp"], reverse=True)
    todo = todo[:max_new]
    if not todo:
        return 0

    client = _client()
    tagged = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i : i + batch_size]
        lines = []
        for p in batch:
            cap = (p.get("caption") or "(no caption)").replace("\n", " ")[:600]
            lines.append(json.dumps({"id": p["id"], "format": p["format"], "caption": cap}, ensure_ascii=False))
        prompt = TAG_PROMPT.format(
            hook_types=", ".join(HOOK_TYPES), topics=", ".join(TOPICS), posts="\n".join(lines)
        )
        try:
            msg = client.messages.create(
                model=model, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
            )
            results = _json_from("".join(b.text for b in msg.content if b.type == "text"))
        except Exception as e:  # keep going; untagged posts retry next run
            print(f"  ! tagging batch failed: {e}")
            continue
        for r in results:
            p = posts.get(str(r.get("id")))
            if not p:
                continue
            p["tags"] = {
                "hook_type": r.get("hook_type") if r.get("hook_type") in HOOK_TYPES else "other",
                "topic": r.get("topic") if r.get("topic") in TOPICS else "other",
                "hook": (r.get("hook") or "")[:120],
            }
            tagged += 1
    return tagged


def pattern_table(posts: list[dict]) -> dict[str, dict[str, dict]]:
    """{dimension: {value: {n, median_outlier}}} over scored, mature posts."""
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for p in posts:
        if p.get("outlier") is None or not p.get("mature"):
            continue
        groups["format"][p["format"]].append(p["outlier"])
        groups["comment_cta"]["yes" if p.get("comment_cta") else "no"].append(p["outlier"])
        t = p.get("tags") or {}
        if t.get("hook_type"):
            groups["hook_type"][t["hook_type"]].append(p["outlier"])
        if t.get("topic"):
            groups["topic"][t["topic"]].append(p["outlier"])
    return {
        dim: {k: {"n": len(v), "median_outlier": round(median(v), 2)} for k, v in vals.items()}
        for dim, vals in groups.items()
    }


def weekly_brief(posts: dict[str, dict], model: str, context: str, days: int = 30) -> dict | None:
    from .scoring import parse_ts, now_utc

    now = now_utc()
    cur = [p for p in posts.values() if parse_ts(p["timestamp"]) >= now - timedelta(days=days)]
    prev = [
        p for p in posts.values()
        if now - timedelta(days=2 * days) <= parse_ts(p["timestamp"]) < now - timedelta(days=days)
    ]
    scored = sorted([p for p in cur if p.get("outlier") and p["mature"]], key=lambda p: -p["outlier"])
    if len(scored) < 5:
        return None

    top = []
    for p in scored[:25]:
        t = p.get("tags") or {}
        top.append(
            f"- @{p['handle']} | {p['format']} | {p['outlier']}x | hook_type={t.get('hook_type','?')} "
            f"| topic={t.get('topic','?')} | comment_cta={p.get('comment_cta')} | "
            f"caption: {(p.get('caption') or '')[:220].replace(chr(10), ' ')}"
        )

    cur_pat, prev_pat = pattern_table(cur), pattern_table(prev)
    pat_lines = []
    for dim, vals in cur_pat.items():
        for k, v in sorted(vals.items(), key=lambda kv: -kv[1]["median_outlier"]):
            pv = prev_pat.get(dim, {}).get(k)
            prior = f" (prior: {pv['median_outlier']}x, n={pv['n']})" if pv else " (prior: none)"
            pat_lines.append(f"- {dim}={k}: {v['median_outlier']}x, n={v['n']}{prior}")

    prompt = BRIEF_PROMPT.format(
        context=context.strip(), days=days, top_posts="\n".join(top), patterns="\n".join(pat_lines)
    )
    msg = _client().messages.create(
        model=model, max_tokens=2500, messages=[{"role": "user", "content": prompt}]
    )
    brief = _json_from("".join(b.text for b in msg.content if b.type == "text"))
    brief["generated_at"] = datetime.now(timezone.utc).isoformat()
    brief["period_days"] = days
    return brief
