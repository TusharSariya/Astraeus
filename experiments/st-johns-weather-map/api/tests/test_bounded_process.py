"""Kernel-enforced decoder limits, exercised with real child processes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import ingest.isolation as isolation
from ingest.isolation import (
    BoundedProcessError,
    BoundedProcessOutputExceeded,
    BoundedProcessUnavailable,
    ProcessAllocationLimits,
    run_bounded_process,
)


LIMITS = ProcessAllocationLimits(
    # This needs headroom for the Python interpreter itself.  The allocation
    # test below asks the child for substantially more than this hard cap.
    address_space_bytes=192 * 1024 * 1024,
    output_bytes=4096,
    stdin_bytes=4096,
    stdout_bytes=1024,
    stderr_bytes=1024,
)

requires_enforcement = pytest.mark.skipif(
    sys.platform == "darwin",
    reason="Darwin exposes RLIMIT_AS but rejects installing a locked address-space cap; production Linux must enforce it",
)


def _command(program: str) -> list[str]:
    return [sys.executable, "-c", program, "{output}"]


def _workspaces(parent: Path) -> list[Path]:
    return list(parent.glob("bounded-decode-*"))


@requires_enforcement
def test_bounded_process_applies_limits_before_input_and_atomically_promotes_one_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.zarr.zip"
    result = run_bounded_process(
        command=_command(
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read()); print('ok')"
        ),
        stdin=b"raw payload",
        destination=destination,
        limits=LIMITS,
    )
    assert result.output_path == destination
    assert destination.read_bytes() == b"raw payload"
    assert result.stdout == b"ok\n"
    assert _workspaces(tmp_path) == []


@requires_enforcement
def test_memory_growth_hits_a_real_child_address_space_limit_and_cleans_up(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.zarr.zip"
    with pytest.raises(BoundedProcessError):
        run_bounded_process(
            command=_command("from pathlib import Path; import sys; bytearray(512 * 1024 * 1024); Path(sys.argv[1]).write_bytes(b'ok')"),
            stdin=b"",
            destination=destination,
            limits=LIMITS,
        )
    assert not destination.exists()
    assert _workspaces(tmp_path) == []


@requires_enforcement
def test_kernel_file_size_limit_stops_oversized_output_and_preserves_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.zarr.zip"
    destination.write_bytes(b"previous complete artifact")
    with pytest.raises(BoundedProcessError):
        run_bounded_process(
            command=_command("from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'x' * 8192)"),
            stdin=b"",
            destination=destination,
            limits=LIMITS,
        )
    assert destination.read_bytes() == b"previous complete artifact"
    assert _workspaces(tmp_path) == []


@requires_enforcement
def test_reply_pipe_is_terminated_before_parent_retains_an_unbounded_result(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.zarr.zip"
    with pytest.raises(BoundedProcessOutputExceeded):
        run_bounded_process(
            command=_command("from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'ok'); print('x' * 2048)"),
            stdin=b"",
            destination=destination,
            limits=LIMITS,
        )
    assert not destination.exists()
    assert _workspaces(tmp_path) == []


@requires_enforcement
def test_extra_child_scratch_is_refused_and_cleaned_up(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.zarr.zip"
    with pytest.raises(BoundedProcessError, match="exactly its one output"):
        run_bounded_process(
            command=_command(
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'ok'); Path('unbounded-scratch').write_bytes(b'x')"
            ),
            stdin=b"",
            destination=destination,
            limits=LIMITS,
        )
    assert not destination.exists()
    assert _workspaces(tmp_path) == []


@requires_enforcement
def test_bounded_inspection_returns_only_a_capped_result_and_refuses_files(tmp_path: Path) -> None:
    result = run_bounded_process(
        command=_command("print('identity')"),
        stdin=b"raw payload",
        destination=None,
        limits=LIMITS,
        require_output=False,
    )
    assert result.output_path is None
    assert result.stdout == b"identity\n"


def test_unsupported_limit_runtime_fails_closed_before_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(isolation, "_resource_module", lambda: None)
    with pytest.raises(BoundedProcessUnavailable):
        run_bounded_process(
            command=_command("raise SystemExit(0)"),
            stdin=b"",
            destination=tmp_path / "artifact.zarr.zip",
            limits=LIMITS,
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="exercises the local platform's actual unsupported RLIMIT_AS behavior")
def test_runtime_that_rejects_a_locked_address_space_cap_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(BoundedProcessUnavailable, match="runtime rejected"):
        run_bounded_process(
            command=_command("raise SystemExit(0)"),
            stdin=b"",
            destination=tmp_path / "artifact.zarr.zip",
            limits=LIMITS,
        )


def test_input_over_its_declared_bound_fails_before_a_child_can_start(tmp_path: Path) -> None:
    too_small = ProcessAllocationLimits(
        address_space_bytes=LIMITS.address_space_bytes,
        output_bytes=LIMITS.output_bytes,
        stdin_bytes=1,
        stdout_bytes=LIMITS.stdout_bytes,
        stderr_bytes=LIMITS.stderr_bytes,
    )
    with pytest.raises(BoundedProcessError, match="above its 1-byte bound"):
        run_bounded_process(
            command=_command("raise SystemExit('must not run')"),
            stdin=b"xx",
            destination=tmp_path / "artifact.zarr.zip",
            limits=too_small,
        )
