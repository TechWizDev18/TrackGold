# tools/fundamental_tool.py
import requests
from bs4 import BeautifulSoup
from crewai.tools import tool
from datetime import datetime

@tool("Fundamental_News_Scraper")
def scrape_fundamental_news() -> str:
    """Scrapes recent news headlines related to gold, Fed policy, interest rates, and USD."""
    
    try:
        headlines = []
        
        # Method 1: Use NewsAPI (requires free API key from https://newsapi.org)
        # Uncomment and add your API key if you want to use this
        """
        NEWS_API_KEY = "your_api_key_here"
        url = f"https://newsapi.org/v2/everything?q=gold+OR+federal+reserve+OR+interest+rates&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            articles = response.json().get('articles', [])[:5]
            for article in articles:
                headlines.append(f"[{article.get('source', {}).get('name', 'Unknown')}] - {article.get('title', 'No title')}")
        """
        
        # Method 2: Scrape from Gold.org news (reliable source)
        try:
            url = "https://www.gold.org/news"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                news_items = soup.find_all('div', class_='view-content')[:5]
                
                for item in news_items:
                    title_tag = item.find('h3') or item.find('a')
                    if title_tag:
                        headlines.append(f"[Gold.org] - {title_tag.get_text(strip=True)}")
        except Exception as e:
            headlines.append(f"[Error] Could not fetch from Gold.org: {str(e)}")
        
        # Method 3: Scrape from Kitco (major gold news site)
        try:
            url = "https://www.kitco.com/news/gold.html"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                articles = soup.find_all('article', limit=5)
                
                for article in articles:
                    title_tag = article.find('h3') or article.find('a')
                    if title_tag:
                        headlines.append(f"[Kitco] - {title_tag.get_text(strip=True)}")
        except Exception as e:
            headlines.append(f"[Error] Could not fetch from Kitco: {str(e)}")
        
        # Method 4: Use simple RSS feed from major financial news
        try:
            url = "https://www.investing.com/commodities/gold"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                news_items = soup.find_all('article', limit=3)
                
                for item in news_items:
                    title_tag = item.find('a')
                    if title_tag:
                        headlines.append(f"[Investing.com] - {title_tag.get_text(strip=True)}")
        except Exception as e:
            pass  # Silently skip if this source fails
        
        # If we got headlines, format and return them
        if headlines:
            output = "Recent Relevant Fundamental Headlines:\n\n"
            for headline in headlines[:10]:  # Limit to 10 headlines
                output += f"{headline}\n"
            
            output += f"\n**Analysis Context:**\n"
            output += f"Focus on themes related to: Federal Reserve policy, interest rate decisions, "
            output += f"US Dollar strength/weakness, inflation trends, and geopolitical tensions.\n"
            output += f"These factors directly impact gold prices as a safe-haven asset."
            
            return output.strip()
        else:
            # Fallback: return generic market context
            return """Recent Relevant Fundamental Headlines:

[Market Context] - Unable to fetch live headlines. General analysis suggests:
- Monitor Federal Reserve interest rate policies (higher rates typically pressure gold)
- Track US Dollar Index movements (inverse relationship with gold)
- Watch for geopolitical tensions (boost safe-haven demand)
- Consider inflation expectations (gold as inflation hedge)

**Recommendation:** Use alternative news sources or enable NewsAPI for real-time data."""
    
    except Exception as e:
        return f"Error fetching fundamental news: {str(e)}. Using general market context instead."