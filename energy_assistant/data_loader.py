import pandas as pd
from config import DATA_PATH


def load_energy_data():
    # Load the CSV, parse timestamps, and run basic sanity checks.
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])

    # Validation
    assert not df["timestamp"].isna().any(), "Missing timestamps detected."
    assert df["timestamp"].is_unique, "Duplicate timestamps detected."
    assert (df["energy_consumption_kwh"] >= 0).all(), "Negative consumption values detected."

    df = df.sort_values("timestamp").reset_index(drop=True)

    min_date = df["timestamp"].min()
    max_date = df["timestamp"].max()

    return df, min_date, max_date
