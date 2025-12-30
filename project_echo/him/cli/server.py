"""Command line entry point for launching the HIM API server."""
from __future__ import annotations

import argparse
import uvicorn

from ..api import create_app
from ..storage import HierarchicalImageMemory


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Hierarchical Image Memory API server")
    parser.add_argument("--data-dir", default="data", help="Directory where snapshot and tile data will be stored")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    store = HierarchicalImageMemory(args.data_dir)
    app = create_app(store)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
