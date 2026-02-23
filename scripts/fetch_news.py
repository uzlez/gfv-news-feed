#!/usr/bin/env python3
"""
GFV News Feed - Fetches and aggregates news about Green Flag Ventures,
GFV, Justin Zeefee, and Deborah Fairlamb from Google News RSS.
Stores articles in a JSON file and generates a static HTML page.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ── Configuration ────────────────────────────────────────────────────────────

KEYWORDS = {
    "Green Flag Ventures": '"Green Flag Ventures"',
    "GFV":                 '"GFV" ventures',
    "Justin Zeefee":       '"Justin Zeefee"',
    "Deborah Fairlamb":    '"Deborah Fairlamb"',
}

DAYS_LOOKBACK = 180

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE  = os.path.join(BASE_DIR, "data", "news_data.json")
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Colour palette for keyword badges ────────────────────────────────────────

KEYWORD_COLORS = {
    "Green Flag Ventures": ("#d1fae5", "#065f46"),   # green
    "GFV":                 ("#dbeafe", "#1e3a8a"),   # blue
    "Justin Zeefee":       ("#fef3c7", "#92400e"),   # amber
    "Deborah Fairlamb":    ("#ede9fe", "#4c1d95"),   # violet
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def rfc2822_to_iso(date_str: str) -> str | None:
    """Convert an RFC-2822 date string to ISO-8601 (UTC)."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def fetch_google_news_rss(query: str) -> list[dict]:
    """Fetch articles from Google News RSS for a given query string."""
    url = (
        "https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    articles = []
    try:
        req  = Request(url, headers=HEADERS)
        with urlopen(req, timeout=20) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        for item in root.iter("item"):
            title_el   = item.find("title")
            link_el    = item.find("link")
            desc_el    = item.find("description")
            pubdate_el = item.find("pubDate")
            source_el  = item.find("source")

            title   = title_el.text.strip()   if title_el   is not None and title_el.text   else ""
            link    = link_el.text.strip()     if link_el    is not None and link_el.text    else ""
            desc    = desc_el.text             if desc_el    is not None and desc_el.text    else ""
            pubdate = pubdate_el.text          if pubdate_el is not None and pubdate_el.text else ""
            source  = source_el.text.strip()   if source_el  is not None and source_el.text  else ""

            # Strip HTML from description
            desc = re.sub(r"<[^>]+>", "", desc).strip()

            iso_date = rfc2822_to_iso(pubdate) if pubdate else None

            if title and link and iso_date:
                articles.append({
                    "title":   title,
                    "link":    link,
                    "description": desc[:400],
                    "published":   iso_date,
                    "source":  source,
                })
    except (URLError, HTTPError, ET.ParseError) as exc:
        print(f"  ⚠️  Error fetching '{query}': {exc}", file=sys.stderr)
    return articles


def load_existing_data() -> list[dict]:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_data(articles: list[dict]) -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)


