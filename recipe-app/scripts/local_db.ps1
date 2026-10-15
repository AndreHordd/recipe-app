param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [ValidateRange(1024, 65535)][int]$Port = 54329
)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$locationFile = Join-Path $appRoot '.local\postgres-location.txt'
if (Test-Path -LiteralPath $locationFile) {
    $portableRoot = (Get-Content -LiteralPath $locationFile -Raw).Trim()
    $binPath = Join-Path $portableRoot 'pgsql\bin'
    $dataPath = Join-Path $portableRoot 'pgdata'
    $logPath = Join-Path $portableRoot 'postgresql.log'
} else {
    $binPath = Join-Path $appRoot '.local\postgresql\pgsql\bin'
    $dataPath = Join-Path $appRoot '.local\pgdata'
    $logPath = Join-Path $appRoot '.local\postgresql.log'
}
$pgControl = Join-Path $binPath 'pg_ctl.exe'
if (-not (Test-Path -LiteralPath $pgControl)) {
    throw 'Download PostgreSQL 17 Windows binaries and extract to .local\postgresql first. See README.'
}
if ($Action -eq 'start') {
    if (-not (Test-Path -LiteralPath (Join-Path $dataPath 'PG_VERSION'))) {
        throw 'Initialize the portable cluster first using the README instructions.'
    }
    & $pgControl -D $dataPath status *> $null
    if ($LASTEXITCODE -eq 0) { Write-Output 'PostgreSQL is already running.'; exit 0 }
    & $pgControl -D $dataPath -l $logPath -o "-h 127.0.0.1 -p $Port" -w start
} elseif ($Action -eq 'stop') {
    & $pgControl -D $dataPath -m fast -w stop
} else {
    & $pgControl -D $dataPath status
}
exit $LASTEXITCODE
