# PatientVectorHub — Kubernetes NetworkPolicy manifests (Phase 10 / ADR-017)

Deny-by-default + explicit allow rules for every service this repo
actually deploys. Delivered as standalone, framework-agnostic manifests
here rather than folded into a Helm chart — there is currently no
`infra/helm/templates/` at all (only `infra/helm/values/{dev,prod}.yaml`
stubs), and standing up the full chart is Phase 12's job ("Helm deploy
`--atomic`"). These manifests are written so Phase 12 can either
`kubectl apply -f` them directly or template them into `templates/`
later without redesigning the policy itself.

## CNI requirement

NetworkPolicy enforcement depends on the cluster's CNI plugin — a
manifest that applies cleanly with `kubectl apply` is not proof it's
being enforced. `prod.yaml`'s `image.registry` comment (ECR) implies an
AWS-hosted cluster; AWS's own VPC CNI has supported NetworkPolicy
enforcement natively since v1.14 (`ENABLE_NETWORK_POLICY=true`), so
Calico is not necessarily required — but this hasn't been confirmed
against whatever cluster Phase 12 actually provisions. Verify with:

```bash
kubectl get pods -n pvh -l app.kubernetes.io/name=redis -o wide
kubectl run netpol-test --rm -it --image=busybox -n pvh -- wget -qO- --timeout=2 redis:6379
# should time out / connection refused once these policies are applied
# and the -f 30-api-gateway.yaml egress-to-redis rule is the only allow
```

## Labeling convention

Every selector below assumes `app.kubernetes.io/name: <service>` labels
(e.g. `app.kubernetes.io/name: api-gateway`), matching the convention
Phase 12's eventual Helm chart is expected to apply — see
`docs/PHASE_10_IMPLEMENTATION_PLAN.md` for the full label mapping if
Phase 12 needs to reconcile against something different.

## Files

| File | Covers |
|---|---|
| `00-default-deny-all.yaml` | Baseline: deny all ingress + egress for every pod in the namespace |
| `01-allow-dns-egress.yaml` | Universal allow for DNS (kube-dns/CoreDNS) — easy to forget, breaks everything silently without it |
| `10-data-plane.yaml` | postgres, redis |
| `11-vector-stores.yaml` | weaviate, qdrant |
| `12-vault.yaml` | vault |
| `13-kafka.yaml` | kafka |
| `14-keycloak.yaml` | keycloak |
| `20-api-gateway.yaml` | api-gateway (the one ingress-facing service) |
| `21-ingestion-workers.yaml` | celery-worker, celery-beat, kafka-consumer |
| `30-observability.yaml` | prometheus, grafana, jaeger, alertmanager |

## Known gaps, deliberately not solved here

- **Aiven-managed Postgres/Kafka in production** (ADR-009 pivoted
  production's data plane to Aiven-managed services, not
  self-hosted K8s pods) means `10-data-plane.yaml` and
  `13-kafka.yaml` below model the **docker-compose / self-hosted
  topology** — accurate for any environment that runs these as pods
  (a local-like staging cluster, for instance), but production's
  actual egress rule would instead need to allow HTTPS/Postgres-port
  traffic to Aiven's external endpoints, whose IP ranges aren't
  fixed any more than the LLM providers' are. Reconciling that is
  genuinely Phase 12's job, once the real Aiven service and its
  VPC-peering or allowlist approach is provisioned — flagged here so
  it isn't mistaken for an oversight.
- **External HTTPS egress** (LLM provider APIs — Anthropic/OpenAI/Gemini,
  HF Inference Endpoints, Cloudflare R2) is left as a broad `0.0.0.0/0`
  port-443 allow on api-gateway and the ingestion workers, not
  IP-allowlisted per provider. Provider IP ranges change without notice
  and aren't published as stable CIDRs by any of the four providers this
  codebase uses — an IP-allowlist would be more security theater than
  security. A DNS-aware egress policy (e.g. via Cilium's FQDN policies)
  would be the real fix, but that's a CNI-specific feature this
  CNI-agnostic manifest set deliberately doesn't assume.
- **Ingress from outside the cluster** (the actual internet-facing edge
  for api-gateway, and for Grafana if exposed) is out of scope for
  NetworkPolicy entirely — that's an Ingress/LoadBalancer + Phase 12's
  job, not something a NetworkPolicy resource controls.
