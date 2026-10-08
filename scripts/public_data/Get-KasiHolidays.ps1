Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\RainShockArchive.psm1') -Force

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$key = [Environment]::GetEnvironmentVariable('DATA_GO_KR_SERVICE_KEY')
if ([string]::IsNullOrWhiteSpace($key)) {
    [pscustomobject]@{ Source='kasi_holidays'; Status='skipped_missing_DATA_GO_KR_SERVICE_KEY'; Year='2025' } | ConvertTo-Json -Depth 4
    exit 0
}
$endpoint = 'https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo'
$runId = New-RainShockRunId
$outDir = Join-Path $root "data\public_rainshock\raw\kasi\holidays\2025\$runId"
New-RainShockDirectory -Path $outDir
$query = [ordered]@{ ServiceKey='<redacted>'; solYear='2025'; numOfRows='100'; pageNo='1'; _type='json' }
Save-JsonFile -Object $query -Path (Join-Path $outDir 'request_sanitized.json')
$url = $endpoint + '?' + ((@('ServiceKey=' + [uri]::EscapeDataString($key)) + ($query.Keys | Where-Object { $_ -ne 'ServiceKey' } | ForEach-Object { [uri]::EscapeDataString($_) + '=' + [uri]::EscapeDataString([string]$query[$_]) })) -join '&')
$rawPath = Join-Path $outDir 'kasi_holidays_2025.raw.json'
try {
    Invoke-WebRequest -Uri $url -OutFile $rawPath -UseBasicParsing | Out-Null
} catch {
    $failure = [ordered]@{
        source_name = 'kasi_holidays'
        status = 'failed_api_request'
        credential_env_var = 'DATA_GO_KR_SERVICE_KEY'
        credential_value_stored = $false
        error_message = $_.Exception.Message
        request_query_sanitized = $query
        failed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    }
    $failurePath = Join-Path $outDir 'failure_manifest.json'
    Save-JsonFile -Object $failure -Path $failurePath
    [pscustomobject]@{ Source='kasi_holidays'; Status='failed_api_request'; Failure=$failurePath } | ConvertTo-Json -Depth 4
    exit 0
}
$manifest = [ordered]@{
    source_name = 'kasi_holidays'
    credential_required = $true
    credential_env_var = 'DATA_GO_KR_SERVICE_KEY'
    credential_present = $true
    credential_value_stored = $false
    source_page_url = 'https://www.data.go.kr/data/15012690/openapi.do'
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
[pscustomobject]@{ Source='kasi_holidays'; Status='completed'; Year='2025'; RawFile=$rawPath } | ConvertTo-Json -Depth 4
