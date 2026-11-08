@echo off
rem Launch mgridPlayer on Windows. Arguments are passed through, e.g.  mgridplayer.bat -g 2x2 C:\Videos
set HERE=%~dp0
if exist "%HERE%.venv\Scripts\pythonw.exe" (
  pushd "%HERE%" & start "" "%HERE%.venv\Scripts\pythonw.exe" -m mgridplayer %* & popd
) else if exist "%HERE%dist\mgridPlayer\mgridPlayer.exe" (
  start "" "%HERE%dist\mgridPlayer\mgridPlayer.exe" %*
) else (
  echo mgridPlayer is not set up yet. Run: powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
  pause
)
