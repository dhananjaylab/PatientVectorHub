"""infra/terraform/tests/test_terraform_structure.py

Structural validation for the Terraform stacks added in Phase 12
(bootstrap/ and cluster/). This is NOT a substitute for `terraform
validate` / `terraform plan` -- those need registry.terraform.io and
real AWS credentials, neither of which this repo's CI (or the sandbox
that wrote these files) has by default. What this checks:

  1. every .tf file parses as syntactically valid HCL
  2. the specific security/cost properties this Phase 12 design
     depends on are actually present (not just "some bucket exists" --
     "the bucket has versioning, encryption, and prevent_destroy")
  3. no obviously-hardcoded secret material sits in checked-in .tf

Run via `make terraform-test` or `pytest infra/terraform/tests -v`.
Requires `python-hcl2` (parser only, no Terraform CLI/provider
download involved). Written and verified against python-hcl2==8.1.4 --
that version wraps every HCL string-literal label and value in an
extra pair of literal `"` characters in its Python output (e.g. a
`namespace = "pvh"` attribute comes back as the 5-character Python
string '"pvh"', not `pvh`) and tags parsed blocks with `__is_block__`
metadata. `_unwrap()` below undoes that -- checked by dumping real
parse output during this session, not assumed from an older hcl2
version's documented shape (the two are not compatible).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import hcl2
import pytest

TF_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_DIR = TF_ROOT / "bootstrap"
CLUSTER_DIR = TF_ROOT / "cluster"

ALL_TF_FILES = sorted(BOOTSTRAP_DIR.glob("*.tf")) + sorted(CLUSTER_DIR.glob("*.tf"))

SECRET_LOOKALIKE = re.compile(
    r"(AKIA[0-9A-Z]{16})"                     # AWS access key id shape
    r"|(-----BEGIN [A-Z ]*PRIVATE KEY-----)"  # PEM private key
    r"|(xox[baprs]-[0-9A-Za-z-]{10,})",       # Slack token shape, just in case
)

_META_KEYS = {"__is_block__", "__comments__", "__inline_comments__"}


def _unwrap(value: Any) -> Any:
    """Strip python-hcl2 8.x's literal quote-wrapping from a string, and
    recurse into dicts/lists. Non-string-literal values (numbers, bools,
    ${...} interpolations) pass through unchanged."""
    if isinstance(value, str) and len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    if isinstance(value, dict):
        return {_unwrap(k): _unwrap(v) for k, v in value.items() if k not in _META_KEYS}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def _load(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return hcl2.load(f)


def _labeled_resources(parsed: dict, res_type: str) -> dict[str, dict]:
    """resource "type" "name" { ... } -> {"name": {...attrs, unwrapped...}}"""
    out: dict[str, dict] = {}
    for block in parsed.get("resource", []):
        for raw_type, named in block.items():
            if _unwrap(raw_type) != res_type:
                continue
            for raw_name, attrs in named.items():
                out[_unwrap(raw_name)] = _unwrap(attrs)
    return out


def _labeled_blocks(parsed: dict, block_type: str) -> dict[str, dict]:
    """variable "name" { ... } / module "name" { ... } -> {"name": {...attrs}}"""
    out: dict[str, dict] = {}
    for block in parsed.get(block_type, []):
        for raw_name, attrs in block.items():
            out[_unwrap(raw_name)] = _unwrap(attrs)
    return out


def _first_locals(parsed: dict) -> dict:
    blocks = parsed.get("locals", [])
    return _unwrap(blocks[0]) if blocks else {}


@pytest.mark.parametrize("path", ALL_TF_FILES, ids=lambda p: str(p.relative_to(TF_ROOT)))
def test_tf_file_parses(path: Path):
    """Every .tf file must be syntactically valid HCL."""
    _load(path)  # raises on malformed syntax


@pytest.mark.parametrize("path", ALL_TF_FILES, ids=lambda p: str(p.relative_to(TF_ROOT)))
def test_no_hardcoded_secret_material(path: Path):
    text = path.read_text()
    match = SECRET_LOOKALIKE.search(text)
    assert not match, f"{path}: looks like hardcoded credential material: {match.group(0)[:12]}..."


class TestBootstrapStack:
    def test_state_bucket_hardened(self):
        parsed = _load(BOOTSTRAP_DIR / "state_backend.tf")
        buckets = _labeled_resources(parsed, "aws_s3_bucket")
        assert len(buckets) == 1, "expected exactly one aws_s3_bucket in state_backend.tf"
        bucket = next(iter(buckets.values()))
        assert bucket["lifecycle"][0]["prevent_destroy"] is True, (
            "the tfstate bucket must have prevent_destroy=true -- it must outlive "
            "every cluster/ terraform destroy"
        )
        assert _labeled_resources(parsed, "aws_s3_bucket_versioning"), "state bucket must have versioning enabled"
        assert _labeled_resources(
            parsed, "aws_s3_bucket_server_side_encryption_configuration"
        ), "state bucket must have SSE configured"
        assert _labeled_resources(
            parsed, "aws_s3_bucket_public_access_block"
        ), "state bucket must have a public access block"

    def test_no_dynamodb_lock_table_anywhere_in_bootstrap(self):
        """Confirms the S3-native-locking design choice -- a regression here
        (someone adding a DynamoDB table back) means the stated rationale
        (TF >= 1.10 use_lockfile) silently changed."""
        for path in BOOTSTRAP_DIR.glob("*.tf"):
            parsed = _load(path)
            assert not _labeled_resources(parsed, "aws_dynamodb_table"), (
                f"{path}: unexpected aws_dynamodb_table -- state locking is meant "
                "to use S3 native locking (use_lockfile), not DynamoDB"
            )

    def test_ecr_repos_present_and_scanned(self):
        parsed = _load(BOOTSTRAP_DIR / "ecr.tf")
        repos = _labeled_resources(parsed, "aws_ecr_repository")
        assert len(repos) == 1, "expected one for_each aws_ecr_repository block"
        repo = next(iter(repos.values()))
        assert repo["for_each"] == "${toset(local.ecr_repos)}"
        assert repo["image_scanning_configuration"][0]["scan_on_push"] is True
        assert repo["image_tag_mutability"] == "IMMUTABLE"

    def test_ecr_repo_names_match_deploy_workflow(self):
        """deploy.yml pushes to $ECR/pvh-api and $ECR/pvh-workers -- if these
        drift, the CI push step 404s."""
        parsed = _load(BOOTSTRAP_DIR / "ecr.tf")
        ecr_repos = _first_locals(parsed)["ecr_repos"]
        assert set(ecr_repos) == {"pvh-api", "pvh-workers"}

    def test_github_oidc_trust_policy_scoped_to_repo_and_environments(self):
        text = (BOOTSTRAP_DIR / "github_oidc.tf").read_text()
        assert "token.actions.githubusercontent.com:sub" in text, (
            "expected a `sub` claim condition -- an unscoped OIDC trust "
            "policy lets any repo/workflow assume the deploy role"
        )
        assert "var.github_repo" in text
        assert "var.github_environments" in text
        # aud condition prevents a token minted for some other AWS-integrated
        # audience from being replayed against this trust policy
        assert "token.actions.githubusercontent.com:aud" in text

    def test_deploy_role_has_no_wildcard_iam_or_ec2_actions(self):
        """The deploy role is for image push + kubectl/helm only -- it must
        not accumulate eks:CreateCluster / iam:* / ec2:* over time."""
        parsed = _load(BOOTSTRAP_DIR / "github_oidc.tf")
        policies = _labeled_resources(parsed, "aws_iam_role_policy")
        policy_text = str(policies)
        for forbidden in ["iam:*", "ec2:*", "eks:CreateCluster", "eks:DeleteCluster"]:
            assert forbidden not in policy_text, f"deploy role policy must not contain {forbidden}"


class TestClusterStack:
    def test_eks_uses_auto_mode(self):
        parsed = _load(CLUSTER_DIR / "eks.tf")
        modules = _labeled_blocks(parsed, "module")
        eks_modules = [m for m in modules.values() if m.get("source") == "terraform-aws-modules/eks/aws"]
        assert len(eks_modules) == 1
        assert eks_modules[0].get("compute_config", {}).get("enabled") is True

    def test_s3_backend_uses_native_locking(self):
        parsed = _load(CLUSTER_DIR / "versions.tf")
        tf_blocks = parsed.get("terraform", [])
        assert tf_blocks, "expected a terraform {} block in versions.tf"
        backend_list = tf_blocks[0].get("backend")
        assert backend_list, 'expected a backend "s3" block'
        backend_body = _unwrap(backend_list[0])
        assert backend_body["s3"]["use_lockfile"] is True

    def test_pod_identity_namespace_matches_network_policies(self):
        """Regression guard for a wrong assumption caught during this
        session's own review: the repo's actual NetworkPolicies
        (infra/k8s/network-policies/*.yaml) all use a single flat `pvh`
        namespace, not a six-namespace layout. If someone "fixes" this
        back to pvh-security later without updating the NetworkPolicies
        too, Pod Identity silently won't apply to the right pods."""
        parsed = _load(CLUSTER_DIR / "pod_identity.tf")
        associations = _labeled_resources(parsed, "aws_eks_pod_identity_association")
        assert len(associations) == 1
        assoc = next(iter(associations.values()))
        assert assoc["namespace"] == "pvh"

    def test_environment_variable_is_validated(self):
        parsed = _load(CLUSTER_DIR / "variables.tf")
        variables = _labeled_blocks(parsed, "variable")
        assert "validation" in variables["environment"], "environment must be validated to dev/staging/production"

    def test_no_always_on_assumption_leaked_into_defaults(self):
        """Guards decision 1 (review-window, not continuous): nothing here
        should default to multi-AZ-NAT or a large minimum node count,
        which would only make sense for an always-on cluster."""
        parsed = _load(CLUSTER_DIR / "variables.tf")
        variables = _labeled_blocks(parsed, "variable")
        assert variables["single_nat_gateway"]["default"] is True
        assert variables["az_count"]["default"] == 2

    def test_vpc_and_eks_pinned_to_current_verified_versions(self):
        """Regression guard against silently drifting to an unverified
        module version during a future edit."""
        vpc_parsed = _load(CLUSTER_DIR / "vpc.tf")
        vpc_modules = _labeled_blocks(vpc_parsed, "module")
        assert vpc_modules["vpc"]["version"] == "~> 6.0"

        eks_parsed = _load(CLUSTER_DIR / "eks.tf")
        eks_modules = _labeled_blocks(eks_parsed, "module")
        assert eks_modules["eks"]["version"] == "~> 21.0"
