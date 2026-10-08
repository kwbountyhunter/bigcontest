Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scripts = @(
    'Get-KmaStationMetadata.ps1',
    'Get-KmaWeatherWarnings.ps1',
    'Get-KmaAsosHourly.ps1',
    'Get-KmaAwsHourly.ps1',
    'Get-KasiHolidays.ps1'
)
$results = @()
foreach ($script in $scripts) {
    $path = Join-Path $PSScriptRoot $script
    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $path
    $results += [ordered]@{ script = $script; output = $output }
}
$results | ConvertTo-Json -Depth 8
