import sys
import os
from unittest.mock import Mock

# Import seed_data from repo root scripts directory
scripts_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, scripts_path)
from scripts import seed_data

def test_seed_data_reset_clears_known_tenant_rows() -> None:
    conn = Mock()

    seed_data._reset_seed_data(conn)

    assert conn.execute.call_count >= 4
