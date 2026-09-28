import sys
import io
from data_loader import load_energy_data
from agent import EnergyAgent
from config import OPENAI_API_KEY

# Fix Windows console encoding - LLM responses may contain Unicode characters
# that cp1252 cannot handle.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main():
    # Pre-flight: API key check
    if not OPENAI_API_KEY:
        print("✗ OPENAI_API_KEY not found.")
        print("  Add your OpenAI API key to the .env file in this directory:")
        print("    OPENAI_API_KEY=sk-proj-...")
        print()
        print("  You can generate or find your key at https://platform.openai.com/api-keys")
        sys.exit(1)

    # Load data
    print("Loading energy data...")
    try:
        df, min_date, max_date = load_energy_data()
    except Exception as e:
        print(f"✗ Failed to load data: {e}")
        sys.exit(1)

    print(f"✓ Loaded {len(df)} hourly readings")
    print(f"  Coverage: {min_date.strftime('%d %b %Y')} – {max_date.strftime('%d %b %Y %H:%M')}")
    print()

    # Initialise agent
    agent = EnergyAgent(df, min_date, max_date)

    print("=" * 60)
    print("  ⚡ Agentic AI Energy Assistant")
    print("  Ask about energy consumption or request an invoice.")
    print("  Type 'quit' or 'exit' to leave.")
    print("=" * 60)
    print()

    # REPL loop
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print()
        response = agent.chat(user_input)
        print(f"Assistant: {response}")
        print()


if __name__ == "__main__":
    main()
