"""Convenience launcher for the Hierarchical Image Memory API service."""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

import uvicorn

from him.api import create_app
from him.storage import HierarchicalImageMemory

TARGET_CPU_FAMILY = "AMD Ryzen 7 7700"
TARGET_GPU_MODEL = "NVIDIA GeForce RTX 4070 SUPER"
MIN_STORAGE_BYTES = 7 * 1024**4  # 7 TiB expressed in bytes.


def _detect_cpu() -> str:
    candidates = [platform.processor(), platform.uname().processor, platform.machine()]
    for value in candidates:
        if value:
            return value
    return "unknown"


def _detect_nvidia_gpus() -> List[Dict[str, str]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    gpus: List[Dict[str, str]] = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = [segment.strip() for segment in line.split(",")]
        if len(parts) == 2:
            name, memory = parts
        else:
            name = parts[0]
            memory = ""
        gpus.append({"name": name, "memory": memory})
    return gpus


def _gather_profile(data_dir: Path) -> Dict[str, object]:
    cpu_name = _detect_cpu()
    gpu_info = _detect_nvidia_gpus()
    total, used, free = shutil.disk_usage(data_dir)
    return {
        "cpu": cpu_name,
        "logical_cpus": os.cpu_count(),
        "gpus": gpu_info,
        "disk_total_bytes": total,
        "disk_used_bytes": used,
        "disk_free_bytes": free,
        "data_dir": str(data_dir),
    }


def _print_profile(profile: Dict[str, object]) -> None:
    disk_total_tb = profile["disk_total_bytes"] / 1024**4
    disk_free_tb = profile["disk_free_bytes"] / 1024**4
    print("Hardware profile detected:")
    print(f"  CPU: {profile['cpu']} (logical cores: {profile['logical_cpus']})")
    if profile["gpus"]:
        for idx, gpu in enumerate(profile["gpus"]):
            memory = f" ({gpu['memory']} MB)" if gpu.get("memory") else ""
            print(f"  GPU {idx}: {gpu['name']}{memory}")
    else:
        print("  GPU: No NVIDIA GPUs detected via nvidia-smi")
    print(f"  Storage (mount backing {profile['data_dir']}): {disk_total_tb:.2f} TiB total, {disk_free_tb:.2f} TiB free")


def _validate_profile(profile: Dict[str, object]) -> List[str]:
    warnings: List[str] = []
    cpu_name = str(profile["cpu"]).lower()
    if TARGET_CPU_FAMILY.lower() not in cpu_name:
        warnings.append(
            f"Expected CPU family '{TARGET_CPU_FAMILY}' for optimal tuning, detected '{profile['cpu']}'."
        )

    if not any(TARGET_GPU_MODEL.lower() in gpu["name"].lower() for gpu in profile["gpus"]):
        if profile["gpus"]:
            gpu_list = ", ".join(gpu["name"] for gpu in profile["gpus"])
            warnings.append(
                f"Expected GPU '{TARGET_GPU_MODEL}' but detected: {gpu_list}."
            )
        else:
            warnings.append(
                f"No NVIDIA GPU detected; target hardware is '{TARGET_GPU_MODEL}'."
            )

    if profile["disk_total_bytes"] < MIN_STORAGE_BYTES:
        warnings.append(
            f"Available storage is below the recommended 7 TiB (detected {profile['disk_total_bytes'] / 1024**4:.2f} TiB)."
        )
    return warnings


def _ensure_storage_ready(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tiles_dir = data_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Hierarchical Image Memory API service")
    parser.add_argument("--data-dir", default="data", help="Directory for persistent HIM state")
    parser.add_argument("--host", default="0.0.0.0", help="Uvicorn bind host")
    parser.add_argument("--port", type=int, default=8000, help="Uvicorn bind port")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Log level passed to uvicorn",
    )
    parser.add_argument(
        "--profile-only",
        action="store_true",
        help="Print the detected hardware profile and exit without starting the server.",
    )
    parser.add_argument(
        "--skip-hardware-checks",
        action="store_true",
        help="Suppress guidance messages about the recommended CPU/GPU/storage targets.",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).expanduser().resolve()
    _ensure_storage_ready(data_dir)

    profile = _gather_profile(data_dir)
    _print_profile(profile)

    if not args.skip_hardware_checks:
        warnings = _validate_profile(profile)
        for warning in warnings:
            print(f"[hardware-warning] {warning}")
        if not warnings:
            print("Hardware profile matches the recommended configuration.")

    if args.profile_only:
        return

    store = HierarchicalImageMemory(data_dir)
    app = create_app(store)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
