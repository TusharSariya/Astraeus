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


@requires_enforcement
def test_deadline_covers_blocked_stdin_and_preserves_previous_artifact(tmp_path: Path) -> None:
    import time
    from dataclasses import replace
    destination = tmp_path / "artifact.zarr.zip"
    destination.write_bytes(b"previous complete artifact")
    started = time.monotonic()
    with pytest.raises(BoundedProcessError, match="timeout"):
        run_bounded_process(
            command=_command("import time; time.sleep(2)"),
            stdin=b"x" * (1024 * 1024), destination=destination,
            limits=replace(LIMITS, stdin_bytes=1024 * 1024), timeout_seconds=.15,
        )
    assert time.monotonic() - started < 1
    assert destination.read_bytes() == b"previous complete artifact"
    assert _workspaces(tmp_path) == []


@requires_enforcement
def test_streaming_input_and_output_share_one_deadline(tmp_path: Path) -> None:
    from dataclasses import replace
    body = b"x" * (256 * 1024)
    result = run_bounded_process(
        command=_command(
            "import sys; from pathlib import Path; "
            "sys.stdout.buffer.write(b'a' * 131072); sys.stdout.buffer.flush(); "
            "data=sys.stdin.buffer.read(); Path(sys.argv[1]).write_bytes(str(len(data)).encode())"
        ), stdin=body, destination=tmp_path / "result",
        limits=replace(LIMITS, stdin_bytes=len(body), stdout_bytes=131072), timeout_seconds=3,
    )
    assert result.stdout == b"a" * 131072
    assert result.output_path.read_bytes() == str(len(body)).encode()
    assert _workspaces(tmp_path) == []


@requires_enforcement
@pytest.mark.parametrize("channel", ["stdout", "stderr"])
def test_output_overflow_stops_child_even_when_sigterm_is_ignored(tmp_path: Path, channel: str) -> None:
    import time
    started = time.monotonic()
    with pytest.raises(BoundedProcessOutputExceeded):
        run_bounded_process(
            command=_command(
                "import signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                f"sys.{channel}.write('x'*2048); sys.{channel}.flush(); time.sleep(2)"
            ), stdin=b"", destination=tmp_path / "artifact", limits=LIMITS, timeout_seconds=3,
        )
    assert time.monotonic() - started < 1
    assert _workspaces(tmp_path) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux process-group cleanup and /proc state")
def test_deadline_kills_descendant_holding_reply_pipe_after_parent_exits(tmp_path: Path) -> None:
    import time
    pid_path = tmp_path / "descendant.pid"
    started = time.monotonic()
    with pytest.raises(BoundedProcessError, match="timeout"):
        run_bounded_process(
            command=_command(
                "import subprocess,sys; from pathlib import Path; "
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)']); "
                f"Path({str(pid_path)!r}).write_text(str(child.pid))"
            ), stdin=b"", destination=tmp_path / "artifact", limits=LIMITS, timeout_seconds=.3,
        )
    assert time.monotonic() - started < 1.5
    pid = int(pid_path.read_text())
    status = Path(f"/proc/{pid}/status")
    # killpg queues SIGKILL; its return does not synchronize an orphan's
    # transition to zombie/absence. PID 1 may also reap it asynchronously.
    # This finite grace is much shorter than the fixture child's five-second
    # sleep, so a missing group kill still fails instead of passing naturally.
    stopped = False
    termination_deadline = time.monotonic() + .5
    try:
        while time.monotonic() < termination_deadline:
            try:
                state = status.read_text()
            except FileNotFoundError:
                stopped = True
                break
            if "State:\tZ" in state:
                stopped = True
                break
            time.sleep(.005)
        assert stopped, "descendant remained alive after bounded group termination"
    finally:
        if not stopped:
            # Keep the negative/mutated regression self-cleaning as well.
            import os
            import signal
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    assert _workspaces(tmp_path) == []


@pytest.mark.parametrize("timeout", [float('nan'), float('inf'), 0, -1])
def test_invalid_deadline_fails_before_launch(monkeypatch, tmp_path: Path, timeout: float) -> None:
    monkeypatch.setattr(isolation, '_resource_module', lambda: object())
    monkeypatch.setattr(isolation.subprocess, 'Popen', lambda *a, **k: pytest.fail('invalid deadline launched child'))
    with pytest.raises(ValueError, match='timeout'):
        run_bounded_process(command=_command('pass'), stdin=b'', destination=tmp_path/'artifact',
                            limits=LIMITS, timeout_seconds=timeout)


@requires_enforcement
def test_caller_cancellation_reaps_child_and_preserves_destination(monkeypatch, tmp_path: Path) -> None:
    launched = []
    original_popen = isolation.subprocess.Popen
    original_selector = isolation.selectors.DefaultSelector
    def launch(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        launched.append(process)
        return process
    class CancelledSelector(original_selector):
        def select(self, timeout=None):
            raise KeyboardInterrupt
    monkeypatch.setattr(isolation.subprocess, 'Popen', launch)
    monkeypatch.setattr(isolation.selectors, 'DefaultSelector', CancelledSelector)
    destination = tmp_path / 'artifact'
    destination.write_bytes(b'previous')
    with pytest.raises(KeyboardInterrupt):
        run_bounded_process(command=_command('import time;time.sleep(5)'), stdin=b'payload',
                            destination=destination, limits=LIMITS)
    assert len(launched) == 1 and launched[0].returncode is not None
    assert all(stream.closed for stream in (launched[0].stdin, launched[0].stdout, launched[0].stderr))
    assert destination.read_bytes() == b'previous' and _workspaces(tmp_path) == []


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux vfork path and actual hard limits')
def test_threaded_decoder_launch_avoids_parent_fork_handlers(tmp_path: Path) -> None:
    """Regression for the live OpenBLAS atfork / astronomy deadlock."""
    import os
    from concurrent.futures import ThreadPoolExecutor
    forks = []
    os.register_at_fork(before=lambda: forks.append(True))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(
            run_bounded_process,
            command=_command(
                'import resource,sys; from pathlib import Path; '
                f'assert resource.getrlimit(resource.RLIMIT_AS) == ({LIMITS.address_space_bytes},)*2; '
                f'assert resource.getrlimit(resource.RLIMIT_FSIZE) == ({LIMITS.output_bytes},)*2; '
                'Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())'
            ), stdin=b'bounded', destination=tmp_path / str(i), limits=LIMITS,
            timeout_seconds=3,
        ) for i in range(6)]
        for future in futures:
            assert future.result(timeout=5).output_path.read_bytes() == b'bounded'
    assert forks == [], 'launch entered parent atfork handlers and can deadlock OpenBLAS'
    assert _workspaces(tmp_path) == []
