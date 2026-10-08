Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'lib\RainShockArchive.psm1') -Force

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$runId = New-RainShockRunId
$outDir = Join-Path $root "data\public_rainshock\raw\kma\weather_warnings\$runId"
New-RainShockDirectory -Path $outDir

$sourcePage = 'https://data.kma.go.kr/data/weatherReport/wsrList.do?pgmNo=647'
$step1Url = 'https://data.kma.go.kr/data/weatherReport/downloadWsrDataCSV.do'
$step2Url = 'https://data.kma.go.kr/download/fileDownload.do'
$step1Body = [ordered]@{
    fileType = 'csv'
    lrgClssCd = 'WRN'
    mddlClssCd = 'WRN01'
    serviceSe = 'F00102'
    dataFormCd = 'F00502'
    pgmNo = '647'
    menuNo = '631'
    stnIds = ''
    elementCds = ''
    elementNms = ''
    reqstPurposeCd = ''
    dataReqstSn = ''
    dataReqstFileSn = ''
    totCnt = ''
    pageIndex = '1'
    schListCnt = '100'
    txtStnNm = ''
    txtElmNm = ''
    stnTreeId = ''
    elementTreeId = ''
    startDt = '20250701'
    endDt = '20251231'
}
Save-JsonFile -Object $step1Body -Path (Join-Path $outDir 'step1_request.json')
$step1Raw = Join-Path $outDir 'step1_temp_path.raw.txt'
$step1 = Invoke-RawFormPost -Url $step1Url -Fields $step1Body -OutFile $step1Raw
Save-JsonFile -Object $step1.Headers -Path (Join-Path $outDir 'step1_headers.json')

$tempPath = $step1.BodyUtf8.Trim()
if ($tempPath -notmatch '^/.+\.csv$') {
    $match = [regex]::Match($step1.BodyUtf8, '(/[A-Za-z0-9_./-]+\.csv)')
    if (-not $match.Success) { throw "Could not parse KMA temporary warning CSV path from step 1 response: $($step1.BodyUtf8)" }
    $tempPath = $match.Groups[1].Value
}
$step2Body = [ordered]@{ file = $tempPath; delYn = 'N' }
Save-JsonFile -Object ([ordered]@{ file = '<ephemeral-temp-path-redacted-from-source-registry>'; delYn = 'N' }) -Path (Join-Path $outDir 'step2_request_sanitized.json')
$csvRaw = Join-Path $outDir 'weather_warnings_20250701_20251231.raw.csv'
$step2 = Invoke-RawFormPost -Url $step2Url -Fields $step2Body -OutFile $csvRaw
Save-JsonFile -Object $step2.Headers -Path (Join-Path $outDir 'step2_headers.json')

$step1Manifest = New-Manifest -SourceName 'kma_weather_warnings_step1' -SourcePageUrl $sourcePage -RequestUrl $step1Url -Method 'POST' -RequestBody $step1Body -RawFile $step1Raw -ResponseInfo $step1 -EncodingDetected 'UTF-8'
Save-JsonFile -Object $step1Manifest -Path (Join-Path $outDir 'step1_manifest.json')
$step2Manifest = New-Manifest -SourceName 'kma_weather_warnings_csv' -SourcePageUrl $sourcePage -RequestUrl $step2Url -Method 'POST' -RequestBody ([ordered]@{ file = '<ephemeral-temp-path>'; delYn = 'N' }) -RawFile $csvRaw -ResponseInfo $step2 -EncodingDetected 'MS949'
$step2Manifest['ephemeral_temp_path_generated_fresh'] = $true
Save-JsonFile -Object $step2Manifest -Path (Join-Path $outDir 'manifest.json')
Add-ChecksumLine -ChecksumFile (Join-Path $root 'data\public_rainshock\checksums\sha256sums.txt') -FilePath $csvRaw

$validation = [ordered]@{
    source = 'kma_weather_warnings'
    run_id = $runId
    step1_status = $step1.StatusCode
    step2_status = $step2.StatusCode
    csv_non_empty = ((Get-Item -LiteralPath $csvRaw).Length -gt 0)
    start_date = '20250701'
    end_date = '20251231'
    temp_path_not_persisted_as_source = $true
}
Save-JsonFile -Object $validation -Path (Join-Path $outDir 'validation.json')

[pscustomobject]@{
    Source = 'kma_weather_warnings'
    RunId = $runId
    Step1Status = $step1.StatusCode
    Step2Status = $step2.StatusCode
    Bytes = (Get-Item -LiteralPath $csvRaw).Length
    RawFile = $csvRaw
} | ConvertTo-Json -Depth 4
