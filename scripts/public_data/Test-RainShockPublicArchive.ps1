Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\RainShockArchive.psm1') -Force

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$base = Join-Path $root 'data\public_rainshock'
$errors = New-Object System.Collections.Generic.List[string]
function Assert-True([bool]$Condition, [string]$Message) { if (-not $Condition) { $errors.Add($Message) } }

Assert-True (Test-Path -LiteralPath $base) 'data\public_rainshock does not exist'
Assert-True (Test-Path -LiteralPath (Join-Path $base 'raw\kma\station_metadata')) 'station metadata directory missing'
Assert-True (Test-Path -LiteralPath (Join-Path $base 'raw\kma\weather_warnings')) 'weather warnings directory missing'

$stationRaw = Get-ChildItem -LiteralPath (Join-Path $base 'raw\kma\station_metadata') -Filter 'station_metadata.raw.csv' -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Assert-True ($stationRaw -ne $null) 'station metadata raw file missing'
if ($stationRaw) {
    Assert-True ($stationRaw.Length -gt 0) 'station metadata raw file is empty'
    Assert-True (Test-Path -LiteralPath (Join-Path $stationRaw.DirectoryName 'manifest.json')) 'station metadata manifest missing'
    Assert-True (Test-Path -LiteralPath (Join-Path $stationRaw.DirectoryName 'validation.json')) 'station metadata validation missing'
}

$warningRaw = Get-ChildItem -LiteralPath (Join-Path $base 'raw\kma\weather_warnings') -Filter 'weather_warnings_20250701_20251231.raw.csv' -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Assert-True ($warningRaw -ne $null) 'weather warning raw file missing'
if ($warningRaw) {
    Assert-True ($warningRaw.Length -gt 0) 'weather warning raw file is empty'
    Assert-True (Test-Path -LiteralPath (Join-Path $warningRaw.DirectoryName 'manifest.json')) 'weather warning manifest missing'
    Assert-True (Test-Path -LiteralPath (Join-Path $warningRaw.DirectoryName 'validation.json')) 'weather warning validation missing'
}

$checksum = Join-Path $base 'checksums\sha256sums.txt'
Assert-True (Test-Path -LiteralPath $checksum) 'checksum file missing'
if (Test-Path -LiteralPath $checksum) { Assert-True ((Get-Item -LiteralPath $checksum).Length -gt 0) 'checksum file is empty' }

$report = [ordered]@{
    validated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    status = if ($errors.Count -eq 0) { 'passed' } else { 'failed' }
    errors = @($errors)
    station_metadata_latest = if ($stationRaw) { $stationRaw.FullName } else { $null }
    weather_warnings_latest = if ($warningRaw) { $warningRaw.FullName } else { $null }
}
$runId = New-RainShockRunId
$runDir = Join-Path $base "meta\runs\$runId"
New-RainShockDirectory -Path $runDir
Save-JsonFile -Object $report -Path (Join-Path $runDir 'validation_report.json')

if ($errors.Count -gt 0) {
    $report | ConvertTo-Json -Depth 6
    exit 1
}
$report | ConvertTo-Json -Depth 6
