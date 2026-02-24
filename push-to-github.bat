@echo off
chcp 65001 >nul
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
    echo Git non trovato. Prova ad aprire "Git Bash" dal menu Start dopo aver installato Git.
    echo Oppure installa Git: https://git-scm.com/download/win
    pause
    exit /b 1
)

git init 2>nul
git add -A
git commit -m "YouTube Portrait tool" 2>nul
git remote remove origin 2>nul
git remote add origin https://github.com/jakephobia/ytcrp.git
git branch -M main
git push -u origin main

echo.
if errorlevel 1 (
    echo Se ti chiede login, completa l'accesso e riesegui questo file.
) else (
    echo Fatto. https://github.com/jakephobia/ytcrp
)
pause
