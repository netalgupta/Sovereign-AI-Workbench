"""Tests for CARD 07: Network Monitor backend (FR-1, FR-15).

Verifies:
1. get_active_connections() flags external IP as is_external=True and loopback as False.
2. Result is sorted with external connections first.
3. Telemetry metrics returns cpuPercent, memoryGb, and networkRate.
4. get_network_status() returns contract-compliant dictionary.
"""

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
        conns = get_active_connections()
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
