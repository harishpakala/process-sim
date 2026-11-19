param(
    [Parameter(Mandatory = $true)]
    [string]$Question,
    [string]$Name = "multihop-01",
    [string]$Model = "llama3.1:8b",
    [string]$Endpoint = "http://localhost:7200/repositories/AAS"
)
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = (Resolve-Path ".\src").Path
$directory = Join-Path (Get-Location) "benchmark-output"
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$base = @(
    "answer",
    "--schema", "semantic/ontology2/dtwise/dtwise-schema-index.json",
    "--mappings", "semantic/ontology2/dtwise/cross-domain-mappings.json",
    "--endpoint", $Endpoint,
    "--model", $Model,
    "--experimental-multihop",
    "--question", $Question
)
function Invoke-Mode([string]$Mode) {
    $out = Join-Path $directory "$Name-$Mode.json"
    $diag = Join-Path $directory "$Name-$Mode-diagnostics.json"
    Write-Host "Running $Mode ..."
    & python -m process_sim.dtwise.unified_answer @base --planning-mode $Mode --prompt-diagnostics $diag --output $out
    if ($LASTEXITCODE -ne 0) { Write-Warning "$Mode exited with code $LASTEXITCODE" }
    if (-not (Test-Path $out)) { throw "No output for $Mode at $out" }
    $report = Get-Content $out -Raw | ConvertFrom-Json
    if ($report.status -ne "executed") {
        Write-Warning "$Mode failed: $($report.error)"
    }
    return $report
}
function Get-CanonicalRows($report) {
    if ($report.status -ne "executed") { return @() }
    $bindings = @($report.results.results.bindings | Where-Object { $null -ne $_ })
    return @($bindings | ForEach-Object {
        $values = @($_.PSObject.Properties | Sort-Object Name | ForEach-Object {
            $v = $_.Value
            # Ignore projection variable names; preserve RDF type, value, and language/datatype.
            [PSCustomObject]@{
                type = $v.type
                value = $v.value
                datatype = $v.datatype
                lang = $v.'xml:lang'
            } | ConvertTo-Json -Compress -Depth 6
        })
        ($values -join "|")
    } | Sort-Object)
}
$hybrid = Invoke-Mode "hybrid"
$explore = Invoke-Mode "ontology_explore"
$hRows = @(Get-CanonicalRows $hybrid)
$eRows = @(Get-CanonicalRows $explore)
$equal = ($hybrid.status -eq "executed" -and $explore.status -eq "executed" -and
    $hRows.Count -eq $eRows.Count -and
    @(Compare-Object $hRows $eRows).Count -eq 0)
[PSCustomObject]@{
    Question = $Question
    HybridStatus = $hybrid.status
    ExploreStatus = $explore.status
    HybridRows = $hRows.Count
    ExploreRows = $eRows.Count
    EqualAnswerMultiset = $equal
    HybridHops = if ($null -ne $hybrid.ir -and $null -ne $hybrid.ir.edges) { @($hybrid.ir.edges).Count } else { $null }
    ExploreHops = if ($null -ne $explore.ir -and $null -ne $explore.ir.edges) { @($explore.ir.edges).Count } else { $null }
    HybridError = $hybrid.error
    ExploreError = $explore.error
    HybridPlanningSeconds = $hybrid.timings.planning_seconds
    ExplorePlanningSeconds = $explore.timings.planning_seconds
} | Format-List
Write-Host "Saved outputs to $directory"
