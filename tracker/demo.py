"""Fake-but-realistic data so you can preview the dashboard before setup.
All handles are prefixed demo_ and are not real accounts."""
from __future__ import annotations

import random
from datetime import timedelta

from .scoring import has_comment_cta, now_utc

CREATORS = [
    ("demo_flowlab", "Flow Lab (demo)", "core", 184000),
    ("demo_inboxcoach", "Inbox Coach (demo)", "core", 96000),
    ("demo_retentionrae", "Retention Rae (demo)", "core", 41000),
    ("demo_klaviyokid", "Klaviyo Kid (demo)", "core", 23500),
    ("demo_smsstack", "SMS Stack (demo)", "core", 12800),
    ("demo_dtcdan", "DTC Dan (demo)", "adjacent", 312000),
    ("demo_shopifyscale", "Shopify Scale (demo)", "adjacent", 158000),
    ("demo_brandbuilderbea", "Brand Builder Bea (demo)", "adjacent", 67000),
]

# (caption, hook_type, topic, hook, strength)
TEMPLATES = [
    ("I audited a $40M brand's Klaviyo account. Here's the $1.2M they were leaving on the table 👇\n\nComment AUDIT and I'll send you my checklist.", "teardown_audit", "flows_automation", "Audited a $40M brand's Klaviyo and found $1.2M missing", 3.2),
    ("Stop sending your welcome flow discount in email #1. Here's why it's killing your LTV.", "contrarian", "flows_automation", "Stop putting the welcome discount in email one", 2.4),
    ("5 subject lines that got 60%+ open rates this month (steal them)", "listicle", "subject_lines", "Five subject lines that hit 60% opens this month", 1.8),
    ("How to set up a browse abandonment flow in 3 minutes", "how_to", "flows_automation", "Set up browse abandonment in three minutes", 1.0),
    ("Your emails are going to spam and you don't even know it. Check these 3 things today.", "mistake_warning", "deliverability", "Your emails are landing in spam without you knowing", 2.1),
    ("We added SMS to this skincare brand and it drove 22% of revenue in 90 days. Full breakdown:", "results_case_study", "sms", "SMS drove 22% of a skincare brand's revenue", 1.9),
    ("Comment FLOWS and I'll DM you the exact 9 flows every Shopify brand needs", "freebie_template", "flows_automation", "The nine flows every Shopify brand needs", 2.9),
    ("BFCM is 9 weeks away. Here's the email calendar we're running for every client.", "how_to", "seasonal_bfcm", "The BFCM email calendar we run for every client", 2.6),
    ("I quit my 9-5 to start an email agency. Year 3 numbers, honestly:", "personal_story", "agency_business", "Year three numbers after quitting to start an agency", 1.4),
    ("Is your popup converting under 5%? Here's the fix.", "mistake_warning", "list_growth", "Popup converting under five percent? Here's the fix", 1.6),
    ("Plain text vs designed emails — we tested both for 6 months.", "results_case_study", "email_design", "Six months testing plain text vs designed emails", 2.2),
    ("Klaviyo just released a new AI feature. Here's what actually matters for your store.", "news_trend", "ai_tools", "Klaviyo's new AI feature, and what matters", 1.3),
    ("The segment that makes us the most money (and nobody builds it)", "contrarian", "segmentation", "The most profitable segment nobody builds", 2.0),
    ("Rate this email design 1-10 👇", "question_poll", "email_design", "Rate this email design one to ten", 0.8),
    ("How we write campaigns that don't sound like every other brand", "how_to", "copywriting", "Writing campaigns that don't sound like everyone else", 1.1),
    ("Your post-purchase flow should NOT be selling. Do this instead.", "contrarian", "flows_automation", "Your post-purchase flow shouldn't be selling", 1.7),
    ("Free template: our entire campaign calendar. Comment CALENDAR to get it.", "freebie_template", "campaigns", "Our entire campaign calendar as a free template", 2.5),
    ("3 metrics I check in every Klaviyo account before anything else", "listicle", "metrics_strategy", "Three metrics I check first in every account", 1.2),
    ("Our agency is booking Q1 clients — link in bio", "promo", "agency_business", "Now booking Q1 clients", 0.5),
    ("Why your abandoned cart flow is only recovering 3%", "mistake_warning", "flows_automation", "Why abandoned cart only recovers three percent", 1.9),
    ("Tearing down a cult DTC brand's welcome series email by email", "teardown_audit", "flows_automation", "Tearing down a famous brand's welcome series", 2.7),
    ("Email marketing is dead? This brand did $3M from it last year.", "contrarian", "ecommerce_general", "'Email is dead' vs a brand doing $3M from it", 2.3),
]


