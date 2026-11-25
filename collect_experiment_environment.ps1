param([string]$OutputPath = 'experiment_manifest.json')
$ErrorActionPreference = 'Continue'
function Capture([string]$Name, [scriptblock]$Action) {
    try { $result = & $Action; return @{status='collected'; data=$result} }
    catch { return @{status='unavailable'; reason=$Name + ': ' + $_.Exception.GetType().Name} }
}
function Native([string]$Exe, [string[]]$Arguments) {
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) { return @{status='not_installed_or_not_on_path'} }
    try {
        $lines = & $Exe @Arguments 2>$null
        $code = $LASTEXITCODE
        if ($code -ne 0) { return @{status='failed'; exit_code=$code} }
        return @{status='collected'; data=@($lines)}
    } catch { return @{status='unavailable'} }
}
$report = [ordered]@{
    schema_version = '1.0'
    collected_at_utc = [DateTime]::UtcNow.ToString('o')
    purpose = 'MODELSWARD 2027 TEP NEXUS environment audit'
    cpu = Capture 'CPU' { Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed }
    memory = Capture 'RAM' { Get-CimInstance Win32_ComputerSystem -ErrorAction Stop | Select-Object @{Name='RAM_GiB';Expression={[math]::Round($_.TotalPhysicalMemory / 1GB,2)}} }
    gpu = Capture 'GPU' { Get-CimInstance Win32_VideoController -ErrorAction Stop | Select-Object Name, DriverVersion }
    nvidia = Native 'nvidia-smi' @('--query-gpu=name,memory.total,driver_version','--format=csv,noheader')
    os = Capture 'OS' { Get-CimInstance Win32_OperatingSystem -ErrorAction Stop | Select-Object Caption, Version, BuildNumber, OSArchitecture }
    python = Native 'python' @('--version')
    python_packages = Native 'python' @('-m','pip','list','--format=json','--disable-pip-version-check')
    ollama_version = Native 'ollama' @('--version')
    ollama_list = Native 'ollama' @('list')
    ollama_running = Native 'ollama' @('ps')
    docker_version = Native 'docker' @('--version')
    docker_containers = Native 'docker' @('ps','--format','{{.Names}} | {{.Image}} | {{.Status}}')
    git_commit = Native 'git' @('rev-parse','HEAD')
    git_status = Native 'git' @('status','--porcelain')
    postgres_client = Native 'psql' @('--version')
    service_versions_note = 'GraphDB, PostgreSQL server and TimescaleDB extension versions and actual deployment topology require separate verification. Docker image tags are not verified server versions.'
    inference_note = 'Installed model metadata is not the effective benchmark inference configuration.'
}
$models = @()
try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10 -ErrorAction Stop
    foreach ($m in $tags.models) {
        $models += [ordered]@{name=$m.name; digest=$m.digest; size_bytes=$m.size; family=$m.details.family; parameter_size=$m.details.parameter_size; quantization=$m.details.quantization_level; format=$m.details.format}
    }
    $report['ollama_model_metadata'] = @{status='collected'; endpoint='local default'; data=$models}
} catch { $report['ollama_model_metadata'] = @{status='unavailable'; note='Default local Ollama API not reachable. Verify actual deployment.'} }
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding UTF8 -ErrorAction Stop
Write-Host "Environment audit saved to $OutputPath"
Write-Host 'Review package names, container names and Git filenames before sharing. No benchmarks were run.'
