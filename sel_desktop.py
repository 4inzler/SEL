"""
SEL Desktop Assistant - Local version with screen viewing and control
Press Numpad 8 to emergency stop
"""

import asyncio
import io
import base64
import time
import sys
from pathlib import Path
from datetime import datetime

# Add project_echo to path
sys.path.insert(0, str(Path(__file__).parent / "project_echo"))

try:
    import pyautogui
    import mss
    from PIL import Image
    from pynput import keyboard
    import pydantic
    import httpx
    import pyperclip
    import psutil
except ImportError as e:
    print(f"Installing required packages... (missing: {e.name})")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyautogui", "mss", "pillow", "pynput", "pydantic", "httpx", "pydantic-settings", "pyperclip", "psutil"])
    import pyautogui
    import mss
    from PIL import Image
    from pynput import keyboard
    import pydantic
    import httpx
    import pyperclip

from sel_bot.config import Settings
from sel_bot.llm_client import OpenRouterClient
import terminal_helper
import sel_tools
import task_memory
import ocr_helper

# Global emergency stop flag
EMERGENCY_STOP = False
PAUSED = False

def on_press(key):
    """Handle keyboard events for emergency stop"""
    global EMERGENCY_STOP, PAUSED
    try:
        # Numpad 8 for emergency stop
        if hasattr(key, 'vk') and key.vk == 104:  # Numpad 8 VK code
            EMERGENCY_STOP = True
            print("\n🛑 EMERGENCY STOP ACTIVATED (Numpad 8)")
            return False  # Stop listener
        # Numpad 5 to pause/resume
        if hasattr(key, 'vk') and key.vk == 101:  # Numpad 5 VK code
            PAUSED = not PAUSED
            print(f"\n⏸️  {'PAUSED' if PAUSED else 'RESUMED'} (Numpad 5)")
    except AttributeError:
        pass

def capture_screen() -> Image.Image:
    """Capture the entire screen"""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        return img

def image_to_base64(img: Image.Image) -> str:
    """Convert PIL Image to base64 string - optimized for speed"""
    # Resize to 1280px for faster upload/processing (was 2000px)
    max_size = 1280
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = tuple(int(dim * ratio) for dim in img.size)
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    buffered = io.BytesIO()
    # Lower quality for speed (was 85)
    img.save(buffered, format="JPEG", quality=70)
    return base64.b64encode(buffered.getvalue()).decode()

async def describe_screen(llm_client: OpenRouterClient) -> str:
    """Capture screen and get AI description"""
    print("[*] Capturing screen...")
    img = capture_screen()
    img_b64 = image_to_base64(img)

    print("[*] Analyzing screen...")
    description = await llm_client.describe_image(
        f"data:image/jpeg;base64,{img_b64}",
        prompt=(
            "Analyze screen for precise automation:\n"
            "1. ALL visible buttons/links - exact text, color, position (x,y estimates)\n"
            "2. Current application/window title\n"
            "3. Any text fields, dropdowns, checkboxes - where?\n"
            "4. Popups, dialogs, notifications\n"
            "5. What changed since likely last action?\n"
            "6. Any errors or warnings visible?\n\n"
            "Be specific: 'Blue PLAY button centered at ~960,540', 'Address bar top-left ~400,50'\n"
            "Estimate coordinates for 1920x1080 screen."
        )
    )
    return description

