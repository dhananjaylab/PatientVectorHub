# PatientVectorHub — developer & operations workflow
#
# This is the Linux/macOS counterpart to scripts/dev.ps1 (Windows). Task
# names are kept 1:1 with dev.ps1's -Task values so `make dev` and
# `.\scripts\dev.ps1 -Task dev` do the same thing. New targets added for
# Phase 12 (terraform-*, helm-*, deploy-*) have no dev.ps1 equivalent yet —
# see infra/terraform/cluster/README.md for the Windows workflow for those.
#
# Reconstructed in Phase 12 (ADR-018 flagged this file as an unrecoverable
# [Binary file] marker blocking new targets) — verified against dev.ps1,
# docker-compose.yml, README.md, and ci.yml rather than re-guessed.

.PHONY: dev dev-lite stop clean logs \
        migrate migration seed setup-vector-stores kafka-topics vault-init \
        test-unit test-integration test-load test-e2e test-security test-phi lint \
        terraform-init terraform-plan terraform-apply terraform-destroy terraform-fmt terraform-test \
        helm-lint helm-template deploy-dev deploy-staging deploy-prod

SHELL := /bin/bash

# ── Local stack (mirrors dev.ps1) ──────────────────────────────────
dev:
	docker compose up -d
	@echo "Waiting for services to be healthy (up to 90s)..."
	@sleep 10
	@for svc in pvh-postgres pvh-redis pvh-weaviate pvh-vault pvh-kafka; do \
		echo "  Checking $$svc..."; \
		for i in $$(seq 1 18); do \
			status=$$(docker inspect --format='{{.State.Health.Status}}' $$svc 2>/dev/null || echo ""); \
			if [ "$$status" = "healthy" ]; then echo "  ok $$svc"; break; fi; \
			if [ $$i -eq 18 ]; then echo "  FAILED: $$svc not healthy after 90s"; exit 1; fi; \
			sleep 5; \
		done; \
	done
	@$(MAKE) vault-init
	@$(MAKE) migrate
	@$(MAKE) kafka-topics
	@$(MAKE) setup-vector-stores
	@$(MAKE) seed
	@echo ""
	@echo "  PatientVectorHub — Local Stack Ready"
	@echo "  FastAPI  -> http://localhost:8000/health"
	@echo "  Weaviate -> http://localhost:8080"
	@echo "  Qdrant   -> http://localhost:6333"
	@echo "  Vault    -> http://localhost:8200"
	@echo "  Keycloak -> http://localhost:8443"
	@echo "  Kafka    -> localhost:9092"
	@echo "  Embed    -> Hugging Face Inference Endpoint (ADR-012, not local)"

dev-lite:
	docker compose up -d postgres redis weaviate kafka vault
	@sleep 8
	@$(MAKE) vault-init
	@$(MAKE) migrate
	@$(MAKE) kafka-topics
	@$(MAKE) seed
	@echo "Lite stack ready (Keycloak + Qdrant skipped)"

stop:
	docker compose down

clean:
	docker compose down -v --remove-orphans

logs:
	docker compose logs -f --tail=50

migrate:
	cd api-gateway && python -m alembic upgrade head

migration:
	@read -p "Migration message: " msg; \
	cd api-gateway && python -m alembic revision --autogenerate -m "$$msg"

seed:
	python scripts/seed_data.py

setup-vector-stores:
	python scripts/setup_weaviate_schema.py
	python scripts/setup_qdrant_schema.py

kafka-topics:
	python scripts/create_kafka_topics.py

vault-init:
	bash scripts/vault_init.sh

# ── Tests ────────────────────────────────────────────────────────
test-unit:
	pytest tests/unit -v --tb=short

test-integration:
	pytest tests/integration -v --tb=short -m integration

test-load:
	locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 5m --host http://localhost:8000

test-e2e:
	cd dashboard && npx playwright test

test-security:
	pytest api-gateway/tests/security -v --tb=short

test-phi:
	python scripts/phi_leak_scan.py tests/artifacts/ --min-score 0.5

lint:
	ruff check .
	cd dashboard && npx eslint src/ --ext .ts,.tsx

# ── Phase 12: infrastructure ────────────────────────────────────────
# Two-stack layout (see infra/terraform/README.md for why):
#   bootstrap/ — apply once, long-lived (state bucket, ECR, GitHub OIDC role)
#   cluster/   — apply per review window, destroyed after (VPC, EKS)
# ENV selects which cluster workspace/tfvars to use (dev|staging|production).
ENV ?= dev

terraform-init:
	cd infra/terraform/cluster && terraform init -backend-config=envs/backend-$(ENV).hcl

terraform-fmt:
	cd infra/terraform && terraform fmt -recursive -check

terraform-plan:
	cd infra/terraform/cluster && terraform plan -var-file=envs/$(ENV).tfvars -out=$(ENV).tfplan

terraform-apply:
	cd infra/terraform/cluster && terraform apply $(ENV).tfplan

terraform-destroy:
	@echo "This tears down the $(ENV) EKS cluster + VPC. Bootstrap (state bucket, ECR, images) is untouched."
	cd infra/terraform/cluster && terraform destroy -var-file=envs/$(ENV).tfvars

terraform-test:
	pytest infra/terraform/tests -v --tb=short

helm-template:
	helm template pvh-app infra/helm/pvh-app -f infra/helm/values/$(ENV).yaml

helm-lint:
	helm lint infra/helm/pvh-app -f infra/helm/values/$(ENV).yaml

deploy-dev:
	$(MAKE) ENV=dev terraform-apply
	helm upgrade --install pvh-app infra/helm/pvh-app -f infra/helm/values/dev.yaml --namespace pvh-app --create-namespace --atomic --timeout 10m --wait

deploy-staging:
	$(MAKE) ENV=staging terraform-apply
	helm upgrade --install pvh-app infra/helm/pvh-app -f infra/helm/values/staging.yaml --namespace pvh-app --create-namespace --atomic --timeout 10m --wait

deploy-prod:
	@echo "Production deploys go through .github/workflows/deploy.yml (GitHub Environment approval gate)."
	@echo "This target is for a local break-glass deploy only — confirm with the on-call runbook first."
	helm upgrade --install pvh-app infra/helm/pvh-app -f infra/helm/values/prod.yaml --namespace pvh-app --atomic --timeout 10m --wait
