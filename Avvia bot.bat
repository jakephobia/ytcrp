@echo off
cd /d "%~dp0"
REM Avvia il bot in background (nessuna finestra). Il token si legge da token.txt o da TELEGRAM_BOT_TOKEN.
pythonw bot.py
if errorlevel 1 (
    echo Il bot non e' partito. Controlla che Python e le dipendenze siano installati
    echo e che token.txt contenga il token di @BotFather.
    pause
)
