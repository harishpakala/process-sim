param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("inspect","adopt","recover","reconcile","initialize")]
    [string]$Mode,
    [string]$Endpoint = "http://localhost:7200/repositories/AAST",
    [string]$Journal = "",
    [string]$EvidenceFile = "",
    [int]$Port = 8002,
    [Parameter(Mandatory=$true)]
    [switch]$ExclusiveWriter,
    [switch]$RemoteQuiescent
)
$ErrorActionPreference = "Stop"
if (-not $ExclusiveWriter) { throw "Exclusive writer ownership must be confirmed" }
$root = Split-Path -Parent $PSScriptRoot
if (-not $Journal) { $Journal = Join-Path $root "runtime-data/aast.sqlite" }
if (-not $EvidenceFile) { $EvidenceFile = Join-Path $root "runtime-data/evidence.json" }
if ($Mode -eq "reconcile" -and -not $RemoteQuiescent) {
    throw "Stop the service and confirm remote quiescence before reconciliation"
}
if ($Mode -eq "initialize" -and $Endpoint.TrimEnd('/').EndsWith("/AAST")) {
    throw "Operational AAST must not be initialized by this launcher; use inspect/adopt/recover"
}
$oldPythonPath = $env:PYTHONPATH
Push-Location $root
try {
    $env:PYTHONPATH = "$(Split-Path -Parent $root);$oldPythonPath"
    $arguments = @("-m","selira.runtime.governance_server","--endpoint",$Endpoint,
        "--journal",$Journal,"--evidence-file",$EvidenceFile,"--mode",$Mode,
        "--port","$Port","--exclusive-writer")
    if ($RemoteQuiescent) { $arguments += "--remote-quiescent" }
    python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Governance command failed: $LASTEXITCODE" }
} finally {
    $env:PYTHONPATH = $oldPythonPath
    Pop-Location
}