async def execute_action(action: dict, confirm: bool = False) -> str:
    """Execute a mouse/keyboard action with optional confirmation"""
    global EMERGENCY_STOP, PAUSED

    if EMERGENCY_STOP:
        return "❌ Stopped by emergency stop"

    if PAUSED:
        return "⏸️  Action paused"

    action_type = action.get("type")

    # Log action (no confirmation in full control mode)
    print(f"🎮 Executing: {action_type}", end="")
    if action_type in ["move_mouse", "click"]:
        print(f" at ({action.get('x', '?')}, {action.get('y', '?')})" if "x" in action else "")
    elif action_type == "type":
        print(f": {action.get('text', '')[:50]}")
    else:
        print()

    if confirm:
        response = input("  Confirm? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            return "❌ Action cancelled by user"

    try:
        if action_type == "move_mouse":
            x, y = action.get("x", 0), action.get("y", 0)
            duration = action.get("duration", 0.3)
            pyautogui.moveTo(x, y, duration=duration)
            return f"✓ Moved mouse to ({x}, {y})"

        elif action_type == "click":
            # Can include x,y to move and click in one action
            x = action.get("x")
            y = action.get("y")
            button = action.get("button", "left")
            clicks = action.get("clicks", 1)

            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
                return f"✓ Clicked {button} at ({x}, {y})" + (f" x{clicks}" if clicks > 1 else "")
            else:
                pyautogui.click(button=button, clicks=clicks)
                return f"✓ Clicked {button} button" + (f" x{clicks}" if clicks > 1 else "")

        elif action_type == "double_click":
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                pyautogui.doubleClick(x=x, y=y)
                return f"✓ Double-clicked at ({x}, {y})"
            else:
                pyautogui.doubleClick()
                return f"✓ Double-clicked"

        elif action_type == "right_click":
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                pyautogui.rightClick(x=x, y=y)
                return f"✓ Right-clicked at ({x}, {y})"
            else:
                pyautogui.rightClick()
                return f"✓ Right-clicked"

        elif action_type == "drag":
            x1, y1 = action.get("x1", 0), action.get("y1", 0)
            x2, y2 = action.get("x2", 0), action.get("y2", 0)
            duration = action.get("duration", 1)
            pyautogui.moveTo(x1, y1, duration=0.2)
            pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
            return f"✓ Dragged from ({x1}, {y1}) to ({x2}, {y2})"

        elif action_type == "type":
            text = action.get("text", "")
            interval = action.get("interval", 0.05)
            pyautogui.write(text, interval=interval)
            return f"✓ Typed: {text}"

        elif action_type == "press_key":
            key = action.get("key", "")
            presses = action.get("presses", 1)
            pyautogui.press(key, presses=presses)
            return f"✓ Pressed key: {key}" + (f" x{presses}" if presses > 1 else "")

        elif action_type == "hotkey":
            keys = action.get("keys", [])
            pyautogui.hotkey(*keys)
            return f"✓ Pressed hotkey: {'+'.join(keys)}"

        elif action_type == "scroll":
            clicks = action.get("clicks", 0)
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                pyautogui.scroll(clicks, x=x, y=y)
                return f"✓ Scrolled {clicks} clicks at ({x}, {y})"
            else:
                pyautogui.scroll(clicks)
                return f"✓ Scrolled {clicks} clicks"

        elif action_type == "wait":
            duration = action.get("duration", 1)
            await asyncio.sleep(duration)
            return f"✓ Waited {duration} seconds"

        elif action_type == "read_terminal":
            # Read terminal text
            terminal_text = terminal_helper.read_terminal_text()
            # Close terminal if requested
            if action.get("close", True):
                force = action.get("force_close", True)
                terminal_helper.close_terminal(force=force)
            return f"✓ Read terminal ({len(terminal_text)} chars): {terminal_text[:100]}..."

        elif action_type == "close_terminal":
            force = action.get("force", True)
            terminal_helper.close_terminal(force=force)
            return f"✓ Closed terminal (force={force})"

        elif action_type == "send_enter":
            terminal_helper.send_enter_to_terminal()
            return f"✓ Sent Enter key"

        elif action_type == "terminal_type":
            text = action.get("text", "")
            terminal_helper.type_in_terminal(text)
            return f"✓ Typed in terminal: {text}"

        elif action_type == "terminal_command":
            command = action.get("command", "")
            wait_seconds = action.get("wait", 1.0)
            terminal_helper.send_terminal_command(command, wait_seconds)
            return f"✓ Executed terminal command: {command}"

        elif action_type == "calculate":
            expression = action.get("expression", "")
            result = sel_tools.calculate(expression)
            return f"✓ Calculate: {result}"

        elif action_type == "read_file":
            file_path = action.get("path", "")
            result = sel_tools.read_file(file_path)
            return f"✓ {result[:200]}..."

        elif action_type == "list_files":
            directory = action.get("directory", ".")
            result = sel_tools.list_files(directory)
            return f"✓ {result[:200]}..."

        elif action_type == "system_info":
            result = sel_tools.get_system_info()
            return f"✓ System info: {result}"

        elif action_type == "ocr_read":
            # Read all text from screen
            result = ocr_helper.ocr_full_screen()
            return f"✓ OCR: {result[:300]}..."

        elif action_type == "ocr_region":
            # Read text from specific region
            x = action.get("x", 0)
            y = action.get("y", 0)
            width = action.get("width", 100)
            height = action.get("height", 100)
            result = ocr_helper.ocr_region(x, y, width, height)
            return f"✓ OCR Region: {result}"

        elif action_type == "ocr_find":
            # Find text on screen and get coordinates
            search_text = action.get("text", "")
            result = ocr_helper.ocr_find_text(search_text)
            if result.get("found"):
                return f"✓ Found '{result['text']}' at ({result['x']}, {result['y']}) with {result['confidence']}% confidence"
            else:
                return f"✗ {result.get('error', 'Text not found')}"

        else:
            return f"❌ Unknown action type: {action_type}"

    except Exception as e:
        return f"❌ Error executing action: {e}"

async def continuous_mode(llm_client: OpenRouterClient):
    """Continuous autonomous monitoring mode with chat interface"""
    global EMERGENCY_STOP, PAUSED

    print("\n" + "="*70)
    print("  SEL CONTINUOUS AUTONOMOUS MODE - Always Watching")
    print("="*70)
    print("\n🤖 SEL has FULL GUI CONTROL and monitors your screen continuously")
    print("   • Sees your screen every 3 seconds")
    print("   • Can click, type, scroll, drag anything")
    print("   • Will proactively assist when needed")
    print("   • You can chat with SEL anytime")
    print("\n🔑 Emergency Controls:")
    print("   • Numpad 8: EMERGENCY STOP (instant halt)")
    print("   • Numpad 5: Pause/Resume")
    print("   • Ctrl+C: Exit")
    print("\n💬 Chat commands:")
    print("   • Just type normally to chat with SEL")
    print("   • 'screen' - see what SEL sees")
    print("   • 'click X Y' - click at coordinates")
    print("   • 'type TEXT' - type text")
    print("   • 'quit' - exit")
    print("\n🖱️  SEL is now watching and ready to control your computer!")
    print("="*70 + "\n")

    # Start keyboard listener in background
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    conversation_history = []
    last_screen_check = 0
    check_interval = 3  # seconds (faster monitoring)
    user_input_queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Input handler in separate thread
    def input_thread():
        """Background thread for user input"""
        while not EMERGENCY_STOP:
            try:
                user_input = input()
                loop.call_soon_threadsafe(user_input_queue.put_nowait, user_input)
            except EOFError:
                break
            except RuntimeError:
                break
            except Exception:
                break

    import threading
    input_thread_obj = threading.Thread(target=input_thread, daemon=True)
    input_thread_obj.start()

    try:
        while not EMERGENCY_STOP:
            if PAUSED:
                await asyncio.sleep(1)
                continue

            current_time = time.time()

            # Check for user messages
            try:
                user_input = user_input_queue.get_nowait()
                if user_input:
                    if user_input.lower() == 'quit':
                        print("👋 Goodbye!")
                        break

                    if user_input.lower() == 'screen':
                        description = await describe_screen(llm_client)
                        print(f"\n👁️  SEL sees:\n{description}\n")
                        print("👤 You: ", end="", flush=True)
                        continue

                    if user_input.lower().startswith('click '):
                        parts = user_input.split()
                        if len(parts) == 3:
                            x, y = int(parts[1]), int(parts[2])
                            result = await execute_action({"type": "move_mouse", "x": x, "y": y}, confirm=False)
                            print(result)
                            result = await execute_action({"type": "click"}, confirm=False)
                            print(result)
                        print("👤 You: ", end="", flush=True)
                        continue

                    if user_input.lower().startswith('type '):
                        text = user_input[5:]
                        result = await execute_action({"type": "type", "text": text}, confirm=False)
                        print(result)
                        print("👤 You: ", end="", flush=True)
                        continue

                    # Chat with SEL
                    conversation_history.append({"role": "user", "content": user_input})

                    # Get screen context for chat
                    description = await describe_screen(llm_client)

                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are SEL with FULL GUI CONTROL over the Windows desktop. "
                                "You can see the screen and control the computer.\n\n"
                                f"CURRENT SCREEN:\n{description}\n\n"
                                "You control the GRAPHICAL desktop - NOT a terminal!\n"
                                "Click buttons, links, menus with x,y coordinates.\n\n"
                                "AVAILABLE ACTIONS:\n"
                                '• Click: {"type": "click", "x": 850, "y": 350}\n'
                                '• Double-click: {"type": "double_click", "x": 640, "y": 480}\n'
                                '• Right-click: {"type": "right_click", "x": 100, "y": 200}\n'
                                '• Drag: {"type": "drag", "x1": 100, "y1": 100, "x2": 500, "y2": 500}\n'
                                '• Type: {"type": "type", "text": "hello"}\n'
                                '• Press key: {"type": "press_key", "key": "enter"}\n'
                                '• Hotkey: {"type": "hotkey", "keys": ["ctrl", "c"]}\n'
                                '• Scroll: {"type": "scroll", "clicks": -3}\n'
                                '• Wait: {"type": "wait", "duration": 2}\n\n'
                                "Example: I'll open Notepad. "
                                '{"type": "hotkey", "keys": ["win", "r"]} '
                                '{"type": "wait", "duration": 1} '
                                '{"type": "type", "text": "notepad"} '
                                '{"type": "press_key", "key": "enter"}'
                            )
                        },
                        *conversation_history[-10:]
                    ]

                    response = await llm_client._chat_completion(
                        model=llm_client.settings.openrouter_main_model,
                        messages=messages,
                        temperature=llm_client.settings.openrouter_main_temp,
                        top_p=llm_client.settings.openrouter_top_p,
                    )

                    print(f"\n🤖 SEL: {response}")
                    conversation_history.append({"role": "assistant", "content": response})

                    # Parse and execute actions
                    import re
                    import json
                    action_pattern = r'\{[^}]*"type":\s*"[^"]*"[^}]*\}'
                    action_matches = re.findall(action_pattern, response)

                    if action_matches:
                        print(f"\n🎯 Found {len(action_matches)} action(s) to execute:")
                    else:
                        print("\n⚠️  No actions detected in response (looking for JSON with 'type' field)")

                    for i, action_str in enumerate(action_matches, 1):
                        print(f"\n  Action {i}: {action_str}")
                        try:
                            action = json.loads(action_str)
                            result = await execute_action(action, confirm=False)
                            print(f"  {result}")
                        except json.JSONDecodeError as e:
                            print(f"  ❌ JSON decode error: {e}")
                        except Exception as e:
                            print(f"  ❌ Execution error: {e}")

                    print("👤 You: ", end="", flush=True)

            except asyncio.QueueEmpty:
                pass

            # Periodic screen monitoring (silent unless noteworthy)
            if current_time - last_screen_check >= check_interval:
                last_screen_check = current_time

                try:
                    description = await describe_screen(llm_client)

                    # Build context-aware monitoring prompt
                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are SEL, silently monitoring the user's computer. "
                                "Only speak up if you notice something important or wrong. "
                                "Most of the time, stay quiet.\n\n"
                                "Current screen: " + description
                            )
                        },
                        *conversation_history[-3:]
                    ]

                    response = await llm_client._chat_completion(
                        model=llm_client.settings.openrouter_main_model,
                        messages=messages,
                        temperature=llm_client.settings.openrouter_main_temp,
                        top_p=llm_client.settings.openrouter_top_p,
                    )

                    # Only print if SEL has something to say
                    if response.strip() and len(response.strip()) > 10:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🤖 SEL: {response}")
                        conversation_history.append({
                            "role": "assistant",
                            "content": response
                        })
                        print("👤 You: ", end="", flush=True)

                        # Parse and execute any actions
                        import re
                        import json
                        action_pattern = r'\{[^}]*"type":\s*"[^"]*"[^}]*\}'
                        action_matches = re.findall(action_pattern, response)

                        for action_str in action_matches:
                            try:
                                action = json.loads(action_str)
                                result = await execute_action(action, confirm=False)
                                print(f"  {result}")
                            except Exception as e:
                                print(f"  ❌ Error: {e}")

                except Exception as e:
                    # Silently log errors during monitoring
                    pass

            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
    finally:
        listener.stop()
        print("👤 You: ", end="", flush=True)  # Reset prompt

