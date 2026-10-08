Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\RainShockArchive.psm1') -Force

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$key = [Environment]::GetEnvironmentVariable('DATA_GO_KR_SERVICE_KEY')
if ([string]::IsNullOrWhiteSpace($key)) {
    [pscustomobject]@{ Source='kma_asos_hourly'; Status='skipped_missing_DATA_GO_KR_SERVICE_KEY'; Stations=@('108','101','93') } | ConvertTo-Json -Depth 4
    exit 0
}

$endpoint = 'https://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList'
$stations = @('108','101','93')
$months = @(
    @{ startDt='20250701'; endDt='20250731'; ym='202507' },
    @{ startDt='20250801'; endDt='20250831'; ym='202508' },
    @{ startDt='20250901'; endDt='20250930'; ym='202509' },
    @{ startDt='20251001'; endDt='20251031'; ym='202510' },
    @{ startDt='20251101'; endDt='20251130'; ym='202511' },
    @{ startDt='20251201'; endDt='20251231'; ym='202512' }
)
$results = @()
foreach ($station in $stations) {
    foreach ($month in $months) {
        $runId = New-RainShockRunId
        $outDir = Join-Path $root "data\public_rainshock\raw\kma\asos_hourly\stn_$station\$runId"
        New-RainShockDirectory -Path $outDir
        $query = [ordered]@{
            ServiceKey = '<redacted>'
            pageNo = '1'
            numOfRows = '999'
            dataType = 'JSON'
            dataCd = 'ASOS'
            dateCd = 'HR'
            startDt = $month.startDt
            startHh = '00'
            endDt = $month.endDt
            endHh = '23'
            stnIds = $station
        }
        Save-JsonFile -Object $query -Path (Join-Path $outDir 'request_sanitized.json')
        $url = $endpoint + '?' + ((@('ServiceKey=' + [uri]::EscapeDataString($key)) + ($query.Keys | Where-Object { $_ -ne 'ServiceKey' } | ForEach-Object { [uri]::EscapeDataString($_) + '=' + [uri]::EscapeDataString([string]$query[$_]) })) -join '&')
        $rawPath = Join-Path $outDir "asos_hourly_stn_$station`_$($month.ym).raw.json"
        try {
            Invoke-WebRequest -Uri $url -OutFile $rawPath -UseBasicParsing | Out-Null
            $rawText = Get-Content -LiteralPath $rawPath -Raw -Encoding UTF8
            $json = $rawText | ConvertFrom-Json
            if ($json.response.header.resultCode -ne '00') {
                throw "API resultCode=$($json.response.header.resultCode), resultMsg=$($json.response.header.resultMsg)"
            }
        } catch {
            $failure = [ordered]@{
                source_name = 'kma_asos_hourly'
                station_id = $station
                year_month = $month.ym
                status = 'failed_api_request'
                credential_env_var = 'DATA_GO_KR_SERVICE_KEY'
                credential_value_stored = $false
                error_message = $_.Exception.Message
                request_query_sanitized = $query
                failed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
            }
            $failurePath = Join-Path $outDir 'failure_manifest.json'
            Save-JsonFile -Object $failure -Path $failurePath
            $results += [ordered]@{ station=$station; ym=$month.ym; status='failed_api_request'; failure=$failurePath }
            continue
        }
        $manifest = [ordered]@{
            source_name = 'kma_asos_hourly'
            station_id = $station
            year_month = $month.ym
            credential_required = $true
            credential_env_var = 'DATA_GO_KR_SERVICE_KEY'
            credential_present = $true
            credential_value_stored = $false
            source_page_url = 'https://www.data.go.kr/data/15057210/openapi.do'
            request_url = $endpoint
            method = 'GET'
            retrieved_at_utc = (Get-Date).ToUniversalTime().ToString('o')
            request_query_sanitized = $query
            raw_file = (Split-Path -Leaf $rawPath)
            raw_sha256 = Get-FileSha256 -Path $rawPath
            raw_bytes = (Get-Item -LiteralPath $rawPath).Length
        }
        Save-JsonFile -Object $manifest -Path (Join-Path $outDir 'manifest.json')
        Add-ChecksumLine -ChecksumFile (Join-Path $root 'data\public_rainshock\checksums\sha256sums.txt') -FilePath $rawPath
        $results += [ordered]@{ station=$station; ym=$month.ym; status='completed'; raw=$rawPath }
    }
}
$expected = $stations.Count * $months.Count
$status = if (@($results | Where-Object { $_.status -eq 'completed' }).Count -eq $expected) { 'completed' } else { 'partial_or_failed' }
[pscustomobject]@{ Source='kma_asos_hourly'; Status=$status; Expected=$expected; Results=$results } | ConvertTo-Json -Depth 6

