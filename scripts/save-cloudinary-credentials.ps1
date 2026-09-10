$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$credentialDirectory = Join-Path $projectRoot 'data/runtime/credentials'
$credentialPath = Join-Path $credentialDirectory 'cloudinary.dpapi'
if (Test-Path -LiteralPath $credentialPath) { throw '이미 저장된 Cloudinary 인증이 있습니다.' }
$cloudName = Read-Host 'Cloud name'
if ($cloudName -notmatch '^[a-z0-9_-]{1,80}$') { throw 'Cloud name 형식을 확인하세요.' }
$cloudKey = Read-Host 'API Key (숨김 입력)' -AsSecureString
$cloudSecret = Read-Host 'API Secret (숨김 입력)' -AsSecureString
$keyPointer = [IntPtr]::Zero
$secretPointer = [IntPtr]::Zero
$payloadSecure = $null
try {
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cloudKey)
    $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cloudSecret)
    $payload = @{cloud_name=$cloudName;api_key=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer);api_secret=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)}
    if ($payload.api_key -notmatch '^[0-9]+$' -or !$payload.api_secret) { throw '인증 입력 형식을 확인하세요.' }
    $payloadSecure = ConvertTo-SecureString ($payload | ConvertTo-Json -Compress) -AsPlainText -Force
    $encrypted = ConvertFrom-SecureString $payloadSecure
    New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
    $stream = [System.IO.File]::Open($credentialPath,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
    try { $bytes = [System.Text.Encoding]::UTF8.GetBytes($encrypted); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    Write-Host 'Cloudinary 인증 암호화 저장 완료. 아직 업로드나 게시를 실행하지 않았습니다.'
} finally {
    if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    if ($secretPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer) }
    $cloudKey.Dispose(); $cloudSecret.Dispose()
    if ($null -ne $payloadSecure) { $payloadSecure.Dispose() }
    $payload = $null; $encrypted = $null
}
