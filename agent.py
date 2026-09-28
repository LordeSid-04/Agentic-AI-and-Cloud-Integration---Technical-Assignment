import json
from openai import OpenAI
from config import OPENAI_API_KEY, MODEL_NAME
from tools import get_total_consumption, generate_invoice


# System prompt (data range is injected dynamically at startup)

def _build_system_prompt(min_date, max_date):
    return (
        "You are an Energy Assistant. You help users query energy consumption "
        "data and generate invoices.\n\n"
        f"**Data coverage:** The dataset contains hourly energy consumption "
        f"readings from {min_date.strftime('%Y-%m-%d %H:%M')} to "
        f"{max_date.strftime('%Y-%m-%d %H:%M')} (August 2026 only).\n\n"
        "**Rules:**\n"
        "- When the user asks about energy consumption for a date range, "
        "use the `get_total_consumption` tool.\n"
        "- When the user asks to generate or create an invoice, "
        "use the `generate_invoice` tool.\n"
        "- Extract dates as YYYY-MM-DD strings. If the user omits the year, "
        "assume 2026.\n"
        "- If the user's request does not clearly map to either tool, "
        "ask a clarifying question instead of guessing.\n"
        "- Never perform energy calculations yourself - always use the tools.\n"
        "- You do not know today's date. If the user uses relative dates such as "
        "'yesterday' or 'last week', ask them for explicit dates instead of guessing.\n"
        "- In every answer, state the exact date range you used (for example "
        "'8 Aug 2026 to 14 Aug 2026').\n"
        "- Present the tool's results clearly to the user, including any "
        "warnings about partial data coverage.\n"
        "- If a tool returns an error, relay it in a helpful, friendly way.\n"
        "- For requests unrelated to energy consumption or invoices, politely "
        "explain that you can only help with energy-related queries.\n"
        "- The energy tariff is SGD 0.25 per kWh.\n"
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
        self.client = OpenAI(api_key=OPENAI_API_KEY)
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
                self.history.append({"role": "assistant", "content": message.content})
                return message.content or "(no response)"

            # Process each tool call
            # Add the assistant message (with tool_calls) to history
            self.history.append(message.model_dump(exclude_none=True))

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
