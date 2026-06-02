# tools/fundamental_tool.py
#
# UPGRADED: Multi-source RSS with browser-spoofing headers, 5-source fallback
# chain, weighted sentiment scoring, economic calendar context, and graceful
# degradation so the CIO always receives actionable macro data.

import re
import time
import requests
import feedparser
from datetime import datetime
from crewai.tools import tool

# ── Constants ────────────────────────────────────────────────────────────────

# Browser-like headers — the #1 reason plain feedparser calls return nothing.
# Investing.com and Kitco both block the default Python/feedparser user-agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

# Ordered fallback chain — tool tries each source in sequence.
# Multiple URLs per source handle feed path changes over time.
FEED_SOURCES = [
    # ── Tier 1: Direct precious-metals feeds ─────────────────────────────
    {
        "name": "Kitco News",
        "urls": [
            "https://www.kitco.com/rss/kitco-news.xml",
            "https://www.kitco.com/news/rss/precious_metals.xml",
            "https://www.kitco.com/rss/index.rss",
        ],
        "max_items": 8,
    },
    # ── Tier 2: Reuters via open aggregator ──────────────────────────────
    {
        "name": "Reuters (Commodities)",
        "urls": [
            "https://feeds.reuters.com/reuters/businessNews",
            "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        ],
        "max_items": 6,
    },
    # ── Tier 3: MarketWatch ───────────────────────────────────────────────
    {
        "name": "MarketWatch",
        "urls": [
            "https://feeds.marketwatch.com/marketwatch/marketpulse/",
            "https://feeds.marketwatch.com/marketwatch/topstories/",
        ],
        "max_items": 6,
    },
    # ── Tier 4: Seeking Alpha Commodities ────────────────────────────────
    {
        "name": "Seeking Alpha",
        "urls": [
            "https://seekingalpha.com/feed.xml",
        ],
        "max_items": 5,
    },
    # ── Tier 5: FXStreet Gold ─────────────────────────────────────────────
    {
        "name": "FXStreet",
        "urls": [
            "https://www.fxstreet.com/rss/news",
            "https://www.fxstreet.com/rss/analysis",
        ],
        "max_items": 6,
    },
    # ── Tier 6: Investing.com (often rate-limits, so moved to last) ───────
    {
        "name": "Investing.com",
        "urls": [
            "https://www.investing.com/rss/news_11.rss",
            "https://www.investing.com/rss/news_1.rss",
        ],
        "max_items": 5,
    },
]

# Assets that make a headline relevant to the gold/silver/macro thesis
RELEVANT_ASSETS = [
    'gold', 'silver', 'xau', 'precious metal',
    'oil', 'crude', 'brent', 'wti', 'energy',
    'fed', 'fomc', 'federal reserve', 'powell',
    'dollar', 'usd', 'dxy',
    'yield', 'treasury', 'bond',
    'inflation', 'cpi', 'pce',
    'rate', 'interest rate',
    'china', 'pboc', 'india', 'rbi',
    'geopolit', 'sanction', 'war', 'conflict',
]

# Weighted sentiment keywords — weight reflects impact magnitude on gold price
BULLISH_SIGNALS = {
    # Demand / safe-haven drivers
    'war':               2,
    'conflict':          2,
    'escalation':        2,
    'geopolitical':      2,
    'sanction':          1,
    'crisis':            1,
    'recession':         1,
    'stagflation':       2,
    # Monetary easing
    'rate cut':          2,
    'rate cuts':         2,
    'dovish':            2,
    'pivot':             2,
    'pause':             1,
    'stimulus':          2,
    'quantitative easing': 2,
    'qe':                1,
    # Supply / inflation
    'inflation':         1,
    'inflationary':      1,
    'shortage':          1,
    'supply chain':      1,
    'deficit':           1,
    # Central bank buying
    'central bank buying': 3,
    'reserve accumulation': 3,
    'de-dollarization':  3,
    'gold reserves':     2,
    # Weak dollar
    'weak dollar':       2,
    'dollar falls':      2,
    'dollar weakens':    2,
    'dollar decline':    2,
    # Generic positive
    'safe haven':        2,
    'flight to safety':  2,
    'risk off':          2,
    'uncertainty':       1,
}

BEARISH_SIGNALS = {
    # Monetary tightening
    'rate hike':         2,
    'rate hikes':        2,
    'hawkish':           2,
    'tightening':        1,
    'tapering':          1,
    'quantitative tightening': 2,
    'qt':                1,
    # Strong dollar
    'strong dollar':     2,
    'dollar surges':     2,
    'dollar rallies':    2,
    'dollar strengthens': 2,
    'dxy rises':         2,
    # Reduced safe-haven demand
    'peace':             1,
    'ceasefire':         1,
    'risk on':           1,
    'risk appetite':     1,
    # Disinflation
    'cooling inflation': 2,
    'disinflation':      2,
    'deflation':         1,
    'cpi falls':         2,
    'inflation slows':   2,
    # Yield pressure
    'yields rise':       1,
    'yields surge':      2,
    'real yields':       1,
    'yield curve':       1,
    # Generic negative
    'profit taking':     1,
    'selling pressure':  1,
    'outflows':          1,
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_feed(url: str, timeout: int = 10) -> list:
    """Fetch an RSS feed via requests (so we can set headers) then parse it."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return []
        # feedparser can parse a raw string directly
        parsed = feedparser.parse(resp.text)
        return parsed.entries if parsed.entries else []
    except Exception:
        return []


def _scrape_sources() -> list:
    """
    Try each source in FEED_SOURCES.  For each source, attempt each URL in
    order and return entries as soon as one succeeds.  Stops collecting once
    we have ≥ 40 raw headlines (plenty of signal, avoids rate-limit hammering).
    """
    all_headlines = []

    for source in FEED_SOURCES:
        if len(all_headlines) >= 40:
            break

        entries_collected = []
        for url in source["urls"]:
            entries = _fetch_feed(url)
            if entries:
                entries_collected = entries[: source["max_items"]]
                print(f"  ✅ {source['name']}: {len(entries_collected)} headlines via {url}")
                break
            time.sleep(0.3)  # small polite delay between URL attempts

        if not entries_collected:
            print(f"  ⚠  {source['name']}: all URLs failed or returned no data")

        for entry in entries_collected:
            title   = entry.get("title", "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", entry.get("description", "")))
            if title:
                all_headlines.append({
                    "source":  source["name"],
                    "title":   title,
                    "summary": summary[:300],
                })

    return all_headlines


def _score_headline(title: str, summary: str) -> tuple[int, list, list]:
    """
    Return (net_score, bullish_triggers, bearish_triggers) for a single headline.
    Uses weighted keyword matching on combined title + summary.
    """
    text = (title + " " + summary).lower()

    bull_score   = 0
    bear_score   = 0
    bull_hits    = []
    bear_hits    = []

    for phrase, weight in BULLISH_SIGNALS.items():
        if phrase in text:
            bull_score += weight
            bull_hits.append(phrase)

    for phrase, weight in BEARISH_SIGNALS.items():
        if phrase in text:
            bear_score += weight
            bear_hits.append(phrase)

    return (bull_score - bear_score), bull_hits, bear_hits


def _is_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(asset in text for asset in RELEVANT_ASSETS)


# ── Economic Calendar Context (static, updated quarterly) ────────────────────
# Provides the CIO with the upcoming macro catalyst schedule even when live
# feeds are sparse.  Update this block each quarter.

ECONOMIC_CALENDAR = [
    {"event": "FOMC Rate Decision",         "date": "May 7, 2026",  "impact": "CRITICAL"},
    {"event": "US CPI (Apr)",               "date": "May 13, 2026", "impact": "HIGH"},
    {"event": "US Non-Farm Payrolls",        "date": "May 1, 2026",  "impact": "HIGH"},
    {"event": "ECB Rate Decision",           "date": "June 5, 2026", "impact": "MEDIUM"},
    {"event": "US PPI (Apr)",               "date": "May 14, 2026", "impact": "MEDIUM"},
    {"event": "Fed Chair Powell Speech",     "date": "May 21, 2026", "impact": "HIGH"},
]

# ── Sovereign Reserves (updated from WGC data, Q1 2026) ──────────────────────

SOVEREIGN_RESERVES = [
    {"country": "United States",      "tonnes": 8133.5,  "status": "Holding",                          "yoy_change": "0%"},
    {"country": "Germany",            "tonnes": 3352.6,  "status": "Holding",                          "yoy_change": "0%"},
    {"country": "China (PBoC)",       "tonnes": 2279.6,  "status": "Strategic Accumulation",           "yoy_change": "+0.8%"},
    {"country": "Russian Federation", "tonnes": 2335.9,  "status": "Accumulating (Sanction Evasion)",  "yoy_change": "+1.2%"},
    {"country": "India (RBI)",        "tonnes": 853.6,   "status": "Active Buying",                    "yoy_change": "+3.9%"},
    {"country": "Turkey",             "tonnes": 612.4,   "status": "Active Buying",                    "yoy_change": "+5.1%"},
    {"country": "Poland",             "tonnes": 448.2,   "status": "Active Buying",                    "yoy_change": "+9.4%"},
    {"country": "Japan (BoJ)",        "tonnes": 845.9,   "status": "Holding",                          "yoy_change": "0%"},
]

# ── Main Tool ─────────────────────────────────────────────────────────────────

@tool("Macro_News_and_Reserves_Analyzer")
def scrape_fundamental_news() -> str:
    """
    Acts as a Global News Desk. Aggregates live financial news from multiple
    global syndicates using browser-spoofed HTTP requests, calculates weighted
    sentiment scores for precious metals and energy, and tracks sovereign central
    bank gold reserves to establish the macro floor for the CIO.
    """
    print("\n" + "=" * 70)
    print("GLOBAL NEWS DESK — Aggregating Macro Context (v2)")
    print("=" * 70)

    # ── 1. Scrape ─────────────────────────────────────────────────────────
    raw_headlines = _scrape_sources()
    print(f"\n  Total raw headlines collected: {len(raw_headlines)}")

    # ── 2. Filter & Score ─────────────────────────────────────────────────
    relevant_news   = []
    sentiment_score = 0

    for item in raw_headlines:
        if not _is_relevant(item["title"], item["summary"]):
            continue

        score, bull_hits, bear_hits = _score_headline(item["title"], item["summary"])
        sentiment_score += score

        item["score"]      = score
        item["bull_hits"]  = bull_hits
        item["bear_hits"]  = bear_hits
        item["sentiment"]  = (
            "STRONGLY BULLISH" if score >= 3
            else "BULLISH"     if score > 0
            else "BEARISH"     if score < 0
            else "NEUTRAL"
        )
        relevant_news.append(item)

    # Sort by absolute impact (strongest signals first)
    relevant_news.sort(key=lambda x: abs(x["score"]), reverse=True)
    top_news = relevant_news[:12]

    # ── 3. Overall bias ───────────────────────────────────────────────────
    overall_bias = (
        "STRONGLY BULLISH" if sentiment_score >= 5
        else "BULLISH"     if sentiment_score >= 1
        else "STRONGLY BEARISH" if sentiment_score <= -5
        else "BEARISH"     if sentiment_score < 0
        else "NEUTRAL"
    )

    bullish_count = sum(1 for n in top_news if n["score"] > 0)
    bearish_count = sum(1 for n in top_news if n["score"] < 0)

    # ── 4. Build Output ───────────────────────────────────────────────────
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    out = []

    out.append(f"GLOBAL MACRO & FUNDAMENTAL REPORT — v2")
    out.append(f"Generated : {ts}")
    out.append(f"Feed hits : {len(raw_headlines)} raw | {len(relevant_news)} relevant | {len(top_news)} displayed")
    out.append("")

    out.append(f"{'=' * 60}")
    out.append(f"OVERALL SENTIMENT: {overall_bias}  (Score: {sentiment_score:+d})")
    out.append(f"Breakdown  — Bullish headlines: {bullish_count} | Bearish: {bearish_count}")
    out.append(f"{'=' * 60}")
    out.append("")

    if top_news:
        out.append("=== TOP MACRO HEADLINES (by impact weight) ===")
        for idx, news in enumerate(top_news, 1):
            out.append(
                f"{idx:>2}. [{news['source']}] {news['title']}"
            )
            if news["bull_hits"]:
                out.append(f"    🟢 Bullish drivers : {', '.join(news['bull_hits'])}")
            if news["bear_hits"]:
                out.append(f"    🔴 Bearish drivers : {', '.join(news['bear_hits'])}")
            out.append(f"    Sentiment Vector  : {news['sentiment']}  (Score: {news['score']:+d})")
            out.append("")
    else:
        out.append("=== TOP MACRO HEADLINES ===")
        out.append(
            "⚠  No relevant headlines retrieved from live feeds. "
            "All sources may be rate-limiting. Sovereign reserve data and "
            "economic calendar context are still valid inputs for the CIO."
        )
        out.append("")

    out.append("=== UPCOMING HIGH-IMPACT EVENTS (Economic Calendar) ===")
    for ev in ECONOMIC_CALENDAR:
        out.append(f"  [{ev['impact']:8s}] {ev['date']:<18} — {ev['event']}")
    out.append("")

    out.append("=== SOVEREIGN GOLD RESERVE TRACKER (WGC Q1 2026) ===")
    for r in SOVEREIGN_RESERVES:
        out.append(
            f"  {r['country']:<25} {r['tonnes']:>7,.1f}t  "
            f"YoY: {r['yoy_change']:>6}  |  {r['status']}"
        )
    out.append("")

    # Structural narrative for the CIO regardless of live feed availability
    accumulating = [r for r in SOVEREIGN_RESERVES if "Buying" in r["status"] or "Accumulation" in r["status"]]
    total_accumulating_tonnes = sum(r["tonnes"] for r in accumulating)
    out.append("=== CENTRAL BANK STRUCTURAL NARRATIVE ===")
    out.append(
        f"  {len(accumulating)} sovereigns are actively accumulating gold "
        f"({total_accumulating_tonnes:,.1f}t combined reserves). "
        "This represents structural, price-insensitive demand that acts as a "
        "fundamental floor against short-term technical weakness."
    )
    out.append(
        "  Key driver: De-dollarization thesis intact. China (+0.8% YoY), "
        "India (+3.9%), Turkey (+5.1%), and Poland (+9.4%) continue to "
        "diversify FX reserves aggressively into physical gold."
    )

    return "\n".join(out)