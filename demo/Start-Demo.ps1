# Starts a temporary API/database, runs the demo, and stops only its own process.
[CmdletBinding()]
param([string]$Python = 'python', [switch]$Repeat)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$demoDirectory = Join-Path ([IO.Path]::GetTempPath()) ("utilities-demo-" + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $demoDirectory
$listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$previousUrl = $env:DATABASE_URL
$process = $null
try {
    $databasePath = (Join-Path $demoDirectory 'demo.db').Replace('\', '/')
    $env:DATABASE_URL = "sqlite:///$databasePath"
    $pythonPath = (Get-Command $Python -ErrorAction Stop).Source
    $process = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$port") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $demoDirectory 'stdout.log') -RedirectStandardError (Join-Path $demoDirectory 'stderr.log')
    $baseUrl = "http://127.0.0.1:$port"
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($process.HasExited) { throw "API stopped. Read $demoDirectory\stderr.log" }
        try {
            $health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 1
            if ($health.status -eq 'UP') { $ready = $true; break }
        }
        catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $ready) { throw "API did not become ready. Read $demoDirectory\stderr.log" }
    & (Join-Path $PSScriptRoot 'Invoke-Demo.ps1') -BaseUrl $baseUrl
    if ($Repeat) { & (Join-Path $PSScriptRoot 'Invoke-Demo.ps1') -BaseUrl $baseUrl }
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id
        $process.WaitForExit()
    }
    $env:DATABASE_URL = $previousUrl
    Write-Host "Isolated database and logs retained at: $demoDirectory"
}
