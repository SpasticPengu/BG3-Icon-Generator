@echo off
rem BG3 Icon Generator (D47 / D48): double-click to start. The first start sets up the app's own Python and libraries in
rem .runtime\ (about 300 MB, needs the internet once; nothing is installed elsewhere and no admin rights are needed).
rem Each start brings the libraries in line with requirements.lock (an update may change them). Delete .runtime\ to
rem set it all up again. The editor runs under iconkit\launch.py (restarts after an update), started with start /b and
rem the batch ends at once: a batch still running makes Ctrl+C ask "Terminate batch job (Y/N)?". From a command
rem prompt the prompt comes back while the editor runs; Ctrl+C or closing the window stops it.
rem An update replaces this file while it runs, and cmd reads a batch file as it goes: so it runs from a copy in
rem .runtime\ (handed over without "call": control never comes back here).
setlocal
if /i not "%~1"=="--run" (
  if not exist "%~dp0.runtime" mkdir "%~dp0.runtime"
  copy /y "%~f0" "%~dp0.runtime\launch.bat" >nul || exit /b 1
  set "ICONGEN_ARGS=%*"
  "%~dp0.runtime\launch.bat" --run "%~dp0."
)
cd /d "%~2"
set "RT=%CD%\.runtime"
set "UV=%RT%\uv\uv.exe"
set "UV_CACHE_DIR=%RT%\cache"
set "UV_PYTHON_INSTALL_DIR=%RT%\python"
if exist "%UV%" goto haveuv
rem uv (the tool that fetches Python and the libraries): its release zip, checked against its published SHA-256
set "UVV=0.12.18"
set "ARCH=x86_64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=aarch64"
set "URL=https://github.com/astral-sh/uv/releases/download/%UVV%/uv-%ARCH%-pc-windows-msvc.zip"
echo First start: downloading uv %UVV%, which sets up the app's own Python...
curl.exe -LsSf -o "%RT%\uv.zip" "%URL%" || goto fail
curl.exe -LsSf -o "%RT%\uv.zip.sha256" "%URL%.sha256" || goto fail
for /f "usebackq tokens=1" %%h in ("%RT%\uv.zip.sha256") do set "WANT=%%h"
for /f "skip=1 tokens=*" %%h in ('certutil -hashfile "%RT%\uv.zip" SHA256') do if not defined GOT set "GOT=%%h"
set "GOT=%GOT: =%"
if /i not "%GOT%"=="%WANT%" (
  echo The uv download doesn't match its published SHA-256: not used.
  goto fail
)
if not exist "%RT%\uv" mkdir "%RT%\uv"
tar -xf "%RT%\uv.zip" -C "%RT%\uv" || goto fail
del "%RT%\uv.zip" "%RT%\uv.zip.sha256"
if not exist "%UV%" goto fail
:haveuv
if exist "%RT%\env\Scripts\python.exe" goto sync
echo First start: setting up Python and the libraries, about a minute...
"%UV%" venv "%RT%\env" --managed-python --python 3.12 --quiet || goto fail
:sync
"%UV%" pip sync requirements.lock --python "%RT%\env\Scripts\python.exe" --require-hashes --quiet || goto fail
set ICONGEN_LAUNCHER=1
start "" /b "%RT%\env\Scripts\python.exe" -m iconkit.launch %ICONGEN_ARGS%
exit /b
:fail
echo.
echo Setting up failed (see above). Check the internet connection and start again; deleting the .runtime folder starts
echo the setup over.
pause
exit /b 1
