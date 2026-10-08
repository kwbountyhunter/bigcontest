Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\RainShockArchive.psm1') -Force

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$runId = New-RainShockRunId
$outDir = Join-Path $root "data\public_rainshock\raw\kma\station_metadata\$runId"
New-RainShockDirectory -Path $outDir

$url = 'https://data.kma.go.kr/tmeta/stn/selectStnListDownload.do'
$sourcePage = 'https://data.kma.go.kr/tmeta/stn/selectStnList.do?pgmNo=123'
$body = [ordered]@{
    fileType = 'csv'
    pageIndex = '1'
    schListCnt = '10'
    mddlClssCd = ''
    stnIds = ''
    serviceSe = 'F00101'
    txtStnNm = ''
    txtElementNm = ''
    dTreeId = ''
    gTreeId = ''
    mddlClssCdDiff = ''
    pgmNo = '123'
}

Save-JsonFile -Object $body -Path (Join-Path $outDir 'request.json')
$rawPath = Join-Path $outDir 'station_metadata.raw.csv'
$response = Invoke-RawFormPost -Url $url -Fields $body -OutFile $rawPath
Save-JsonFile -Object $response.Headers -Path (Join-Path $outDir 'headers.json')
$manifest = New-Manifest -SourceName 'kma_station_metadata' -SourcePageUrl $sourcePage -RequestUrl $url -Method 'POST' -RequestBody $body -RawFile $rawPath -ResponseInfo $response -EncodingDetected 'MS949'
Save-JsonFile -Object $manifest -Path (Join-Path $outDir 'manifest.json')
Add-ChecksumLine -ChecksumFile (Join-Path $root 'data\public_rainshock\checksums\sha256sums.txt') -FilePath $rawPath

$bytes = [System.IO.File]::ReadAllBytes($rawPath)
$text = [System.Text.Encoding]::GetEncoding(949).GetString($bytes)
$stationIds = @('108','101','93','400')
$validation = [ordered]@{
    source = 'kma_station_metadata'
    run_id = $runId
    non_empty = ((Get-Item -LiteralPath $rawPath).Length -gt 0)
    response_status = $response.StatusCode
    stations_checked = $stationIds
    stations_found_by_text_search = @{}
}
foreach ($id in $stationIds) {
    $validation.stations_found_by_text_search[$id] = ($text -match "(^|[^0-9])$id([^0-9]|$)")
}
Save-JsonFile -Object $validation -Path (Join-Path $outDir 'validation.json')

[pscustomobject]@{
    Source = 'kma_station_metadata'
    RunId = $runId
    Status = $response.StatusCode
    Bytes = (Get-Item -LiteralPath $rawPath).Length
    RawFile = $rawPath
} | ConvertTo-Json -Depth 4
