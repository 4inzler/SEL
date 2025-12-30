"""
Terminal interaction helper for SEL Desktop
Allows reading terminal output and sending keystrokes
"""
import pyautogui
import pyperclip
import time

def read_terminal_text() -> str:
    """
    Read text from current terminal window
    Uses Ctrl+A, Ctrl+C to select all and copy
    """
    # Save current clipboard
    old_clipboard = ""
    try:
        old_clipboard = pyperclip.paste()
    except:
        pass

    # Select all text in terminal
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)

    # Copy to clipboard
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(0.2)

    # Get copied text
    try:
        terminal_text = pyperclip.paste()
    except:
        terminal_text = ""

    # Restore old clipboard
    try:
        pyperclip.copy(old_clipboard)
    except:
        pass

    # Click to deselect
    pyautogui.click()

    return terminal_text

def send_enter_to_terminal():
    """Send Enter key to current terminal window"""
    pyautogui.press('enter')
    time.sleep(0.1)

def type_in_terminal(text: str):
    """Type text in current terminal window"""
    pyautogui.write(text, interval=0.05)

def send_terminal_command(command: str, wait_seconds: float = 1.0):
    """
    Send command to terminal and press Enter
    """
    pyautogui.write(command, interval=0.05)
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(wait_seconds)

def close_terminal(force: bool = False):
    """
    Close terminal window
    First tries Enter, then Alt+F4 if force=True
    """
    # Try pressing Enter first
    pyautogui.press('enter')
    time.sleep(0.3)

    # If force close requested, use Alt+F4
    if force:
        pyautogui.hotkey('alt', 'f4')
        time.sleep(0.2)
