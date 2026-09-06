"""Measure the GEFS bounded-child/parent/cache copy topology without network I/O.

This is a structural preflight.  It deliberately does not claim ecCodes or
provider-payload measurements; the reviewed one-lead capture must supply those.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import zipfile
from pathlib import Path

from ingest.isolation import run_bounded_process
from weather_api.gefs_query import (
    GEFS_CACHE_MAX_BYTES,
    GEFS_CHILD_LIMITS,
    GEFS_MARGIN_BYTES,
    GEFS_MEMORY_LIMIT_BYTES,
    GEFS_TEMP_LIMIT_BYTES,
)


def _integer(path: Path) -> int:
    return int(path.read_text().strip())


def _events(path: Path) -> dict[str, int]:
    return {line.split()[0]: int(line.split()[1]) for line in path.read_text().splitlines()}


def _workspace_usage(root: Path) -> tuple[int, int]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return sum(path.stat().st_blocks * 512 for path in files), len(files)


def child(source: Path, output: Path) -> None:
    payload = source.read_bytes()
    manifest = json.dumps({"fixture": True, "payload_sha256": hashlib.sha256(payload).hexdigest()})
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr("result.json", manifest)
        bundle.writestr("artifacts/noaa_gefs_members.zarr.zip", payload)


def measure(workspace: Path, payload_mib: int) -> dict[str, object]:
    # The fresh-container measurement established 704 MiB as the conservative
    # policy ceiling that retains the required 128 MiB aggregate headroom.
    if not 1 <= payload_mib <= 704:
        raise ValueError("payload-mib must be between 1 and 704")
    memory_root = Path("/sys/fs/cgroup")
    memory_limit = _integer(memory_root / "memory.max")
    if memory_limit != GEFS_MEMORY_LIMIT_BYTES:
        raise RuntimeError(f"expected exact 4 GiB cgroup, found {memory_limit}")
    geometry = os.statvfs(workspace)
    capacity = geometry.f_blocks * geometry.f_frsize
    if capacity > GEFS_TEMP_LIMIT_BYTES:
        raise RuntimeError(f"workspace capacity {capacity} exceeds 3 GiB")
    if any(workspace.iterdir()):
        raise RuntimeError("measurement workspace must start empty")
    before_events = _events(memory_root / "memory.events")
    initial_memory_peak = _integer(memory_root / "memory.peak")
    source = workspace / "local-normalized-fixture.zip"
    block = b"gefs-local-topology\0" * 4096
    remaining = payload_mib * 1024 * 1024
    with source.open("wb") as stream:
        while remaining:
            piece = block[: min(len(block), remaining)]
            stream.write(piece)
            remaining -= len(piece)
    destination = workspace / "parent-result.zip"
    peak_workspace = [0]
    peak_files = [0]
    stop = threading.Event()

    def observe() -> None:
        while not stop.is_set():
            used, count = _workspace_usage(workspace)
            peak_workspace[0] = max(peak_workspace[0], used)
            peak_files[0] = max(peak_files[0], count)
            time.sleep(0.005)

    observer = threading.Thread(target=observe, daemon=True)
    observer.start()
    try:
        run_bounded_process(
            command=[os.sys.executable, __file__, "--child", str(source), "{output}"],
            stdin=b"{}",
            destination=destination,
            limits=GEFS_CHILD_LIMITS,
            timeout_seconds=120,
        )
        with zipfile.ZipFile(destination) as bundle:
            payload = bundle.read("artifacts/noaa_gefs_members.zarr.zip")
        cache_copy = bytes(bytearray(payload))
        if len(cache_copy) > GEFS_CACHE_MAX_BYTES:
            raise RuntimeError("fixture exceeded cache ceiling")
        used, count = _workspace_usage(workspace)
        peak_workspace[0] = max(peak_workspace[0], used)
        peak_files[0] = max(peak_files[0], count)
        memory_current = _integer(memory_root / "memory.current")
        memory_peak = _integer(memory_root / "memory.peak")
        payload_sha = hashlib.sha256(cache_copy).hexdigest()
    finally:
        stop.set()
        observer.join()
    after_events = _events(memory_root / "memory.events")
    oom_delta = after_events.get("oom", 0) - before_events.get("oom", 0)
    kill_delta = after_events.get("oom_kill", 0) - before_events.get("oom_kill", 0)
    if oom_delta or kill_delta:
        raise RuntimeError(f"cgroup OOM changed: oom={oom_delta}, kill={kill_delta}")
    if peak_workspace[0] > GEFS_TEMP_LIMIT_BYTES:
        raise RuntimeError("workspace peak exceeded aggregate ceiling")
    if memory_peak > memory_limit - GEFS_MARGIN_BYTES:
        raise RuntimeError("cgroup peak leaves less than the required 128 MiB margin")
    if peak_files[0] > 4:
        raise RuntimeError(f"unexpected aggregate file topology: {peak_files[0]}")
    return {
        "measurement_kind": "local-structural-no-network-no-eccodes",
        "payload_bytes": len(cache_copy),
        "payload_sha256": payload_sha,
        "cgroup_memory_limit_bytes": memory_limit,
        "cgroup_memory_current_bytes": memory_current,
        "cgroup_memory_initial_peak_bytes": initial_memory_peak,
        "cgroup_memory_peak_bytes": memory_peak,
        "oom_delta": oom_delta,
        "oom_kill_delta": kill_delta,
        "workspace_capacity_bytes": capacity,
        "workspace_physical_peak_bytes": peak_workspace[0],
        "workspace_file_count_peak": peak_files[0],
        "workspace_file_count_scope": "structural fixture only; provider capture records 31 idx plus present ranges",
        "child_address_space_limit_bytes": GEFS_CHILD_LIMITS.address_space_bytes,
        "child_output_limit_bytes": GEFS_CHILD_LIMITS.output_bytes,
        "cache_ceiling_bytes": GEFS_CACHE_MAX_BYTES,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("/work"))
    parser.add_argument("--payload-mib", type=int, default=64)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("child_source", type=Path, nargs="?")
    parser.add_argument("child_output", type=Path, nargs="?")
    args = parser.parse_args()
    if args.child:
        if args.child_source is None or args.child_output is None:
            parser.error("child mode requires source and output")
        child(args.child_source, args.child_output)
        return
    result = measure(args.workspace, args.payload_mib)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
