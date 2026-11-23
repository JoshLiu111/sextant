"""A throwaway local Postgres cluster for tests and e2e. Never touches Neon.

Library use (tests/conftest.py):  ``with ephemeral_cluster() as url: ...``

Command use (Playwright starts the compute service this way when no
``E2E_DATABASE_URL`` is given)::

    uv run python scripts/ephemeral_postgres.py -- uv run uvicorn main:app

starts a cluster, runs the command with ``DATABASE_URL`` pointing at a fresh
database, and removes the cluster when the command exits or is terminated.
Needs ``initdb``/``pg_ctl`` on PATH or a Homebrew ``postgresql@NN``.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def find_pg_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in sorted(Path("/opt/homebrew/opt").glob("postgresql@*/bin"), reverse=True):
        if (candidate / name).exists():
            return str(candidate / name)
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def ephemeral_cluster() -> Iterator[str]:
    """Yield the URL of the ``postgres`` database on a fresh temp cluster."""
    initdb, pg_ctl = find_pg_bin("initdb"), find_pg_bin("pg_ctl")
    if not (initdb and pg_ctl):
        raise FileNotFoundError("Postgres binaries (initdb, pg_ctl) not found")
    tmp = Path(tempfile.mkdtemp(prefix="sextant-pg-"))
    data = tmp / "data"
    port = _free_port()
    subprocess.run(
        [initdb, "-D", str(data), "-U", "postgres", "--auth=trust", "-E", "UTF8"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            pg_ctl, "-D", str(data), "-l", str(tmp / "log"), "-w", "start",
            "-o", f"-p {port} -k {tmp} -c listen_addresses=127.0.0.1 -c fsync=off",
        ],
        check=True,
        capture_output=True,
    )
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run([pg_ctl, "-D", str(data), "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    command = argv[argv.index("--") + 1 :]
    with ephemeral_cluster() as url:
        env = {**os.environ, "DATABASE_URL": url}
        child = subprocess.Popen(command, env=env)

        def forward(signum, _frame):
            child.send_signal(signum)

        signal.signal(signal.SIGTERM, forward)
        signal.signal(signal.SIGINT, forward)
        return child.wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
