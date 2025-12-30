"""Quick test of SEL Desktop core functions"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'project_echo'))

from sel_bot.llm_client import OpenRouterClient
from sel_bot.config import Settings
from sel_desktop import capture_screen, describe_screen

async def test():
    print("\n[TEST] SEL Desktop - Quick Function Test\n")

    print("[1/3] Testing screen capture...")
    img = capture_screen()
    print(f"[OK] Screen captured: {img.size[0]}x{img.size[1]}")

    print("\n[2/3] Testing LLM client...")
    settings = Settings()
    llm = OpenRouterClient(settings)
    print(f"[OK] Using model: {llm.settings.openrouter_vision_model}")

    print("\n[3/3] Testing screen description...")
    description = await describe_screen(llm)
    print(f"[OK] Screen description: {description[:100]}...")

    print("\n[SUCCESS] All core functions working!")
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
