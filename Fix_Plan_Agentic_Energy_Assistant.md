# Fix Plan: Agentic AI Energy Assistant

**Repo:** `LordeSid-04/Agentic-AI-and-Cloud-Integration---Technical-Assignment`
**Deadline:** Wednesday, 30 September 2026
**Goal:** Apply the review fixes, re-verify end to end, then record the demo.

---

## How to read this plan

| Tag | Meaning |
|---|---|
| **MUST** | Fix before recording. Affects submission risk or correctness of what a reviewer sees. |
| **SHOULD** | Small, cheap robustness or polish fixes. Do them if time allows (all are quick). |
| **NIT** | Housekeeping. |

**Testing status:** the `tools.py` and `data_loader.py` patches below were applied to a scratch copy of your repo and run against the dataset (results in the verification section). The LLM-facing changes (`config.py`, `agent.py`, `main.py`) could **not** be tested here because they need a live API key, so run the checklist in Phase 4 yourself.

## Priority summary

| # | Priority | Fix | File(s) | Time |
|---|---|---|---|---|
| 1 | MUST | Switch to a free-tier LLM via an OpenAI-compatible endpoint | `config.py`, `agent.py`, `main.py`, `.env.example`, README | ~10 min |
| 2 | MUST | Add the missing `.env.example` | `.env.example` | 1 min |
| 3 | MUST | Fix the misleading partial-overlap invoice | `tools.py` | ~5 min (code below) |
| 4 | MUST | Clean up `model_dump()` in the tool-call loop | `agent.py` | 1 min |
| 5 | SHOULD | Handle relative dates safely | `agent.py` (system prompt) | 2 min |
| 6 | SHOULD | Echo the interpreted date range in every answer | `agent.py` (system prompt) | 1 min |
| 7 | SHOULD | Hour-level coverage check | `tools.py` | included in #3 |
| 8 | SHOULD | Explicit handling of missing/`None` dates | `tools.py` | included in #3 |
| 9 | SHOULD | Replace the `TextIOWrapper` stdout hack | `main.py` | 1 min |
| 10 | SHOULD | `assert` to `raise ValueError` in the loader | `data_loader.py` | 2 min |
| 11 | NIT | Remove unused `google-genai` dependency and unused imports | `requirements.txt`, `tools.py` | 1 min |
| 12 | NIT | Update README to match the final implementation | `README.md` | 5 min |

---

## Phase 1: Must-fix items

### Fix 1 (MUST): Use a free-tier LLM

**Why:** The brief says a paid LLM is not required and asks for a free or free-tier model. OpenAI's API needs prepaid credits, so a reviewer cannot run your code without funding a key. This is the biggest reproducibility risk in the submission.

**Approach:** keep `agent.py` almost unchanged. The OpenAI Python SDK can talk to any OpenAI-compatible endpoint, and both Gemini and Groq offer free tiers with one. You only change the base URL, model name and key variable.

> Confirm the current endpoint URL, model name and free-tier limits in the provider's docs before you commit. Model names and quotas change.

**`config.py`** (replace the LLM block):

```python
# LLM (any OpenAI-compatible provider; defaults to Gemini free tier)
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
MODEL_NAME = os.getenv("LLM_MODEL", "gemini-2.5-flash")
```

**`agent.py`:**

```python
from config import LLM_API_KEY, LLM_BASE_URL, MODEL_NAME
...
self.client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
```

**`main.py`:** replace `OPENAI_API_KEY` with `LLM_API_KEY` in the import and the pre-flight check, and update the help text:

```python
if not LLM_API_KEY:
    print("X LLM_API_KEY not found.")
    print("  Copy .env.example to .env and paste your free API key.")
    sys.exit(1)
```

**Fallback if Gemini's compatibility layer gives you trouble:** switch to Groq by changing only the `.env` values (see Fix 2). If neither behaves, use the provider's native SDK for the agent loop, but only as a last resort since it means rewriting `agent.py`.

### Fix 2 (MUST): Add `.env.example`

**Why:** The README says `cp .env.example .env`, but the file is not in the repo, so the Quick Start fails on a fresh clone.

Create `.env.example` (placeholder only, never a real key):

