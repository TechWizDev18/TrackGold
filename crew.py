# crew.py
import os
import yaml
from crewai import Agent, Task, Crew, Process, LLM
from dotenv import load_dotenv

# Load Tools
from tools.technical_tool import get_technical_signals
from tools.fundamental_tool import scrape_fundamental_news

load_dotenv()

def load_config(file_path):
    """Utility function to load YAML configuration files."""
    try:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading config file {file_path}: {e}")
        return {}

class GoldTrackerCrew:
    def __init__(self):
        # 1. Load Configs
        self.agents_config = load_config('config/agents.yaml')
        self.tasks_config = load_config('config/tasks.yaml')

        # 2. Initialize Gemini LLM
        # Ensure GEMINI_API_KEY is set in .env
        self.gemini_llm = LLM(
            model='gemini-2.5-flash', 
            temperature=0.1, 
            api_key=os.getenv("GEMINI_API_KEY")
        )

    def kickoff(self):
        # --- 1. Define Agents ---
        technical_analyst = Agent(
            role=self.agents_config['technical_analyst']['role'],
            goal=self.agents_config['technical_analyst']['goal'],
            backstory=self.agents_config['technical_analyst']['backstory'],
            tools=[get_technical_signals],
            llm=self.gemini_llm,
            verbose=True
        )

        fundamental_economist = Agent(
            role=self.agents_config['fundamental_economist']['role'],
            goal=self.agents_config['fundamental_economist']['goal'],
            backstory=self.agents_config['fundamental_economist']['backstory'],
            tools=[scrape_fundamental_news],
            llm=self.gemini_llm,
            verbose=True
        )

        position_strategist = Agent(
            role=self.agents_config['position_strategist']['role'],
            goal=self.agents_config['position_strategist']['goal'],
            backstory=self.agents_config['position_strategist']['backstory'],
            llm=self.gemini_llm,
            verbose=True
        )
        
        # --- 2. Define Tasks ---
        technical_task = Task(
            description=self.tasks_config['technical_analysis_task']['description'],
            expected_output=self.tasks_config['technical_analysis_task']['expected_output'],
            agent=technical_analyst,
        )

        fundamental_task = Task(
            description=self.tasks_config['fundamental_sentiment_task']['description'],
            expected_output=self.tasks_config['fundamental_sentiment_task']['expected_output'],
            agent=fundamental_economist,
        )

        final_recommendation_task = Task(
            description=self.tasks_config['final_recommendation_task']['description'],
            expected_output=self.tasks_config['final_recommendation_task']['expected_output'],
            agent=position_strategist,
            context=[technical_task, fundamental_task]
        )

        # --- 3. Create and Run the Crew ---
        gold_crew = Crew(
            agents=[technical_analyst, fundamental_economist, position_strategist],
            tasks=[technical_task, fundamental_task, final_recommendation_task],
            process=Process.sequential, 
            verbose=True  # ✅ Changed from 2 to True
        )

        print("--- Starting GoldTracker Crew Analysis ---")
        result = gold_crew.kickoff()
        return result