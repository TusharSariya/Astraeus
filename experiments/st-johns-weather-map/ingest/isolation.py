"""Fail-closed process limits for bounded experimental payload decoders.

The worker's admission reservation prevents competing operations from starting
when their declared allocations cannot coexist.  That is not a memory limit:
the decoder itself must run where its address-space growth is capped before it
reads a payload.  This module supplies that narrow execution boundary.

It deliberately does not claim a general directory quota.  A caller using
``run_bounded_process`` must write exactly one artifact at ``{output}``; the
child's file-size limit covers that file and the caller's admission bound must
cover the measured parent/child and filesystem overlap.  Any extra workspace
file is refused and the entire workspace is removed.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class BoundedProcessError(RuntimeError):
    """A bounded decoder did not produce a promotable artifact."""


class BoundedProcessUnavailable(BoundedProcessError):
    """The target platform cannot apply the required kernel limits."""


class BoundedProcessOutputExceeded(BoundedProcessError):
    """The child exceeded its bounded stdout or stderr channel."""


@dataclass(frozen=True)
class ProcessAllocationLimits:
    """Limits enforced before a child decoder receives any payload bytes.

    ``address_space_bytes`` is an OS virtual-address-space cap, not a claimed
    measurement of process RSS.  ``output_bytes`` is an OS per-file cap and is
    safe only for a decoder that writes its complete artifact directly to the
    one supplied output path.  ``stdin_bytes``, ``stdout_bytes`` and
    ``stderr_bytes`` bound the parent/child transport buffers.
    """

    address_space_bytes: int
    output_bytes: int
    stdin_bytes: int
    stdout_bytes: int
    stderr_bytes: int

    def validate(self) -> None:
        for name, value in (
            ("address_space_bytes", self.address_space_bytes),
            ("output_bytes", self.output_bytes),
            ("stdin_bytes", self.stdin_bytes),
            ("stdout_bytes", self.stdout_bytes),
            ("stderr_bytes", self.stderr_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"process allocation limit {name} must be a positive integer")


@dataclass(frozen=True)
class BoundedProcessResult:
    """A promoted single-file artifact and its bounded machine-readable reply."""

    output_path: Path
    stdout: bytes


def _resource_module() -> object | None:
    if os.name != "posix":
        return None
    try:
        import resource  # noqa: PLC0415
    except ImportError:
        return None
    if not hasattr(resource, "RLIMIT_AS") or not hasattr(resource, "RLIMIT_FSIZE"):
        return None
    return resource


def _limit_preexec(limits: ProcessAllocationLimits) -> None:
    """Install hard limits in the child immediately before ``exec``."""
    resource = _resource_module()
    if resource is None:
        raise BoundedProcessUnavailable("RLIMIT_AS and RLIMIT_FSIZE are unavailable on this runtime")
    for limit_name, requested in (("RLIMIT_AS", limits.address_space_bytes), ("RLIMIT_FSIZE", limits.output_bytes)):
        limit = getattr(resource, limit_name)
        _soft, hard = resource.getrlimit(limit)
        if hard != resource.RLIM_INFINITY and requested > hard:
            raise BoundedProcessUnavailable(f"{limit_name} hard limit {hard} is below requested {requested}")
        # POSIX refuses lowering the hard limit beneath the *current* soft
        # limit, even when both requested values are valid.  Lower soft first,
        # then lock hard to the same value so the exec'd decoder cannot relax
        # its own ceiling.
        resource.setrlimit(limit, (requested, hard))
        resource.setrlimit(limit, (requested, requested))


def _bounded_reader(
    stream: object,
    *,
    maximum: int,
    process: subprocess.Popen[bytes],
    exceeded: threading.Event,
    collected: bytearray,
) -> None:
    """Drain one pipe without ever retaining more than its declared bound."""
    while True:
        chunk = stream.read(min(64 * 1024, maximum + 1))
        if not chunk:
            return
        if len(collected) + len(chunk) > maximum:
            exceeded.set()
            process.terminate()
            return
        collected.extend(chunk)


def _replace_output_argument(command: Sequence[str], output: Path) -> list[str]:
    replaced = [str(output) if item == "{output}" else str(item) for item in command]
    if replaced == list(map(str, command)) or replaced.count(str(output)) != 1:
        raise ValueError("bounded process command must contain exactly one {output} argument")
    return replaced


def run_bounded_process(
    *,
    command: Sequence[str],
    stdin: bytes,
    destination: Path,
    limits: ProcessAllocationLimits,
    timeout_seconds: float = 60.0,
) -> BoundedProcessResult:
    """Run a one-artifact decoder under kernel limits and atomically promote it.

    The child starts in a private sibling workspace and receives the absolute
    path for its only allowed output via a literal ``{output}`` argv item.  It
    receives at most ``stdin_bytes`` before exec, and parent-side pipe readers
    terminate it before retaining more than either reply bound.  Failure never
    leaves a destination file or workspace behind.
    """
    limits.validate()
    if not isinstance(stdin, bytes):
        raise TypeError("bounded process stdin must be bytes")
    if len(stdin) > limits.stdin_bytes:
        raise BoundedProcessError(
            f"decoder input is {len(stdin)} bytes, above its {limits.stdin_bytes}-byte bound"
        )
    if _resource_module() is None:
        raise BoundedProcessUnavailable("bounded decoding requires RLIMIT_AS and RLIMIT_FSIZE")
    if timeout_seconds <= 0:
        raise ValueError("bounded process timeout must be positive")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="bounded-decode-", dir=destination.parent))
    output = workspace / "artifact"
    stdout = bytearray()
    stderr = bytearray()
    stdout_exceeded = threading.Event()
    stderr_exceeded = threading.Event()
    process: subprocess.Popen[bytes] | None = None
    try:
        try:
            process = subprocess.Popen(
                _replace_output_argument(command, output),
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: _limit_preexec(limits),
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.SubprocessError as error:
            # Some POSIX platforms expose the constants but reject a locked
            # address-space limit.  Treat that as unavailable rather than
            # running a decoder under an imagined limit.
            raise BoundedProcessUnavailable("runtime rejected required kernel allocation limits") from error
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        out_reader = threading.Thread(
            target=_bounded_reader,
            kwargs={"stream": process.stdout, "maximum": limits.stdout_bytes, "process": process,
                    "exceeded": stdout_exceeded, "collected": stdout},
            daemon=True,
        )
        err_reader = threading.Thread(
            target=_bounded_reader,
            kwargs={"stream": process.stderr, "maximum": limits.stderr_bytes, "process": process,
                    "exceeded": stderr_exceeded, "collected": stderr},
            daemon=True,
        )
        out_reader.start()
        err_reader.start()
        try:
            try:
                process.stdin.write(stdin)
            except BrokenPipeError:
                # The child failure is reported below using its exit status.
                pass
            finally:
                process.stdin.close()
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise BoundedProcessError(f"bounded decoder exceeded {timeout_seconds:g}-second timeout") from error
        finally:
            out_reader.join(timeout=5)
            err_reader.join(timeout=5)

        if stdout_exceeded.is_set() or stderr_exceeded.is_set():
            raise BoundedProcessOutputExceeded("bounded decoder exceeded its stdout or stderr bound")
        if exit_code != 0:
            if exit_code < 0:
                signame = signal.Signals(-exit_code).name
                raise BoundedProcessError(f"bounded decoder ended by {signame}: {stderr.decode(errors='replace')}")
            raise BoundedProcessError(f"bounded decoder exited {exit_code}: {stderr.decode(errors='replace')}")
        workspace_entries = list(workspace.iterdir())
        if workspace_entries != [output] or output.is_symlink() or not output.is_file():
            raise BoundedProcessError("bounded decoder must leave exactly its one output file in the workspace")
        if output.stat().st_size > limits.output_bytes:
            raise BoundedProcessError("bounded decoder output exceeded its enforced file-size limit")
        output.replace(destination)
        return BoundedProcessResult(output_path=destination, stdout=bytes(stdout))
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        shutil.rmtree(workspace, ignore_errors=True)
