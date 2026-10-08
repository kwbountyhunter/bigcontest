Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function New-RainShockRunId {
    return (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
}

function New-RainShockDirectory {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function ConvertTo-FormBody {
    param([Parameter(Mandatory=$true)][hashtable]$Fields)
    $pairs = New-Object System.Collections.Generic.List[string]
    foreach ($key in $Fields.Keys) {
        $value = [string]$Fields[$key]
        $pairs.Add(([uri]::EscapeDataString([string]$key) + '=' + [uri]::EscapeDataString($value)))
    }
    return ($pairs -join '&')
}

function Get-FileSha256 {
    param([Parameter(Mandatory=$true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Save-JsonFile {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Path
    )
    $json = $Object | ConvertTo-Json -Depth 12
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Get-SanitizedHeaders {
    param($Headers)
    $result = [ordered]@{}
    foreach ($key in $Headers.Keys) {
        $result[$key] = [string]$Headers[$key]
    }
    return $result
}

function Invoke-RawFormPost {
    param(
        [Parameter(Mandatory=$true)][string]$Url,
        [Parameter(Mandatory=$true)][hashtable]$Fields,
        [Parameter(Mandatory=$true)][string]$OutFile
    )
    $body = ConvertTo-FormBody -Fields $Fields
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    $request = [System.Net.HttpWebRequest]::Create($Url)
    $request.Method = 'POST'
    $request.ContentType = 'application/x-www-form-urlencoded; charset=UTF-8'
    $request.UserAgent = 'RainShock-public-data-fetcher/1.0'
    $request.ContentLength = $bytes.Length
    $stream = $request.GetRequestStream()
    try {
        $stream.Write($bytes, 0, $bytes.Length)
    }
    finally {
        $stream.Close()
    }
    try {
        $response = [System.Net.HttpWebResponse]$request.GetResponse()
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response -eq $null) { throw }
        $response = [System.Net.HttpWebResponse]$_.Exception.Response
    }
    $memory = New-Object System.IO.MemoryStream
    $responseStream = $response.GetResponseStream()
    try {
        $buffer = New-Object byte[] 8192
        while (($read = $responseStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $memory.Write($buffer, 0, $read)
        }
    }
    finally {
        if ($responseStream) { $responseStream.Close() }
    }
    $raw = $memory.ToArray()
    [System.IO.File]::WriteAllBytes($OutFile, $raw)
    $headers = [ordered]@{}
    foreach ($name in $response.Headers.AllKeys) {
        $headers[$name] = $response.Headers[$name]
    }
    return [ordered]@{
        StatusCode = [int]$response.StatusCode
        StatusDescription = $response.StatusDescription
        Headers = $headers
        Bytes = $raw.Length
        BodyUtf8 = [System.Text.Encoding]::UTF8.GetString($raw)
    }
}

function New-Manifest {
    param(
        [Parameter(Mandatory=$true)][string]$SourceName,
        [Parameter(Mandatory=$true)][string]$SourcePageUrl,
        [Parameter(Mandatory=$true)][string]$RequestUrl,
        [Parameter(Mandatory=$true)][string]$Method,
        [Parameter(Mandatory=$true)][hashtable]$RequestBody,
        [Parameter(Mandatory=$true)][string]$RawFile,
        [Parameter(Mandatory=$true)]$ResponseInfo,
        [string]$EncodingDetected = 'unknown',
        [bool]$CredentialRequired = $false,
        [string]$CredentialEnvVar = ''
    )
    $hash = Get-FileSha256 -Path $RawFile
    return [ordered]@{
        source_name = $SourceName
        credential_required = $CredentialRequired
        credential_env_var = $CredentialEnvVar
        credential_present = if ($CredentialEnvVar) { -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($CredentialEnvVar)) } else { $false }
        credential_value_stored = $false
        source_page_url = $SourcePageUrl
        request_url = $RequestUrl
        method = $Method
        retrieved_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        retrieved_at_kst = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), 'Korea Standard Time').ToString('o')
        request_body_sanitized = $RequestBody
        response_status = $ResponseInfo.StatusCode
        response_status_description = $ResponseInfo.StatusDescription
        response_headers_sanitized = $ResponseInfo.Headers
        encoding_detected = $EncodingDetected
        raw_file = (Split-Path -Leaf $RawFile)
        raw_sha256 = $hash
        raw_bytes = (Get-Item -LiteralPath $RawFile).Length
    }
}

function Add-ChecksumLine {
    param(
        [Parameter(Mandatory=$true)][string]$ChecksumFile,
        [Parameter(Mandatory=$true)][string]$FilePath
    )
    $hash = Get-FileSha256 -Path $FilePath
    $line = "$hash  $FilePath"
    Add-Content -LiteralPath $ChecksumFile -Value $line -Encoding UTF8
}

Export-ModuleMember -Function *
