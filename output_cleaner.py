# utils/output_cleaner.py
import re

def clean_output(text):
    """
    Remove markdown formatting from text output.
    Converts markdown to clean, structured plain text.
    """
    if not text:
        return text
    
    # Remove markdown headers (# ## ###)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # Remove bold (**text**)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    
    # Remove italic (*text* or _text_)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    
    # Remove bullet points (- or *)
    text = re.sub(r'^\s*[-*]\s+', '  ', text, flags=re.MULTILINE)
    
    # Remove numbered lists (1. 2. etc.)
    text = re.sub(r'^\s*\d+\.\s+', '  ', text, flags=re.MULTILINE)
    
    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def format_for_display(text):
    """
    Format the cleaned text for better display.
    """
    # Add proper section separators
    text = text.replace('TECHNICAL SIGNAL:', '\n' + '='*50 + '\nTECHNICAL SIGNAL:')
    text = text.replace('FUNDAMENTAL SIGNAL:', '\n' + '='*50 + '\nFUNDAMENTAL SIGNAL:')
    text = text.replace('GOLDTRACKER FINAL RECOMMENDATION', '='*50 + '\nGOLDTRACKER FINAL RECOMMENDATION\n' + '='*50)
    
    return text

def extract_recommendation_data(text):
    """
    Extract key data from the recommendation text for structured display.
    Returns a dictionary with parsed values.
    """
    data = {
        'recommendation': None,
        'entry_price': None,
        'stop_loss': None,
        'target_price': None,
        'position_size': None,
        'timeframe': None,
        'risk_level': None,
        'technical_summary': None,
        'fundamental_summary': None
    }
    
    # Extract recommendation
    rec_match = re.search(r'RECOMMENDATION:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if rec_match:
        data['recommendation'] = rec_match.group(1).strip()
    
    # Extract entry price
    entry_match = re.search(r'ENTRY PRICE:\s*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if entry_match:
        data['entry_price'] = entry_match.group(1).replace(',', '')
    
    # Extract stop-loss
    stop_match = re.search(r'STOP[-\s]?LOSS:\s*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if stop_match:
        data['stop_loss'] = stop_match.group(1).replace(',', '')
    
    # Extract target price
    target_match = re.search(r'TARGET PRICE:\s*\$?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if target_match:
        data['target_price'] = target_match.group(1).replace(',', '')
    
    # Extract position size
    pos_match = re.search(r'POSITION SIZE:\s*([\d.]+)%', text, re.IGNORECASE)
    if pos_match:
        data['position_size'] = pos_match.group(1)
    
    # Extract timeframe
    time_match = re.search(r'TIMEFRAME:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if time_match:
        data['timeframe'] = time_match.group(1).strip()
    
    # Extract risk level
    risk_match = re.search(r'RISK ASSESSMENT:\s*(High|Medium|Low)', text, re.IGNORECASE)
    if risk_match:
        data['risk_level'] = risk_match.group(1).strip()
    
    return data