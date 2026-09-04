@echo off
setlocal
set "TARGET=%~dp0local_converter.exe"
set "SHORTCUT=%USERPROFILE%\Desktop\local_converter.lnk"

if not exist "%TARGET%" (
    echo Nie znaleziono local_converter.exe w tym folderze.
    echo Uruchom ten plik z folderu, w ktorym jest local_converter.exe.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = '%TARGET%';" ^
  "$s.Save()"

if %errorlevel%==0 (
    echo Gotowe! Skrot "local_converter" pojawil sie na Pulpicie.
) else (
    echo Cos poszlo nie tak przy tworzeniu skrotu.
)
pause
