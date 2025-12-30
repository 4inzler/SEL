"""
Persistent task memory for SEL Desktop
Remembers what tasks worked/failed across sessions
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict

MEMORY_FILE = Path(__file__).parent / "sel_task_memory.json"

def load_memory() -> List[Dict]:
    """Load task memory from file"""
    if not MEMORY_FILE.exists():
        return []

    try:
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_memory(memory: List[Dict]):
    """Save task memory to file"""
    try:
        with open(MEMORY_FILE, 'w') as f:
            json.dump(memory[-100:], f, indent=2)  # Keep last 100 tasks
    except Exception as e:
        print(f"Warning: Could not save task memory: {e}")

def remember_task(task: str, success: bool, notes: str = ""):
    """Remember a completed task"""
    memory = load_memory()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "task": task,
        "success": success,
        "notes": notes
    }

    memory.append(entry)
    save_memory(memory)

def get_similar_tasks(task: str, limit: int = 5) -> List[Dict]:
    """Get similar tasks from memory"""
    memory = load_memory()

    # Simple keyword matching
    keywords = set(task.lower().split())
    scored = []

    for entry in memory:
        entry_keywords = set(entry['task'].lower().split())
        overlap = len(keywords & entry_keywords)
        if overlap > 0:
            scored.append((overlap, entry))

    # Sort by relevance
    scored.sort(key=lambda x: x[0], reverse=True)

    return [entry for _, entry in scored[:limit]]

def get_memory_summary() -> str:
    """Get a summary of task memory"""
    memory = load_memory()

    if not memory:
        return "No task memory yet."

    total = len(memory)
    successful = sum(1 for m in memory if m['success'])
    recent = memory[-5:]

    summary = f"Task Memory: {successful}/{total} successful tasks\n\nRecent:\n"
    for m in recent:
        status = "✓" if m['success'] else "✗"
        summary += f"{status} {m['task'][:50]}...\n"

    return summary
