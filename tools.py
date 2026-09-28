import pandas as pd
from datetime import timedelta
from openpyxl.styles import Font, Alignment, numbers
from config import TARIFF_SGD_PER_KWH, OUTPUT_DIR


# Tool 1: Total energy consumption

def get_total_consumption(df: pd.DataFrame, start_date: str, end_date: str) -> dict:
    # Sum energy_consumption_kwh for the date range [start_date, end_date+1 day)
    # Parse dates
    try:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
    except (ValueError, TypeError):
        return {"error": f"Could not parse dates: start='{start_date}', end='{end_date}'. "
                         f"Please use YYYY-MM-DD format."}

    if start > end:
        return {"error": f"Start date ({start_date}) is after end date ({end_date}). "
                         f"Please check the order."}

    # Filter
    end_exclusive = end + timedelta(days=1)
    mask = (df["timestamp"] >= start) & (df["timestamp"] < end_exclusive)
    filtered = df.loc[mask]

    if filtered.empty:
        data_min = df["timestamp"].min().strftime("%d %B %Y")
        data_max = df["timestamp"].max().strftime("%d %B %Y")
        return {
            "error": f"No data available for {start_date} to {end_date}. "
                     f"The dataset covers {data_min} to {data_max}."
        }

    total_kwh = round(float(filtered["energy_consumption_kwh"].sum()), 2)

    # Check for partial coverage
    requested_days = (end - start).days + 1
    actual_dates = sorted(filtered["timestamp"].dt.date.unique())
    actual_days = len(actual_dates)

    result = {
        "total_kwh": total_kwh,
        "start_date": start_date,
        "end_date": end_date,
        "days_covered": actual_days,
    }

    if actual_days < requested_days:
        covered_from = actual_dates[0].strftime("%d %B %Y")
        covered_to = actual_dates[-1].strftime("%d %B %Y")
        missing_days = requested_days - actual_days
        result["warning"] = (
            f"Only {actual_days} of {requested_days} requested days have data "
            f"(data available from {covered_from} to {covered_to}). "
            f"{missing_days} day(s) outside the dataset were excluded - "
            f"the total shown covers only the available days."
        )

    return result


# Tool 2: Invoice generation

def generate_invoice(df: pd.DataFrame, start_date: str, end_date: str) -> dict:
    # Build an Excel invoice and save to the output directory.
    # Reuse the consumption calculation (and its validation)
    consumption = get_total_consumption(df, start_date, end_date)
    if "error" in consumption:
        return consumption

    total_kwh = consumption["total_kwh"]
    total_cost = round(total_kwh * TARIFF_SGD_PER_KWH, 2)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Daily breakdown
    start = pd.Timestamp(start_date)
    end_exclusive = pd.Timestamp(end_date) + timedelta(days=1)
    mask = (df["timestamp"] >= start) & (df["timestamp"] < end_exclusive)
    filtered = df.loc[mask].copy()
    filtered["date"] = filtered["timestamp"].dt.date

    daily = (
        filtered
        .groupby("date")["energy_consumption_kwh"]
        .sum()
        .reset_index()
    )
    daily.columns = ["Date", "Consumption (kWh)"]
    daily["Date"] = daily["Date"].astype(str)  # clean YYYY-MM-DD strings in Excel
    daily["Cost (SGD)"] = (daily["Consumption (kWh)"] * TARIFF_SGD_PER_KWH).round(2)
    daily["Consumption (kWh)"] = daily["Consumption (kWh)"].round(2)

    # Write Excel
    filename = f"invoice_{start_date}_to_{end_date}.xlsx"
    filepath = OUTPUT_DIR / filename

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # --- Summary section ---
        summary_df = pd.DataFrame({
            "Field": [
                "Billing Period",
                "Total Energy Consumption (kWh)",
                "Energy Tariff (SGD/kWh)",
                "Total Amount Payable (SGD)",
            ],
            "Value": [
                f"{start_date} to {end_date}",
                total_kwh,
                TARIFF_SGD_PER_KWH,
                total_cost,
            ],
        })
        summary_df.to_excel(writer, sheet_name="Invoice", index=False, startrow=0)

        # --- Daily breakdown section (below the summary, with a gap row) ---
        breakdown_start_row = len(summary_df) + 2
        daily.to_excel(writer, sheet_name="Invoice", index=False, startrow=breakdown_start_row)

        # --- Formatting ---
        ws = writer.sheets["Invoice"]
        bold = Font(bold=True)

        # Bold the summary header row
        for cell in ws[1]:
            cell.font = bold

        # Bold the breakdown header row
        for cell in ws[breakdown_start_row + 1]:
            cell.font = bold

        # Auto-fit column widths
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col) + 2
            ws.column_dimensions[col[0].column_letter].width = max_length

    # Result
    result = {
        "message": "Invoice generated successfully.",
        "file_path": str(filepath.resolve()),
        "billing_period": f"{start_date} to {end_date}",
        "total_kwh": total_kwh,
        "tariff_sgd_per_kwh": TARIFF_SGD_PER_KWH,
        "total_payable_sgd": total_cost,
    }

    if "warning" in consumption:
        result["warning"] = consumption["warning"]

    return result
