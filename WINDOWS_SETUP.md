# Windows Development Setup Guide

This guide helps you run PatientVectorHub on Windows without WSL or additional overhead.

## Quick Start

### Option 1: PowerShell (Recommended)
```powershell
# Set execution policy (run once)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Start full stack
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev

# Or use individual tasks
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev-lite
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task stop
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task seed
```

### Option 2: Command Prompt (CMD)
```cmd
REM Start full stack
scripts\dev.bat dev

REM Start minimal stack
scripts\dev.bat dev-lite

REM Stop containers
scripts\dev.bat stop

REM View logs
scripts\dev.bat logs
```

### Option 3: Using Makefile.windows
If you have `make` installed (via Chocolatey, MinGW, or Git Bash):
```bash
make -f Makefile.windows dev
make -f Makefile.windows dev-lite
make -f Makefile.windows stop
```

---

## Available Commands

### Development Stack

| Command | Description |
|---------|-------------|
| `dev` | Start full stack (all 8 services) |
| `dev-lite` | Start minimal stack (Postgres, Redis, Weaviate, Kafka, Vault) |
| `stop` | Stop all containers |
| `logs` | View real-time container logs |

### Database & Setup

| Command | Description |
|---------|-------------|
| `migrate` | Run Alembic database migrations |
| `seed` | Load synthetic test data |
| `setup-vector-stores` | Initialize Weaviate + Qdrant schemas |
| `kafka-topics` | Create Kafka topics |
| `vault-init` | Initialize Vault with dev secrets |

### Testing

| Command | Description |
|---------|-------------|
| `test-unit` | Run unit tests |
| `test-integration` | Run integration tests (requires running stack) |

---

## Prerequisites

### Required
- **Docker Desktop** (with Docker Compose v2+)
  - Download: https://www.docker.com/products/docker-desktop
  - Verify: `docker --version` & `docker compose version`

- **Python 3.9+**
  - Download: https://www.python.org/downloads/
  - Verify: `python --version`
  - Add to PATH during installation

- **pip** (included with Python)
  - Verify: `pip --version`

### Optional (for direct command use)
- **PowerShell 7+** (for better scripting experience)
  - Download: https://github.com/PowerShell/PowerShell/releases
  - Or upgrade: `winget install Microsoft.PowerShell`

---

## Setup Instructions

### 1. Install Dependencies

```cmd
REM Install Python dependencies
pip install -r api-gateway\requirements.txt
pip install -r ingestion\requirements.txt
pip install -r rag-engine\requirements.txt
pip install -r vector-store\requirements.txt
pip install -r requirements-dev.txt

REM Install Node.js packages (for dashboard)
cd dashboard
npm install
cd ..
```

### 2. Configure Environment

```cmd
REM Copy example env file
copy .env.example .env

REM Edit .env with your settings
notepad .env
```

### 3. Start the Stack

```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev
```

or

```cmd
REM CMD
scripts\dev.bat dev
```

Wait ~2-3 minutes for all services to be healthy.

---

## Accessing Services

Once the stack is running:

| Service | URL |
|---------|-----|
| FastAPI (API) | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| Weaviate | http://localhost:8080 |
| Qdrant | http://localhost:6333 |
| Vault | http://localhost:8200 |
| Keycloak | http://localhost:8443 |
| Kafka | localhost:9092 |
| Redis | localhost:6379 |
| Embedding Server | http://localhost:8001 |

---

## Troubleshooting

### Docker Desktop not starting
```cmd
REM Check if Docker is installed and running
docker ps

REM Start Docker Desktop manually or:
wsl --update
```

### Python not found
```cmd
REM Verify Python is in PATH
python --version

REM If not found, add to PATH:
set PATH=%PATH%;C:\Users\YourUsername\AppData\Local\Programs\Python\Python311\
```

### Permission denied in PowerShell
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Container fails to start
```cmd
REM Check container logs
docker compose logs postgres
docker compose logs redis

REM Or use script logs
docker compose logs -f --tail=100
```

### Port already in use
```cmd
REM Find what's using the port (replace 8000 with your port)
netstat -ano | findstr :8000

REM Kill the process (replace PID with the actual process ID)
taskkill /PID <PID> /F
```

### Services not healthy
```powershell
# Increase wait time
Start-Sleep -Seconds 30

# Then manually check individual services
docker compose logs postgres
docker compose logs redis
docker compose logs weaviate
```

---

## Common Tasks

### Run Migrations
```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task migrate
```

```cmd
REM CMD
scripts\dev.bat migrate
```

### Seed Test Data
```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task seed
```

```cmd
REM CMD
scripts\dev.bat seed
```

### Run Unit Tests
```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task test-unit
```

```cmd
REM CMD
scripts\dev.bat test-unit
```

### View Logs in Real-time
```cmd
docker compose logs -f
```

### Stop Everything
```powershell
# PowerShell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task stop
```

```cmd
REM CMD
scripts\dev.bat stop
```

### Clean Up (Remove Volumes)
```cmd
docker compose down -v --remove-orphans
```

---

## Using Make (Optional)

If you install `make` via Chocolatey:

```powershell
choco install make
```

Then use the Windows-compatible Makefile:

```bash
make -f Makefile.windows dev
make -f Makefile.windows test-unit
make -f Makefile.windows stop
```

---

## Performance Tips

1. **Use dev-lite for faster startup**
   - Excludes Keycloak and Qdrant (heavy services)
   ```cmd
   scripts\dev.bat dev-lite
   ```

2. **Allocate more resources to Docker**
   - Docker Desktop → Settings → Resources
   - Recommended: 4+ CPU cores, 8GB+ memory

3. **Use SSD for Docker volumes**
   - Ensures faster database operations

4. **Cache Python packages**
   - Run `pip install -r requirements.txt` once
   - Speeds up container builds

---

## Windows-Specific Notes

- **Path separators**: Scripts use backslashes (`\`) instead of forward slashes (`/`)
- **Line endings**: Use CRLF for `.bat` and `.ps1` files
- **Ports**: Ensure ports 5432, 6379, 8000, 8001, 8080, 8200, 8443, 9092 are available
- **Firewall**: May need to allow Docker/Docker Desktop through Windows Firewall

---

## Next Steps

1. ✅ Follow the quick start above
2. 📖 Read the main [README.md](README.md)
3. 🚀 Start development with `make -f Makefile.windows run-api`
4. 🧪 Run tests with `scripts\dev.bat test-unit`

For issues, check Docker logs: `docker compose logs [service-name]`
