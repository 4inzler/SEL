# project_echo

Hierarchical Image Memory (HIM) reference implementation that exposes a FastAPI service backed by a SQLite-powered storage layer.

## Bundles & single-line installer

- `him_bundle_oneliner.sh`: executes a single Python one-liner that recreates the
  entire project directory tree. Run `./him_bundle_oneliner.sh` to extract into a
  directory named `him_bundle` or provide a custom destination as the first
  argument, e.g. `./him_bundle_oneliner.sh /tmp/him`.
- `him_all_in_one.sh`: fully self-extracting installer with additional
  validation and cleanup to unpack the project into a chosen directory.

Need a traditional zip? Generate one locally without committing binaries:

```bash
poetry run python tools/gen_oneliner.py --zip-out dist/him_bundle.zip
```

## Getting started

The project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
./setup.sh
```

The script installs Poetry (if needed), resolves dependencies, prepares the storage directories, and prints a hardware profile tuned for an AMD Ryzen 7 7700 CPU alongside an NVIDIA GeForce RTX 4070 SUPER GPU with at least 7 TiB of disk space.

### Running the API server

```bash
poetry run python run_him.py --data-dir ./data
```

`run_him.py` prints the detected hardware profile, highlights any deviations from the recommended CPU/GPU/storage envelope, and then boots the FastAPI service (powered by Uvicorn). The server implements the endpoints described in `HIM_Spec_v1.1.md` and stores snapshots and tiles under the `data/` directory. The storage engine maintains snapshot metadata and tile statistics in `data/him.db`, tracks hint logs for the query planner, and persists tile payloads under `data/tiles/` using content-addressed paths.

To inspect the system profile without starting the server, run:

```bash
poetry run python run_him.py --profile-only
```

### Features

- Snapshot and tile metadata persisted in SQLite with automatic hotness tracking.
- Content-addressed tile payloads organised by stream/snapshot/level/coordinate.
- Query planner that fuses access telemetry with prefetch hints to prioritise tiles.
- Prefetch hints accepted via `/v1/prefetch` and reused by `/v1/query`.

### Running tests

```bash
poetry run pytest
```
