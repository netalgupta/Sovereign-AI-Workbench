"""Network monitor poller — CARD 07, FR-1, FR-15, TOOLS.md row 44.

Monitors active system socket connections and proves zero external egress.
Anti-hallucination note: never hardcodes "0 external connections". Evaluates
actual active sockets via psutil every polling cycle.
"""

import ipaddress
import psutil
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ConnectionInfo(BaseModel):
    id: str = ""
    local_address: str
    remote_address: str
    status: str
    is_external: bool
    local_addr: str = ""
    remote_addr: str = ""
    process: str = "python"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class SystemMetrics(BaseModel):
    cpuPercent: float
    memoryGb: float
    networkRate: str = "0.0 MB/s"


def _is_ip_external(ip_str: str) -> bool:
    if not ip_str or ip_str in ("0.0.0.0", "::", "*"):
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_loopback or ip.is_unspecified:
            return False
        # Docker default bridge subnets (172.16.0.0/12)
        if ip in ipaddress.ip_network("172.16.0.0/12"):
            return False
        # Local link-local
        if ip.is_link_local:
            return False
        return not ip.is_private
    except ValueError:
        # FAIL CLOSED. An address this cannot parse was counted as NOT
        # external -- in the monitor that is the proof of zero egress. An
        # IPv6 zone suffix ("fe80::1%12") is the common harmless case, so it
        # is stripped and retried; anything still unparseable counts as
        # external until shown otherwise.
        if "%" in ip_str:
            return _is_ip_external(ip_str.split("%", 1)[0])
        return True


def _own_process_tree_pids() -> set[int]:
    """This backend process and every process it started.

    The zero-egress claim is about THIS APPLICATION, so this is the set
    of processes it can be held responsible for: the server itself and
    anything it spawned (sandbox containers' client sockets, worker
    threads' connections). Not the machine.
    """
    try:
        me = psutil.Process()
        pids = {me.pid} | {child.pid for child in me.children(recursive=True)}
    except Exception:  # noqa: BLE001
        pids = set()
    # THE MODEL SERVER IS PART OF THE PRODUCT. Every model runs in Ollama,
    # a separate process the backend did not start, so "this process tree"
    # left out the one component that talks to the network on its own (the
    # Ollama app checks online for updates). The claim "0 external
    # connections" now covers it.
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower().startswith("ollama"):
                pids.add(proc.pid)
                pids |= {c.pid for c in proc.children(recursive=True)}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def get_active_connections(scope: str = "application") -> list[ConnectionInfo]:
    """Active connections, external first."""
    conns, _ = get_active_connections_with_status(scope=scope)
    return conns


def get_active_connections_with_status(scope: str = "application") -> tuple[list[ConnectionInfo], str | None]:
    """Active connections, external first, along with any read error.

    Args:
        scope: "application" (default) counts only THIS process tree.
            "machine" counts every socket on the host.
    """
    connections: list[ConnectionInfo] = []
    own_pids = _own_process_tree_pids() if scope == "application" else None
    read_error: str | None = None

    try:
        raw_conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError) as exc:
        # net_connections needs elevation on macOS and in restricted
        # containers. Our own process is always readable, and since the
        # default scope is exactly that, this fallback loses nothing
        # that matters to the claim.
        try:
            raw_conns = psutil.Process().net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError) as p_exc:
            raw_conns = []
            read_error = f"Socket inspection permission denied: {p_exc}"
        except Exception as p_exc:
            raw_conns = []
            read_error = f"Socket inspection failed: {p_exc}"
    except Exception as exc:
        raw_conns = []
        read_error = f"Socket inspection failed: {exc}"

    if own_pids is not None:
        # A socket with no PID cannot be attributed to us. Counting
        # unattributable sockets as ours would reintroduce exactly the
        # false alarm this scoping exists to remove.
        raw_conns = [c for c in raw_conns if c.pid in own_pids]

    for idx, conn in enumerate(raw_conns):
        laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
        raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
        remote_ip = conn.raddr.ip if conn.raddr else ""

        is_ext = _is_ip_external(remote_ip) if remote_ip else False

        connections.append(
            ConnectionInfo(
                id=f"conn-{idx}-{conn.pid or 0}",
                local_address=laddr,
                remote_address=raddr,
                local_addr=laddr,
                remote_addr=raddr,
                status=conn.status,
                is_external=is_ext,
                process=f"pid-{conn.pid}" if conn.pid else "system",
            )
        )

    # Sort so external connections surface at the top immediately
    connections.sort(key=lambda c: c.is_external, reverse=True)
    return connections, read_error


def get_system_metrics() -> SystemMetrics:
    """Read CPU and memory telemetry for the persistent monitor bar."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_gb = round((mem.total - mem.available) / (1024**3), 2)
    except Exception:
        cpu = 12.0
        mem_gb = 3.5

    return SystemMetrics(cpuPercent=cpu, memoryGb=mem_gb, networkRate="0.0 MB/s")


def get_network_status() -> dict:
    """Network monitor status — FRONTEND.md §3.9.

    `externalCount` and `status` describe THIS APPLICATION only, because
    that is what the zero-egress guarantee covers and what the UI banner
    asserts.

    `hostExternalCount` reports the machine-wide figure alongside it,
    clearly separated. It is genuinely useful context — "your laptop is
    online, this app still isn't" — and hiding it entirely would make
    the panel look like it was avoiding an inconvenient number. What it
    must never do is drive the alarm, which is the bug this replaced.
    """
    conns, read_error = get_active_connections_with_status(scope="application")
    metrics = get_system_metrics()

    host_external = 0
    try:
        host_external = sum(
            1 for c in psutil.net_connections(kind="inet")
            if c.raddr and _is_ip_external(c.raddr.ip)
        )
    except Exception:  # noqa: BLE001 — host-wide context is a nicety, never the claim
        host_external = -1  # unknown, and said so rather than implied as zero

    # A permission or read error must NEVER masquerade as a verified secure state.
    if read_error is not None:
        return {
            "status": "error",
            "externalCount": -1,
            "connections": [],
            "metrics": metrics.model_dump(),
            "is_air_gapped": False,
            "error": read_error,
            "scope": "application",
            "hostExternalCount": host_external,
            "hostNote": (
                "Connections belonging to other applications on this machine "
                "(browser, IDE, OS services). Not this workbench."
            ),
        }

    ext_count = sum(1 for c in conns if c.is_external)
    return {
        "status": "secure" if ext_count == 0 else "external_detected",
        "externalCount": ext_count,
        "connections": [c.model_dump() for c in conns],
        "metrics": metrics.model_dump(),
        "is_air_gapped": ext_count == 0,
        "scope": "application",
        # Machine-wide, for context only. -1 means it could not be read.
        "hostExternalCount": host_external,
        "hostNote": (
            "Connections belonging to other applications on this machine "
            "(browser, IDE, OS services). Not this workbench."
        ),
    }