```
LLM_API_KEY=your_api_key_here

# Default: Google Gemini (free tier)
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-2.5-flash

# Alternative: Groq (free tier). Uncomment these two and comment out the Gemini pair above.
# LLM_BASE_URL=https://api.groq.com/openai/v1
# LLM_MODEL=llama-3.3-70b-versatile
```

Make sure `.env.example` is committed and `.env` is not (`.gitignore` already covers `.env`).

### Fix 3 (MUST): Partial-overlap invoice must not bill a period it does not cover

**Problem:** For "28 August to 3 September", the invoice file says *Billing Period: 2026-08-28 to 2026-09-03* but only bills 4 days. The warning appears in the chat only, so anyone who opens the spreadsheet sees a 7-day period with a 4-day total.

**Fix:** bill only the period with data, clip the billing period to it, and put a **Note** row inside the file. This matches how the consumption tool already behaves and stays true to "do not assume missing data".

This patch also delivers Fixes 7 and 8 (hour-level coverage, missing dates) and part of Fix 11 (unused imports). **Replace your whole `tools.py` with this tested version:**

```python
import pandas as pd
from datetime import timedelta
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
    total_cost = round(total_kwh * TARIFF_SGD_PER_KWH, 2)

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
    daily["Cost (SGD)"] = (daily["Consumption (kWh)"] * TARIFF_SGD_PER_KWH).round(2)
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

        # Auto-fit column widths
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col) + 2
            ws.column_dimensions[col[0].column_letter].width = max_length

    # Result
    result = {
        "message": "Invoice generated successfully.",
        "file_path": str(filepath.resolve()),
        "billing_period": f"{period_start} to {period_end}",
        "total_kwh": total_kwh,
        "tariff_sgd_per_kwh": TARIFF_SGD_PER_KWH,
        "total_payable_sgd": total_cost,
    }

    if "warning" in consumption:
        result["warning"] = consumption["warning"]

    return result
```

**What changed vs. your version:**
- New `_parse_range()` helper: rejects missing/`None` dates, normalises `"2026-08-08 13:00"` to a date, checks order.
- Coverage is now checked per **hour** (`hours_found` vs `hours_expected`), so it catches both out-of-range days and a missing hour inside a day.
- `get_total_consumption` now also returns `covered_start` and `covered_end`.
- `generate_invoice` clips the billing period to the covered dates, uses that in the filename and summary, and adds a **Note** row when the range was partial.
- Removed unused imports (`Alignment`, `numbers`).

### Fix 4 (MUST): Send clean assistant messages back to the API

**Problem:** `self.history.append(message.model_dump())` includes extra `None` fields (`annotations`, `refusal`, `audio`, and so on). OpenAI tolerates them, but other providers' OpenAI-compatible endpoints often reject unknown message fields. This could break tool-calling the moment you do Fix 1.

**`agent.py`:**

```python
self.history.append(message.model_dump(exclude_none=True))
```

If a provider still rejects it, build the dict by hand (`role`, `content`, and `tool_calls` with only `id`, `type` and `function`).

---

## Phase 2: Should-fix items

### Fix 5 and 6 (SHOULD): System-prompt additions

The model does not know today's date, so "last week" or "yesterday" would get an arbitrary date. Also, showing the interpreted range on camera makes any date-extraction mistake visible. Add these two rules to the list in `_build_system_prompt`:

```python
"- You do not know today's date. If the user uses relative dates such as "
"'yesterday' or 'last week', ask them for explicit dates instead of guessing.\n"
"- In every answer, state the exact date range you used (for example "
"'8 Aug 2026 to 14 Aug 2026').\n"
```

Optional wording tweak: change the "(August 2026 only)" phrase so it is not hardcoded next to the dynamically injected dates.

### Fix 9 (SHOULD): Cleaner Windows encoding fix in `main.py`

Delete `import io` and the two `sys.stdout = io.TextIOWrapper(...)` / `sys.stderr = ...` lines. Replace them with:

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

Same result, without swapping the stream objects (avoids buffering surprises on camera).

### Fix 10 (SHOULD): Loader raises instead of asserting

`assert` statements are stripped when Python runs with `-O`. **Replace `data_loader.py` with this tested version:**

```python
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
```

---

## Phase 3: Nits and docs

### Fix 11 (NIT): Dependencies

`requirements.txt` should be:

```
openai>=1.0.0
pandas>=2.0.0
openpyxl>=3.1.0
python-dotenv>=1.0.0
```

