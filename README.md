# Outlier board

A daily-updating website that shows which Instagram posts in the ecommerce email marketing niche are beating their creator's normal performance, and what those posts have in common.

- **Outliers** lists posts ranked by how far they beat the creator's own median (e.g. 4.2× = four times their usual views). Each post shows its hook, format, topic, and numbers.
- **Patterns** shows which hook types, topics, formats, and CTAs are outperforming, compared with the previous period.
- **Creators** shows followers, growth, posting cadence, Reels share, median views, and hit rate per creator.
- **Discover** shows top posts on your hashtags, for finding creators you aren't tracking yet.
- **This week's read** is a Claude-written brief with trends, what's cooling off, and post ideas for you (optional).

Everything runs on free tiers: Instagram's official API, GitHub Actions, and Cloudflare Pages. The only optional cost is the Claude API for tagging and the weekly brief, typically a few dollars a month at most.

---

## Preview it first (2 minutes, no accounts needed)

```bash
pip install -r requirements.txt
python -m tracker.main --demo
python -m http.server -d site 8000
```

Open http://localhost:8000. Everything you see is fake demo data (`demo_` handles).

---

## Setup (about 30–45 minutes, one time)

### 1. Prepare your Instagram account
1. In the Instagram app: **Settings → Account type and tools → Switch to professional account** (Creator or Business). Skip this if it already is.
2. Link it to a Facebook Page you manage: in Instagram go to **Accounts Center**, or in Facebook go to **Page settings → Linked accounts → Instagram**. Any Page works; it can be a bare Page just for this.

### 2. Create a Meta app
1. Go to https://developers.facebook.com → **My Apps → Create app**.
2. When asked for a use case, pick the option for managing everything on your Page / Instagram (or **Other → Business** if shown).
3. In the app dashboard, add the **Instagram** product and choose **API setup with Facebook login**.
4. Leave the app in **Development mode**. You're the only user, so no App Review is needed.
5. Note your **App ID** and **App Secret** (App settings → Basic).

### 3. Get your token
1. Open the **Graph API Explorer**: https://developers.facebook.com/tools/explorer
2. Choose your app in the top-right. Under **User or Page**, choose **Get User Access Token** and tick these permissions:
   `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `business_management`, `ads_read`
   (`ads_read` is only required when your Page access comes through a Meta Business portfolio, but including it does no harm.)
3. Click **Generate Access Token**. When Facebook asks, grant access to the Page linked to your Instagram.
4. Copy the token, then run:
   ```bash
   python scripts/get_token.py
   ```
   Paste your App ID, App Secret, and the token. The script tests the connection and prints your `IG_USER_ID` and `IG_ACCESS_TOKEN`. The printed token is a Page token, which normally doesn't expire.

### 4. Put the project on GitHub
1. Create a new **private** repository on GitHub and push this folder to it.
2. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `IG_USER_ID`
   - `IG_ACCESS_TOKEN`
   - `ANTHROPIC_API_KEY` (optional; create one at https://console.anthropic.com. Without it the AI brief and tags are skipped.)

### 5. Host the dashboard on Cloudflare Pages (free, works with private repos)
1. In Cloudflare go to **Workers & Pages → Create → Pages → Connect to Git**, and choose your repo.
2. Framework preset: **None**. Build command: *leave empty*. Build output directory: `site`.
3. Deploy. You get a URL like `outlier-board.pages.dev`. Every data update the workflow commits redeploys it automatically.
4. To keep it private (recommended), in the Pages project go to **Settings → Access policy / Cloudflare Access**, enable it, and allow only your email. You'll log in with a one-time code.

If Cloudflare's screens look different, look for "Import a repository" and set the output directory to `site`.

### 6. Add creators and run
1. Edit `config/creators.yaml`: fill in each handle and uncomment the line. Commit and push.
2. On GitHub go to **Actions → Update outlier board → Run workflow**.
3. After that it runs every morning on its own. Any handle that fails shows up under "issues" at the bottom of the dashboard with the reason.

The first few runs build up baselines. Outlier scores need at least 5 settled posts per creator per type, which most creators have from day one because each run pulls their last 50 posts. The weekly brief appears once there's enough scored data.

---

## How the scoring works

- **Outlier score** = a post's primary number divided by that creator's median for the same post type over their last 30 settled posts.
  - For Reels, the primary number is views.
  - For carousels and images, it's likes + 2×comments. Comments count double because they take more effort than a like.
  - If a creator hides likes, comments alone are used.
- Reels and static posts get **separate baselines**, since they reach very different audience sizes.
- Posts under 48 hours old are marked **Still growing** and left out of baselines. Their scores keep updating each day.
- A **hit** is a post at 2× or more (change `hit_threshold` in `config/settings.yaml`).
- **Comment-keyword CTAs** ("Comment FLOWS and I'll DM you…") are detected automatically. They pump comments, so the Patterns tab shows them separately, letting you see whether a post truly broke out or just farmed comments.

## Configuration

`config/settings.yaml` controls:
- posts pulled per creator
- baseline window
- hit threshold
- the AI models, and turning AI on or off
- the context the weekly brief uses to tailor ideas to you
- discovery hashtags

To change the schedule, edit the `cron` line in `.github/workflows/update.yml`. It's daily by default; Instagram's rate limit (200 calls/hour) easily covers 30–40 creators.

## Refresh your token

If the dashboard says the token is invalid, repeat step 3 and update the `IG_ACCESS_TOKEN` secret. Page tokens normally stay valid unless you change your Facebook password, remove the app, or lose admin access to the Page.

## Known limits (Instagram API)

- **Shares and saves** aren't available for other people's posts from any source.
- **View counts** come for Reels only. Carousels and images are judged on likes and comments.
- **Thumbnails** are Instagram image links that expire after a while. Older posts show a placeholder; the numbers and links still work.
- **Discover** can't show who posted each result, because the hashtag API doesn't return usernames. Open the post to see the creator. If Meta returns a permissions error for hashtag search, that feature needs extra access. It's listed under issues, and everything else keeps working. Instagram allows 30 unique hashtags per rolling 7 days.

## Files

```
config/creators.yaml     who to track
config/settings.yaml     scoring, AI, and discovery settings
tracker/instagram.py     Instagram Graph API client
tracker/scoring.py       outlier + engagement scoring
tracker/ai.py            Claude tagging and weekly brief (optional)
tracker/main.py          runs everything
tracker/demo.py          fake data for previewing
scripts/get_token.py     one-time token helper
site/index.html          the dashboard
site/data.json           generated data the dashboard reads
data/                    history the pipeline keeps between runs
.github/workflows/       daily schedule
```
