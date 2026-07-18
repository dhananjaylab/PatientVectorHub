from unittest.mock import Mock

from scripts import seed_data


def test_seed_data_reset_clears_known_tenant_rows() -> None:
    conn = Mock()

    seed_data._reset_seed_data(conn)

    assert conn.execute.call_count >= 4
