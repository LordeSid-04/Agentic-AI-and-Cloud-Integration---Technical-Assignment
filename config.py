import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "simulated_energy_data_aug.csv"
OUTPUT_DIR = BASE_DIR / "output"

# Energy tariff
TARIFF_SGD_PER_KWH = 0.25

# LLM (any OpenAI-compatible provider; defaults to Groq free tier)
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
MODEL_NAME = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

