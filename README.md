# Agentic AI Energy Assistant

An AI-powered command-line assistant that answers natural-language questions about energy consumption and generates Excel invoices - built for the ERI@NTU Agentic AI Development & Cloud Integration technical assignment.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your LLM API key
cp .env.example .env
# Edit .env and paste your Groq API key:
# LLM_API_KEY=gsk_...

# 3. Run
python main.py
```

You can get a free Groq API key at [console.groq.com](https://console.groq.com).

---

## Approach & How It Works

### Architecture

The solution is a single-loop agent built around OpenAI-compatible function calling via the Groq free tier (`openai/gpt-oss-120b`). The user types a natural-language query into a CLI; the LLM interprets the request and selects one of two registered tools; the corresponding Python function performs the actual calculation with Pandas and returns the result; the LLM then formats a human-friendly response.

This keeps a clean separation of concerns: the LLM handles language understanding and tool selection, while all arithmetic and data access happen in deterministic Python code - exactly as the brief requires.

### Design Trade-offs

- **No heavy frameworks.** The agent loop is deliberately built as a plain, native function-calling loop with no LangChain, LangGraph, or similar orchestration frameworks, matching the brief's instruction to "keep the solution simple".
- **Provider-agnostic.** The codebase uses the OpenAI Python SDK pointed at any OpenAI-compatible endpoint. Switching from Groq to Gemini (or any other provider) is a one-line change in `.env`.
- **LLM resolves dates; Python validates every range.** The model extracts dates from natural language. The Python tools then independently validate, filter, and calculate - the LLM never performs arithmetic.

### LLM Choice

We use [Groq](https://groq.com)'s free-tier API with the `openai/gpt-oss-120b` model. It provides reliable function-calling fidelity via an OpenAI-compatible endpoint, requires no paid subscription (fulfilling the assignment requirement), and offers extremely fast inference.

### Tools

The LLM has access to two tools:

| Tool | Purpose |
|---|---|
| `get_total_consumption` | Sums hourly kWh readings for a date range and returns the total. |
| `generate_invoice` | Computes the same total, multiplies by the SGD 0.25/kWh tariff, and writes a formatted `.xlsx` file with a summary and daily breakdown. |

Both tools share the same date-validation and filtering logic via a `_parse_range()` helper. The date range uses an interval-start convention: `timestamp >= start_date` AND `timestamp < end_date + 1 day`, so that the full 24 hours of the end date are always included.

### Edge-Case Handling

The brief emphasises not assuming or fabricating missing data. The assistant handles this in three ways:

1. **Fully out-of-range requests** (e.g. September dates) are refused with a clear message stating the dataset boundaries.
2. **Partially overlapping ranges** (e.g. 28 August - 3 September) bill only the period with data. The generated Excel file clips the billing period to the covered dates and adds a **Note** row explaining the exclusion. The assistant also warns the user in chat.
3. **Reversed dates**, **missing dates**, and **unparseable input** are caught and surfaced as friendly error messages rather than stack traces.

Off-topic queries (e.g. "What's the capital of France?") receive a polite refusal - the system prompt constrains the LLM to energy-related queries only.

### Multi-Turn Conversation

The assistant maintains conversation history, so users can ask follow-up questions naturally (e.g. "now generate the invoice for the same period") without repeating context.

### Invoice Format

The generated `.xlsx` file contains:
- A **summary section** with billing period, total kWh, tariff, and total payable.
- A **daily breakdown table** showing each day's consumption and cost.
- A **Note** row (when the requested range is partially outside the dataset).

Headers are bolded and columns are auto-sized for readability.

---

## Project Structure

```
├── main.py            # CLI REPL loop (entry point)
├── agent.py           # LLM integration + function-call routing
├── tools.py           # get_total_consumption() & generate_invoice()
├── data_loader.py     # Loads and validates the CSV at startup
├── config.py          # Tariff, paths, model name (API key from .env)
├── .env.example       # Template for the API key
├── .gitignore
├── requirements.txt
├── README.md
├── data/
│   └── simulated_energy_data_aug.csv
└── output/            # Generated invoices are saved here (gitignored)
```

---

## Example Queries

```
You: What was the total energy consumption from 8 August to 14 August?
You: How much power did I use between the 8th and the 14th?
You: Generate an invoice from 15 August to 21 August
You: Total consumption from 1 to 5 September       (-> refuses, no data)
You: Invoice from 28 August to 3 September          (-> partial, warns + clips)
You: What's the capital of France?                   (-> politely declines)
```
