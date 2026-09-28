# Agentic AI Energy Assistant — Implementation Plan

**Prepared for:** ERI@N (Energy Research Institute @ NTU) — Agentic AI Development and Cloud Integration Internship
**Assignment due:** Wednesday, 30 September 2026

## Data check

Before designing anything, the provided dataset was inspected directly:

- 744 rows = exactly one full month of hourly readings (1–31 August 2026)
- No missing timestamps, no duplicates
- Values range from 0.10 to 5.24 kWh, no negatives or obvious anomalies

This means the "don't assume missing data" requirement in the brief is really about **handling user-requested ranges that fall outside this window** (e.g. September dates), not about gaps inside the file itself.

## Architecture

The flow is a single, linear agent loop with a two-way branch:

1. User types a natural-language query into a CLI.
2. The LLM (with function/tool calling) extracts the date range and decides which of two tools to call — it never does arithmetic itself.
3. The selected Python tool validates the range against the loaded data and performs the calculation with pandas.
4. The result is returned either as a console message or as a generated `.xlsx` invoice.

```
User query (CLI)
       │
       ▼
LLM (Gemini 2.5 Flash, free tier)
  Extracts dates, picks a tool
       │
   ┌───┴────┐
   ▼        ▼
Total        Invoice
consumption  generation
tool         tool
(pandas sum) (pandas sum
             + xlsx export)
   │            │
   ▼            ▼
Console      invoice.xlsx
answer       file
```

## LLM choice

**Primary: Gemini 2.5 Flash via Google AI Studio.**
Free, no credit card required, native function/tool calling support, generous daily quota — more than sufficient for a CLI demo. `pip install google-genai`.

**Fallback: Groq (Llama 3.3 70B).**
Also free, OpenAI-compatible function-calling interface, and noticeably faster inference — useful as a backup if Gemini API key setup causes any last-minute friction.

**Deliberately not using LangGraph** for this task, even though it's part of my existing toolkit. The assignment explicitly asks for simplicity, and a plain two-tool function-calling loop is easier to verify and debug under a deadline. This trade-off is worth naming explicitly in the written explanation.

## Project structure

```
energy_assistant/
├── main.py            # CLI REPL loop
├── agent.py           # LLM call + tool-call parsing + routing
├── tools.py           # calculate_total() and generate_invoice() — pure Python/pandas
├── data_loader.py      # loads + validates the CSV once at startup
├── config.py           # TARIFF = 0.25, DATA_PATH, MODEL_NAME
├── .env.example         # GEMINI_API_KEY=your_key_here
├── .gitignore           # .env
├── requirements.txt
└── data/simulated_energy_data_aug.csv
```

## Tool schemas (what the LLM sees)

| Tool | Arguments | Returns |
|---|---|---|
| `get_total_consumption` | `start_date`, `end_date` (YYYY-MM-DD) | Total kWh + a coverage note |
| `generate_invoice` | `start_date`, `end_date` (YYYY-MM-DD) | Writes `invoice_<start>_<end>.xlsx`, confirms the file path |

The system prompt tells the LLM: the dataset only covers August 2026; if the user omits a year, assume 2026; extract dates as ISO strings; if the request doesn't clearly map to either tool, ask a clarifying question instead of guessing.

## The date-range detail worth getting right

The data uses interval-start timestamps — a 13:00 reading covers the 13:00–14:00 hour. So the end date of a range must be **inclusive of the whole day**:

```
timestamp >= start_date  AND  timestamp < (end_date + 1 day)
```

Using `<= end_date 00:00:00` instead would silently drop the last day's 23 hours. This is called out explicitly here because it's an easy way to lose correctness points without realising it.

## Edge cases and error handling

The brief mentions "don't assume missing data" twice in different words, which suggests this is a deliberate grading focus.

| Case | Expected behaviour |
|---|---|
| Range fully outside the data (e.g. 3–10 September) | Refuse clearly: "No data available for that period — dataset covers 1–31 August 2026." Never return zero or a fabricated number. |
| Range partially overlapping (e.g. 28 Aug – 3 Sept) | Compute the total only for the days that exist, and explicitly state which days were excluded. Never extrapolate the missing days. |
| `start_date` after `end_date` | Reject with a message asking the user to check the order. |
| Unparseable or ambiguous date | The LLM asks a follow-up question rather than picking a default. |
| Off-topic query (e.g. "what's the weather") | No tool call fires; the LLM responds conversationally that it only handles consumption/invoice queries. |
| Malformed LLM output (bad JSON, missing arguments) | Caught by a try/except in `agent.py`; surfaced as a friendly retry message, never a stack trace. |

## Invoice file specification

A single worksheet with four rows is sufficient — no need to overbuild it:

| Field | Example value |
|---|---|
| Billing period | 15 Aug 2026 – 21 Aug 2026 |
| Total energy consumption (kWh) | 412.35 |
| Energy tariff (SGD/kWh) | 0.25 |
| Total amount payable (SGD) | 103.09 |

Built with `openpyxl` (or `pandas.ExcelWriter(engine="openpyxl")`). Bold headers and a currency number format are a nice touch; anything beyond that isn't needed given the brief explicitly asks for "a simple Excel file."

## Test script (doubles as the screen-recording script)

Running these six queries in order forms a compact demo that touches every requirement in the brief:

1. Example phrasing verbatim — *"What was the total energy consumption from 8 August to 14 August?"*
2. A reworded variant, to demonstrate this isn't keyword matching — *"How much power did I use between the 8th and the 14th?"*
3. Invoice generation — *"Generate an invoice from 15 August to 21 August"* — then open the resulting `.xlsx`.
4. Fully out-of-range — *"Total consumption from 1 to 5 September"* — should refuse cleanly.
5. Partial overlap — *"Invoice from 28 August to 3 September"* — should compute for the 4 available days and say so.
6. Off-topic — *"What's the capital of France?"* — should decline gracefully, without crashing.

## Deliverables checklist

- [ ] Source code, organised as above
- [ ] `.env` scrubbed before submission — keep only `.env.example` with a placeholder key; double-check no key is hardcoded in `config.py` or anywhere in commit history
- [ ] Screen recording following the test script above (3–5 minutes)
- [ ] Written explanation, maximum 700 words — best drafted after the code is finished, so it accurately reflects the implementation rather than the plan

## Timeline

With the deadline on Wednesday 30 September: build the core tools and agent loop first, test against every edge case above, record the demo, and write the explanation last so it describes what was actually built.
