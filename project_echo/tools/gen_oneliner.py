#!/usr/bin/env python3
"""Generate a single-line installer by zipping tracked files on the fly."""

from __future__ import annotations

import argparse
import base64
import io
import pathlib
import subprocess
import zipfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "him_bundle_oneliner.sh"
ZIP_COMPRESSION = dict(compression=zipfile.ZIP_DEFLATED, compresslevel=9)
IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "dist",
}
IGNORED_FILE_NAMES = {".DS_Store"}


def iter_repo_files() -> list[pathlib.Path]:
    """Return a sorted list of files that should be packaged."""

    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        files = [
            path
            for path in REPO_ROOT.rglob("*")
            if path.is_file() and should_include(path)
        ]
    else:
        files = [REPO_ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]
        files = [path for path in files if should_include(path)]

    return sorted(files)


def should_include(path: pathlib.Path) -> bool:
    rel_parts = path.relative_to(REPO_ROOT).parts
    if any(part in IGNORED_DIRS for part in rel_parts[:-1]):
        return False
    if path.name in IGNORED_FILE_NAMES:
        return False
    return True


def build_archive_bytes() -> bytes:
    """Zip the repository files into an in-memory archive."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", **ZIP_COMPRESSION) as zf:
        for path in iter_repo_files():
            arcname = path.relative_to(REPO_ROOT).as_posix()
            zf.write(path, arcname)
    return buffer.getvalue()


def create_oneliner_script(archive: bytes, destination: pathlib.Path) -> None:
    archive_b64 = base64.b64encode(archive).decode("ascii")
    python_cmd = (
        "python3 -c \"import base64,io,zipfile,sys,pathlib; "
        "data=base64.b64decode('{b64}'); "
        "target=sys.argv[1] if len(sys.argv)>1 else 'him_bundle'; "
        "target_path=pathlib.Path(target).expanduser(); "
        "target_path.mkdir(parents=True, exist_ok=True); "
        "zipfile.ZipFile(io.BytesIO(data)).extractall(target_path)\""
    )
    script_contents = "#!/usr/bin/env bash\n" + python_cmd.format(b64=archive_b64) + " \"$@\"\n"
    destination.write_text(script_contents)
    destination.chmod(0o755)


def write_zip(archive: bytes, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(archive)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT,
        help="Path for the generated installer script (default: him_bundle_oneliner.sh)",
    )
    parser.add_argument(
        "--zip-out",
        type=pathlib.Path,
        help="Optional path to also write the zip archive",
    )
    args = parser.parse_args()

    archive = build_archive_bytes()
    create_oneliner_script(archive, args.output)

    if args.zip_out is not None:
        write_zip(archive, args.zip_out)


if __name__ == "__main__":
    main()
