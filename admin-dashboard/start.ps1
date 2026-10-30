param(
    [int]$Port = 8765,
    [switch]$Lan,
    [switch]$NoBrowser,
    [switch]$Rebuild
)
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
Set-Location -LiteralPath $projectDirectory
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
$localUrl = "http://127.0.0.1:$Port"
try {
    $existingServer = Invoke-RestMethod -Uri "$localUrl/api/health" -TimeoutSec 2
    if ($existingServer.application -eq 'reloop') {
        Write-Host "Reloop is already running: $localUrl"
        if (-not $NoBrowser) { Start-Process $localUrl }
        return
    }
} catch { }
$pythonCommand = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonCommand)) {
    $pythonCommand = (Get-Command python -ErrorAction Stop).Source
    $savedErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $pythonCommand -c 'import fastapi, uvicorn, pydantic; assert int(pydantic.__version__[0]) >= 2' 2>$null
    $dependencyExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedErrorPreference
    if ($dependencyExitCode -ne 0) {
        & $pythonCommand -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
        $pythonCommand = Join-Path $projectDirectory '.venv\Scripts\python.exe'
        & $pythonCommand -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    }
}
if ($Rebuild -or -not (Test-Path -LiteralPath (Join-Path $projectDirectory 'dist\index.html'))) {
    $npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
    & $npmCommand ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    & $npmCommand run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
$logDirectory = Join-Path $projectDirectory 'logs'
$dataDirectory = Join-Path $projectDirectory 'data'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
$bindAddress = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$serverArguments = @('-m', 'uvicorn', 'server.app:app', '--app-dir', ('"' + $projectDirectory + '"'), '--host', $bindAddress, '--port', "$Port")
$serverProcess = Start-Process -FilePath $pythonCommand -ArgumentList $serverArguments -WorkingDirectory $projectDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'server.out.log') -RedirectStandardError (Join-Path $logDirectory 'server.err.log')
Set-Content -LiteralPath (Join-Path $dataDirectory 'server.pid') -Value $serverProcess.Id
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    $serverProcess.Refresh()
    if ($serverProcess.HasExited) { throw "Reloop could not start. See logs/server.err.log." }
    try { $health = Invoke-RestMethod -Uri "$localUrl/api/health" -TimeoutSec 1; if ($health.application -eq 'reloop') { $ready = $true; break } } catch { }
}
if (-not $ready) { throw 'The server did not become ready. Check logs/server.err.log.' }
Write-Host "Reloop is ready: $localUrl"
Write-Host 'Demo account: demo@reloop.local / Demo1234!'
Write-Host 'Use stop.ps1 to stop the server.'
if ($Lan) { Write-Host 'LAN mode: use this PC IP address and the same port on the sensor device.' }
if (-not $NoBrowser) { Start-Process $localUrl }
