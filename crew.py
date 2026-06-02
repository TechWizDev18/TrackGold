# crew.py
import os
import yaml
from crewai import Agent, Task, Crew, Process, LLM
from dotenv import load_dotenv

from tools.technical_tool import get_technical_signals
from tools.fundamental_tool import scrape_fundamental_news

load_dotenv()

def load_config(file_path):
    try:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return {}

class TrackGoldTerminal:
    def __init__(self):
        # We define the agents directly here to ensure the prompts are perfectly
        # aligned with our new 2026 Institutional logic.
        
        print(f"\n{'='*70}")
        print(f"  TRACKGOLD: INSTITUTIONAL TERMINAL INITIALIZING")
        print(f"{'='*70}\n")

        # Use Gemini 2.5 Flash for rapid, high-context reasoning
        self.llm = LLM(
            model='gemini/gemini-2.5-flash',
            temperature=0.1, # Keep it highly analytical, zero hallucination
            api_key=os.getenv("GEMINI_API_KEY")
        )

    def kickoff(self):
        # ── 1. AGENTS (The Hub and Spoke) ────────────────────────────────────
        
        quant_desk = Agent(
            role="Head Quantitative Analyst",
            goal="Analyze multi-asset technical data (Gold, Silver, WTI) to identify liquidity sweeps, Volume Point of Control (POC), and dynamic ATR volatility.",
            backstory="You are a ruthless quantitative analyst at a tier-1 hedge fund. You do not care about narratives, only math, volume, and momentum divergences. You heavily weight the Gold/Silver ratio for structural rotations.",
            tools=[get_technical_signals],
            llm=self.llm,
            verbose=True
        )

        macro_desk = Agent(
            role="Global Macro Strategist",
            goal="Synthesize global news syndicates, score sentiment, and track sovereign central bank reserves to establish the fundamental floor for precious metals.",
            backstory="You are a seasoned macroeconomist. You know that central banks and real yields drive gold. You look for 'Smart Money' accumulation (China/India reserves) and geopolitical risk premiums.",
            tools=[scrape_fundamental_news],
            llm=self.llm,
            verbose=True
        )

        cio_hub = Agent(
            role="Chief Investment Officer (CIO)",
            goal="Synthesize Quant and Macro data into a definitive, single-page trading mandate with precise sizing, stops, and conviction levels.",
            backstory="You manage a $5B precious metals portfolio. You are the ultimate decision-maker. You filter out noise. If the Quant Desk says 'Sell' but the Macro Desk shows massive Central Bank buying, you identify the dip as a 'Liquidity Sweep' and issue a 'Buy' order.",
            llm=self.llm,
            verbose=True
        )

        # ── 2. TASKS (The Workflow) ──────────────────────────────────────────
        
        quant_task = Task(
            description="""Run the Multi_Asset_Technical_Engine tool. 
            Extract the exact Current Price, Volume POC, Dynamic Stop (2x ATR), and Gold/Silver Ratio. 
            Format this into a clean quantitative brief.""",
            expected_output="A structured quantitative brief detailing support/resistance via Volume POC, momentum divergences, and cross-asset ratio warnings.",
            agent=quant_desk,
        )

        macro_task = Task(
            description="""Run the Macro_News_and_Reserves_Analyzer tool. 
            Extract the overall Sentiment Score, the top 3 highest-impact geopolitical/economic headlines, and the status of Central Bank accumulation.
            Format this into a clean macroeconomic brief.""",
            expected_output="A structured macro brief detailing global sentiment, inflation/yield vectors, and sovereign reserve floors.",
            agent=macro_desk,
        )

        final_mandate_task = Task(
            description="""You are the CIO. Review the Quant Brief and the Macro Brief.
            Produce the final 'TrackGold Institutional Mandate'.
            
            MANDATORY SECTIONS:
            1. **EXECUTIVE SUMMARY:** (1 paragraph clear directional bias: STRONG BUY, BUY, NEUTRAL, SELL)
            2. **THE 'SMART MONEY' CONTEXT:** (Combine the Gold/Silver ratio, Central Bank flow, and WTI Crude inflation threat into a coherent narrative).
            3. **KEY LEVELS TO TRADE:** - State the exact Current Gold Price.
               - Invalidation Level (Use the 2x ATR dynamic stop from the Quant).
               - Institutional Floor (Use the Volume POC).
            4. **TRADE EXECUTION:** (How to play the next 48 hours).
            
            CRITICAL RULE: Never invent prices. Only use the exact numbers provided by the Quant Desk.""",
            expected_output="A highly professional, Markdown-formatted trading mandate ready for a hedge fund dashboard.",
            agent=cio_hub,
            context=[quant_task, macro_task]
        )

        # ── 3. EXECUTION (The Engine) ────────────────────────────────────────
        
        crew = Crew(
            agents=[quant_desk, macro_desk, cio_hub],
            tasks=[quant_task, macro_task, final_mandate_task],
            process=Process.sequential,
            verbose=True
        )

        print(f"\n🚀 Initiating Multi-Asset Analysis Protocol...\n")
        result = crew.kickoff()
        
        print(f"\n✅ Institutional Analysis Complete.\n")
        return result