# app.py — TrackGold Institutional Terminal v3
# Full backend with all institutional endpoints:
#   /api/gold-price         — live spot price (GC=F with fallbacks)
#   /api/market-data        — Gold + Silver + WTI + DXY + TNX (10yr yield)
#   /api/technical-indicators — full indicator suite (SMA/EMA/RSI/MACD/BB/ATR/Stoch/OBV)
#   /api/smart-money        — Volume POC, ATR execution levels, liquidity sweep status
#   /api/macro-news         — multi-source RSS with weighted sentiment scoring
#   /api/central-banks      — WGC reserve data + YoY accumulation tracking
#   /api/local-prices       — XAU in INR/EUR/GBP/JPY/CNY/AUD via FX cross
#   /api/chart-data         — OHLCV + overlay indicators for Plotly
#   /api/correlation-matrix — rolling 30d correlation between Gold/Silver/WTI/DXY
#   /api/economic-calendar  — upcoming high-impact macro events
#   /api/regime-signals     — market regime (inflation, risk-off, risk-on, stagflation)
#   /api/start-analysis     — trigger CrewAI mandate generation
#   /api/analysis-status    — poll CrewAI progress

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from crew import TrackGoldTerminal
from datetime import datetime
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objs as go
import plotly.utils
import threading
import requests
import feedparser
import json
import os
import time
import re

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────────────────────
analysis_status = {
    'running': False, 'progress': 0, 'message': '',
    'result': None, 'error': None, 'parsed_data': None
}

_caches = {}   # { key: {'data': ..., 'ts': datetime } }

def _cache_get(key, ttl_seconds):
    entry = _caches.get(key)
    if entry and (datetime.now() - entry['ts']).total_seconds() < ttl_seconds:
        return entry['data']
    return None

def _cache_set(key, data):
    _caches[key] = {'data': data, 'ts': datetime.now()}
    return data

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────────────────────────────────────
# PRICE FETCHING
# ─────────────────────────────────────────────────────────────────────────────
def _yf_history(symbol, period="5d", interval="1d"):
    try:
        ticker = yf.Ticker(symbol)
        time.sleep(0.2)
        df = ticker.history(period=period, interval=interval, timeout=12)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    return None

def fetch_gold_price_robust():
    symbols = [
        ("GC=F",     "Gold Futures (COMEX)",  1),
        ("XAUUSD=X", "Gold Spot USD",         1),
        ("GLD",      "Gold ETF (SPDR)",       10),
    ]
    for symbol, desc, mult in symbols:
        df = _yf_history(symbol)
        if df is None or len(df) < 2:
            continue
        cur  = float(df['Close'].iloc[-1]) * mult
        prev = float(df['Close'].iloc[-2]) * mult
        if not (500 < cur < 15000):
            continue
        chg     = cur - prev
        chg_pct = (chg / prev * 100) if prev else 0
        return {
            'price':      round(cur, 2),
            'change':     round(chg, 2),
            'change_pct': round(chg_pct, 2),
            'source':     f"{symbol}",
            'market_open': datetime.now().weekday() < 5,
        }
    return None

def get_gold_price():
    cached = _cache_get('gold_price', 60)
    if cached:
        return cached
    data = fetch_gold_price_robust()
    if data:
        return _cache_set('gold_price', data)
    return _caches.get('gold_price', {}).get('data') or {'price': None, 'change': 0, 'change_pct': 0, 'source': 'unavailable'}