def make_demo():
    rnd = random.Random(7)
    now = now_utc()
    posts, creators = {}, {}
    pid = 10_000

    for handle, name, group, followers in CREATORS:
        creators[handle] = {
            "name": name, "group": group, "followers": followers, "avatar": None,
            "history": [
                {"date": (now - timedelta(days=d)).date().isoformat(),
                 "followers": int(followers * (1 - 0.0012 * d * rnd.uniform(0.3, 1.6)))}
                for d in range(35, -1, -7)
            ],
        }
        base_views = followers * rnd.uniform(0.18, 0.6)
        for _ in range(rnd.randint(30, 55)):
            cap, hook_type, topic, hook, strength = rnd.choice(TEMPLATES)
            age = timedelta(hours=rnd.uniform(6, 24 * 85))
            fmt = rnd.choices(["reel", "carousel", "image"], [0.62, 0.3, 0.08])[0]
            mult = strength * rnd.lognormvariate(0, 0.45)
            if rnd.random() < 0.05:
                mult *= rnd.uniform(2, 4)  # occasional breakout
            if age < timedelta(hours=48):
                mult *= min(1.0, age.total_seconds() / (48 * 3600)) + 0.2
            cta = has_comment_cta(cap)
            views = int(base_views * mult) if fmt == "reel" else None
            likes = int((views or base_views * 0.9 * mult) * rnd.uniform(0.02, 0.05))
            comments = int(likes * (rnd.uniform(0.6, 1.4) if cta else rnd.uniform(0.02, 0.08)))
            pid += 1
            posts[str(pid)] = {
                "id": str(pid), "handle": handle, "format": fmt, "caption": cap,
                "permalink": "https://www.instagram.com/",
                "timestamp": (now - age).strftime("%Y-%m-%dT%H:%M:%S+0000"), "thumb": None,
                "views": views, "likes": None if rnd.random() < 0.04 else likes,
                "comments": comments, "comment_cta": cta,
                "tags": {"hook_type": hook_type, "topic": topic, "hook": hook},
            }

    summary = {
        "generated_at": now.isoformat(),
        "period_days": 30,
        "headline": "Teardowns of real brand accounts are the most reliable breakout format right now — they hit 2.7× their creators' normal reach on median.",
        "trends": [
            {"title": "Teardowns and audits lead", "detail": "Audit/teardown posts ran a 2.7× median outlier across 21 posts, up from 1.9× the prior month."},
            {"title": "Comment-keyword CTAs inflate comments", "detail": "Posts with a 'comment WORD' CTA median 2.4× vs 1.3× without — but mostly through comments, not views."},
            {"title": "BFCM prep is heating up", "detail": "Seasonal posts jumped to 2.6× (n=9) as creators start Q4 planning content."},
        ],
        "cooling": [
            {"title": "Generic how-tos", "detail": "Straight tutorials slipped to 1.0× from 1.3× — they need a sharper hook to stand out."},
        ],
        "ideas": [
            {"title": "Audit a well-known DTC brand's welcome flow on camera", "angle": "Teardown hook + screen-recorded Reel", "why": "Top pattern this month (2.7×)."},
            {"title": "Our BFCM email calendar, free", "angle": "Freebie with comment CTA, carousel", "why": "Seasonal + freebie posts are both over 2.5×."},
            {"title": "The flow every brand gets wrong", "angle": "Contrarian hook, talking-head Reel", "why": "Contrarian flow takes averaged 2.1× on core creators."},
            {"title": "What $1M in email revenue looks like inside Klaviyo", "angle": "Results reveal, screen recording", "why": "Case-study posts with a dollar figure outperform ones without."},
        ],
    }

    disc = []
    for i, (cap, *_rest) in enumerate(TEMPLATES[:14]):
        disc.append({
            "id": f"d{i}", "hashtags": [rnd.choice(["emailmarketing", "klaviyo", "smsmarketing", "ecommercemarketing"])],
            "format": rnd.choice(["reel", "carousel"]), "caption": cap, "permalink": "https://www.instagram.com/",
            "timestamp": (now - timedelta(days=rnd.randint(1, 20))).strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "likes": rnd.randint(300, 9000), "comments": rnd.randint(10, 900),
        })
    disc.sort(key=lambda r: -(r["likes"] + 2 * r["comments"]))
    return posts, creators, summary, {"updated_at": now.isoformat(), "posts": disc}
