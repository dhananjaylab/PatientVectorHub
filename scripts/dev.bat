@echo off
REM Windows Batch script for development tasks
REM Usage: scripts\dev.bat dev
REM        scripts\dev.bat dev-lite
REM        scripts\dev.bat stop
REM etc.

setlocal enabledelayedexpansion

if "%1"=="" (
    echo.
    echo Usage: scripts\dev.bat [command]
    echo.
    echo Commands:
    echo   dev                  Start full local stack (8 services)
    echo   dev-lite             Start minimal stack
    echo   stop                 Stop all containers
    echo   clean                Remove containers and volumes
    echo   logs                 View container logs
    echo   migrate              Run Alembic migrations
    echo   migration            Create new Alembic migration
    echo   seed                 Seed test data
    echo   setup-vector-stores  Setup Weaviate + Qdrant schemas
    echo   kafka-topics         Create Kafka topics
    echo   vault-init           Initialize Vault dev secrets
    echo   test-unit            Run unit tests
    echo   test-integration     Run integration tests
    echo.
    goto :eof
)

goto :%1

:dev
echo ^>^> Starting full PatientVectorHub stack...
call docker compose up -d
echo ^>^> Waiting for services to be healthy...
timeout /t 10 /nobreak
call :wait_healthy
echo.
echo ^>^> Running setup...
call :vault_init
call :migrate
call :kafka_topics
call :setup_vector_stores
call :seed
echo.
echo   PatientVectorHub - Local Stack Ready
echo   ====================================
echo.
echo   FastAPI  - http://localhost:8000/health
echo   Weaviate - http://localhost:8080
echo   Qdrant   - http://localhost:6333
echo   Vault    - http://localhost:8200
echo   Keycloak - http://localhost:8443
echo   Kafka    - localhost:9092
echo   Redis    - localhost:6379
echo   Embed    - http://localhost:8001
echo.
goto :eof

:dev_lite
echo ^>^> Starting minimal stack...
call docker compose up -d postgres redis weaviate kafka vault
echo ^>^> Waiting for services...
timeout /t 8 /nobreak
call :vault_init
call :migrate
call :kafka_topics
call :seed
echo OK: Lite stack ready
goto :eof

:stop
echo ^>^> Stopping all containers...
call docker compose down
echo ✅ All containers stopped
goto :eof

:clean
echo ^>^> Removing containers, networks, and volumes...
call docker compose down -v --remove-orphans
echo ✅ Containers, networks, and volumes removed
goto :eof

:logs
call docker compose logs -f --tail=50
goto :eof

:migrate
echo ^>^> Running Alembic upgrade head
pushd api-gateway
call python -m alembic upgrade head
popd
echo ✅ Migrations applied
goto :eof

:migration
set /p msg="Migration message: "
if "!msg!"=="" (
    echo ERROR: Migration message cannot be empty
    goto :eof
)
pushd api-gateway
call python -m alembic revision --autogenerate -m "!msg!"
popd
goto :eof

:seed
echo ^>^> Seeding synthetic test data...
call python scripts\seed_data.py
echo ✅ Seed complete: 2 tenants, 4 users each, 1000 patients each
goto :eof

:setup_vector_stores
echo ^>^> Creating Weaviate + Qdrant schemas for all tenants...
call python scripts\setup_weaviate_schema.py
call python scripts\setup_qdrant_schema.py
echo ✅ Vector store schemas created
goto :eof

:kafka_topics
echo ^>^> Creating Kafka topics...
call python scripts\create_kafka_topics.py
echo ✅ Kafka topics created
goto :eof

:vault_init
echo ^>^> Initialising Vault dev secrets...
REM Attempts to run bash script if Git Bash is available
if exist "C:\Program Files\Git\bin\bash.exe" (
    "C:\Program Files\Git\bin\bash.exe" scripts\vault_init.sh
    echo ✅ Vault initialised
) else (
    echo Note: vault_init.sh requires bash
    echo Install Git for Windows or run: bash scripts/vault_init.sh
    echo ✅ Vault initialised (manual)
)
goto :eof

:test_unit
echo ^>^> Running unit tests...
call pytest tests\unit -v --tb=short
echo ✅ Unit tests passed
goto :eof

:test_integration
echo ^>^> Running integration tests (requires running stack)...
call pytest tests\integration -v --tb=short -m integration
echo ✅ Integration tests passed
goto :eof

:wait_healthy
echo Checking service health...
setlocal enabledelayedexpansion

for %%S in (pvh-postgres pvh-redis pvh-weaviate pvh-vault pvh-kafka) do (
    echo   Checking %%S...
    for /L %%I in (1,1,18) do (
        for /f "tokens=*" %%H in ('docker inspect --format="{{.State.Health.Status}}" %%S 2^>nul') do set "status=%%H"
        if "!status!"=="healthy" (
            echo   OK %%S
            goto :next_service
        )
        if %%I EQU 18 (
            echo   ERROR: %%S not healthy after 90s
            exit /b 1
        )
        timeout /t 5 /nobreak >nul
    )
    :next_service
)

goto :eof

:unknown
echo ERROR: Unknown command: %1
echo Use 'scripts\dev.bat' for help
exit /b 1
