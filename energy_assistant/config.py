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

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-4o-mini"  # cost-effective, supports function calling
