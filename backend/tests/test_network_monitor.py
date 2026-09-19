"""Tests for CARD 07: Network Monitor backend (FR-1, FR-15).

Verifies:
1. get_active_connections() flags external IP as is_external=True and loopback as False.
2. Result is sorted with external connections first.
3. Telemetry metrics returns cpuPercent, memoryGb, and networkRate.
4. get_network_status() returns contract-compliant dictionary.
5. An external socket owned by THIS application's process tree flips the
   monitor red — the /monitor demo beat, proven offline with a mocked
   psutil connection list (hard constraint #1 forbids the real thing).
"""

import os

from unittest.mock import MagicMock, patch
from backend.audit.network_monitor import (
    _is_ip_external,
    get_active_connections,
    get_network_status,
    get_system_metrics,
)


def test_ip_external_classification():
    assert not _is_ip_external("127.0.0.1")
    assert not _is_ip_external("127.0.0.5")
    assert not _is_ip_external("0.0.0.0")
    assert not _is_ip_external("::1")
    # Private RFC1918 / Docker bridge
    assert not _is_ip_external("10.0.0.1")
    assert not _is_ip_external("172.17.0.2")
    assert not _is_ip_external("192.168.1.10")

    # Real external public IPs
    assert _is_ip_external("8.8.8.8")
    assert _is_ip_external("1.1.1.1")
    assert _is_ip_external("142.250.190.46")


def test_get_active_connections_mocked():
    """Classification and ordering, over machine scope.

    Explicitly scope="machine" because the mocked sockets carry pids 100
    and 101, which are not in this process tree — under the default
    application scope they are correctly filtered out, since a socket
    belonging to another process is not evidence about this one. What
    this test is actually about is that an external remote is recognised
    and sorted to the top, which is orthogonal to whose socket it is."""
    mock_local = MagicMock(ip="127.0.0.1", port=8000)
    mock_internal_remote = MagicMock(ip="127.0.0.1", port=5173)
    mock_external_remote = MagicMock(ip="8.8.8.8", port=443)

    conn_internal = MagicMock(
        laddr=mock_local, raddr=mock_internal_remote, status="ESTABLISHED", pid=100
    )
    conn_external = MagicMock(
        laddr=mock_local, raddr=mock_external_remote, status="ESTABLISHED", pid=101
    )

    with patch("psutil.net_connections", return_value=[conn_internal, conn_external]):
        conns = get_active_connections(scope="machine")
        assert len(conns) == 2
        # External connection must surface at the top
        assert conns[0].is_external is True
        assert conns[0].remote_address == "8.8.8.8:443"
        assert conns[1].is_external is False
        assert conns[1].remote_address == "127.0.0.1:5173"


def test_get_system_metrics():
    metrics = get_system_metrics()
    assert metrics.cpuPercent >= 0.0
    assert metrics.memoryGb >= 0.0
    assert isinstance(metrics.networkRate, str)


def test_get_network_status_structure():
    status = get_network_status()
    assert "status" in status
    assert "externalCount" in status
    assert "connections" in status
    assert "metrics" in status
    assert "is_air_gapped" in status


# ---- zero-egress scoping (CARD 07) --------------------------------------


def test_external_count_covers_this_application_not_the_whole_machine():
    """The flagship claim is that THIS APPLICATION makes no outbound
    calls. Counting host-wide sockets made the UI display
    "ALERT: External Traffic - 44 external connections" on a developer
    machine where the backend owned ZERO of them; the rest belonged to an
    IDE language server, a browser, Spotify and Windows Defender.

    A safety indicator that fires on someone else's music stream is worse
    than no indicator: it trains people to ignore it, and in a demo it
    reads as the product disproving its own core promise."""
    from backend.audit.network_monitor import get_network_status

    status = get_network_status()

    assert status["scope"] == "application"
    assert status["externalCount"] == 0
    assert status["is_air_gapped"] is True
    assert status["status"] == "secure"


def test_machine_wide_figure_is_reported_separately_and_labelled():
    """Hiding it would make the panel look like it was dodging an
    inconvenient number. It is real and useful context -- "your laptop is
    online, this app still isn't" -- it simply must not drive the alarm."""
    from backend.audit.network_monitor import get_network_status

    status = get_network_status()

    assert "hostExternalCount" in status
    assert "Not this workbench" in status["hostNote"]


def test_unattributable_sockets_are_not_counted_as_ours():
    """A socket with no PID cannot be shown to be ours. Counting it would
    reintroduce the false alarm this scoping removes."""
    from backend.audit.network_monitor import get_active_connections

    app_conns = get_active_connections(scope="application")
    machine_conns = get_active_connections(scope="machine")

    assert len(app_conns) <= len(machine_conns)


# ---- the /monitor red-state demo beat (Task 4) ---------------------------


def _mock_own_external_socket():
    """A socket on a public IP owned by THIS process tree.

    The application-scope filter in get_active_connections_with_status
    (``c.pid in own_pids``) keeps only sockets whose pid is us or a child
    we spawned, so the mock must carry ``pid=os.getpid()`` or it is
    correctly filtered out and never reaches the external count.
    """
    return MagicMock(
        laddr=MagicMock(ip="127.0.0.1", port=8000),
        raddr=MagicMock(ip="8.8.8.8", port=443),
        status="ESTABLISHED",
        pid=os.getpid(),
    )


def test_own_external_socket_flips_the_status_to_external_detected():
    """The demo beat, proven offline.

    The whole point of the /monitor page is "prove the monitor goes red,
    on camera". Red fires on externalCount >= 1 for THIS application's
    process tree — no other figure. The only offline way to exercise that
    path is a mocked psutil connection list carrying our own pid: making
    a REAL outbound call to a public IP would be exactly the egress this
    product exists to detect (hard constraint #1). A mock is not a
    substitute for the real socket, but there is no real socket to make;
    this proves the classification -> count -> status path is alive.
    """
    with patch("psutil.net_connections", return_value=[_mock_own_external_socket()]):
        status = get_network_status()

    assert status["status"] == "external_detected"
    assert status["externalCount"] >= 1
    assert status["is_air_gapped"] is False
    assert status["scope"] == "application"
    assert status["connections"][0]["is_external"] is True


def test_api_network_status_goes_red_end_to_end():
    """The red state survives the whole HTTP path, not just the unit.

    A tool is not built until it has been CALLED; the route is what the
    frontend poll hits every second, so the red signal has to survive
    /api/network/status exactly as the browser consumes it."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with patch("psutil.net_connections", return_value=[_mock_own_external_socket()]):
        response = TestClient(app).get("/api/network/status")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "external_detected"
    assert data["externalCount"] >= 1
    assert data["is_air_gapped"] is False


def test_host_wide_figure_survives_the_mock_without_driving_the_alarm():
    """With the mocked socket, hostExternalCount reflects it too — but the
    ALARM key (externalCount / status / is_air_gapped) stays the claim."""
    with patch("psutil.net_connections", return_value=[_mock_own_external_socket()]):
        status = get_network_status()

    assert status["hostExternalCount"] >= 1
    assert status["status"] == "external_detected"
