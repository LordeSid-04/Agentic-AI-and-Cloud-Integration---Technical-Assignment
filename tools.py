import pandas as pd
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from openpyxl.styles import Font
from config import TARIFF_SGD_PER_KWH, OUTPUT_DIR


# Tool 1: Total energy consumption

def _parse_range(start_date, end_date):
    """Return (start, end, error). Dates are normalised to midnight."""
    if not start_date or not end_date:
        return None, None, "Both a start date and an end date are required."
    try:
        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize()
    except (ValueError, TypeError):
        return None, None, (f"Could not parse dates: start='{start_date}', end='{end_date}'. "
                            f"Please use YYYY-MM-DD format.")
    if pd.isna(start) or pd.isna(end):
        return None, None, "Could not read one of the dates. Please provide explicit dates."
    if start > end:
        return None, None, (f"Start date ({start.date()}) is after end date ({end.date()}). "
                            f"Please check the order.")
    return start, end, None


def get_total_consumption(df: pd.DataFrame, start_date: str, end_date: str) -> dict:
    # Sum energy_consumption_kwh for the date range [start_date, end_date + 1 day)
    start, end, err = _parse_range(start_date, end_date)
    if err:
        return {"error": err}

    mask = (df["timestamp"] >= start) & (df["timestamp"] < end + timedelta(days=1))
    filtered = df.loc[mask]

    if filtered.empty:
        data_min = df["timestamp"].min().strftime("%d %B %Y")
        data_max = df["timestamp"].max().strftime("%d %B %Y")
        return {
            "error": f"No data available for {start.date()} to {end.date()}. "
                     f"The dataset covers {data_min} to {data_max}."
        }

    total_kwh = round(float(filtered["energy_consumption_kwh"].sum()), 2)

    # Hour-level coverage check: catches out-of-range days AND missing hours
    hours_expected = ((end - start).days + 1) * 24
    hours_found = len(filtered)
    covered_start = filtered["timestamp"].min().normalize()
    covered_end = filtered["timestamp"].max().normalize()

    result = {
        "total_kwh": total_kwh,
        "start_date": str(start.date()),
        "end_date": str(end.date()),
        "covered_start": str(covered_start.date()),
        "covered_end": str(covered_end.date()),
        "hours_found": hours_found,
        "hours_expected": hours_expected,
    }

    if hours_found < hours_expected:
        result["warning"] = (
            f"Only {hours_found} of {hours_expected} requested hourly readings exist "
            f"(data available from {covered_start.strftime('%d %B %Y')} to "
            f"{covered_end.strftime('%d %B %Y')}). The total covers only the available "
            f"readings; nothing was estimated for the rest."
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
    total_cost = float(
        (Decimal(str(total_kwh)) * Decimal(str(TARIFF_SGD_PER_KWH)))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )

    # Bill only what the data covers; say so inside the file itself
    partial = "warning" in consumption
    period_start = consumption["covered_start"] if partial else consumption["start_date"]
    period_end = consumption["covered_end"] if partial else consumption["end_date"]

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Daily breakdown
    start = pd.Timestamp(period_start)
    end_exclusive = pd.Timestamp(period_end) + timedelta(days=1)
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
    daily["Consumption (kWh)"] = daily["Consumption (kWh)"].round(2)

    # Write Excel
    filename = f"invoice_{period_start}_to_{period_end}.xlsx"
    filepath = OUTPUT_DIR / filename

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        # --- Summary section ---
        fields = ["Billing Period", "Total Energy Consumption (kWh)",
                  "Energy Tariff (SGD/kWh)", "Total Amount Payable (SGD)"]
        values = [f"{period_start} to {period_end}", total_kwh, TARIFF_SGD_PER_KWH, total_cost]
        if partial:
            fields.append("Note")
            values.append(f"Requested {consumption['start_date']} to {consumption['end_date']}; "
                          f"billed only for the period with data.")
        summary_df = pd.DataFrame({"Field": fields, "Value": values})
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

        # Format numeric cells in summary section to 2 decimal places (0.00)
        for row in range(2, len(summary_df) + 2):
            cell = ws.cell(row=row, column=2)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.00"

        # Format daily consumption cells to 2 decimal places (0.00, e.g. 16.60)
        for row in range(breakdown_start_row + 2, breakdown_start_row + 2 + len(daily)):
            ws.cell(row=row, column=2).number_format = "0.00"

        # Auto-fit column widths
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col) + 2
            ws.column_dimensions[col[0].column_letter].width = max(max_length, 12)

    # Result
    result = {
        "message": "Invoice generated successfully.",
        "file_path": str(filepath.resolve()),
        "file_name": filename,
        "billing_period": f"{period_start} to {period_end}",
        "total_kwh": total_kwh,
        "tariff_sgd_per_kwh": TARIFF_SGD_PER_KWH,
        "total_payable_sgd": total_cost,
    }

    if "warning" in consumption:
        result["warning"] = consumption["warning"]

    return result
