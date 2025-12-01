import os
from crewai import Agent, Task, Crew
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

class GoldTrackerCrew:
    def __init__(self):
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        
    def fetch_gold_data(self):
        """Fetch gold price data with proper error handling."""
        try:
            # Fetch 1 year of data to ensure we have enough for analysis
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            
            gold = yf.Ticker("GC=F")
            df = gold.history(start=start_date, end=end_date, interval="1d")
            
            if df.empty:
                raise ValueError("No data returned from Yahoo Finance")
            
            # Calculate technical indicators
            df['SMA_10'] = df['Close'].rolling(window=10).mean()
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            
            # Calculate RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # Get latest values
            latest = df.iloc[-1]
            current_price = round(latest['Close'], 2)
            sma_10 = round(latest['SMA_10'], 2) if pd.notna(latest['SMA_10']) else current_price
            sma_50 = round(latest['SMA_50'], 2) if pd.notna(latest['SMA_50']) else current_price
            rsi = round(latest['RSI'], 2) if pd.notna(latest['RSI']) else 50.0
            
            # Calculate 24h change
            if len(df) >= 2:
                prev_close = df.iloc[-2]['Close']
                change_24h = round(((current_price - prev_close) / prev_close) * 100, 2)
            else:
                change_24h = 0.0
            
            return {
                'current_price': current_price,
                'sma_10': sma_10,
                'sma_50': sma_50,
                'rsi': rsi,
                'change_24h': change_24h,
                'volume': int(latest['Volume']) if pd.notna(latest['Volume']) else 0,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            print(f"Error fetching gold data: {e}")
            # Return fallback data
            return {
                'current_price': 2650.00,
                'sma_10': 2645.00,
                'sma_50': 2620.00,
                'rsi': 55.0,
                'change_24h': 0.5,
                'volume': 150000,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'note': 'Using fallback data due to API error'
            }

    def technical_analyst_agent(self):
        """Technical Analysis Agent"""
        return Agent(
            role='Technical Analyst',
            goal='Analyze gold price charts, identify trends, support/resistance levels, and provide technical trading signals',
            backstory="""You are an expert technical analyst specializing in precious metals.
            You use price action, moving averages, RSI, and volume to identify trading opportunities.
            You provide clear entry/exit points with risk management.""",
            verbose=True,
            allow_delegation=False
        )

    def fundamental_analyst_agent(self):
        """Fundamental Analysis Agent"""
        return Agent(
            role='Fundamental Analyst',
            goal='Analyze macroeconomic factors, geopolitical events, and market sentiment affecting gold prices',
            backstory="""You are a fundamental analyst focused on gold markets.
            You track inflation data, central bank policies, USD strength, and safe-haven demand.
            You identify long-term trends and catalysts for gold price movements.""",
            verbose=True,
            allow_delegation=False
        )

    def risk_manager_agent(self):
        """Risk Management Agent"""
        return Agent(
            role='Risk Manager',
            goal='Assess portfolio risk, determine position sizing, and set stop-loss levels',
            backstory="""You are a professional risk manager specializing in commodities trading.
            You calculate risk-reward ratios, volatility metrics, and provide position sizing recommendations.
            You prioritize capital preservation while maximizing returns.""",
            verbose=True,
            allow_delegation=False
        )

    def technical_analysis_task(self, agent, gold_data):
        """Task for technical analysis"""
        return Task(
            description=f"""Analyze the current technical setup for gold (GC=F):
            
            Current Price: ${gold_data['current_price']}
            10-Day SMA: ${gold_data['sma_10']}
            50-Day SMA: ${gold_data['sma_50']}
            RSI (14): {gold_data['rsi']}
            24h Change: {gold_data['change_24h']}%
            Volume: {gold_data['volume']:,}
            
            Provide:
            1. Current trend (bullish/bearish/neutral)
            2. Key support and resistance levels
            3. Technical indicators interpretation
            4. Entry/exit recommendations with specific price levels""",
            agent=agent,
            expected_output="Detailed technical analysis with specific price levels and trading signals"
        )

    def fundamental_analysis_task(self, agent, gold_data):
        """Task for fundamental analysis"""
        return Task(
            description=f"""Analyze fundamental factors affecting gold price:
            
            Current Gold Price: ${gold_data['current_price']}
            Recent Change: {gold_data['change_24h']}%
            
            Consider:
            1. US Dollar strength and trends
            2. Inflation expectations and Fed policy
            3. Geopolitical tensions and safe-haven demand
            4. Central bank gold purchases
            5. Real interest rates
            
            Provide your fundamental outlook (bullish/bearish/neutral) with reasoning.""",
            agent=agent,
            expected_output="Comprehensive fundamental analysis with market outlook"
        )

    def risk_assessment_task(self, agent, gold_data):
        """Task for risk assessment"""
        return Task(
            description=f"""Assess risk for gold trading position:
            
            Current Price: ${gold_data['current_price']}
            RSI: {gold_data['rsi']}
            Volatility: Recent 24h change is {gold_data['change_24h']}%
            
            Provide:
            1. Overall risk level (Low/Medium/High)
            2. Recommended position size (% of portfolio)
            3. Stop-loss level with reasoning
            4. Take-profit targets (short-term and long-term)
            5. Risk-reward ratio""",
            agent=agent,
            expected_output="Detailed risk assessment with specific recommendations"
        )

    def final_recommendation_task(self, agent, gold_data):
        """Final synthesis task"""
        return Task(
            description=f"""Based on all previous analyses, provide final trading recommendation:
            
            Current Gold Price: ${gold_data['current_price']}
            
            Synthesize technical, fundamental, and risk analysis into:
            1. Clear action: BUY / SELL / HOLD
            2. Entry price (if BUY)
            3. Stop-loss level
            4. Target price(s)
            5. Position size recommendation
            6. Time horizon (short/medium/long term)
            7. Key risks to watch
            
            Format as a clear, actionable recommendation.""",
            agent=agent,
            expected_output="Final trading recommendation with all key parameters",
            context=[]  # Will be filled with previous task outputs
        )

    def kickoff(self):
        """Execute the analysis crew"""
        print("🚀 Starting Gold Analysis Crew...")
        
        # Fetch real gold data
        print("📊 Fetching gold market data...")
        gold_data = self.fetch_gold_data()
        print(f"✓ Current Gold Price: ${gold_data['current_price']}")
        
        # Create agents
        technical_agent = self.technical_analyst_agent()
        fundamental_agent = self.fundamental_analyst_agent()
        risk_agent = self.risk_manager_agent()
        
        # Create tasks
        technical_task = self.technical_analysis_task(technical_agent, gold_data)
        fundamental_task = self.fundamental_analysis_task(fundamental_agent, gold_data)
        risk_task = self.risk_assessment_task(risk_agent, gold_data)
        final_task = self.final_recommendation_task(risk_agent, gold_data)
        
        # Link tasks for context
        final_task.context = [technical_task, fundamental_task, risk_task]
        
        # Create and run crew
        crew = Crew(
            agents=[technical_agent, fundamental_agent, risk_agent],
            tasks=[technical_task, fundamental_task, risk_task, final_task],
            verbose=True
        )
        
        print("🔍 Running analysis...")
        result = crew.kickoff()
        print("✅ Analysis complete!")
        
        return result