async def interactive_mode(llm_client: OpenRouterClient):
    """Interactive desktop assistant mode"""
    global EMERGENCY_STOP, PAUSED

    print("\n" + "="*70)
    print("  SEL Desktop Assistant - FULL GUI CONTROL MODE")
    print("="*70)
    print("\n⚠️  SEL HAS COMPLETE CONTROL OVER YOUR DESKTOP")
    print("   • Can see your screen in real-time")
    print("   • Can click any button, link, or UI element")
    print("   • Can type, scroll, drag, open programs")
    print("   • Will execute tasks autonomously until complete")
    print("\n🔑 Emergency Controls:")
    print("   • Numpad 8: EMERGENCY STOP (instant halt)")
    print("   • Numpad 5: Pause/Resume")
    print("   • Type 'quit' to exit")
    print("\n💬 Example commands:")
    print("   • 'open chrome and search for python tutorials'")
    print("   • 'download vesktop from github'")
    print("   • 'organize my desktop files into folders'")
    print("   • 'open notepad and write a shopping list'")
    print("   • 'find and play a youtube video about cats'")
    print("   • 'screen' - see what SEL sees")
    print("\n🖱️  SEL will control mouse/keyboard to complete tasks!")
    print("="*70 + "\n")

    # Start keyboard listener in background
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    conversation_history = []

    try:
        while not EMERGENCY_STOP:
            if PAUSED:
                await asyncio.sleep(0.5)
                continue

            user_input = input("\n👤 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() == 'quit':
                print("👋 Goodbye!")
                break

            if user_input.lower() == 'screen':
                description = await describe_screen(llm_client)
                print(f"\n👁️  SEL sees:\n{description}")
                conversation_history.append({
                    "role": "user",
                    "content": f"[Screen captured at {datetime.now().strftime('%H:%M:%S')}]"
                })
                conversation_history.append({
                    "role": "assistant",
                    "content": description
                })
                continue

            if user_input.lower().startswith('click '):
                parts = user_input.split()
                if len(parts) == 3:
                    x, y = int(parts[1]), int(parts[2])
                    result = await execute_action({"type": "move_mouse", "x": x, "y": y}, confirm=False)
                    print(result)
                    result = await execute_action({"type": "click"}, confirm=False)
                    print(result)
                continue

            if user_input.lower().startswith('type '):
                text = user_input[5:]
                result = await execute_action({"type": "type", "text": text}, confirm=False)
                print(result)
                continue

            # Chat with SEL - intelligent task/chat detection
            conversation_history.append({"role": "user", "content": user_input})

            # Check if this is a task or just chat
            is_task = any(word in user_input.lower() for word in
                         ["open", "click", "type", "close", "start", "run", "launch",
                          "press", "move", "find", "search", "create", "delete", "do"])

            if is_task:
                # Check task memory for similar tasks
                similar_tasks = task_memory.get_similar_tasks(user_input)
                memory_context = ""
                if similar_tasks:
                    print(f"\n[Memory] Found {len(similar_tasks)} similar past tasks")
                    memory_context = "\n\nPAST EXPERIENCE:\n"
                    for t in similar_tasks:
                        status = "✓ Succeeded" if t['success'] else "✗ Failed"
                        memory_context += f"- {status}: {t['task'][:50]} ({t.get('notes', '')})\n"

                # Task execution loop - many iterations since we do 1 action at a time
                max_iterations = 50
                task_success = False
                for iteration in range(max_iterations):
                    print(f"\n📸 Capturing screen (iteration {iteration + 1})...")
                    description = await describe_screen(llm_client)

                    if iteration == 0:
                        system_prompt = (
                            "SCREEN: " + description + memory_context + "\n\n"
                            "THINK FIRST:\n"
                            "1. Current state: [What do I see?]\n"
                            "2. Goal: [What am I trying to do?]\n"
                            "3. Next step: [What action will get me closer?]\n"
                            "4. Learn from past experience if available.\n\n"
                            "Then output 1-2 actions:\n"
                            'GUI: {"type":"click","x":960,"y":540}\n'
                            '     {"type":"type","text":"firefox"}\n'
                            '     {"type":"hotkey","keys":["win","r"]}\n'
                            '     {"type":"wait","duration":2}\n'
                            'TOOLS: {"type":"calculate","expression":"2+2"}\n'
                            '       {"type":"read_file","path":"file.txt"}\n'
                            '       {"type":"list_files","directory":"."}\n'
                            '       {"type":"system_info"}\n'
                            '       {"type":"read_terminal","close":true}\n'
                            'OCR: {"type":"ocr_read"}\n'
                            '     {"type":"ocr_region","x":100,"y":100,"width":200,"height":50}\n'
                            '     {"type":"ocr_find","text":"Submit"}\n\n'
                            'Format: Brief reasoning, then JSON. Say TASK COMPLETE when done.\n'
                            'Screen 1920x1080. Use tools when needed.'
                        )
                    else:
                        system_prompt = (
                            "SCREEN: " + description + "\n\n"
                            "REFLECT:\n"
                            "- Did my last action work? What changed?\n"
                            "- Am I closer to the goal?\n"
                            "- If stuck, try different approach.\n\n"
                            'Output 1-2 actions: {"type":"click","x":960,"y":540}\n'
                            'Brief reflection, then actions. Say TASK COMPLETE when done.'
                        )

                    # Include more context for better understanding (last 10 messages)
                    messages = [
                        {"role": "system", "content": system_prompt},
                        *conversation_history[-10:]  # Increased from 3 to 10 for better context
                    ]

                    print("🤖 SEL: ", end="", flush=True)

                    try:
                        response = await llm_client._chat_completion(
                            model=llm_client.settings.openrouter_main_model,
                            messages=messages,
                            temperature=llm_client.settings.openrouter_main_temp,
                            top_p=llm_client.settings.openrouter_top_p,
                        )
                    except Exception as e:
                        print(f"\n❌ LLM Error: {e}")
                        response = ""

                    if not response or not response.strip():
                        print("\n⚠️  Empty response - retrying...")
                        # Retry with explicit format
                        try:
                            messages = [
                                {
                                    "role": "system",
                                    "content": (
                                        f"SCREEN: {description[:500]}\n\n"
                                        'Output 1-2 actions in this EXACT format:\n'
                                        '{"type":"click","x":960,"y":540}\n'
                                        '{"type":"type","text":"firefox"}\n'
                                        '{"type":"press_key","key":"enter"}\n'
                                        'If complete, output only: TASK COMPLETE.'
                                    )
                                },
                                {"role": "user", "content": "Next action?"}
                            ]
                            response = await llm_client._chat_completion(
                                model=llm_client.settings.openrouter_main_model,
                                messages=messages,
                                temperature=0.7,
                                top_p=0.9,
                            )
                        except Exception as e:
                            print(f"❌ Retry failed: {e}")
                            response = ""

                    print(response)

                    conversation_history.append({"role": "assistant", "content": response})

                    # Execute actions FIRST, then check for completion
                    import re
                    import json
                    action_pattern = r'\{[^}]*"type":\s*"[^"]*"[^}]*\}'
                    action_matches = re.findall(action_pattern, response)

                    if action_matches:
                        max_actions = 6
                        actions_to_run = action_matches[:max_actions]
                        if len(action_matches) > max_actions:
                            print(f"\nWarning: received {len(action_matches)} actions; executing first {max_actions}.")

                        print(f"\nExecuting {len(actions_to_run)} action(s) with screen feedback:")
                        for idx, action_str in enumerate(actions_to_run, 1):
                            print(f"  {idx}. {action_str}")
                            try:
                                action = json.loads(action_str)
                                result = await execute_action(action, confirm=False)
                                print(f"     {result}")
                            except Exception as e:
                                print(f"     Error: {e}")
                                break

                            if EMERGENCY_STOP or PAUSED:
                                break
                    else:
                        # No actions but SEL is analyzing - continue unless response is empty
                        if not response.strip():
                            print("\n⚠️  Empty response from SEL")
                            break
                        # Check for completion if no actions
                        if "TASK COMPLETE" in response.upper():
                            print("\n✅ Task completed!\n")
                            task_success = True
                            break
                        print("\n💭 SEL is thinking (no actions this iteration)...")
                        await asyncio.sleep(1)

                if iteration >= max_iterations - 1:
                    print("\n⚠️  Max iterations reached\n")

                # Save task result to memory
                notes = ""
                if task_success:
                    notes = f"Completed in {iteration + 1} iterations"
                else:
                    notes = f"Failed or interrupted after {iteration + 1} iterations"

                task_memory.remember_task(
                    task=user_input,
                    success=task_success,
                    notes=notes
                )
                print(f"[Memory] Saved task result: {'Success' if task_success else 'Failure'}")

            else:
                # Just chat - single response
                print("\n💬 Chatting with SEL...")
                description = await describe_screen(llm_client)

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are SEL, a desktop assistant with full GUI control. The user is chatting with you.\n\n"
                            f"CURRENT SCREEN:\n{description}\n\n"
                            "Respond conversationally. If they ask you to do something, output actions as JSON:\n"
                            '• Click: {"type": "click", "x": 850, "y": 350}\n'
                            '• Double-click: {"type": "double_click", "x": 640, "y": 480}\n'
                            '• Right-click: {"type": "right_click", "x": 100, "y": 200}\n'
                            '• Type: {"type": "type", "text": "hello"}\n'
                            '• Scroll: {"type": "scroll", "clicks": -3}\n'
                            '• Wait: {"type": "wait", "duration": 1}\n\n'
                            "You control the GRAPHICAL desktop - click buttons, links, menus using x,y coordinates!"
                        )
                    },
                    *conversation_history[-10:]
                ]

                print("🤖 SEL: ", end="", flush=True)

                response = await llm_client._chat_completion(
                    model=llm_client.settings.openrouter_main_model,
                    messages=messages,
                    temperature=llm_client.settings.openrouter_main_temp,
                    top_p=llm_client.settings.openrouter_top_p,
                )
                print(response)

                conversation_history.append({"role": "assistant", "content": response})
                print()

    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
    finally:
        listener.stop()

async def main():
    """Main entry point"""
    print("Starting SEL Desktop Assistant...")

    # Load settings
    settings = Settings()
    llm_client = OpenRouterClient(settings)

    print("✓ Loaded configuration")
    print(f"✓ Using vision model: {settings.openrouter_vision_model}")

    # Safety settings
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1  # Small delay between actions

    # Mode selection
    print("\n" + "="*60)
    print("SELECT MODE:")
    print("="*60)
    print("1. Interactive Mode - Wait for your commands")
    print("2. Continuous Mode - Run indefinitely, monitor automatically")
    print("="*60)

    mode = input("\nEnter mode (1 or 2, default=2): ").strip() or "2"

    if mode == "1":
        await interactive_mode(llm_client)
    else:
        await continuous_mode(llm_client)

if __name__ == "__main__":
    asyncio.run(main())
