@echo off
REM ============================================
REM  TokenSlayer Repo-Wide Scan
REM  Scans all source files and reports savings
REM ============================================
setlocal enabledelayedexpansion

set TS_JS=%~dp0..\Forge\scratch\TokenSlayer\standalone\tokenslayer.js
set BATCH_JS=%~dp0..\Forge\scratch\TokenSlayer\standalone\tokenslayer-batch.js
set LUMAX_ROOT=%~dp0..

echo ============================================
echo  TokenSlayer Repo-Wide Scan
echo  Scanning source files for token savings...
echo ============================================
echo.

REM Collect all source files
set FILE_LIST=
set COUNT=0

for /r "%LUMAX_ROOT%\Backend" %%f in (*.py) do (
  set "FILE_LIST=!FILE_LIST! "%%f""
  set /a COUNT+=1
)
for /r "%LUMAX_ROOT%\Forge" %%f in (*.py *.ts *.js) do (
  set "FILE_LIST=!FILE_LIST! "%%f""
  set /a COUNT+=1
)
for /r "%LUMAX_ROOT%\Frontend" %%f in (*.py *.ts *.js *.html *.css) do (
  set "FILE_LIST=!FILE_LIST! "%%f""
  set /a COUNT+=1
)
for /r "%LUMAX_ROOT%\Tools" %%f in (*.py *.ts *.js) do (
  set "FILE_LIST=!FILE_LIST! "%%f""
  set /a COUNT+=1
)

echo Found %COUNT% source files. Running batch analysis...
echo.

REM Run batch analysis on collected files
node "%BATCH_JS%" %FILE_LIST%

echo.
echo ============================================
echo  Scan complete.
echo  Use: node "%TS_JS%" ^<filepath^> --level ^<0-3^>
echo  For single-file skeletonization.
echo ============================================