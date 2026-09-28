# Agentic AI Energy Assistant — Written Explanation

**Applicant:** Siddhesh  
**Institution:** Energy Research Institute @ NTU (ERI@N)  
**Role:** Agentic AI Development and Cloud Integration Internship  

---

### 1. Architectural Approach & Overview

The objective was to create an Agentic AI Energy Assistant capable of interpreting natural-language requests, determining appropriate tools, and performing tasks on simulated hourly energy consumption data (August 2026) without doing arithmetic inside the LLM.

To achieve this cleanly and avoid unnecessary framework overhead, we implemented a modular, lightweight Python agent built on native function calling (`gpt-4o-mini`). The system maintains a strict separation of concerns across four core layers:

1. **CLI Interface & REPL (`main.py`):** Provides an interactive command-line session with Windows UTF-8 encoding support and pre-flight API key checks.
2. **Agent & Decision Engine (`agent.py`):** Feeds the conversation history and dynamic dataset boundary context into the LLM. The system prompt directs the LLM to extract dates (YYYY-MM-DD), delegate calculations exclusively to tools, and refuse off-topic requests.
3. **Deterministic Tool Execution (`tools.py`):** Pure Python and Pandas functions that execute filtering, aggregations, and Excel invoice generation.
4. **Data Validation & Ingestion (`data_loader.py`):** Loads the CSV once at startup, validates timestamp integrity (no nulls, no duplicates, monotonic sorting), and guarantees non-negative consumption readings.

```
User Query (CLI)
       │
       ▼
LLM Decision Engine (Tool Calling)
       │
  ┌────┴──────────────────────────┐
  ▼                               ▼
Tool 1: get_total_consumption    Tool 2: generate_invoice
  │                               │
  ▼                               ▼
Pandas Aggregation (kWh)        Pandas + OpenPyXL (.xlsx)
  │                               │
  └───────────────┬───────────────┘
                  ▼
         LLM Formatted Reply
```

---

### 2. Tool Design & Technical Implementation

The assistant exposes two explicit tool schemas to the model:

- **`get_total_consumption(start_date, end_date)`:** Computes total energy consumption in kWh for the requested window.
- **`generate_invoice(start_date, end_date)`:** Computes total kWh, applies the statutory SGD 0.25/kWh tariff, and writes a professionally styled Excel file (`.xlsx`) containing an executive summary table and an itemized daily breakdown table.

#### Date Handling Precision (Interval-Start Convention)
The dataset notes that hourly timestamps denote the *start* of the interval (e.g., `13:00` represents `13:00–14:00`). To ensure that queries such as *"from 8 August to 14 August"* include the entire 24 hours of 14 August, the filter condition is strictly formulated as:
$$\text{start} \le \text{timestamp} < (\text{end} + 1\text{ day})$$
Using a naive `timestamp <= end` would omit 23 hours of the final day.

---

### 3. Handling Missing Data & Edge Cases

The assignment specification strongly emphasizes handling invalid requests without hallucinating or extrapolating data:

1. **Out-of-Bound Dates:** Queries completely outside the August 2026 dataset (e.g., September dates) return an explicit error stating the data boundary rather than fabricating numbers.
2. **Partial Overlaps:** If a query spans both covered and uncovered dates (e.g., 28 August to 3 September), the tool calculates consumption strictly for the available August dates and injects a warning message highlighting that 3 days were excluded from the total.
3. **Input Inversions:** If `start_date` occurs after `end_date`, the tool rejects the query with a corrective prompt.
4. **Off-Topic / Ambiguous Queries:** Off-topic prompts (e.g., general trivia) are rejected conversationally without invoking tools. Ambiguous dates trigger clarifying questions.

---

### 4. LLM Selection Rationale

The solution uses OpenAI's `gpt-4o-mini` with native tool calling. In accordance with the assignment guidelines stating that a paid subscription is not required, this lightweight model was chosen for its near-zero inference latency, deterministic tool-calling adherence, and cost efficiency. All business logic, tariff calculations, and aggregations remain 100% deterministic within Python.
