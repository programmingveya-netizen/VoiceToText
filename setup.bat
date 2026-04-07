@echo off
setlocal EnableDelayedExpansion
title Voice To Text - Instalace
color 1F

echo.
echo  ============================================
echo       Voice To Text - Instalace
echo       Aplikace pro prevod videa na text
echo  ============================================
echo.

REM -- Krok 1: Najit nebo nainstalovat Python --
echo [1/5] Hledam Python...

set PYTHON_CMD=
where py >nul 2>&1 && set PYTHON_CMD=py
if not defined PYTHON_CMD where python >nul 2>&1 && set PYTHON_CMD=python

if defined PYTHON_CMD (
    echo        Python nalezen: !PYTHON_CMD!
    goto :python_ok
)

echo        Python nenalezen - stahuji automaticky...
echo.

set PYTHON_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
set PYTHON_INSTALLER=%TEMP%\python_installer.exe

echo        Stahuji Python 3.12...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"

if not exist "%PYTHON_INSTALLER%" (
    echo.
    echo  [CHYBA] Nelze stahnout Python.
    echo  Stahnete ho rucne z: https://www.python.org/downloads/
    echo  Pri instalaci ZASKRTNETE "Add Python to PATH"
    pause
    exit /b 1
)

echo        Instaluji Python...
"%PYTHON_INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1

timeout /t 5 /nobreak >nul

set PYTHON_CMD=
where py >nul 2>&1 && set PYTHON_CMD=py
if not defined PYTHON_CMD where python >nul 2>&1 && set PYTHON_CMD=python

if not defined PYTHON_CMD (
    echo.
    echo  [CHYBA] Python se nainstaloval ale neni v PATH.
    echo  Zavrete toto okno, RESTARTUJTE pocitac a spustte setup znovu.
    pause
    exit /b 1
)

echo        Python uspesne nainstalovany!

:python_ok
echo.

REM -- Krok 2: Nainstalovat knihovny --
echo [2/5] Instaluji potrebne knihovny...
echo        (toto muze trvat nekolik minut)
echo.

!PYTHON_CMD! -m pip install --upgrade pip >nul 2>&1
!PYTHON_CMD! -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo.
    echo  [CHYBA] Instalace knihoven se nezdarila.
    pause
    exit /b 1
)

echo.

REM -- Krok 3: Detekce GPU a instalace CUDA knihoven --
echo [3/5] Kontroluji grafickou kartu...

!PYTHON_CMD! -c "import ctranslate2; types=ctranslate2.get_supported_compute_types('cuda'); print('        NVIDIA GPU nalezena - CUDA dostupna') if 'float16' in types else (_ for _ in ()).throw(RuntimeError())" 2>nul
if not errorlevel 1 (
    echo        GPU akcelerace bude pouzita automaticky.
    goto :gpu_done
)

REM Zkontrolovat jestli je NVIDIA GPU pritomna
nvidia-smi >nul 2>&1
if not errorlevel 1 (
    echo        NVIDIA GPU nalezena, instaluji CUDA podporu...
    !PYTHON_CMD! -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 2>nul
    if not errorlevel 1 (
        echo        CUDA podpora nainstalovana - prepis bude rychlejsi!
    ) else (
        echo        CUDA se nepodarilo nainstalovat, bude pouzit CPU.
    )
) else (
    echo        NVIDIA GPU nenalezena - bude pouzit CPU.
    echo        (Prepis bude fungovat, jen bude pomalejsi)
)

:gpu_done
echo.

REM -- Krok 4: Predstahnout Whisper model --
echo [4/5] Stahuji jazykovy model pro prepis (medium)...
echo        (pri prvnim stazeni to muze trvat par minut)
echo.

!PYTHON_CMD! -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8'); print('        Model stazen uspesne!')"
if errorlevel 1 (
    echo        Model se stahne pri prvnim pouziti aplikace.
)

echo.

REM -- Krok 5: Vytvorit zastupce na plose --
echo [5/5] Vytvarim zastupce na plose...

set "SCRIPT_DIR=%~dp0"
set "DESKTOP=%USERPROFILE%\Desktop"
set "VBS_FILE=%TEMP%\create_shortcut.vbs"

> "%VBS_FILE%" echo Set WshShell = WScript.CreateObject("WScript.Shell")
>> "%VBS_FILE%" echo Set lnk = WshShell.CreateShortcut("%DESKTOP%\Voice To Text.lnk")
>> "%VBS_FILE%" echo lnk.TargetPath = "%SCRIPT_DIR%start.bat"
>> "%VBS_FILE%" echo lnk.WorkingDirectory = "%SCRIPT_DIR%"
>> "%VBS_FILE%" echo lnk.Description = "Voice To Text"
>> "%VBS_FILE%" echo lnk.IconLocation = "%SCRIPT_DIR%icon.ico,0"
>> "%VBS_FILE%" echo lnk.WindowStyle = 7
>> "%VBS_FILE%" echo lnk.Save

cscript //nologo "%VBS_FILE%" 2>nul
del "%VBS_FILE%" 2>nul

if exist "%DESKTOP%\Voice To Text.lnk" (
    echo        Zastupce s ikonou vytvoren na plose!
) else (
    echo        Zastupce se nepodarilo vytvorit, aplikaci spustte pres start.bat
)

echo.
echo  ============================================
echo       Instalace dokoncena!
echo.
echo       Spustte aplikaci kliknutim na ikonu
echo       "Voice To Text" na plose.
echo  ============================================
echo.
pause