(`google-genai` is unused.) The unused `tools.py` imports are already gone in the version above.

### Fix 12 (NIT): README updates

- **Quick Start:** `LLM_API_KEY` instead of `OPENAI_API_KEY`, and mention the free-tier provider.
- **LLM Choice:** name the free provider and model, and explain the choice: free tier, native function calling, OpenAI-compatible endpoint so switching providers is a config change.
- **Edge-case handling:** update the partial-overlap description to say invoices are billed only for the covered period and the file includes a note.
- **Add one sentence on design trade-offs:** the loop is deliberately plain function-calling with no agent framework, matching the brief's "keep the solution simple". Also state the limitation you chose: the LLM resolves dates, and Python validates every range.
- Keep the written explanation under 700 words. The current "Approach" section is about 400 words, so you have room.
- Optional: commit one sample invoice (for example in `samples/`), since `output/` is gitignored and a reviewer may like to see a real file.

---

## Verification: results from the scratch-copy test

Run against the provided dataset with the patched `tools.py`:

| Case | Result |
|---|---|
| 8 to 14 Aug total | 424.27 kWh (168 of 168 hours), matches an independent pandas sum |
| 1 to 5 Sept | Clean "no data" error naming the dataset range |
| 28 Aug to 3 Sept (consumption) | 222.30 kWh, 96 of 168 hours, warning, nothing estimated |
| Reversed dates | Order error |
| `None` start date | "Both a start date and an end date are required." |
| `"2026-08-08 13:00"` as start | Normalised to 8 Aug, 24 of 24 hours |
| One hour deleted from a single day (simulated) | 23 of 24 hours, warning (the old day-count check would have missed this) |
| Invoice 15 to 21 Aug | 420.29 kWh, SGD 105.07, no note, daily rows sum to the header total |
| Invoice 28 Aug to 3 Sept | Billing period clipped to 2026-08-28 to 2026-08-31, SGD 55.58, **Note** row present in the file |

Known cosmetic quirk: for a single-day gap the warning reads "from 05 August 2026 to 05 August 2026". Harmless.

---

## Phase 4: Pre-recording checklist (needs your live API key)

Run these in a fresh terminal and confirm each behaves as expected before you press record:

1. `pip install -r requirements.txt` in a **fresh virtual environment**, then `python main.py` starts cleanly.
2. "What was the total energy consumption from 8 August to 14 August?" returns **424.27 kWh** and states the date range.
3. "How much power did I use between the 8th and the 14th?" gives the same result (proves it is not keyword matching).
4. "Generate an invoice from 15 August to 21 August" creates the file. Open the `.xlsx` and check the four required fields.
5. "Total consumption from 1 to 5 September" refuses cleanly.
6. "Invoice from 28 August to 3 September" produces a clipped invoice with a Note row, and the assistant explains the exclusion.
7. "What's the capital of France?" declines politely.
8. **Multi-turn:** ask a consumption question, then "now generate the invoice for the same period". It should reuse the dates.
9. **Relative date:** "how much did I use last week?" should ask for explicit dates.
10. **Tool-calling round trip on your chosen provider:** confirm turns 2 and 4 completed without a 400 error (this is where Fix 4 matters).

If any step fails, fix it before recording. The video should be one clean take.

## Phase 5: Recording

- 3 to 5 minutes, terminal font large enough to read.
- Show steps 2, 3 (briefly), 4 (open the xlsx), 5, 6 (open the clipped xlsx), 7. Optionally 8.
- Say the design choice out loud once: LLM picks the tool and extracts dates, Python does all arithmetic.
- Make sure no API key, `.env` file or terminal history showing the key appears on screen.

## Phase 6: Pre-submission checklist

- [ ] `git status` clean; `.env` is **not** tracked (`git ls-files | grep .env` returns only `.env.example`)
- [ ] `grep -rniE "AIza|gsk_|sk-[A-Za-z0-9]" .` returns nothing real, in files **and** in `git log -p`
- [ ] Fresh-clone test: clone the repo into a new folder, create a venv, install, add your own `.env`, run one query
- [ ] README matches the final implementation (provider, partial-invoice behaviour)
- [ ] Written explanation is at most 700 words
- [ ] Screen recording exported and playable
- [ ] Email reply to Shruthi before Wednesday 30 September 2026, with the repo link, the recording and the explanation
