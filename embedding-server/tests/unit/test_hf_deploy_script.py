import importlib.util
from pathlib import Path

def _load_script_module():
    module_path = Path(__file__).resolve().parents[1] / ".." / "scripts" / "deploy_hf_embedding_endpoint.py"
    spec = importlib.util.spec_from_file_location("deploy_hf_embedding_endpoint", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def test_format_creation_error_mentions_billing_requirement():
    module = _load_script_module()

    message = module._format_creation_error(Exception("Payment method required for namespace: demo"))

    assert "billing" in message.lower()
    assert "https://huggingface.co/settings/billing" in message
