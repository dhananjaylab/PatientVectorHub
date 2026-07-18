# Virtual Environment Management & Git Ignore

**Updated:** July 17, 2026  
**Status:** ✅ `.gitignore` configured to ignore all venv directories

---

## What Was Changed

Updated `.gitignore` to exclude all virtual environment directories:

```diff
# Environments
.env
.envrc
.venv
env/
venv/
+ venv-*/      ← Added to catch venv-ingestion, venv-rag-engine, etc.
ENV/
env.bak/
venv.bak/
```

---

## Ignored Patterns

Your `.gitignore` now excludes:

| Pattern | Matches | Example |
|---------|---------|---------|
| `.venv` | .venv directory | `.venv/` |
| `venv/` | Root-level venv | `venv/` |
| `venv-*/` | Service-specific venvs | `venv-ingestion/`, `venv-rag-engine/`, `venv-vector-store/`, `venv-api-gateway/` |
| `env/` | Generic env directory | `env/` |
| `ENV/` | Uppercase ENV | `ENV/` |
| `env.bak/` | Backup environments | `env.bak/`, `venv.bak/` |

---

## Your Service Virtual Environments

Each service can have its own isolated venv:

```
PatientVectorHub/
├── api-gateway/
│   ├── venv-api-gateway/        ← IGNORED
│   ├── requirements.txt          ← COMMITTED
│   └── src/
├── ingestion/
│   ├── venv-ingestion/          ← IGNORED
│   ├── requirements.txt          ← COMMITTED
│   ├── embedding-server/
│   │   ├── venv-embedding/      ← IGNORED
│   │   └── requirements.txt      ← COMMITTED
│   └── src/
├── rag-engine/
│   ├── venv-rag-engine/         ← IGNORED
│   ├── requirements.txt          ← COMMITTED
│   └── src/
├── vector-store/
│   ├── venv-vector-store/       ← IGNORED
│   ├── requirements.txt          ← COMMITTED
│   └── src/
└── .gitignore                    ← UPDATED
```

---

## Setting Up Development Environment

### Option 1: Individual Service venvs (Recommended for dev)

```bash
# API Gateway
cd api-gateway
python -m venv venv-api-gateway
.\venv-api-gateway\Scripts\activate   # Windows
source venv-api-gateway/bin/activate  # Linux/Mac
pip install -r requirements.txt
cd ..

# Ingestion
cd ingestion
python -m venv venv-ingestion
.\venv-ingestion\Scripts\activate
pip install -r requirements.txt
cd ..

# RAG Engine
cd rag-engine
python -m venv venv-rag-engine
.\venv-rag-engine\Scripts\activate
pip install -r requirements.txt
cd ..

# Vector Store
cd vector-store
python -m venv venv-vector-store
.\venv-vector-store\Scripts\activate
pip install -r requirements.txt
cd ..
```

### Option 2: Single Root venv (Simpler but larger)

```bash
# Create one venv for all dependencies
python -m venv venv

# Activate
.\venv\Scripts\activate   # Windows
source venv/bin/activate  # Linux/Mac

# Install all requirements
pip install -r api-gateway/requirements.txt
pip install -r ingestion/requirements.txt
pip install -r rag-engine/requirements.txt
pip install -r vector-store/requirements.txt
```

### Option 3: Docker Containers (Best for production)

```bash
# Don't create venvs locally, let Docker handle isolation
docker-compose up
```

---

## Verify Nothing Is Committed

Check that venv directories aren't tracked:

```bash
# List all tracked Python files (venvs should NOT appear)
git ls-files | grep -E "venv|\.pyc"

# Expected: Only shows requirements.txt and source files
# NOT any venv/* or venv-*/* paths
```

If any venv files ARE tracked (shouldn't be), remove them:

```bash
# Remove from git cache WITHOUT deleting local files
git rm --cached -r venv venv-*

# Commit the removal
git commit -m "Remove venv directories from tracking"
```

---

## CI/CD Pipeline Setup

### GitHub Actions Example

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    steps:
      - uses: actions/checkout@v3
      
      # Python will be installed by the action, venv created automatically
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      # No need to create venv in CI—it's created automatically
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r ingestion/requirements.txt
          pip install -r api-gateway/requirements.txt
          # ... etc for other services
      
      - name: Run tests
        run: |
          pytest tests/
```

---

## Best Practices

### ✅ DO

- ✅ Commit `requirements.txt` files (specify exact versions with `==`)
- ✅ Commit `pyproject.toml` if using Poetry
- ✅ Ignore `venv/`, `.venv/`, and `venv-*/` directories
- ✅ Use `.gitignore` to prevent accidental commits
- ✅ Document venv setup in README.md
- ✅ Use Python version lock file for reproducibility

### ❌ DON'T

- ❌ Commit virtual environment directories (they're platform-specific)
- ❌ Commit `.env` files with secrets
- ❌ Use global Python packages for project work
- ❌ Hardcode paths to venv in scripts
- ❌ Mix different venv styles in the same project

---

## Troubleshooting

### Problem: Still seeing venv in git status

```bash
# Check if .gitignore is being read
git check-ignore -v venv-ingestion/

# Expected output:
# .gitignore:141:venv-*/    venv-ingestion/
```

If no output, the pattern isn't matching. Re-check `.gitignore` syntax.

### Problem: Accidentally committed venv files

```bash
# Remove from git history
git rm --cached -r venv-*

# Commit the removal
git commit -m "Remove accidentally committed venv directories"

# Push
git push origin main
```

### Problem: Contributors still creating venvs in repo

Add a pre-commit hook to prevent venv commits:

Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Prevent committing venv directories
if git diff --cached --name-only | grep -qE 'venv[^/]*/|\.venv/|env/'; then
    echo "❌ Error: Attempting to commit virtual environment files"
    echo "Virtual environments should be in .gitignore"
    exit 1
fi
exit 0
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Docker Alternative (No Local venv Needed)

If you're using Docker, you don't need local venvs at all:

```dockerfile
# Dockerfile for ingestion service
FROM python:3.11-slim

WORKDIR /app

# Copy requirements only (enables better layer caching)
COPY ingestion/requirements.txt .

# Install dependencies in container (no local venv needed)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ingestion/src .

CMD ["python", "-m", "uvicorn", "main:app"]
```

Then developers run:
```bash
# No venv setup needed—just use Docker
docker-compose up

# Tests run in containers too
docker-compose run --rm ingestion pytest tests/
```

---

## Summary

| Item | Status | Details |
|------|--------|---------|
| `.gitignore` updated | ✅ | Added `venv-*/` pattern |
| Venv pattern | ✅ | Catches `.venv`, `venv/`, `venv-*` |
| Already tracked venvs | ✅ | None found (no cleanup needed) |
| Documentation | ✅ | This file |
| Pre-commit hook | ⏭️ | Optional—add if needed |

---

## References

- [Python venv documentation](https://docs.python.org/3/tutorial/venv.html)
- [.gitignore spec](https://git-scm.com/docs/gitignore)
- [GitHub Python .gitignore template](https://github.com/github/gitignore/blob/main/Python.gitignore)
