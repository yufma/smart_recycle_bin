$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'data\server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No Reloop server started by this launcher was found.'; return }
$serverProcessId = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
$serverInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $serverProcessId" -ErrorAction SilentlyContinue
if (-not $serverInfo) { Write-Host 'Reloop is already stopped.'; return }
if ($serverInfo.CommandLine -notlike '*uvicorn*' -or -not $serverInfo.CommandLine.Contains($PSScriptRoot)) {
    throw 'The saved process is not this Reloop server. It was not stopped.'
}
Stop-Process -Id $serverProcessId
Write-Host 'Reloop has stopped. All saved data is retained.'
