import json
import re
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, MODEL_NAME, TARIFF_SGD_PER_KWH
from tools import get_total_consumption, generate_invoice


# System prompt (data range is injected dynamically at startup)

def _build_system_prompt(min_date, max_date):
    coverage_start = min_date.strftime("%d %B %Y")
    coverage_end = max_date.strftime("%d %B %Y")
    default_year = min_date.year
    date_example = f"{min_date.strftime('%d %b %Y')} to {max_date.strftime('%d %b %Y')}"

    return (
        "You are an Energy Assistant. You help users query energy consumption "
        "data and generate invoices.\n\n"
        f"Data coverage: The dataset contains hourly energy consumption readings "
        f"from {coverage_start} to {coverage_end}.\n\n"
        "**Rules:**\n"
        "- When the user asks about energy consumption for a date range, "
        "use the `get_total_consumption` tool.\n"
        "- When the user asks to generate or create an invoice, "
        "use the `generate_invoice` tool.\n"
        "- Extract dates as YYYY-MM-DD strings. If the user omits the year, "
        f"assume {default_year}.\n"
        "- If the user's request does not clearly map to either tool, "
        "ask a clarifying question instead of guessing.\n"
        "- Never perform energy calculations yourself - always use the tools.\n"
        "- You do not know today's date. If the user uses relative dates such as "
        "'yesterday' or 'last week', ask them for explicit dates instead of guessing.\n"
        "- In every answer, state the exact date range you used (for example "
        f"'{date_example}').\n"
        "- Present the tool's results clearly to the user, including any "
        "warnings about partial data coverage.\n"
        "- Respond in plain text for a command-line terminal. Do not use Markdown: "
        "no asterisks, hash headings, tables, or Markdown links. Use short labels "
        "and line breaks instead.\n"
        "- After successfully reporting consumption, offer once to generate an invoice for the same period.\n"
        "- After successfully generating an invoice, state the billing period, "
        "total consumption, tariff, total payable, and the clean output filename. "
        "Do not recommend further analysis.\n"
        "- If a tool returns an error, relay it in a helpful, friendly way.\n"
        "- For requests unrelated to energy consumption or invoices, politely "
        "explain that you can only help with energy-related queries.\n"
        f"- The energy tariff is SGD {TARIFF_SGD_PER_KWH:.2f} per kWh.\n"
    )


# Tool definitions (OpenAI function-calling format)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_total_consumption",
            "description": (
                "Calculate the total energy consumption in kWh for a "
                "user-specified date range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format (inclusive)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format (inclusive)",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_invoice",
            "description": (
                "Generate an energy invoice as an Excel (.xlsx) file for a "
                "user-specified date range. The invoice includes the billing "
                "period, total consumption, tariff, total payable amount, "
                "and a daily breakdown."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date of the billing period in YYYY-MM-DD format (inclusive)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date of the billing period in YYYY-MM-DD format (inclusive)",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
]


# Agent class

class EnergyAgent:
    """Thin wrapper around OpenAI that routes tool calls to local functions."""

    def __init__(self, df, min_date, max_date):
        self.df = df
        self.client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.system_prompt = _build_system_prompt(min_date, max_date)
        # Conversation history - enables multi-turn follow-ups
        self.history: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

    # Tool dispatcher

    def _execute_tool(self, name: str, args: dict) -> dict:
        if name == "get_total_consumption":
            return get_total_consumption(self.df, args["start_date"], args["end_date"])
        elif name == "generate_invoice":
            return generate_invoice(self.df, args["start_date"], args["end_date"])
        else:
            return {"error": f"Unknown tool: {name}"}

    @staticmethod
    def _format_terminal_response(response: str) -> str:
        """Remove Markdown formatting and make model output terminal-friendly."""
        if not response:
            return "(no response)"

        # Convert Markdown links to readable text and remove emphasis/code marks.
        response = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", response)
        # Keep underscores intact because invoice filenames contain them.
        response = re.sub(r"[*`#]", "", response)
        response = response.replace("\u00a0", " ")

        # Turn Markdown tables into simple label/value lines.
        lines = response.splitlines()
        cleaned = []
        table_headers = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    continue
                if table_headers is None:
                    table_headers = cells
                else:
                    for header, value in zip(table_headers, cells):
                        cleaned.append(f"{header}: {value}")
                    table_headers = None
                continue
            cleaned.append(line.rstrip())

        # Collapse excessive blank lines without changing the response content.
        return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()

    # Main chat method

    def chat(self, user_input: str) -> str:
        # Send a user message, handle tool calls, and return text
        self.history.append({"role": "user", "content": user_input})

        # Call the LLM
        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=self.history,
                tools=_TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            self.history.pop()  # roll back so history stays consistent
            return f"Could not reach the AI service: {e}\nPlease try again."

        # Function-call loop (max 5 iterations as a safety net)
        for _ in range(5):
            message = response.choices[0].message

            # Check if the model wants to call tool(s)
            if not message.tool_calls:
                # No tool call -> final text answer
                self.history.append({"role": "assistant", "content": message.content or ""})
                return self._format_terminal_response(message.content or "")

            # Process each tool call
            # Add the assistant message (with tool_calls) to history
            assistant_msg = message.model_dump(exclude_none=True)
            if not assistant_msg.get("content"):
                assistant_msg["content"] = message.content or ""
            self.history.append(assistant_msg)

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                    tool_result = self._execute_tool(fn_name, fn_args)
                except Exception as e:
                    tool_result = {"error": f"Tool execution failed: {e}"}

                # Add tool response to history
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result),
                })

            # Get next response from the model
            try:
                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=self.history,
                    tools=_TOOLS,
                    tool_choice="auto",
                )
            except Exception as e:
                return f"Error during follow-up call: {e}\nPlease try again."

        return "The assistant took too many steps. Please rephrase your request."