@app.route('/api/gold-price')
def api_gold_price():
    try:
        d = get_gold_price()
        return jsonify({'success': True, **d, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ASSET MARKET DATA  (Gold / Silver / WTI / DXY / TNX)
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/api/market-data')
def api_market_data():
    cached = _cache_get('market_data', 30)
    if cached:
        return jsonify({'success': True, **cached})

    ASSETS = {
        'Gold':    ('GC=F',  1),
        'Silver':  ('SI=F',  1),
        'WTI':     ('CL=F',  1),
        'DXY':     ('DX-Y.NYB', 1),   # US Dollar Index
        'TNX':     ('^TNX',  1),       # 10-yr Treasury Yield
        'Platinum':('PL=F',  1),
        'Copper':  ('HG=F',  1),
    }
    results = {}
    for name, (sym, mult) in ASSETS.items():
        df = _yf_history(sym)
        if df is not None and len(df) >= 2:
            cur  = float(df['Close'].iloc[-1]) * mult
            prev = float(df['Close'].iloc[-2]) * mult
            chg  = cur - prev
            results[name] = {
                'price':      round(cur, 4),
                'change':     round(chg, 4),
                'change_pct': round((chg / prev * 100) if prev else 0, 2),
                'symbol':     sym,
            }

    # Derived ratios
    if 'Gold' in results and 'Silver' in results:
        results['GoldSilverRatio'] = round(results['Gold']['price'] / results['Silver']['price'], 2)
    if 'Gold' in results and 'Copper' in results:
        results['GoldCopperRatio'] = round(results['Gold']['price'] / results['Copper']['price'], 2)

    payload = {'data': results, 'timestamp': datetime.now().isoformat()}
    _cache_set('market_data', payload)
    return jsonify({'success': True, **payload})

# ─────────────────────────────────────────────────────────────────────────────
# FULL TECHNICAL INDICATOR SUITE
# ─────────────────────────────────────────────────────────────────────────────
def compute_full_indicators(df):
    close = df['Close']
    high  = df['High']
    low   = df['Low']
    vol   = df['Volume']
    ind   = {}

    # ── Moving Averages ───────────────────────────────────────────────────
    for period in [10, 20, 50, 100, 200]:
        if len(df) >= period:
            ind[f'sma_{period}'] = round(float(close.rolling(period).mean().iloc[-1]), 2)
    for span in [9, 21, 55]:
        if len(df) >= span:
            ind[f'ema_{span}'] = round(float(close.ewm(span=span, adjust=False).mean().iloc[-1]), 2)

    cur = float(close.iloc[-1])
    ind['current_price'] = round(cur, 2)

    # ── RSI (14) ──────────────────────────────────────────────────────────
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_g = gains.ewm(com=13, min_periods=14).mean()
    avg_l = losses.ewm(com=13, min_periods=14).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    rsi   = (100 - (100 / (1 + rs))).iloc[-1]
    ind['rsi'] = round(float(rsi), 2)
    ind['rsi_signal'] = 'OVERBOUGHT' if rsi > 70 else 'OVERSOLD' if rsi < 30 else 'NEUTRAL'

    # ── Stochastic RSI ────────────────────────────────────────────────────
    if len(df) >= 28:
        rsi_series = 100 - (100 / (1 + rs))
        rsi_min = rsi_series.rolling(14).min()
        rsi_max = rsi_series.rolling(14).max()
        stoch_rsi_k = ((rsi_series - rsi_min) / (rsi_max - rsi_min + 1e-10) * 100)
        stoch_rsi_d = stoch_rsi_k.rolling(3).mean()
        ind['stoch_rsi_k'] = round(float(stoch_rsi_k.iloc[-1]), 2)
        ind['stoch_rsi_d'] = round(float(stoch_rsi_d.iloc[-1]), 2)

    # ── MACD (12/26/9) ────────────────────────────────────────────────────
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    ind['macd']          = round(float(macd.iloc[-1]), 2)
    ind['macd_signal']   = round(float(signal.iloc[-1]), 2)
    ind['macd_hist']     = round(float(hist.iloc[-1]), 2)
    ind['macd_bullish']  = bool(macd.iloc[-1] > signal.iloc[-1])
    # Histogram direction (momentum acceleration)
    ind['macd_accelerating'] = bool(abs(hist.iloc[-1]) > abs(hist.iloc[-2])) if len(df) > 1 else False

    # ── Bollinger Bands (20, 2σ) ──────────────────────────────────────────
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_up  = bb_mid + 2 * bb_std
    bb_lo  = bb_mid - 2 * bb_std
    ind['bb_upper']  = round(float(bb_up.iloc[-1]), 2)
    ind['bb_middle'] = round(float(bb_mid.iloc[-1]), 2)
    ind['bb_lower']  = round(float(bb_lo.iloc[-1]), 2)
    bb_width = (bb_up.iloc[-1] - bb_lo.iloc[-1]) / bb_mid.iloc[-1] * 100
    ind['bb_width']  = round(float(bb_width), 2)
    ind['bb_pct_b']  = round(float((cur - bb_lo.iloc[-1]) / (bb_up.iloc[-1] - bb_lo.iloc[-1] + 1e-10) * 100), 2)

    # ── ATR & Volatility ──────────────────────────────────────────────────
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    ind['atr']         = round(float(atr.iloc[-1]), 2)
    ind['atr_pct']     = round(float(atr.iloc[-1] / cur * 100), 2)
    ind['dynamic_stop']   = round(cur - 2.0 * float(atr.iloc[-1]), 2)
    ind['dynamic_target'] = round(cur + 3.0 * float(atr.iloc[-1]), 2)

    # ── Keltner Channels ──────────────────────────────────────────────────
    if len(df) >= 20:
        kc_mid = close.ewm(span=20, adjust=False).mean()
        ind['kc_upper'] = round(float((kc_mid + 2 * atr).iloc[-1]), 2)
        ind['kc_lower'] = round(float((kc_mid - 2 * atr).iloc[-1]), 2)
        # Squeeze: BB inside Keltner = low volatility before big move
        ind['squeeze_active'] = bool(
            ind['bb_upper'] < ind['kc_upper'] and
            ind['bb_lower'] > ind['kc_lower']
        )

    # ── OBV (On-Balance Volume) ───────────────────────────────────────────
    if vol.sum() > 0:
        obv   = (np.sign(close.diff()) * vol).fillna(0).cumsum()
        obv_m = obv.rolling(20).mean()
        ind['obv_trend'] = 'UP' if float(obv.iloc[-1]) > float(obv_m.iloc[-1]) else 'DOWN'

    # ── Support / Resistance ──────────────────────────────────────────────
    ind['resistance_60d'] = round(float(high.tail(60).max()), 2)
    ind['support_60d']    = round(float(low.tail(60).min()), 2)
    ind['resistance_20d'] = round(float(high.tail(20).max()), 2)
    ind['support_20d']    = round(float(low.tail(20).min()), 2)

    # ── Volume POC (90-day) ───────────────────────────────────────────────
    if len(df) >= 30:
        try:
            recent = df.tail(90).copy()
            bins   = np.linspace(float(recent['Low'].min()), float(recent['High'].max()), 15)
            recent['_bin'] = pd.cut(recent['Close'], bins=bins)
            poc = recent.groupby('_bin', observed=False)['Volume'].sum().idxmax().mid
            ind['poc_90d']        = round(float(poc), 2)
            ind['poc_relation']   = 'ABOVE' if cur > poc else 'BELOW'
        except Exception:
            pass

    # ── Trend Strength ────────────────────────────────────────────────────
    sma10  = ind.get('sma_10')
    sma50  = ind.get('sma_50')
    sma200 = ind.get('sma_200')
    if sma10 and sma50 and sma200:
        if cur > sma10 > sma50 > sma200:
            ind['trend'] = 'STRONG_UP'
        elif cur > sma50 and sma50 > sma200:
            ind['trend'] = 'UP'
        elif cur < sma10 < sma50 < sma200:
            ind['trend'] = 'STRONG_DOWN'
        elif cur < sma50 and sma50 < sma200:
            ind['trend'] = 'DOWN'
        else:
            ind['trend'] = 'CONSOLIDATING'
    else:
        ind['trend'] = 'NEUTRAL'

    # ── Golden / Death Cross ──────────────────────────────────────────────
    if sma50 and sma200:
        ind['golden_cross'] = bool(sma50 > sma200)
        prev_sma50  = float(close.rolling(50).mean().iloc[-5]) if len(df) >= 55 else sma50
        prev_sma200 = float(close.rolling(200).mean().iloc[-5]) if len(df) >= 205 else sma200
        ind['cross_recent'] = bool(
            (sma50 > sma200 and prev_sma50 <= prev_sma200) or
            (sma50 < sma200 and prev_sma50 >= prev_sma200)
        )

    # ── RSI Divergence ────────────────────────────────────────────────────
    if len(df) >= 14:
        price_trend = float(close.iloc[-1]) - float(close.iloc[-10])
        rsi_s       = 100 - (100 / (1 + rs))
        rsi_trend   = float(rsi_s.iloc[-1]) - float(rsi_s.iloc[-10])
        if price_trend > 0 and rsi_trend < -5:
            ind['divergence'] = 'BEARISH'
        elif price_trend < 0 and rsi_trend > 5:
            ind['divergence'] = 'BULLISH'
        else:
            ind['divergence'] = 'NONE'

    return ind

@app.route('/api/technical-indicators')
def api_technical_indicators():
    cached = _cache_get('tech_indicators', 300)
    if cached:
        return jsonify({'success': True, 'indicators': cached})
    try:
        df = _yf_history("GC=F", period="1y")
        if df is not None and len(df) >= 50:
            ind = compute_full_indicators(df)
            _cache_set('tech_indicators', ind)
            return jsonify({'success': True, 'indicators': ind})
        return jsonify({'success': False, 'error': 'Insufficient data'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# SMART MONEY / INSTITUTIONAL POSITIONING
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/api/smart-money')
def api_smart_money():
    cached = _cache_get('smart_money', 300)
    if cached:
        return jsonify({'success': True, **cached})
    try:
        df  = _yf_history("GC=F", period="90d")
        df2 = _yf_history("SI=F", period="5d")
        if df is None or len(df) < 30:
            return jsonify({'success': False, 'error': 'Insufficient data'}), 500

        cur = float(df['Close'].iloc[-1])
        tr  = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['Close'].shift()).abs(),
            (df['Low']  - df['Close'].shift()).abs()
        ], axis=1).max(axis=1)
        atr = float(tr.ewm(span=14, adjust=False).mean().iloc[-1])

        bins = np.linspace(float(df['Low'].min()), float(df['High'].max()), 15)
        df_c = df.copy()
        df_c['_b'] = pd.cut(df_c['Close'], bins=bins)
        poc  = float(df_c.groupby('_b', observed=False)['Volume'].sum().idxmax().mid)

        # Value Area (70% of volume)
        vp = df_c.groupby('_b', observed=False)['Volume'].sum().sort_values(ascending=False)
        total_vol = vp.sum()
        cum       = 0
        va_bins   = []
        for b, v in vp.items():
            cum += v
            va_bins.append(b)
            if cum >= total_vol * 0.7:
                break
        va_mids   = [b.mid for b in va_bins]
        vah = round(max(va_mids), 2)   # Value Area High
        val = round(min(va_mids), 2)   # Value Area Low

        # Liquidity sweep detection
        recent_low  = float(df['Low'].tail(5).min())
        recent_high = float(df['High'].tail(5).max())
        prev_low    = float(df['Low'].iloc[-20:-5].min()) if len(df) > 20 else recent_low
        prev_high   = float(df['High'].iloc[-20:-5].max()) if len(df) > 20 else recent_high

        sweep = 'NONE'
        if recent_low < prev_low and cur > prev_low:
            sweep = 'BULLISH_SWEEP'   # swept lows then reclaimed
        elif recent_high > prev_high and cur < prev_high:
            sweep = 'BEARISH_SWEEP'

        payload = {
            'current_price': round(cur, 2),
            'poc':           round(poc, 2),
            'vah':           vah,
            'val':           val,
            'poc_relation':  'ABOVE' if cur > poc else 'BELOW',
            'atr':           round(atr, 2),
            'atr_pct':       round(atr / cur * 100, 2),
            'floor':         round(cur - 2.0 * atr, 2),
            'target':        round(cur + 3.0 * atr, 2),
            'tight_stop':    round(cur - 1.0 * atr, 2),
            'liquidity_sweep': sweep,
            'vol_risk':      'HIGH' if atr / cur * 100 > 1.5 else 'MODERATE' if atr / cur * 100 > 0.8 else 'LOW',
        }
        _cache_set('smart_money', payload)
        return jsonify({'success': True, **payload})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# MACRO NEWS + SENTIMENT ENGINE (v2 — multi-source with weighted scoring)
# ─────────────────────────────────────────────────────────────────────────────
BULLISH_W = {
    'war': 2, 'conflict': 2, 'escalation': 2, 'geopolitical': 2, 'sanction': 1,
    'crisis': 1, 'recession': 1, 'stagflation': 2, 'rate cut': 2, 'dovish': 2,
    'pivot': 2, 'pause': 1, 'stimulus': 2, 'qe': 1, 'inflation': 1, 'shortage': 1,
    'central bank buying': 3, 'de-dollarization': 3, 'gold reserves': 2,
    'weak dollar': 2, 'dollar falls': 2, 'safe haven': 2, 'flight to safety': 2,
    'risk off': 2, 'uncertainty': 1, 'debt ceiling': 1, 'deficit': 1,
}
BEARISH_W = {
    'rate hike': 2, 'hawkish': 2, 'tightening': 1, 'tapering': 1, 'qt': 1,
    'strong dollar': 2, 'dollar surges': 2, 'dollar rallies': 2, 'dxy rises': 2,
    'peace': 1, 'ceasefire': 1, 'risk on': 1, 'cooling inflation': 2,
    'disinflation': 2, 'cpi falls': 2, 'inflation slows': 2, 'yields rise': 1,
    'yields surge': 2, 'real yields': 1, 'profit taking': 1, 'outflows': 1,
}
RELEVANT_ASSETS = [
    'gold', 'silver', 'xau', 'precious metal', 'oil', 'crude', 'brent', 'wti',
    'fed', 'fomc', 'federal reserve', 'powell', 'dollar', 'usd', 'dxy',
    'yield', 'treasury', 'bond', 'inflation', 'cpi', 'pce', 'rate',
    'china', 'pboc', 'india', 'rbi', 'geopolit', 'sanction', 'war',
]
FEED_SOURCES = [
    {'name': 'Kitco',       'urls': ['https://www.kitco.com/rss/kitco-news.xml',
                                     'https://www.kitco.com/news/rss/precious_metals.xml'], 'max': 8},
    {'name': 'MarketWatch', 'urls': ['https://feeds.marketwatch.com/marketwatch/marketpulse/',
                                     'https://feeds.marketwatch.com/marketwatch/topstories/'], 'max': 6},
    {'name': 'FXStreet',    'urls': ['https://www.fxstreet.com/rss/news',
                                     'https://www.fxstreet.com/rss/analysis'], 'max': 6},
    {'name': 'Reuters',     'urls': ['https://feeds.reuters.com/reuters/businessNews'], 'max': 6},
    {'name': 'Investing.com','urls': ['https://www.investing.com/rss/news_11.rss',
                                      'https://www.investing.com/rss/news_1.rss'],  'max': 5},
]

def _fetch_rss(url):
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        if resp.status_code == 200:
            p = feedparser.parse(resp.text)
            return p.entries if p.entries else []
    except Exception:
        pass
    return []

def _scrape_all_feeds():
    headlines = []
    for src in FEED_SOURCES:
        if len(headlines) >= 50:
            break
        for url in src['urls']:
            entries = _fetch_rss(url)
            if entries:
                for e in entries[:src['max']]:
                    title   = e.get('title', '').strip()
                    summary = re.sub(r'<[^>]+>', '', e.get('summary', e.get('description', '')))
                    if title:
                        headlines.append({'source': src['name'], 'title': title, 'summary': summary[:300]})
                break
    return headlines

@app.route('/api/macro-news')
def api_macro_news():
    cached = _cache_get('macro_news', 300)
    if cached:
        return jsonify({'success': True, **cached})

    raw        = _scrape_all_feeds()
    relevant   = []
    total_score = 0

    for item in raw:
        text = (item['title'] + ' ' + item['summary']).lower()
        if not any(a in text for a in RELEVANT_ASSETS):
            continue
        bs = sum(w for p, w in BULLISH_W.items() if p in text)
        br = sum(w for p, w in BEARISH_W.items() if p in text)
        sc = bs - br
        total_score += sc
        item['score']     = sc
        item['bull_hits'] = [p for p in BULLISH_W if p in text]
        item['bear_hits'] = [p for p in BEARISH_W if p in text]
        item['sentiment'] = ('STRONGLY BULLISH' if sc >= 3 else 'BULLISH' if sc > 0
                             else 'STRONGLY BEARISH' if sc <= -3 else 'BEARISH' if sc < 0
                             else 'NEUTRAL')
        relevant.append(item)

    relevant.sort(key=lambda x: abs(x['score']), reverse=True)
    top = relevant[:12]

    overall = ('STRONGLY BULLISH' if total_score >= 5 else 'BULLISH' if total_score >= 1
               else 'STRONGLY BEARISH' if total_score <= -5 else 'BEARISH' if total_score < 0
               else 'NEUTRAL')
    gauge = max(0, min(100, 50 + total_score * 8))

    payload = {
        'score':    total_score,
        'overall':  overall,
        'gauge':    gauge,
        'headlines': top,
        'raw_count': len(raw),
        'relevant_count': len(relevant),
        'timestamp': datetime.now().isoformat(),
    }
    _cache_set('macro_news', payload)
    return jsonify({'success': True, **payload})

# ─────────────────────────────────────────────────────────────────────────────
# CENTRAL BANKS + SOVEREIGN RESERVES
# ─────────────────────────────────────────────────────────────────────────────
SOVEREIGN_RESERVES = [
    {'country': 'United States',      'flag': '🇺🇸', 'tonnes': 8133.5,  'pct_reserves': 72.4, 'status': 'Holding',                          'yoy': '0.0%'},
    {'country': 'Germany',            'flag': '🇩🇪', 'tonnes': 3352.6,  'pct_reserves': 68.4, 'status': 'Holding',                          'yoy': '0.0%'},
    {'country': 'Italy',              'flag': '🇮🇹', 'tonnes': 2451.8,  'pct_reserves': 63.4, 'status': 'Holding',                          'yoy': '0.0%'},
    {'country': 'China (PBoC)',       'flag': '🇨🇳', 'tonnes': 2279.6,  'pct_reserves': 4.6,  'status': 'Strategic Accumulation',           'yoy': '+0.8%'},
    {'country': 'Russian Federation', 'flag': '🇷🇺', 'tonnes': 2335.9,  'pct_reserves': 27.1, 'status': 'Accumulating (Sanction Evasion)',  'yoy': '+1.2%'},
    {'country': 'Switzerland',        'flag': '🇨🇭', 'tonnes': 1040.0,  'pct_reserves': 7.0,  'status': 'Holding',                          'yoy': '0.0%'},
    {'country': 'Japan (BoJ)',         'flag': '🇯🇵', 'tonnes': 845.9,   'pct_reserves': 4.3,  'status': 'Holding',                          'yoy': '0.0%'},
    {'country': 'India (RBI)',        'flag': '🇮🇳', 'tonnes': 853.6,   'pct_reserves': 9.2,  'status': 'Active Buying',                    'yoy': '+3.9%'},
    {'country': 'Turkey',             'flag': '🇹🇷', 'tonnes': 612.4,   'pct_reserves': 33.4, 'status': 'Active Buying',                    'yoy': '+5.1%'},
    {'country': 'Poland',             'flag': '🇵🇱', 'tonnes': 448.2,   'pct_reserves': 15.3, 'status': 'Active Buying',                    'yoy': '+9.4%'},
]

@app.route('/api/central-banks')
def api_central_banks():
    cached = _cache_get('central_banks', 3600)
    if cached:
        return jsonify({'success': True, **cached})

    # Try WGC feed with browser headers
    wgc_news = []
    try:
        resp = requests.get('https://www.gold.org/goldhub/rss.xml', headers=BROWSER_HEADERS, timeout=8)
        if resp.status_code == 200:
            feed = feedparser.parse(resp.text)
            wgc_news = [{'title': e.get('title', ''), 'link': e.get('link', ''), 'published': e.get('published', '')}
                        for e in feed.entries[:6]]
    except Exception:
        pass

    payload = {
        'major_holders': SOVEREIGN_RESERVES,
        'wgc_news':      wgc_news,
        'timestamp':     datetime.now().isoformat(),
        'accumulating_count':  sum(1 for r in SOVEREIGN_RESERVES if 'Buying' in r['status'] or 'Accumulation' in r['status']),
        'total_tracked_tonnes': sum(r['tonnes'] for r in SOVEREIGN_RESERVES),
    }
    _cache_set('central_banks', payload)
    return jsonify({'success': True, **payload})

# ─────────────────────────────────────────────────────────────────────────────
# LOCAL / MULTI-CURRENCY XAU PRICES  (FX cross via yfinance)
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/api/local-prices')
def api_local_prices():
    cached = _cache_get('local_prices', 120)
    if cached:
        return jsonify({'success': True, **cached})

    # Get USD base price
    base = fetch_gold_price_robust()
    if not base or not base['price']:
        return jsonify({'success': False, 'error': 'Base price unavailable'}), 500

    usd_price = base['price']
    prices    = {'USD': {'price': usd_price, 'symbol': '$', 'live': True}}

    # FX pairs: try direct XAU cross first, fall back to FX rate × USD price
    FX = {
        'INR': ('XAUINR=X', 'INR=X', '₹'),
        'EUR': ('XAUEUR=X', 'EURUSD=X', '€'),
        'GBP': ('XAUGBP=X', 'GBPUSD=X', '£'),
        'JPY': ('XAUJPY=X', 'JPY=X',   '¥'),
        'CNY': ('XAUCNY=X', 'CNY=X',   '¥'),
        'AUD': ('XAUAUD=X', 'AUDUSD=X','A$'),
        'CHF': ('XAUCHF=X', 'CHFUSD=X','Fr'),
    }
    for cur, (xau_sym, fx_sym, sym_icon) in FX.items():
        price = None
        try:
            df = _yf_history(xau_sym, period="2d")
            if df is not None and len(df) > 0:
                price = round(float(df['Close'].iloc[-1]), 2)
        except Exception:
            pass

        if price is None:
            try:
                df = _yf_history(fx_sym, period="2d")
                if df is not None and len(df) > 0:
                    rate = float(df['Close'].iloc[-1])
                    # For currencies quoted as USD/FOREIGN multiply; for FOREIGN/USD divide
                    if cur in ('EUR', 'GBP', 'AUD'):
                        price = round(usd_price / rate, 2)
                    else:
                        price = round(usd_price * rate, 2)
            except Exception:
                pass

        if price:
            prices[cur] = {'price': price, 'symbol': sym_icon, 'live': True}

    payload = {'prices': prices, 'timestamp': datetime.now().isoformat()}
    _cache_set('local_prices', payload)
    return jsonify({'success': True, **payload})

# ─────────────────────────────────────────────────────────────────────────────
# ROLLING CORRELATION MATRIX (Gold / Silver / WTI / DXY / TNX)
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/api/correlation-matrix')
def api_correlation():
    cached = _cache_get('correlation', 600)
    if cached:
        return jsonify({'success': True, **cached})
    try:
        SYMS = {'Gold': 'GC=F', 'Silver': 'SI=F', 'WTI': 'CL=F', 'DXY': 'DX-Y.NYB', 'TNX': '^TNX'}
        closes = {}
        for name, sym in SYMS.items():
            df = _yf_history(sym, period="3mo")
            if df is not None and len(df) > 30:
                closes[name] = df['Close']

        if len(closes) < 2:
            return jsonify({'success': False, 'error': 'Insufficient assets'}), 500

        master = pd.DataFrame(closes).dropna()
        corr   = master.corr().round(3)
        payload = {
            'matrix': corr.to_dict(),
            'assets': list(corr.columns),
            'window': '60d rolling',
            'timestamp': datetime.now().isoformat(),
        }
        _cache_set('correlation', payload)
        return jsonify({'success': True, **payload})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# MARKET REGIME SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/api/regime-signals')
def api_regime():
    cached = _cache_get('regime', 600)
    if cached:
        return jsonify({'success': True, **cached})
    try:
        gold_df = _yf_history("GC=F", period="90d")
        wti_df  = _yf_history("CL=F", period="90d")
        dxy_df  = _yf_history("DX-Y.NYB", period="90d")
        tnx_df  = _yf_history("^TNX",  period="90d")

        def pct_chg(df, n=20):
            if df is None or len(df) < n:
                return 0
            return round((float(df['Close'].iloc[-1]) / float(df['Close'].iloc[-n]) - 1) * 100, 2)

        gold_chg = pct_chg(gold_df)
        wti_chg  = pct_chg(wti_df)
        dxy_chg  = pct_chg(dxy_df)
        tnx_chg  = pct_chg(tnx_df)

        # Regime classification
        signals = []
        if wti_chg > 5 and gold_chg > 3:
            signals.append({'regime': 'STAGFLATION', 'color': 'red',    'desc': 'Rising energy + gold: cost-push inflation with stagnant growth'})
        if dxy_chg < -2 and gold_chg > 3:
            signals.append({'regime': 'DOLLAR FLIGHT', 'color': 'gold', 'desc': 'Dollar weakness driving safe-haven demand for gold'})
        if tnx_chg > 10 and gold_chg < 0:
            signals.append({'regime': 'YIELD PRESSURE', 'color': 'orange', 'desc': 'Rising real yields suppressing non-yielding gold'})
        if gold_chg > 5 and dxy_chg > 2:
            signals.append({'regime': 'CENTRAL BANK BID', 'color': 'green', 'desc': 'Gold rising despite strong dollar: institutional/sovereign buying'})
        if not signals:
            signals.append({'regime': 'NEUTRAL',  'color': 'gray', 'desc': 'No dominant macro regime signal detected'})

        payload = {
            'regime':    signals,
            'changes':   {'gold': gold_chg, 'wti': wti_chg, 'dxy': dxy_chg, 'tnx': tnx_chg},
            'window':    '20 trading days',
            'timestamp': datetime.now().isoformat(),
        }
        _cache_set('regime', payload)
        return jsonify({'success': True, **payload})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# ECONOMIC CALENDAR (static, update quarterly)
# ─────────────────────────────────────────────────────────────────────────────
ECON_CALENDAR = [
    {'event': 'FOMC Rate Decision',           'date': 'May 7, 2026',   'impact': 'CRITICAL', 'gold_bias': 'BULLISH if pause/cut, BEARISH if hike'},
    {'event': 'US Non-Farm Payrolls (Apr)',    'date': 'May 1, 2026',   'impact': 'HIGH',     'gold_bias': 'BEARISH if strong, BULLISH if weak'},
    {'event': 'US CPI (Apr)',                  'date': 'May 13, 2026',  'impact': 'HIGH',     'gold_bias': 'BULLISH if hot, BEARISH if cool'},
    {'event': 'US PPI (Apr)',                  'date': 'May 14, 2026',  'impact': 'MEDIUM',   'gold_bias': 'BULLISH if high, BEARISH if low'},
    {'event': 'Fed Chair Powell Speech',       'date': 'May 21, 2026',  'impact': 'HIGH',     'gold_bias': 'Hawkish = BEARISH, Dovish = BULLISH'},
    {'event': 'ECB Rate Decision',             'date': 'June 5, 2026',  'impact': 'MEDIUM',   'gold_bias': 'EUR strength = mild BULLISH gold'},
    {'event': 'US GDP Q1 Final',               'date': 'June 25, 2026', 'impact': 'MEDIUM',   'gold_bias': 'Weak GDP = BULLISH gold safe-haven'},
    {'event': 'Bank of Japan Meeting',         'date': 'June 16, 2026', 'impact': 'MEDIUM',   'gold_bias': 'Yield curve control changes matter'},
]

@app.route('/api/economic-calendar')
def api_economic_calendar():
    return jsonify({'success': True, 'events': ECON_CALENDAR, 'timestamp': datetime.now().isoformat()})

# ─────────────────────────────────────────────────────────────────────────────
# CHART DATA — OHLCV + OVERLAYS
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/api/chart-data')
def chart_data():
    period = request.args.get('period', '6mo')
    cache_key = f'chart_{period}'
    cached = _cache_get(cache_key, 300)
    if cached:
        return jsonify({'success': True, **cached})
    try:
        df = _yf_history("GC=F", period=period)
        if df is None or len(df) < 10:
            return jsonify({'success': False, 'error': 'No data'}), 500

        # ── Strip timezone ────────────────────────────────────────────────
        df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index

        # ── Indicators ────────────────────────────────────────────────────
        df['SMA10'] = df['Close'].rolling(10).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        bb_mid      = df['Close'].rolling(20).mean()
        bb_std      = df['Close'].rolling(20).std()
        bb_up       = bb_mid + 2 * bb_std
        bb_lo       = bb_mid - 2 * bb_std

        # ── NUMERICAL INDEX APPROACH ──────────────────────────────────────
        # Use plain integers (0, 1, 2, ..., n-1) as x-values. This gives us
        # absolute control: no calendar math, no gaps, no autorange surprises.
        # Custom tick labels show actual dates at thinned intervals.
        n     = len(df)
        xs    = list(range(n))  # [0, 1, 2, ..., n-1]
        dates = [d.strftime('%d %b') for d in df.index]  # "27 Apr"
        
        # Show ~10 date labels evenly spaced
        tick_step = max(1, n // 10)
        tick_positions = list(range(0, n, tick_step))
        tick_labels    = [dates[i] for i in tick_positions]

        # Y range: 7% padding so wicks don't clip
        y_lo = float(df['Low'].min())
        y_hi = float(df['High'].max())
        y_pad = (y_hi - y_lo) * 0.07
        y_min = y_lo - y_pad
        y_max = y_hi + y_pad

        fig = go.Figure()

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=xs,
            open=df['Open'].tolist(),
            high=df['High'].tolist(),
            low=df['Low'].tolist(),
            close=df['Close'].tolist(),
            text=dates,  # hover shows full date
            increasing_line_color='#3DBA7A',
            decreasing_line_color='#E05252',
            increasing_fillcolor='rgba(61,186,122,0.6)',
            decreasing_fillcolor='rgba(224,82,82,0.6)',
            name='Gold',
            showlegend=False,
        ))

        # Overlays
        fig.add_trace(go.Scatter(
            x=xs, y=df['SMA10'].tolist(), mode='lines', name='SMA10',
            line=dict(color='rgba(91,155,213,0.9)', width=1.5, dash='dot')))
        fig.add_trace(go.Scatter(
            x=xs, y=df['SMA50'].tolist(), mode='lines', name='SMA50',
            line=dict(color='rgba(201,168,76,1.0)', width=2.2)))
        fig.add_trace(go.Scatter(
            x=xs, y=df['EMA21'].tolist(), mode='lines', name='EMA21',
            line=dict(color='rgba(139,110,216,0.85)', width=1.5)))

        # Bollinger Bands
        fig.add_trace(go.Scatter(
            x=xs, y=bb_up.tolist(), mode='lines', name='BB Upper',
            line=dict(color='rgba(255,255,255,0.12)', width=1), showlegend=False))
        fig.add_trace(go.Scatter(
            x=xs, y=bb_lo.tolist(), mode='lines', name='BB Lower',
            line=dict(color='rgba(255,255,255,0.12)', width=1),
            fill='tonexty', fillcolor='rgba(255,255,255,0.04)', showlegend=False))

        fig.update_layout(
            template='plotly_dark',
            margin=dict(l=0, r=0, t=5, b=35),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis_rangeslider_visible=False,
            legend=dict(
                x=0.01, y=0.99,
                bgcolor='rgba(0,0,0,0)',
                font=dict(size=10, color='#8FA3B4'),
                orientation='h',
            ),
            xaxis=dict(
                range=[0, n - 1],
                tickmode='array',
                tickvals=tick_positions,
                ticktext=tick_labels,
                tickfont=dict(size=9, color='#5A6B7A'),
                gridcolor='rgba(255,255,255,0.05)',
                linecolor='rgba(255,255,255,0.08)',
                zeroline=False,
                showspikes=True,
                spikecolor='rgba(201,168,76,0.4)',
                spikethickness=1,
                spikedash='dot',
            ),
            yaxis=dict(
                range=[y_min, y_max],
                side='right',
                tickprefix='$',
                tickfont=dict(size=10, color='#5A6B7A'),
                gridcolor='rgba(255,255,255,0.05)',
                linecolor='rgba(255,255,255,0.08)',
                zeroline=False,
                showspikes=True,
                spikecolor='rgba(201,168,76,0.4)',
                spikethickness=1,
            ),
            hovermode='x unified',
            hoverlabel=dict(
                bgcolor='rgba(15,21,32,0.95)',
                bordercolor='rgba(201,168,76,0.35)',
                font=dict(size=11, family='DM Mono, monospace'),
            ),
        )

        payload = {
            'chart':  json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder),
            'symbol': 'GC=F',
            'points': len(df),
            'period': period,
            'y_range': [y_min, y_max],
        }
        _cache_set(cache_key, payload)
        return jsonify({'success': True, **payload})
    except Exception as e:
        import traceback
        print(f"Chart error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# CREWAI EXECUTION
# ─────────────────────────────────────────────────────────────────────────────
def run_analysis_async():
    global analysis_status
    try:
        analysis_status.update({
            'running': True, 'progress': 5,
            'message': 'Initializing Institutional Terminal…',
            'error': None, 'result': None
        })
        time.sleep(0.5)  # Let the UI catch the update
        
        print(f"\n{'='*70}")
        print(f"  TRACKGOLD: INSTITUTIONAL TERMINAL INITIALIZING")
        print(f"{'='*70}\n")
        
        terminal = TrackGoldTerminal()
        
        analysis_status.update({
            'progress': 20,
            'message': 'Quant Desk: fetching multi-asset technicals…'
        })
        
        # Run the crew with a reasonable timeout expectation
        result = terminal.kickoff()
        
        analysis_status.update({
            'progress': 95,
            'message': 'Finalizing mandate…'
        })
        
        # Save to file
        os.makedirs('reports', exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = f'reports/mandate_{ts}.md'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(str(result))
        
        analysis_status.update({
            'progress': 100,
            'message': 'Mandate complete.',
            'result': str(result)
        })
        
        print(f"\n✅ Institutional Analysis Complete.")
        
    except MemoryError as e:
        error_msg = "Memory limit exceeded — RSS feed response too large. Try again."
        print(f"\n❌ MemoryError: {error_msg}")
        analysis_status.update({
            'error': error_msg,
            'message': 'Analysis failed: memory error',
            'progress': 0
        })
    except Exception as e:
        error_msg = str(e)[:500]  # Truncate to prevent huge error strings
        print(f"\n❌ Analysis Error: {error_msg}")
        analysis_status.update({
            'error': error_msg,
            'message': f'Error: {error_msg[:100]}',
            'progress': 0
        })
    finally:
        analysis_status['running'] = False

@app.route('/api/start-analysis', methods=['POST'])
def start_analysis():
    global analysis_status
    if analysis_status['running']:
        return jsonify({'success': False, 'error': 'Analysis already running'}), 400
    # Reset state before starting
    analysis_status.update({
        'running': True, 'progress': 0, 'message': 'Starting…',
        'result': None, 'error': None, 'parsed_data': None
    })
    threading.Thread(target=run_analysis_async, daemon=True).start()
    return jsonify({'success': True})

@app.route('/api/analysis-status')
def get_analysis_status():
    return jsonify(analysis_status)

@app.route('/api/reset-analysis', methods=['POST'])
def reset_analysis():
    """Force-reset analysis state if it gets stuck."""
    global analysis_status
    analysis_status.update({
        'running': False, 'progress': 0, 'message': '',
        'result': None, 'error': None, 'parsed_data': None
    })
    return jsonify({'success': True, 'message': 'Analysis state reset'})

@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """Dev utility — bust all caches so new chart code takes effect immediately."""
    keys_to_clear = [k for k in _caches if k.startswith('chart_')]
    for k in keys_to_clear:
        del _caches[k]
    _caches.clear()
    return jsonify({'success': True, 'cleared': len(keys_to_clear) + 1})

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/')
def index():          return render_template('index.html')

@app.route('/dashboard')
def dashboard():      return render_template('dashboard.html')

@app.route('/analysis')
def analysis_page():  return render_template('analysis.html')

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  TRACKGOLD INSTITUTIONAL TERMINAL v3 — STARTING")
    print("=" * 70)
    os.makedirs('reports', exist_ok=True)

    # Prime the price cache on startup
    print("\n💰 FETCHING GOLD PRICE (real-time)")
    pd_init = fetch_gold_price_robust()
    if pd_init:
        _cache_set('gold_price', pd_init)
        print(f"✅ Live Price: ${pd_init['price']:.2f} | Source: {pd_init['source']}")
    print("=" * 70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))