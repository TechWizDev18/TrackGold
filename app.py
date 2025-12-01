# app.py - PRODUCTION READY FOR RENDER
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from crew import GoldTrackerCrew
from datetime import datetime
import yfinance as yf
import plotly.graph_objs as go
import plotly.utils
import json
import threading
import os
import warnings

# Suppress yfinance warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)
CORS(app)

# Global variable to store analysis status
analysis_status = {
    'running': False,
    'progress': 0,
    'message': '',
    'result': None,
    'error': None
}

# Cache for gold price to avoid excessive API calls
price_cache = {
    'price': 2650.00,
    'change': 0.00,
    'change_pct': 0.00,
    'timestamp': datetime.now(),
    'cache_duration': 60  # seconds - increased for production
}

def get_current_gold_price_realtime():
    """
    Fetch current gold price with proper error handling and caching.
    Uses Yahoo Finance with daily interval to ensure we have enough data.
    """
    global price_cache
    
    # Check cache first
    cache_age = (datetime.now() - price_cache['timestamp']).total_seconds()
    if cache_age < price_cache['cache_duration']:
        print(f"Using cached price: ${price_cache['price']}")
        return price_cache
    
    try:
        # Fetch last 5 trading days with DAILY intervals
        df = yf.download(
            "GC=F",
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
            timeout=10
        )
        
        if df is None or len(df) == 0:
            print("Warning: No data returned from yfinance")
            return price_cache  # Return cached data
        
        # Get current price from latest available data
        latest_price = df['Close'].iloc[-1].item()
        
        # Calculate change if we have at least 2 data points
        if len(df) >= 2:
            prev_price = df['Close'].iloc[-2].item()
            change = latest_price - prev_price
            change_pct = (change / prev_price) * 100
        else:
            # Fallback: compare with cached previous price
            change = latest_price - price_cache['price']
            change_pct = (change / price_cache['price']) * 100 if price_cache['price'] > 0 else 0
        
        # Update cache
        price_cache = {
            'price': round(latest_price, 2),
            'change': round(change, 2),
            'change_pct': round(change_pct, 2),
            'timestamp': datetime.now(),
            'cache_duration': 60
        }
        
        print(f"✓ Updated price: ${price_cache['price']} (change: {price_cache['change']:+.2f}, {price_cache['change_pct']:+.2f}%)")
        return price_cache
        
    except Exception as e:
        print(f"Error fetching gold price: {e}")
        # Return last known good data
        return price_cache

def get_gold_price_data(period="6mo"):
    """Fetch gold price data for charts."""
    try:
        df = yf.download("GC=F", period=period, interval="1d", progress=False, auto_adjust=True, timeout=10)
        
        if len(df) == 0:
            return None
        
        # Calculate indicators
        df['SMA_10'] = df['Close'].rolling(window=10).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        
        return df
    except Exception as e:
        print(f"Error fetching chart data: {e}")
        return None

def create_price_chart(df):
    """Create an interactive Plotly chart."""
    if df is None or len(df) == 0:
        return None
    
    fig = go.Figure()
    
    # Add candlestick chart
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='Gold Price',
        increasing_line_color='#22c55e',
        decreasing_line_color='#ef4444'
    ))
    
    # Add SMA lines
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['SMA_10'],
        mode='lines',
        name='10-Day SMA',
        line=dict(color='#3b82f6', width=2)
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['SMA_50'],
        mode='lines',
        name='50-Day SMA',
        line=dict(color='#f59e0b', width=2)
    ))
    
    # Update layout
    fig.update_layout(
        title='Gold Spot Price with Technical Indicators',
        yaxis_title='Price (USD per oz)',
        xaxis_title='Date',
        template='plotly_dark',
        hovermode='x unified',
        height=500,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e5e7eb'),
        xaxis_rangeslider_visible=False
    )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

def run_analysis_async():
    """Run the crew analysis in background with timeout protection."""
    global analysis_status
    
    try:
        analysis_status['running'] = True
        analysis_status['progress'] = 10
        analysis_status['message'] = 'Initializing analysis...'
        analysis_status['error'] = None
        
        gold_crew = GoldTrackerCrew()
        
        analysis_status['progress'] = 30
        analysis_status['message'] = 'Analyzing technical indicators...'
        
        result = gold_crew.kickoff()
        
        analysis_status['progress'] = 100
        analysis_status['message'] = 'Analysis complete!'
        analysis_status['result'] = str(result)
        
        # Save report (only if filesystem is writable)
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("reports", exist_ok=True)
            filename = f"reports/gold_analysis_{timestamp}.md"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# Gold Tracker Analysis Report\n")
                f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")
                f.write(str(result))
            print(f"✓ Report saved: {filename}")
        except Exception as e:
            # Filesystem might be read-only on Render - that's okay
            print(f"Warning: Could not save report to disk: {e}")
        
    except Exception as e:
        analysis_status['error'] = str(e)
        analysis_status['message'] = f'Error: {str(e)}'
        print(f"Analysis error: {e}")
    finally:
        analysis_status['running'] = False

@app.route('/')
def index():
    """Landing page."""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Main dashboard."""
    return render_template('dashboard.html')

@app.route('/api/gold-price')
def api_gold_price():
    """API endpoint for current gold price."""
    try:
        price_data = get_current_gold_price_realtime()
        
        return jsonify({
            'success': True,
            'price': price_data['price'],
            'change': price_data['change'],
            'change_pct': price_data['change_pct'],
            'timestamp': datetime.now().isoformat(),
            'source': 'Yahoo Finance (GC=F)'
        })
        
    except Exception as e:
        print(f"Critical error in api_gold_price: {e}")
        # Return last known good data
        return jsonify({
            'success': True,
            'price': price_cache['price'],
            'change': price_cache['change'],
            'change_pct': price_cache['change_pct'],
            'timestamp': datetime.now().isoformat(),
            'source': 'Cached',
            'note': 'Using cached data due to API error'
        })

@app.route('/api/start-analysis', methods=['POST'])
def start_analysis():
    """Start AI analysis."""
    global analysis_status
    
    if analysis_status['running']:
        return jsonify({
            'success': False,
            'error': 'Analysis already running'
        }), 400
    
    analysis_status = {
        'running': True,
        'progress': 0,
        'message': 'Starting analysis...',
        'result': None,
        'error': None
    }
    
    thread = threading.Thread(target=run_analysis_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'message': 'Analysis started'
    })

@app.route('/api/analysis-status')
def get_analysis_status():
    """Get analysis status."""
    return jsonify(analysis_status)

@app.route('/analysis')
def analysis_page():
    """Analysis results page."""
    return render_template('analysis.html')

@app.route('/api/chart-data')
def get_chart_data():
    """Get chart data."""
    period = request.args.get('period', '6mo')
    
    df = get_gold_price_data(period)
    
    if df is not None:
        chart_json = create_price_chart(df)
        return jsonify({
            'success': True,
            'chart': chart_json
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Unable to fetch chart data'
        }), 500

if __name__ == '__main__':
    # Create reports directory if possible (might fail on Render - that's okay)
    try:
        os.makedirs('reports', exist_ok=True)
    except Exception as e:
        print(f"Warning: Cannot create reports directory: {e}")
    
    # Get port from environment (Render sets this)
    port = int(os.environ.get('PORT', 10000))
    
    print("🚀 Starting GoldTracker")
    print(f"📡 Listening on port {port}")
    
    # ALWAYS run in production mode (debug=False)
    # Gunicorn will handle this properly
    app.run(debug=False, host='0.0.0.0', port=port)