def prune_old_articles(articles: list[dict], days: int = DAYSLOOKBACK) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for a in articles:
        try:
            dt = datetime.fromisoformat(a["published"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                kept.append(a)
        except ValueError:
            pass
    return kept


def deduplicate(articles: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for a in articles:
        key = a["link"]
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def merge_articles(existing: list[dict], new_batch: list[dict]) -> list[dict]:
    merged = existing + new_batch
    merged = deduplicate(merged)
    merged = prune_old_articles(merged)
    return merged


# ── HTML generation ────────────────────────────────────────────────────────────

def format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return iso


def article_html(article: dict, keyword: str) -> str:
    bg, fg = KEYWORD_COLORS.get(keyword, ("#f3f4f6", "#374151"))
    title   = article["title"].replace('"', "&quot;").replace("<", "&lt;")
    desc    = article.get("description", "").replace("<", "&lt;").replace('"', "&quot;")
    source  = article.get("source", "Unknown")
    pub     = format_date(article["published"])
    link    = article["link"]

    return f"""
    <div class="article-card" data-keyword="{keyword}">
      <div class="card-header">
        <span class="badge" style="background:{bg};color:{fg}">{keyword}</span>
        <span class="pub-date">{pub}</span>
      </div>
      <h3 class="article-title">
        <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
      </h3>
      {"<p class='article-desc'>" + desc + "</p>" if desc else ""}
      <div class="card-footer">
        <span class="source-name">📰 {source}</span>
      </div>
    </div>"""


def generate_html(articles_by_keyword: dict[str, list[dict]], all_articles: list[dict]) -> str:
    now_str = datetime.now(timezone.utc).strftime("%B %-d, %Y at %H:%M UTC")
    total   = len(all_articles)

    # Build filter buttons
    filter_buttons = '<button class="filter-btn active" onclick="filterBy(\'all\', this)">All <span class="count">' + str(total) + "</span></button>\n"
    for kw, arts in articles_by_keyword.items():
        bg, fg = KEYWORD_COLORS.get(kw, ("#f3f4f6", "#374151"))
        cnt = len(arts)
        filter_buttons += (
            f'    <button class="filter-btn" onclick="filterBy(\'{kw}\', this)" '
            f'style="--kw-bg:{bg};--kw-fg:{fg}">{kw} <span class="count">{cnt}</span></button>\n'
        )

    # Build article cards sorted newest-first
    sorted_articles = sorted(all_articles, key=lambda x: x["published"], reverse=True)
    # Build a reverse lookup: link → keyword (keep first keyword match)
    link_to_kw: dict[str, str] = {}
    for kw, arts in articles_by_keyword.items():
        for a in arts:
            if a["link"] not in link_to_kw:
                link_to_kw[a["link"]] = kw

    cards_html = "\n".join(
        article_html(a, link_to_kw.get(a["link"], list(KEYWORDS.keys())[0]))
        for a in sorted_articles
    )

    if not cards_html:
        cards_html = """
        <div class="empty-state">
          <p>No news found yet. The feed will populate on the next scheduled run.</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GFV News Feed</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:       #f9fafb;
      --surface:  #ffffff;
      --border:   #e5e7eb;
      --text:     #111827;
      --muted:    #6b7280;
      --accent:   #059669;
      --radius:   10px;
      --shadow:   0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.06);
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 0 0 60px;
    }}

    /* ── Header ── */
    .site-header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 24px 20px 18px;
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .header-inner {{
      max-width: 860px;
      margin: 0 auto;
    }}
    .site-header h1 {{
      font-size: 1.35rem;
      font-weight: 700;
      color: var(--accent);
      letter-spacing: -0.3px;
    }}
    .header-meta {{
      font-size: .78rem;
      color: var(--muted);
      margin-top: 4px;
    }}

    /* ── Filters ── */
    .filters {{
      max-width: 860px;
      margin: 20px auto 0;
      padding: 0 20px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .filter-btn {{
      border: 1.5px solid var(--border);
      background: var(--surface);
      color: var(--text);
      padding: 5px 13px;
      border-radius: 20px;
      font-size: .8rem;
      font-weight: 500;
      cursor: pointer;
      transition: all .15s;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .filter-btn.active {{
      background: var(--kw-bg, var(--accent));
      color: var(--kw-fg, #fff);
      border-color: transparent;
    }}
    .filter-btn .count {{
      background: rgba(0,0,0,.08);
      border-radius: 10px;
      padding: 1px 6px;
      font-size: .72rem;
    }}

    /* ── Article grid ── */
    .articles-container {{
      max-width: 860px;
      margin: 22px auto 0;
      padding: 0 20px;
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }}

    /* ── Card ── */
    .article-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: var(--shadow);
      transition: box-shadow .15s;
    }}
    .article-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,.1); }}
    .article-card.hidden {{ display: none; }}

    .card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }}
    .badge {{
      font-size: .7rem;
      font-weight: 600;
      padding: 2px 9px;
      border-radius: 12px;
      letter-spacing: .3px;
      text-transform: uppercase;
    }}
    .pub-date {{
      font-size: .75rem;
      color: var(--muted);
    }}

    .article-title {{
      font-size: .95rem;
      font-weight: 600;
      line-height: 1.4;
      margin-bottom: 7px;
    }}
    .article-title a {{
      color: var(--text);
      text-decoration: none;
    }}
    .article-title a:hover {{ color: var(--accent); text-decoration: underline; }}

    .article-desc {{
      font-size: .83rem;
      color: var(--muted);
      line-height: 1.55;
      margin-bottom: 10px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .card-footer {{
      font-size: .75rem;
      color: var(--muted);
    }}
    .source-name {{ font-weight: 500; }}

    /* ── Empty state ── */
    .empty-state {{
      text-align: center;
      padding: 60px 20px;
      color: var(--muted);
    }}

    /* ── Responsive ── */
    @media (min-width: 600px) {{
      .articles-container {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <h1>🟢	 GFV News Feed</h1>
    <p class="header-meta">
      {total} article{"s" if total != 1 else ""} from the last {DAYS_LOOKBACK} days
      &nbsp;·&nbsp; Updated {now_str}
    </p>
  </div>
</header>

<div class="filters">
  {filter_buttons}
</div>

<div class="articles-container" id="articles-container">
  {cards_html}
</div>

<script>
  function filterBy(keyword, btn) {{
    // Update active button
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    // Show/hide cards
    document.querySelectorAll('.article-card').forEach(card => {{
      if (keyword === 'all' || card.dataset.keyword === keyword) {{
        card.classList.remove('hidden');
      }} else {{
        card.classList.add('hidden');
      }}
    }});
  }}
</script>

</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("🔍 Fetching news for GFV-related keywords…")

    existing = load_existing_data()
    print(f"  Loaded {len(existing)} existing articles from {DATA_FILE}")

    articles_by_keyword: dict[str, list[dict]] = {}
    new_articles: list[dict] = []

    for label, query in KEYWORDS.items():
        print(f"  → Searching: {label!r} (query: {query!r})")
        fetched = fetch_google_news_rss(query)
        print(f"     Found {len(fetched)} articles")
        articles_by_keyword[label] = fetched
        for a in fetched:
            a["keyword"] = label
        new_articles.extend(fetched)

    all_articles = merge_articles(existing, new_articles)
    print(f"\n✅ Total after merge & dedup: {len(all_articles)} articles")

    save_data(all_articles)
    print(f"💾 Saved to {DATA_FILE}")

    # Re-group by keyword for the HTML (use stored keyword field)
    regrouped: dict[str, list[dict]] = {k: [] for k in KEYWORDS}
    for a in all_articles:
        kw = a.get("keyword", "")
        if kw in regrouped:
            regrouped[kw].append(a)

    html = generate_html(regrouped, all_articles)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🌐 HTML written to {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
