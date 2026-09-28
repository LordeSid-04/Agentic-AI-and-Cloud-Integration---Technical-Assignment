import pandas as pd
from config import DATA_PATH


def load_energy_data():
    # Load the CSV, parse timestamps, and run basic sanity checks.
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])

    # Validation
    if df["timestamp"].isna().any():
        raise ValueError("Missing timestamps detected.")
    if not df["timestamp"].is_unique:
        raise ValueError("Duplicate timestamps detected.")
    if not (df["energy_consumption_kwh"] >= 0).all():
        raise ValueError("Negative consumption values detected.")

    df = df.sort_values("timestamp").reset_index(drop=True)

    min_date = df["timestamp"].min()
    max_date = df["timestamp"].max()

    return df, min_date, max_date
