"""Test if mouse/keyboard automation works"""

import pyautogui
import time

print("Testing PyAutoGUI automation...")
print("Moving mouse in 3 seconds...")
time.sleep(3)

# Test mouse movement
print("Moving mouse to center of screen...")
screen_width, screen_height = pyautogui.size()
pyautogui.moveTo(screen_width // 2, screen_height // 2, duration=1)
print(f"[OK] Moved to ({screen_width // 2}, {screen_height // 2})")

time.sleep(1)

# Test typing
print("\nOpening Run dialog and typing...")
pyautogui.hotkey('win', 'r')
time.sleep(0.5)
pyautogui.write('notepad', interval=0.1)
time.sleep(0.5)
pyautogui.press('enter')
print("[OK] Should have opened Notepad")

time.sleep(2)

print("\nTyping in Notepad...")
pyautogui.write('Hello from SEL automation test!', interval=0.05)
print("[OK] Typed text")

print("\n[SUCCESS] All tests completed!")
print("If you see Notepad with text, automation works!")
