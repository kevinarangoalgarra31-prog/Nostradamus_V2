$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$phase4Runner = Join-Path $PSScriptRoot "run_phase4_daily.ps1"
$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$pythonCommand = "python"
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c "import pandas, yaml, xgboost, yfinance" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = $venvPython
    }
}

Set-Location -LiteralPath $projectRoot
Write-Output "[Diario] Ejecutando recolección de sentimiento V4..."
& $phase4Runner

$logDirectory = Join-Path $projectRoot "output\v6\logs"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$logPath = Join-Path $logDirectory "$stamp.log"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

Write-Output "[Diario] Ejecutando paper trading V6..."
$previousErrorActionPreference = $ErrorActionPreference
$previousConsoleEncoding = [Console]::OutputEncoding
$previousPythonIoEncoding = $env:PYTHONIOENCODING
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"
try {
    & $pythonCommand ".\phase6_paper_trade.py" 2>&1 |
        ForEach-Object { $_.ToString() } |
        Tee-Object -FilePath $logPath
    $pythonExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
    [Console]::OutputEncoding = $previousConsoleEncoding
    $env:PYTHONIOENCODING = $previousPythonIoEncoding
}

if ($pythonExitCode -ne 0) {
    throw "El paper trading diario falló. Revisa $logPath"
}
