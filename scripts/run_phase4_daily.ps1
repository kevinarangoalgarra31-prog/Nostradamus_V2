$ErrorActionPreference = "Stop"
$previousConsoleEncoding = [Console]::OutputEncoding
$previousPythonIoEncoding = $env:PYTHONIOENCODING
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$pythonCommand = "python"
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c "import yaml, feedparser, groq" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = $venvPython
    }
}
$logDirectory = Join-Path $projectRoot "output\v4_history\logs"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$logPath = Join-Path $logDirectory "$stamp.log"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Set-Location -LiteralPath $projectRoot

# Python escribe el progreso en stderr para mantener el JSON final limpio en
# stdout. Windows PowerShell 5.1 convierte esas líneas en NativeCommandError
# cuando ErrorActionPreference es Stop, aunque el proceso siga funcionando.
# Durante la ejecución permitimos ambos flujos y validamos el código de salida
# real de Python al terminar.
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $pythonCommand ".\phase4_sentiment.py" `
        --provider google_news `
        --with-llm `
        --archive-run `
        --output-dir ".\output\v4_history" 2>&1 |
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
    throw "La recolección diaria falló. Revisa $logPath"
}
