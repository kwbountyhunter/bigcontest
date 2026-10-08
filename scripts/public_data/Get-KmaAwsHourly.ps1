Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\RainShockArchive.psm1') -Force
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$runId = New-RainShockRunId
$outDir = Join-Path $root "data\public_rainshock\raw\kma\aws_hourly\stn_400\$runId"
New-RainShockDirectory -Path $outDir
$record = [ordered]@{
    source_name = 'kma_aws_400_historical_manual_placeholder'
    station_id = '400'
    status = 'manual_acquisition_required'
    reason = 'The public data.go.kr AWS endpoint identified for automatic access is recent-two-day AWS minute data and is not suitable for 2025-07-01..2025-12-31 historical retrieval. Use the KMA Data Open Portal AWS historical data/file-set workflow for station 400 and preserve the raw export here.'
    official_portal_page = 'https://data.kma.go.kr/data/grnd/selectAwsRltmList.do?pgmNo=56'
    desired_period_start = '2025-07-01 00:00 KST'
    desired_period_end = '2025-12-31 23:00 KST'
    created_at_utc = (Get-Date).ToUniversalTime().ToString('o')
}
Save-JsonFile -Object $record -Path (Join-Path $outDir 'manual_acquisition_required.json')
[pscustomobject]@{ Source='kma_aws_400'; Status='manual_acquisition_required'; Marker=(Join-Path $outDir 'manual_acquisition_required.json') } | ConvertTo-Json -Depth 4
