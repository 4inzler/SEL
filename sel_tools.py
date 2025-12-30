"""
Tool access for SEL Desktop - web search, file operations, calculations
"""
import os
import json
from pathlib import Path
from datetime import datetime

def calculate(expression: str) -> str:
    """
    Safely evaluate mathematical expressions
    """
    try:
        # Only allow safe operations
        allowed = set('0123456789+-*/()., ')
        if not all(c in allowed for c in expression):
            return "Error: Only basic math operations allowed"

        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except Exception as e:
        return f"Calculation error: {e}"

def read_file(file_path: str) -> str:
    """
    Read text from a file
    """
    try:
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"Error: File not found: {file_path}"

        if path.stat().st_size > 100000:  # 100KB limit
            return f"Error: File too large (max 100KB)"

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return f"File content ({len(content)} chars):\n{content}"
    except Exception as e:
        return f"Error reading file: {e}"

def list_files(directory: str = ".") -> str:
    """
    List files in a directory
    """
    try:
        path = Path(directory).expanduser()
        if not path.exists():
            return f"Error: Directory not found: {directory}"

        if not path.is_dir():
            return f"Error: Not a directory: {directory}"

        files = []
        for item in path.iterdir():
            if item.is_file():
                files.append(f"  FILE: {item.name}")
            elif item.is_dir():
                files.append(f"  DIR:  {item.name}/")

        return f"Contents of {directory}:\n" + "\n".join(files[:50])  # Limit to 50 items
    except Exception as e:
        return f"Error listing directory: {e}"

def get_system_info() -> str:
    """
    Get current system information
    """
    import platform
    import psutil

    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python": platform.python_version(),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent if platform.system() != 'Windows' else psutil.disk_usage('C:\\').percent,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return json.dumps(info, indent=2)

def search_web_query(query: str) -> str:
    """
    Generate a web search - returns instruction to open browser
    """
    # We can't actually search, but we can tell SEL how to do it
    return f"To search '{query}': Open browser, go to google.com, type query, press enter"
