# utils/price_fetcher.py - Robust gold price fetching utility
import yfinance as yf
from datetime import datetime
import time
from typing import Dict, Optional


class GoldPriceFetcher:
    """Handles gold price fetching with multiple symbols and fallback methods."""

    SYMBOLS = [
        ("GC=F", "Gold Futures (COMEX)", 1),
        ("XAUUSD=X", "Gold Spot USD", 1),
        ("GLD", "Gold ETF (SPDR)", 10),
    ]

    def __init__(self, cache_duration: int = 60):
        self.cache_duration = cache_duration
        self.cache: Dict = {
            'price': None, 'change': 0.0, 'change_pct': 0.0,
            'timestamp': None, 'method': None, 'symbol': None
        }

    def is_cache_valid(self) -> bool:
        if not self.cache.get('timestamp') or not self.cache.get('price'):
            return False
        return (datetime.now() - self.cache['timestamp']).total_seconds() < self.cache_duration

    def _fetch_via_history(self, symbol: str, period: str = "5d") -> Optional[Dict]:
        try:
            ticker = yf.Ticker(symbol)
            time.sleep(0.3)
            hist = ticker.history(period=period, interval="1d", timeout=10)
            if hist is None or len(hist) == 0:
                return None
            current = float(hist['Close'].iloc[-1])
            prev = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else current
            if current > 10:
                return {'current': current, 'previous': prev, 'method': 'history'}
        except Exception as e:
            print(f"  _history({symbol}): {e}")
        return None

    def _fetch_via_ticker_info(self, symbol: str) -> Optional[Dict]:
        try:
            ticker = yf.Ticker(symbol)
            time.sleep(0.3)
            info = ticker.info
            if not info or len(info) < 5:
                return None
            price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('price')
            prev = info.get('previousClose') or info.get('regularMarketPreviousClose')
            if price and float(price) > 10:
                return {'current': float(price), 'previous': float(prev) if prev else float(price), 'method': 'ticker.info'}
        except Exception as e:
            print(f"  _ticker_info({symbol}): {e}")
        return None

    def get_price(self, force_refresh: bool = False) -> Dict:
        """
        Get current gold price with automatic multi-source fallback.
        Returns dict: price, change, change_pct, timestamp, method, symbol
        """
        if not force_refresh and self.is_cache_valid():
            return self.cache

        for symbol, label, multiplier in self.SYMBOLS:
            print(f"Trying {label} ({symbol})...")
            for fetch_fn in [self._fetch_via_history, self._fetch_via_ticker_info]:
                result = fetch_fn(symbol)
                if not result:
                    continue
                current = result['current'] * multiplier
                prev = result['previous'] * multiplier
                if not (300 < current < 20000):
                    print(f"  Price ${current:.2f} out of expected range, skipping")
                    continue
                change = current - prev
                change_pct = (change / prev * 100) if prev > 0 else 0
                self.cache = {
                    'price': round(current, 2),
                    'change': round(change, 2),
                    'change_pct': round(change_pct, 2),
                    'timestamp': datetime.now(),
                    'method': result['method'],
                    'symbol': symbol
                }
                print(f"  ✅ ${current:.2f} via {symbol}/{result['method']}")
                return self.cache

        # All failed — return stale or fallback
        if self.cache.get('price'):
            print("⚠ Using stale cached price")
            self.cache['method'] = 'stale_cache'
            return self.cache

        print("⚠ Emergency fallback price")
        self.cache = {
            'price': 3300.00, 'change': 0.0, 'change_pct': 0.0,
            'timestamp': datetime.now(), 'method': 'emergency_fallback', 'symbol': None
        }
        return self.cache

    def get_historical_data(self, period: str = "6mo"):
        """Fetch historical OHLCV data for charting and indicator computation."""
        for symbol, label, multiplier in self.SYMBOLS:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period, interval="1d")
                if hist is None or len(hist) < 20:
                    continue
                for col in ['Open', 'High', 'Low', 'Close']:
                    hist[col] = hist[col] * multiplier
                # Attach SMAs
                hist['SMA_10'] = hist['Close'].rolling(10).mean()
                hist['SMA_20'] = hist['Close'].rolling(20).mean()
                hist['SMA_50'] = hist['Close'].rolling(50).mean()
                print(f"✓ Historical data: {len(hist)} days from {symbol}")
                return hist
            except Exception as e:
                print(f"Historical ({symbol}): {e}")
        return None