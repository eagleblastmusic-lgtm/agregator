@echo off
setlocal
cd /d "%~dp0"

title Faro Emaile - uruchamianie GUI

if not exist ".venv\Scripts\python.exe" (
    echo [FARO] Tworze srodowisko Python 3.12...
    py -3.12 -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import agregator" >nul 2>&1
if errorlevel 1 (
    echo [FARO] Instaluje aplikacje i zaleznosci...
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 goto :error
)

if not exist ".venv\Scripts\pythonw.exe" goto :no_pythonw

start "Faro Emaile" ".venv\Scripts\pythonw.exe" -m agregator.gui
exit /b 0

:no_pythonw
echo [FARO] Nie znaleziono pythonw.exe w .venv.
goto :error

:error
echo.
echo [FARO] Nie udalo sie uruchomic GUI.
echo Sprawdz, czy masz zainstalowany Python 3.12 oraz polecenie py.
echo.
pause
exit /b 1
