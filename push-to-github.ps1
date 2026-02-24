# Tutto automatico: installa Git se serve, poi carica il progetto su https://github.com/jakephobia/ytcrp
# Esegui: tasto destro su questo file -> "Esegui con PowerShell" (oppure da PowerShell: .\push-to-github.ps1)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

function Get-GitExe {
    $g = Get-Command git -ErrorAction SilentlyContinue
    if ($g) { return "git" }
    $path = "C:\Program Files\Git\bin\git.exe"
    if (Test-Path $path) { return $path }
    return $null
}

# Installa Git con winget se non presente
if (-not (Get-GitExe)) {
    Write-Host "Git non trovato. Installazione in corso (winget)..." -ForegroundColor Yellow
    try {
        winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements --silent
    } catch {
        Write-Host "Impossibile usare winget. Installa Git manualmente: https://git-scm.com/download/win" -ForegroundColor Red
        Start-Process "https://git-scm.com/download/win"
        exit 1
    }
    # Aggiorna PATH nella sessione corrente
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

$git = Get-GitExe
if (-not $git) {
    $git = "C:\Program Files\Git\bin\git.exe"
    if (-not (Test-Path $git)) {
        Write-Host "Riapri PowerShell e riesegui questo script, oppure installa Git da https://git-scm.com/download/win" -ForegroundColor Red
        exit 1
    }
}

& $git config --local user.email "jakephobia@users.noreply.github.com" 2>$null
& $git config --local user.name "jakephobia" 2>$null

Write-Host "Repository locale..." -ForegroundColor Cyan
if (-not (Test-Path .git)) { & $git init }
& $git branch -M main

Write-Host "Aggiunta file e commit..." -ForegroundColor Cyan
& $git add -A
& $git status -s
& $git commit -m "YouTube Portrait tool - Flask, pytubefix, ffmpeg, deploy Render"
if ($LASTEXITCODE -ne 0) {
    # Nessun cambiamento o nulla da committare: va bene, procedi
    $null = $LASTEXITCODE
}

Write-Host "Collegamento a GitHub..." -ForegroundColor Cyan
$remote = "https://github.com/jakephobia/ytcrp.git"
try { & $git remote get-url origin 2>$null | Out-Null } catch { }
if ($LASTEXITCODE -ne 0) { & $git remote add origin $remote } else { & $git remote set-url origin $remote }

Write-Host "Caricamento su GitHub (può aprirsi il browser per il login)..." -ForegroundColor Cyan
& $git push -u origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Il push richiede l'accesso a GitHub. Si aprira' la pagina del repo." -ForegroundColor Yellow
    Write-Host "Se non sei loggato: accedi, poi riesegui questo script (doppio click su push-to-github.ps1)." -ForegroundColor Yellow
    Start-Process "https://github.com/jakephobia/ytcrp"
    exit 1
}

Write-Host ""
Write-Host "Fatto. Codice caricato su https://github.com/jakephobia/ytcrp" -ForegroundColor Green
Start-Process "https://github.com/jakephobia/ytcrp"
