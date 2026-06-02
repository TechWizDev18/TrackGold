# main.py
from crew import GoldTrackerCrew
from datetime import datetime
import sys
import os

# Support both flat layout (files in root) and utils/ subfolder layout
try:
    from utils.output_cleaner import clean_output, format_for_display
except ModuleNotFoundError:
    from output_cleaner import clean_output, format_for_display


def save_report(result, price, source):
    os.makedirs("reports", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"reports/gold_analysis_{ts}.md"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# GoldTracker Analysis Report\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Live Price:** ${price:.2f}  \n")
        f.write(f"**Source:** {source}\n\n---\n\n")
        f.write(str(result))
    if os.path.exists(path):
        print(f"\n✅ Report saved: {os.path.abspath(path)} ({os.path.getsize(path)} bytes)")
        return path
    return None


def main():
    print("=" * 80)
    print("🥇 GOLDTRACKER — AI-Powered Gold Trading Analysis")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        # Fetch live price first — support both flat and utils/ layouts
        try:
            from utils.price_fetcher import GoldPriceFetcher
        except ModuleNotFoundError:
            from price_fetcher import GoldPriceFetcher
        fetcher = GoldPriceFetcher()
        pd = fetcher.get_price(force_refresh=True)
        print(f"\n📊 Live Gold Price: ${pd['price']:.2f} ({pd['method']}, {pd['symbol']})\n")

        # Run crew with live price
        crew = GoldTrackerCrew(current_price=pd['price'])
        result = crew.kickoff()

        cleaned = clean_output(str(result))
        display = format_for_display(cleaned)

        print("\n" + "=" * 80)
        print("📋 FINAL ANALYSIS REPORT")
        print("=" * 80)
        print(display)
        print("=" * 80)

        save_report(cleaned, pd['price'], pd['method'])
        print("\n✅ Analysis complete.")
        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user.")
        return 1
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())