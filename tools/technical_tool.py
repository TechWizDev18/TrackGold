# tools/technical_tool.py
import yfinance as yf
import pandas as pd
from crewai.tools import tool
import time

GOLD_TICKER = "GC=F"
MAX_RETRIES = 3

@tool("Technical_Analysis_Tool")
def get_technical_signals() -> str:
    """Fetches gold price, calculates SMA crossover and RSI, and returns a summary."""
    
    for attempt in range(MAX_RETRIES):
        try:
            # Download gold price data with retry logic
            df = yf.download(
                GOLD_TICKER, 
                period="6mo", 
                interval="1d", 
                progress=False,
                auto_adjust=True
            )
            
            # Check if data was downloaded successfully
            if len(df) == 0:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)  # Wait before retry
                    continue
                return f"Error: No data available for {GOLD_TICKER} after {MAX_RETRIES} attempts."
            
            # Calculate technical indicators
            df['SMA_10'] = df['Close'].rolling(window=10).mean()
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            
            # Calculate RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # Get latest values - FIXED: Use .item() to avoid FutureWarning
            current_price = df['Close'].iloc[-1].item()
            sma_10 = df['SMA_10'].iloc[-1].item()
            sma_50 = df['SMA_50'].iloc[-1].item()
            rsi = df['RSI'].iloc[-1].item()
            
            # Calculate percentage difference for SMA crossover strength
            sma_diff_pct = ((sma_10 - sma_50) / sma_50) * 100
            
            # Determine Technical Signal (Strong Buy, Buy, Neutral, Sell, Strong Sell)
            if sma_10 > sma_50 and rsi < 50:
                if sma_diff_pct > 2 and rsi < 40:
                    signal = "Strong Buy"
                else:
                    signal = "Buy"
            elif sma_10 < sma_50 and rsi > 50:
                if sma_diff_pct < -2 and rsi > 60:
                    signal = "Strong Sell"
                else:
                    signal = "Sell"
            elif rsi > 70:
                signal = "Sell"  # Overbought
            elif rsi < 30:
                signal = "Buy"  # Oversold
            else:
                signal = "Neutral"
            
            # Determine SMA signal description
            sma_signal = f"Bullish (10-day SMA {abs(sma_diff_pct):.2f}% above 50-day)" if sma_10 > sma_50 else f"Bearish (10-day SMA {abs(sma_diff_pct):.2f}% below 50-day)"
            
            # Determine RSI signal
            if rsi > 70:
                rsi_signal = f"Overbought (RSI: {rsi:.2f})"
            elif rsi < 30:
                rsi_signal = f"Oversold (RSI: {rsi:.2f})"
            else:
                rsi_signal = f"Neutral (RSI: {rsi:.2f})"
            
            # Create summary with clear signal
            summary = f"""**Gold Technical Analysis ({GOLD_TICKER})**

**Current Price:** ${current_price:.2f}
**10-day SMA:** ${sma_10:.2f}
**50-day SMA:** ${sma_50:.2f}
**RSI (14-period):** {rsi:.2f}

**Technical Signal:** {signal}

**Rationale:**
- SMA Status: {sma_signal}
- RSI Status: {rsi_signal}
- Momentum: {'Positive' if sma_10 > sma_50 else 'Negative'}
"""
            
            return summary.strip()
        
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return f"Error fetching technical analysis after {MAX_RETRIES} attempts: {str(e)}"
    
    return "Failed to fetch technical analysis data."