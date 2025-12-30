"""
Automated test for SEL Desktop - Wordle completion
"""
import asyncio
import sys
import os

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'project_echo'))

from sel_bot.llm_client import OpenRouterClient
from sel_desktop import interactive_mode

async def run_test():
    """Run automated Wordle test"""
    print("=" * 60)
    print("SEL AUTOMATED WORDLE TEST")
    print("=" * 60)
    print("\n✓ Loading configuration...")

    try:
        llm_client = OpenRouterClient()
        print(f"✓ Using vision model: {llm_client.settings.openrouter_vision_model}")
        print("\n🎯 Starting Wordle completion test...\n")

        # Simulate the user command
        import sel_desktop
        # Temporarily override input to provide test command
        original_input = __builtins__.input

        inputs = iter(['complete a wordle'])
        __builtins__.input = lambda _: next(inputs)

        # Run interactive mode
        await interactive_mode(llm_client)

        # Restore input
        __builtins__.input = original_input

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
