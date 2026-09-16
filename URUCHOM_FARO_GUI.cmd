@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Faro Emaile - uruchamianie GUI

if exist ".venv\Scripts\python.exe" goto :venv_ready

echo [FARO] Szukam zainstalowanego Pythona 3.12 lub nowszego...
set "PYTHON_CMD="

where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.14 3.13 3.12) do (
        py -%%V -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=py -%%V"
            goto :create_venv
        )
    )
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
        goto :create_venv
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        goto :create_venv
    )
)

echo.
echo [FARO] Nie znaleziono Pythona 3.12 lub nowszego.
echo Zainstaluj Python 3.12+ albo dodaj istniejacego Pythona do PATH.
goto :error

:create_venv
echo [FARO] Uzywam: %PYTHON_CMD%
echo [FARO] Tworze srodowisko .venv...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto :error

:venv_ready
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [FARO] Istniejace .venv ma nieobslugiwana wersje Pythona.
    echo Usun folder .venv i uruchom ten plik ponownie.
    goto :error
)

".venv\Scripts\python.exe" -c "import agregator" >nul 2>&1
if errorlevel 1 (
    echo [FARO] Instaluje aplikacje i zaleznosci...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto :error
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [FARO] Python nie ma modulu tkinter potrzebnego do GUI.
    echo Zainstaluj pelna wersje Pythona dla Windows z obsluga Tcl/Tk.
    goto :error
)

if exist ".venv\Scripts\pythonw.exe" (
    start "Faro Emaile" ".venv\Scripts\pythonw.exe" -m agregator.gui_app
) else (
    start "Faro Emaile" ".venv\Scripts\python.exe" -m agregator.gui_app
)
exit /b 0

:error
echo.
echo [FARO] Nie udalo sie uruchomic GUI.
echo.
pause
exit /b 1
