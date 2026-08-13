@echo off
REM Batch script to run tests with common options
REM Usage: run_tests.bat [unit|integration|all] [options]

setlocal enabledelayedexpansion
set TEST_TYPE=%1
set COVERAGE=
set VERBOSE=

if "%TEST_TYPE%"=="" set TEST_TYPE=all
if "%TEST_TYPE%"=="help" goto show_help
if "%TEST_TYPE%"=="--help" goto show_help
if "%TEST_TYPE%"=="-h" goto show_help

if "%TEST_TYPE%"=="unit" (
    echo Running unit tests (no Docker required)...
    pytest -v --tb=short -m unit %*
    exit /b !errorlevel!
)

if "%TEST_TYPE%"=="integration" (
    echo Running integration tests (requires Docker)...
    pytest -v --tb=short -m integration %*
    exit /b !errorlevel!
)

if "%TEST_TYPE%"=="all" (
    echo Running all tests...
    pytest -v --tb=short %*
    exit /b !errorlevel!
)

:show_help
echo Usage: run_tests.bat [unit^|integration^|all] [options]
echo.
echo Commands:
echo   unit           Run only unit tests (no Docker required)
echo   integration    Run only integration tests (requires Docker)
echo   all            Run all tests (default)
echo   help           Show this help message
echo.
echo Examples:
echo   run_tests.bat unit
echo   run_tests.bat integration
echo   run_tests.bat all
echo.
exit /b 0
