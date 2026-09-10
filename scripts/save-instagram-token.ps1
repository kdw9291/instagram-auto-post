# Interactive local credential input. Never pass a token as a command argument.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$credentialDirectory = Join-Path $projectRoot 'data/runtime/credentials'
$credentialPath = Join-Path $credentialDirectory 'instagram-token.dpapi'
if (Test-Path -LiteralPath $credentialPath) {
    throw '이미 저장된 토큰이 있습니다. 기존 연결 확인 후 갱신 절차를 진행하세요.'
}
$instagramToken = Read-Host 'Meta에서 생성한 액세스 토큰을 붙여넣고 Enter (입력은 숨겨집니다)' -AsSecureString
try {
    if ($instagramToken.Length -lt 20) { throw '토큰 입력이 비어 있거나 너무 짧습니다. 저장하지 않았습니다.' }
    $encryptedToken = ConvertFrom-SecureString -SecureString $instagramToken
    New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
    # CreateNew prevents accidental replacement, including concurrent setup runs.
    $credentialStream = [System.IO.File]::Open($credentialPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $encryptedBytes = [System.Text.Encoding]::UTF8.GetBytes($encryptedToken)
        $credentialStream.Write($encryptedBytes, 0, $encryptedBytes.Length)
    } finally { $credentialStream.Dispose() }
    Write-Host '암호화 저장 완료. 현재 Windows 사용자 계정에서 복호화할 수 있습니다.'
    Write-Host '아직 Instagram 인증 확인이나 게시를 실행한 것은 아닙니다. Codex에 저장 완료라고 알려주세요.'
} finally {
    if ($null -ne $instagramToken) { $instagramToken.Dispose() }
    $encryptedToken = $null
}
