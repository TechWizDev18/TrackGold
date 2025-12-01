# app.py
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_cors import CORS
from crew import GoldTrackerCrew
from datetime import datetime
import yfinance as yf
import plotly.graph_objs as go
import plotly.utils
import json
import threading
import os

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

def get_gold_price_data(period="6mo"):
    """Fetch gold price data for charts."""
    try:
        df = yf.download("GC=F", period=period, interval="1d", progress=False, auto_adjust=True)
        
        if len(df) == 0:
            return None
        
        # Calculate indicators for the chart
        df['SMA_10'] = df['Close'].rolling(window=10).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        
        return df
    except Exception as e:
        print(f"Error fetching gold data: {e}")
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
        title='Gold Price (GC=F) with Technical Indicators',
        yaxis_title='Price (USD)',
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
    """Run the crew analysis in background."""
    global analysis_status
    
    try:
        analysis_status['running'] = True
        analysis_status['progress'] = 10
        analysis_status['message'] = 'Initializing analysis...'
        analysis_status['error'] = None
        
        # Initialize crew
        gold_crew = GoldTrackerCrew()
        
        analysis_status['progress'] = 30
        analysis_status['message'] = 'Fetching technical indicators...'
        
        # Run the analysis
        result = gold_crew.kickoff()
        
        analysis_status['progress'] = 100
        analysis_status['message'] = 'Analysis complete!'
        analysis_status['result'] = str(result)
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("reports", exist_ok=True)
        filename = f"reports/gold_analysis_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Gold Tracker Analysis Report\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write(str(result))
        
    except Exception as e:
        analysis_status['error'] = str(e)
        analysis_status['message'] = f'Error: {str(e)}'
    finally:
        analysis_status['running'] = False

@app.route('/')
def index():
    """Landing page with hero section and features."""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Main dashboard with live gold price and analysis."""
    return render_template('dashboard.html')

@app.route('/api/gold-price')
def api_gold_price():
    """API endpoint for current gold price."""
    df = get_gold_price_data(period="5d")
    
    if df is not None and len(df) > 0:
        latest_price = float(df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2])
        change = latest_price - prev_price
        change_pct = (change / prev_price) * 100
        
        return jsonify({
            'success': True,
            'price': round(latest_price, 2),
            'change': round(change, 2),
            'change_pct': round(change_pct, 2),
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Unable to fetch gold price'
        }), 500

@app.route('/api/start-analysis', methods=['POST'])
def start_analysis():
    """Start the AI analysis in background."""
    global analysis_status
    
    if analysis_status['running']:
        return jsonify({
            'success': False,
            'error': 'Analysis already running'
        }), 400
    
    # Reset status
    analysis_status = {
        'running': True,
        'progress': 0,
        'message': 'Starting analysis...',
        'result': None,
        'error': None
    }
    
    # Run analysis in background thread
    thread = threading.Thread(target=run_analysis_async)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'message': 'Analysis started'
    })

@app.route('/api/analysis-status')
def get_analysis_status():
    """Get current analysis status."""
    return jsonify(analysis_status)

@app.route('/analysis')
def analysis_page():
    """Analysis results page."""
    return render_template('analysis.html')

@app.route('/api/chart-data')
def get_chart_data():
    """Get chart data for different timeframes."""
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
    # Ensure reports directory exists
    os.makedirs('reports', exist_ok=True)
    
    print("🥇 GoldTracker Web App Starting...")
    print("📊 Access the app at: http://127.0.0.1:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000)