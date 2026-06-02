# tools/technical_tool.py
from crewai.tools import tool
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time

@tool("Multi_Asset_Technical_Engine")
def get_technical_signals() -> str:
    """
    Fetches real-time data for Gold, Silver, and WTI Crude Oil.
    Calculates Volume Profiles (Point of Control), Dynamic ATR stops, 
    RSI divergences, and the Gold/Silver Ratio to provide institutional-grade
    technical context for the macro-strategy agent.
    """
    
    assets = {
        "Gold": "GC=F",
        "Silver": "SI=F",
        "WTI_Crude": "CL=F"
    }
    
    print("\n" + "="*70)
    print("QUANTITATIVE TECHNICAL ENGINE — Fetching Multi-Asset Data")
    print("="*70)

    reports = []
    prices = {}

    for name, symbol in assets.items():
        print(f"\n  Processing {name} ({symbol})...")
        try:
            ticker = yf.Ticker(symbol)
            time.sleep(0.5)
            df = ticker.history(period="1y", interval="1d", timeout=20)
            
            if df is None or len(df) < 60:
                print(f"  [!] Insufficient data for {name}")
                continue

            current_price = float(df["Close"].iloc[-1])
            prices[name] = current_price
            close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]

            # Dynamic Volatility (ATR)
            tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.ewm(span=14, adjust=False).mean().iloc[-1])
            atr_pct = (atr / current_price) * 100
            dynamic_stop = current_price - (2.0 * atr)
            dynamic_target = current_price + (3.0 * atr)

            # Volume Profile (POC)
            recent_df = df.tail(90)
            bins = np.linspace(recent_df["Low"].min(), recent_df["High"].max(), 12)
            recent_df_copy = recent_df.copy()
            recent_df_copy['Price_Bin'] = pd.cut(recent_df_copy['Close'], bins=bins)
            volume_profile = recent_df_copy.groupby('Price_Bin', observed=False)['Volume'].sum()
            poc_price = volume_profile.idxmax().mid
            
            # Momentum
            delta = close.diff()
            gains = delta.clip(lower=0)
            losses = (-delta).clip(lower=0)
            avg_gain = gains.ewm(com=13, min_periods=14).mean()
            avg_loss = losses.ewm(com=13, min_periods=14).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            current_rsi = float(rsi.iloc[-1])
            
            # Divergence Check
            recent_price_trend = close.iloc[-1] - close.iloc[-10]
            recent_rsi_trend = rsi.iloc[-1] - rsi.iloc[-10]
            divergence_alert = "None"
            if recent_price_trend > 0 and recent_rsi_trend < -5: divergence_alert = "BEARISH DIVERGENCE"
            elif recent_price_trend < 0 and recent_rsi_trend > 5: divergence_alert = "BULLISH DIVERGENCE"

            # Trend
            sma_20 = float(close.rolling(20).mean().iloc[-1])
            sma_50 = float(close.rolling(50).mean().iloc[-1])
            sma_200 = float(close.rolling(200).mean().iloc[-1])

            report_block = f"""
=== {name.upper()} ({symbol}) ===
Current Price     : ${current_price:.2f}
Volatility (ATR)  : ${atr:.2f} ({atr_pct:.2f}% daily swing expected)
Dynamic Stop (2x) : ${dynamic_stop:.2f}
Dynamic Target(3x): ${dynamic_target:.2f}

-- Institutional Positioning --
Volume POC (90d)  : ${poc_price:.2f}
Relation to POC   : {'Trading ABOVE Volume Support (Bullish)' if current_price > poc_price else 'Trading BELOW Volume Resistance (Bearish)'}

-- Momentum & Trend --
RSI (14)          : {current_rsi:.2f}
Divergence Alert  : {divergence_alert}
Trend Alignment   : {'BULLISH' if current_price > sma_50 and sma_50 > sma_200 else 'BEARISH' if current_price < sma_50 else 'CONSOLIDATING'}
"""
            reports.append(report_block.strip())
            
        except Exception as e:
            print(f"  [!] Failed to process {name}: {str(e)}")
            continue

    macro_context = "\n=== MACRO CORRELATIONS ===\n"
    if "Gold" in prices and "Silver" in prices:
        gs_ratio = prices["Gold"] / prices["Silver"]
        macro_context += f"Gold/Silver Ratio: {gs_ratio:.2f}\n-> Interpretation: "
        if gs_ratio > 80: macro_context += "Ratio HIGH. Silver undervalued relative to Gold.\n"
        elif gs_ratio < 60: macro_context += "Ratio LOW. Silver overvalued relative to Gold.\n"
        else: macro_context += "Ratio NEUTRAL.\n"

    if "WTI_Crude" in prices:
        macro_context += f"WTI Crude Price  : ${prices['WTI_Crude']:.2f}\n"

    return f"MULTI-ASSET QUANTITATIVE REPORT\n\n{chr(10).join(reports)}\n{macro_context}".strip()