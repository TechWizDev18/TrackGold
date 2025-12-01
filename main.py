# main.py
from crew import GoldTrackerCrew
from datetime import datetime
import sys
import os

# Import output cleaner if available
try:
    from utils.output_cleaner import clean_output, format_for_display
    USE_CLEANER = True
except ImportError:
    USE_CLEANER = False
    print("Note: Output cleaner not available, using raw output")

def save_report(result, filename=None):
    """Save the analysis report to a file."""
    try:
        # Create reports directory if it doesn't exist
        os.makedirs("reports", exist_ok=True)
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"reports/gold_analysis_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Gold Tracker Analysis Report\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write(str(result))
        
        # Verify file was created
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"\n✅ Report saved successfully!")
            print(f"   Location: {os.path.abspath(filename)}")
            print(f"   Size: {file_size} bytes")
            return filename
        else:
            print(f"\n⚠️  Error: File was not created at {filename}")
            return None
            
    except Exception as e:
        print(f"\n❌ Could not save report: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main execution function."""
    print("=" * 80)
    print("🥇 GOLDTRACKER - AI-Powered Gold Trading Analysis System")
    print("=" * 80)
    print(f"Analysis started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    try:
        # Initialize and run the crew
        gold_crew = GoldTrackerCrew()
        result = gold_crew.kickoff()
        
        # Clean the output if cleaner is available
        if USE_CLEANER:
            cleaned_result = clean_output(str(result))
            display_result = format_for_display(cleaned_result)
        else:
            cleaned_result = str(result)
            display_result = str(result)
        
        print("\n" + "=" * 80)
        print("📊 FINAL ANALYSIS REPORT")
        print("=" * 80)
        print(display_result)
        print("=" * 80)
        
        # Save report to file
        save_report(cleaned_result)
        
        print("\n✅ Analysis completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user.")
        return 1
    except Exception as e:
        print(f"\n\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)