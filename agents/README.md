# LangChain agents for Sel

Place Python files here to expose LangChain-style agents to Sel. Each file should define:

```python
DESCRIPTION = "Short summary of what the agent does"

def run(query: str, **kwargs):
    """Return a string response."""
    ...
```

Sel loads `*.py` modules in this folder at startup; you can add new agents without rebuilding the image if this folder is mounted as a volume.
