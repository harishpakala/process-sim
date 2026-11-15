param(
    [string]$DtwiseRoot = "C:\Users\haris\eclipse-workspace\Vectorized_Retr",
    [string]$Endpoint = "http://pakala:7200/repositories/AAS",
    [string]$OutputDir = "reports\dtwise_B01_B31",
    [string]$Python = "python",
    [int]$StartAt = 1
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bridge = Join-Path $PSScriptRoot "dtwise_bridge.py"
$schema = Join-Path $DtwiseRoot "semantic\ontology\dtwise\dtwise-schema-index.json"
$csv = Join-Path $DtwiseRoot "DTwise_B01_B48_regression_questions.csv"
if (-not (Test-Path -LiteralPath $bridge)) { throw "Bridge not found: $bridge" }
if (-not (Test-Path -LiteralPath $schema)) { throw "Schema not found: $schema" }
if (-not (Test-Path -LiteralPath $csv)) { throw "Frozen benchmark CSV not found: $csv" }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$cases = @(Import-Csv -LiteralPath $csv | Where-Object { $_.id -match '^B(0[1-9]|[12][0-9]|3[01])$' } | Sort-Object id)
if ($cases.Count -ne 31) { throw "Expected 31 B01-B31 cases, found $($cases.Count)" }
if ($StartAt -lt 1 -or $StartAt -gt 31) { throw "StartAt must be 1..31" }
$cases = @($cases | Where-Object { [int]$_.id.Substring(1) -ge $StartAt })
$summary = @()
foreach ($case in $cases) {
    $id = $case.id
    $out = Join-Path $OutputDir "$id.json"
    $log = Join-Path $OutputDir "$id.log"
    Remove-Item -LiteralPath $out -ErrorAction SilentlyContinue
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host "=== $id : $($case.question) ===" -ForegroundColor Cyan
    # Redirect at the native process level to avoid Windows PowerShell 5.1
    # turning Python stderr into a terminating NativeCommandError.
    $argsList = @($bridge, "--dtwise-root", $DtwiseRoot, "--schema", $schema,
        "--graphdb-url", $Endpoint, "--question", $case.question,
        "--execute", "--output", $out)
    $stdoutLog = Join-Path $OutputDir "$id.stdout.log"
    $stderrLog = Join-Path $OutputDir "$id.stderr.log"
    $exit = -1
    try {
        $proc = Start-Process -FilePath $Python -ArgumentList $argsList -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
        $exit = $proc.ExitCode
        $stdOutText = Get-Content -LiteralPath $stdoutLog -Raw -ErrorAction SilentlyContinue
        $stdErrText = Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue
        [string]::Concat($stdOutText, "`n", $stdErrText) | Set-Content -LiteralPath $log -Encoding UTF8
    } catch {
        $_.Exception.ToString() | Set-Content -LiteralPath $log -Encoding UTF8
    }
    $watch.Stop()
    $status = "FAILED"
    $count = $null
    $err = ""
    if ($exit -eq 0 -and (Test-Path -LiteralPath $out)) {
        try {
            $result = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
            if ($result.executed -eq $true -and -not [string]::IsNullOrWhiteSpace($result.sparql)) {
                $status = "EXECUTED_REVIEW_PENDING"
                if ($null -ne $result.answer.count) { $count = $result.answer.count }
            } else { $err = "Missing SPARQL or execution confirmation" }
        } catch { $err = $_.Exception.Message }
    } else {
        $err = ((Get-Content -LiteralPath $log -Tail 6 -ErrorAction SilentlyContinue) -join " ")
    }
    $summary += [pscustomobject]@{
        id=$id; category=$case.category; question=$case.question
        status=$status; exit_code=$exit; count=$count
        seconds=[math]::Round($watch.Elapsed.TotalSeconds,2)
        error=$err; result_file=$out; log_file=$log
        semantic_verification="PENDING_REVIEW"
    }
    Write-Host "$id : $status" -ForegroundColor $(if ($status -eq "FAILED") { "Yellow" } else { "Green" })
}
$summaryFile = Join-Path $OutputDir "summary.csv"
$summary | Export-Csv -LiteralPath $summaryFile -NoTypeInformation -Encoding UTF8
$summary | Format-Table id,status,count,seconds -AutoSize
Write-Host "Summary: $summaryFile"
Write-Host "EXECUTED_REVIEW_PENDING is not a semantic PASS; inspect outputs against frozen reference expectations."
