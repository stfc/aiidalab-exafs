"""Host-side TCP forwarder to the AiiDAlab container.

Fallback for hosts where ``launch.py``'s socat proxy containers cannot be used
(e.g. no permission to create a user-defined Docker network).  Prefer
``launch.py``, which resolves the container by name and needs no configuration.

Usage::

    # Resolve the container IP automatically:
    python proxy.py --container aiidalab_aiidalab-feff

    # Or point it at an address directly:
    AIIDALAB_CONTAINER_IP=172.17.0.2 python proxy.py

Forwards host 5050 -> container 5000 (AiiDA REST API) and host 2718 -> container
2718 (Marimo).  Both listeners are unauthenticated, so bind them to a host that
is not reachable from an untrusted network, or tunnel over SSH instead::

    ssh -L 5050:localhost:5050 -L 2718:localhost:2718 <host>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

#: (host_port, container_port) pairs to forward.
PORT_MAP = ((5050, 5000), (2718, 2718))


def resolve_container_ip(container: str | None) -> str:
    """Return the container's bridge IP.

    The IP is assigned at container start and changes whenever the container is
    recreated, so it must be looked up rather than hardcoded.
    """
    explicit = os.environ.get("AIIDALAB_CONTAINER_IP")
    if explicit:
        return explicit
    if not container:
        raise SystemExit(
            "Pass --container NAME or set AIIDALAB_CONTAINER_IP; the container's "
            "bridge IP changes every time the container is recreated."
        )
    fmt = "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"
    for runtime in ("docker", "podman"):
        try:
            out = subprocess.run(
                [runtime, "inspect", "-f", fmt, container],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
        except (OSError, subprocess.CalledProcessError):
            continue
        if out:
            return out[0]
    raise SystemExit(f"Could not determine an IP address for container {container!r}.")


def create_forwarder(target_ip: str, target_port: int):
    """Build a connection handler that pipes both directions to ``target_ip:port``."""

    async def forward(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            remote_reader, remote_writer = await asyncio.open_connection(target_ip, target_port)
        except OSError as exc:
            print(f"proxy: cannot reach {target_ip}:{target_port}: {exc}", file=sys.stderr)
            writer.close()
            return

        async def pipe(r: asyncio.StreamReader, w: asyncio.StreamWriter):
            try:
                while not r.at_eof():
                    data = await r.read(65536)
                    if not data:
                        break
                    w.write(data)
                    await w.drain()
            except OSError:
                pass
            finally:
                w.close()

        asyncio.create_task(pipe(reader, remote_writer))
        asyncio.create_task(pipe(remote_reader, writer))

    return forward


async def main(container: str | None, bind: str) -> None:
    """Serve every forwarder in :data:`PORT_MAP` until interrupted."""
    target_ip = resolve_container_ip(container)
    servers = []
    for host_port, container_port in PORT_MAP:
        servers.append(
            await asyncio.start_server(create_forwarder(target_ip, container_port), bind, host_port)
        )
        print(f"proxy: {bind}:{host_port} -> {target_ip}:{container_port}")

    async with asyncio.TaskGroup() as tg:
        for server in servers:
            tg.create_task(server.serve_forever())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", help="Container name to resolve an IP for.")
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="Address to listen on. Defaults to loopback; these ports are unauthenticated.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.container, args.bind))
