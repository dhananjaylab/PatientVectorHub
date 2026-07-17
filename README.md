# PatientVectorHub

Enterprise-scale HIPAA-compliant RAG platform for 1.5B patient documents. Designed and optimized for native Windows environments.

---

## 🏗️ Architecture Overview

All-OSS stack — no paid managed services required:

- **API Gateway**: FastAPI + Kong OSS
- **Auth & Identity**: Keycloak 24 (OIDC PKCE)
- **Secrets Management**: HashiCorp Vault OSS
- **Messaging & Ingestion**: Apache Kafka via Strimzi
- **Database**: PostgreSQL 15 (with Row Level Security)
- **Primary Vector Store**: Weaviate
- **Disaster Recovery Vector Store**: Qdrant
- **Embeddings**: Self-hosted clinical-bert (`emilyalsentzer/Bio_ClinicalBERT`)
- **LLM Integrations**: Anthropic Claude, OpenAI GPT-4o, Google Gemini
- **Document & Backup Storage**: Cloudflare R2 / S3-compatible API
- **Observability**: Prometheus + Grafana + Jaeger + Loki

---

## 📋 Prerequisites

Before starting, ensure you have the following software installed on Windows:

### Required
1. **Docker Desktop for Windows**
   - [Download Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Ensure the Linux Containers mode is enabled (WSL 2 backend is highly recommended).
   - Ensure `docker compose` is available: `docker compose version`
2. **Python 3.9+**
   - [Download Python](https://www.python.org/downloads/)
   - **Important**: Make sure to check the box to **"Add Python to PATH"** during installation.
   - Verify installation: `python --version` & `pip --version`
3. **Node.js 18+** (Optional, only needed for running the frontend dashboard)
   - [Download Node.js](https://nodejs.org/)

### Optional
- **PowerShell 7+** (Provides a superior CLI environment: `winget install Microsoft.PowerShell`)
- **Make for Windows** (If you prefer using `make` commands: install via Chocolatey `choco install make` or download via MinGW)

---

## 🚀 Setup Guides

Choose one of the two options below depending on your development requirements.

### 🐳 Option A: Docker (Recommended for Local Development)

This launches the full 8-service container stack locally on your Windows machine.

#### 1. Setup Environment
```cmd
REM Copy the environment template
copy .env.example .env

REM Open in Notepad to add your LLM API keys (e.g. ANTHROPIC_API_KEY)
notepad .env
```

#### 2. Start the Local Stack
Choose the CLI tool you prefer to orchestrate the Docker container setup:

- **PowerShell** (Recommended):
  ```powershell
  # Set execution policy if you haven't already (run once as user)
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

  # Start the development task
  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev
  ```
- **Command Prompt (CMD)**:
  ```cmd
  scripts\dev.bat dev
  ```
- **Make**:
  ```cmd
  make dev
  ```

*Note: The startup process spins up the containers, waits for services to become healthy (~90s), runs migrations, sets up schemas, and seeds synthetic test data.*

---

### ☁️ Option B: Cloud Services (Production-Ready Development)

Use this option if you connect to managed cloud services (e.g. RDS PostgreSQL, AWS MSK, Weaviate Cloud, Qdrant Cloud) while running only the FastAPI app and embedding server locally.

#### 1. Configure Cloud Endpoints
```cmd
copy .env.example.cloud .env
notepad .env
```
Fill in the cloud endpoint details in `.env`:
- `DATABASE_URL` / `DATABASE_URL_SYNC` (PostgreSQL)
- `REDIS_URL` (Redis)
- `KAFKA_BROKERS` (Kafka broker list)
- `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT`
- `QDRANT_HOST`, `QDRANT_PORT`
- Cloudflare R2 Credentials (`R2_ENDPOINT_URL`, access keys, and buckets)
- LLM API keys

#### 2a. Install Local Dependencies (Option: Single Unified venv)
```cmd
REM Create a single virtual environment
python -m venv venv
call venv\Scripts\activate.bat

REM Install Python dependencies
pip install --upgrade pip
pip install -r api-gateway\requirements.txt
pip install -r ingestion\requirements.txt
pip install -r rag-engine\requirements.txt
pip install -r vector-store\requirements.txt
pip install -r requirements-dev.txt
```

#### 2b. Install Local Dependencies (Option: Separate venv per Service - Recommended for Service Isolation)

This approach isolates each service's dependencies, preventing conflicts and mapping to production deployments.

```cmd
REM 1. API Gateway venv
python -m venv venv-api-gateway
call venv-api-gateway\Scripts\activate.bat
pip install --upgrade pip
pip install -r api-gateway\requirements.txt
deactivate

REM 2. Ingestion Service venv
python -m venv venv-ingestion
call venv-ingestion\Scripts\activate.bat
pip install --upgrade pip
pip install -r ingestion\requirements.txt
deactivate

REM 3. RAG Engine venv
python -m venv venv-rag-engine
call venv-rag-engine\Scripts\activate.bat
pip install --upgrade pip
pip install -r rag-engine\requirements.txt
deactivate

REM 4. Vector Store venv
python -m venv venv-vector-store
call venv-vector-store\Scripts\activate.bat
pip install --upgrade pip
pip install -r vector-store\requirements.txt
deactivate
```

**Separate venv Pros & Cons:**
- ✅ **Isolation**: Each service's dependencies won't conflict
- ✅ **Production-like**: Maps to how services are deployed separately
- ✅ **Efficient**: Only installs what each service needs
- ❌ **Friction**: Must activate/deactivate different venvs per service
- ❌ **Disk Space**: Redundant packages across venvs (~8-12GB total vs. ~4-5GB unified)

#### 2c. Initialize Infrastructure

Choose the venv activation that matches your setup:

```cmd
REM If using unified venv:
call venv\Scripts\activate.bat

REM If using separate venvs, activate the API gateway venv:
call venv-api-gateway\Scripts\activate.bat

REM Run Alembic database migrations
cd api-gateway
python -m alembic upgrade head
cd ..

REM Seed synthetic database data
python scripts\seed_data.py

REM Initialize vector store schemas
python scripts\setup_weaviate_schema.py
python scripts\setup_qdrant_schema.py

REM Create Kafka topics
python scripts\create_kafka_topics.py
```

#### 3. Start Local Python Servers
Open two separate Command Prompt or PowerShell terminals:

**If using unified venv:**
```cmd
REM Terminal 1 - Embedding Server (port 8001)
call venv\Scripts\activate.bat
cd ingestion\embedding-server
python main.py

REM Terminal 2 - FastAPI Gateway (port 8000)
call venv\Scripts\activate.bat
cd api-gateway
uvicorn src.main:app --reload --port 8000
```

**If using separate venvs:**
```cmd
REM Terminal 1 - Embedding Server (port 8001)
call venv-ingestion\Scripts\activate.bat
cd ingestion\embedding-server
python main.py

REM Terminal 2 - FastAPI Gateway (port 8000)
call venv-api-gateway\Scripts\activate.bat
cd api-gateway
uvicorn src.main:app --reload --port 8000
```

**For PowerShell users:**
```powershell
REM Terminal 1 - Embedding Server
.\venv-ingestion\Scripts\Activate.ps1
cd ingestion\embedding-server
python main.py

REM Terminal 2 - FastAPI Gateway
.\venv-api-gateway\Scripts\Activate.ps1
cd api-gateway
uvicorn src.main:app --reload --port 8000
```

---

## 🛠️ Service Endpoints

When running the local Docker stack, you can access the following services:

| Service | Protocol / Port | URL |
| :--- | :--- | :--- |
| **FastAPI Gateway** | HTTP 8000 | [http://localhost:8000](http://localhost:8000) |
| **API Interactive Docs** | HTTP 8000 | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **FastAPI Health Check** | HTTP 8000 | [http://localhost:8000/health](http://localhost:8000/health) |
| **Weaviate Console/API** | HTTP 8080 | [http://localhost:8080](http://localhost:8080) |
| **Qdrant Dashboard** | HTTP 6333 | [http://localhost:6333/dashboard](http://localhost:6333/dashboard) |
| **HashiCorp Vault** | HTTP 8200 | [http://localhost:8200](http://localhost:8200) |
| **Keycloak Admin** | HTTP 8080 | [http://localhost:8080/admin](http://localhost:8080/admin) |
| **Keycloak OIDC** | HTTP 8080 | [http://localhost:8080](http://localhost:8080) |
| **Apache Kafka** | TCP 9092 | `localhost:9092` |
| **Redis Cache** | TCP 6379 | `localhost:6379` |
| **Embedding Server** | HTTP 8001 | [http://localhost:8001](http://localhost:8001) |
| **Jaeger Query UI** | HTTP 16686 | [http://localhost:16686](http://localhost:16686) |
| **Jaeger OTLP gRPC** | gRPC 4317 | `localhost:4317` (trace collection) |
| **Web Dashboard** | HTTP 5173 | [http://localhost:5173](http://localhost:5173) (requires `npm run dev`) |

---

## 🔑 Test Credentials

All synthetic test users share the password: `test-password-123`

| Email | Role | Tenant |
| :--- | :--- | :--- |
| `admin@tenant1.test` | Admin | Acme Health |
| `engineer@tenant1.test` | Engineer | Acme Health |
| `analyst@tenant1.test` | Analyst | Acme Health |
| `auditor@tenant1.test` | Auditor | Acme Health |
| `admin@tenant2.test` | Admin | Riverside Medical |
| `engineer@tenant2.test` | Engineer | Riverside Medical |

---

## ⌨️ Windows Command Reference

The tasks configured in `scripts\dev.ps1`, `scripts\dev.bat`, and `Makefile` include:

| Task | PowerShell command | CMD / batch command | Make command |
| :--- | :--- | :--- | :--- |
| **Start Full Stack** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev` | `scripts\dev.bat dev` | `make dev` |
| **Start Lite Stack** * | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev-lite` | `scripts\dev.bat dev-lite` | `make dev-lite` |
| **Stop Stack** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task stop` | `scripts\dev.bat stop` | `make stop` |
| **Tear Down & Clean** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task clean` | `scripts\dev.bat clean` | `make clean` |
| **Run Migrations** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task migrate` | `scripts\dev.bat migrate` | `make migrate` |
| **New Migration** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task migration` | `scripts\dev.bat migration` | `make migration` |
| **Seed Test Data** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task seed` | `scripts\dev.bat seed` | `make seed` |
| **Setup Schemas** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task setup-vector-stores` | `scripts\dev.bat setup-vector-stores` | `make setup-vector-stores` |
| **Create Kafka Topics**| `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task kafka-topics` | `scripts\dev.bat kafka-topics` | `make kafka-topics` |
| **Run Unit Tests** | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task test-unit` | `scripts\dev.bat test-unit` | `make test-unit` |
| **Run Integration Tests**| `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task test-integration` | `scripts\dev.bat test-integration` | `make test-integration` |

*\* Lite Stack runs PostgreSQL, Redis, Weaviate, Kafka, and Vault, bypassing Keycloak, Qdrant, and local Embeddings server to conserve system RAM.*

---

## ⚙️ Windows-Specific Tips

- **Path Separators**: Use backslashes (`\`) for local file operations in CMD and PowerShell (e.g. `scripts\dev.bat`). In code configuration blocks and python imports, standard syntax applies.
- **Line Endings (CRLF)**: Ensure scripts inside the repository (.bat, .ps1) are checked out or saved using CRLF line endings to avoid script parser errors on Windows.
- **Docker Resource Allocation**: For a smooth experience with the full local stack, configure Docker Desktop settings to allocate at least **4 CPU cores** and **8GB of memory**.
- **Execution Policy Permissions**: If you get a permission error in PowerShell when invoking the scripts, run PowerShell as Administrator once and run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```

---

## 🔐 Keycloak Setup (Authentication & Authorization)

Keycloak provides OpenID Connect (OIDC) authentication for the dashboard and API. All test users are pre-configured in the realm.

### Step 1: Start Keycloak (Non-Docker)

If you're running Keycloak locally without Docker:

```cmd
cd C:\keycloak-26.6.4\bin
kc.bat start-dev
```

Keycloak will start on **http://localhost:8080** (development mode, HTTP only).

> **Note**: Use `start-dev` for local development. The `start` command requires HTTPS certificates.

### Step 2: Import the Realm Configuration

1. Open **http://localhost:8080/admin** in your browser
2. Log in with your Keycloak admin credentials
3. Click **"Add realm"** (top left dropdown)
4. Click **"Import"**
5. Select and upload `infra/keycloak/realm.json`
6. Click **"Create"**

This configures:
- ✅ Realm: `patientvectorhub`
- ✅ Client: `pvh-spa` (SPA application with PKCE)
- ✅ Test users with different roles (admin, engineer, analyst, auditor)
- ✅ Redirect URIs for `http://localhost:5173` (dashboard dev server)
- ✅ Role-based access control (RBAC) policies

### Step 3: Verify JWKS Endpoint

Test that Keycloak is serving the public keys for token validation:

```cmd
curl http://localhost:8080/realms/patientvectorhub/protocol/openid-connect/certs
```

You should receive a JSON response with public keys. If successful, your authentication is ready.

### Step 4: Test Login Flow

Once the dashboard is running (`npm run dev` on port 5173):

1. Navigate to **http://localhost:5173**
2. You'll be redirected to Keycloak login
3. Log in with test credentials:
   - **Username**: `admin@tenant1.test`
   - **Password**: `test-password-123`
4. After successful authentication, you'll be redirected back to the dashboard

---

## 📊 Jaeger Setup (Distributed Tracing & Observability)

Jaeger collects and visualizes distributed traces from all microservices, helping you understand request flows and identify performance bottlenecks.

### Step 1: Start Jaeger (Standalone)

If running Jaeger locally without Docker:

```cmd
cd C:\jaeger-2.19.0-windows-amd64
jaeger.exe
```

Jaeger will start with:
- **Query UI**: http://localhost:16686
- **OTLP gRPC Receiver**: localhost:4317
- **OTLP HTTP Receiver**: localhost:4318

### Step 2: Verify Jaeger is Receiving Data

Test the Jaeger API to ensure it's running:

```cmd
curl http://localhost:16686/api/services
```

Expected response (initially):
```json
{"data":["jaeger"],"total":1,"limit":0,"offset":0,"errors":null}
```

The `jaeger` service shown is Jaeger's self-monitoring.

### Step 3: Configure Your Application

Your `.env` is already configured:

```bash
JAEGER_ENDPOINT=http://localhost:4317
LOG_LEVEL=DEBUG
ENVIRONMENT=development
```

**For multiple applications sharing Jaeger:**
- Each application automatically identifies itself by `service.name`
- Jaeger UI shows a service dropdown to filter traces
- No additional Jaeger configuration is needed per application

### Step 4: View Traces in Jaeger UI

Once your application is running (`make dev`):

1. Open **http://localhost:16686**
2. Select your service from the **Service** dropdown (e.g., `patientvectorhub`)
3. Click **Find Traces**
4. Click a trace to see:
   - Request timeline and latency
   - Service-to-service calls
   - Error details and stack traces
   - Span duration and logs

### Example: Tracing a Request

When you log in to the dashboard:
1. Browser sends request → Dashboard (SPA)
2. Dashboard calls API → FastAPI Gateway (port 8000)
3. Gateway validates token → Keycloak (port 8080)
4. Gateway queries database → PostgreSQL
5. Each hop is traced and visible in Jaeger

---



### Port Conflict Issues
If a container fails to start because a port is already allocated:
1. Identify the process ID (PID) using that port (e.g., port `8000`):
   ```cmd
   netstat -ano | findstr :8000
   ```
2. Terminate the process (replace `<PID>` with the final number in the output):
   ```cmd
   taskkill /PID <PID> /F
   ```

### Docker Desktop Connection Failures
If commands fail with connection issues, run:
```cmd
docker ps
```
Ensure Docker Desktop is open and the Docker daemon is fully started. If WSL 2 errors pop up, run `wsl --update` inside PowerShell as administrator.

### Vault Initialization Fails
The Vault configuration uses a bash script (`scripts\vault_init.sh`).
- If you have Git for Windows installed, PowerShell will automatically detect `C:\Program Files\Git\bin\bash.exe` and execute it.
- If not installed, you can install Git for Windows or manually run the commands inside `scripts\vault_init.sh` inside a WSL window.

### Virtual Environment Issues

#### Wrong venv Active When Running Services
If you get import errors (e.g., `ModuleNotFoundError: No module named 'fastapi'`), ensure the correct venv is activated:
```cmd
REM Check which Python executable is being used
where python

REM This should show your venv path, e.g.:
REM a:\PatientVectorHub\venv-api-gateway\Scripts\python.exe
```

#### Stale venv After Dependencies Change
If you added new dependencies to a `requirements.txt` file:
```cmd
REM Activate the corresponding venv and reinstall
call venv-api-gateway\Scripts\activate.bat
pip install -r api-gateway\requirements.txt --force-reinstall
```

#### Switch Between Unified and Separate venvs
If you want to migrate from one approach to another:
```cmd
REM Deactivate current venv
deactivate

REM Delete old venv(s)
rmdir /s /q venv
rmdir /s /q venv-api-gateway venv-ingestion venv-rag-engine venv-vector-store

REM Create new venv setup (see section 2a, 2b, or 2c above)
```

#### Virtual Environment Not Found in IDE
If VSCode/PyCharm can't find your Python interpreter:
- In **VSCode**: Press `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose your venv path (e.g., `.\venv-api-gateway\Scripts\python.exe`)
- In **PyCharm**: Go to File → Settings → Project → Python Interpreter → Add Interpreter → Existing Environment → Navigate to venv\Scripts\python.exe
