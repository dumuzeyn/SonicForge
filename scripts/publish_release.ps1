param(
    [Parameter(Mandatory=$true)][string]$Commit,
    [string]$Tag = 'v2.0.0',
    [long]$ResumeDraftId = 0
)
$ErrorActionPreference = 'Stop'
$ReleaseRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ReleaseAssets = @(
    (Join-Path $ReleaseRoot 'dist\SonicForge-Setup-2.0.0.exe'),
    (Join-Path $ReleaseRoot 'dist\SonicForge-2.0.0-windows-x64.zip'),
    (Join-Path $ReleaseRoot 'dist\SHA256SUMS.txt')
)
if ($Commit -notmatch '^[a-f0-9]{40}$' -or $Tag -ne 'v2.0.0') { throw 'Unexpected release identity' }
foreach ($ReleaseAsset in $ReleaseAssets) {
    if (-not (Test-Path -LiteralPath $ReleaseAsset -PathType Leaf)) { throw 'Missing release asset' }
}
Set-Location -LiteralPath $ReleaseRoot
$ReleaseHead = git rev-parse HEAD
if ($ReleaseHead -ne $Commit) { throw 'Release commit does not match local HEAD' }
$ReleaseRemote = git ls-remote origin refs/heads/main
if ($LASTEXITCODE -ne 0 -or $ReleaseRemote -notmatch "^$Commit\s") { throw 'Release commit is not pushed to main' }
$ReleaseCredentialLines = "protocol=https`nhost=github.com`n`n" | git credential fill
$ReleaseCredentials = @{}
foreach ($ReleaseLine in $ReleaseCredentialLines) {
    if ($ReleaseLine -match '^([^=]+)=(.*)$') { $ReleaseCredentials[$matches[1]] = $matches[2] }
}
if (-not $ReleaseCredentials.password) { throw 'GitHub authentication is unavailable' }
$ReleaseHeaders = @{ Authorization = 'Bearer ' + $ReleaseCredentials.password;
    Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
$ReleaseApi = 'https://api.github.com/repos/dumuzeyn/SonicForge'
try {
    $ReleaseRepository = Invoke-RestMethod -Uri $ReleaseApi -Headers $ReleaseHeaders
    if ($ReleaseRepository.full_name -ne 'dumuzeyn/SonicForge' -or -not $ReleaseRepository.permissions.push) {
        throw 'Unexpected repository or insufficient publishing permissions'
    }
    $ReleaseExisting = Invoke-RestMethod -Uri "$ReleaseApi/releases?per_page=100" -Headers $ReleaseHeaders
    $ReleaseMatching = $ReleaseExisting | Where-Object { $_.tag_name -eq $Tag }
    if ($ReleaseMatching -and (-not $ResumeDraftId -or $ReleaseMatching.id -ne $ResumeDraftId -or -not $ReleaseMatching.draft)) {
        throw 'This release already exists; it will not be overwritten'
    }
    $ReleaseBody = Get-Content -LiteralPath (Join-Path $ReleaseRoot 'docs\RELEASE-2.0.md') -Raw -Encoding UTF8
    $ReleasePayload = @{ tag_name=$Tag; target_commitish=$Commit; name='SonicForge 2.0';
        body=$ReleaseBody; draft=$true; prerelease=$false } | ConvertTo-Json
    if ($ResumeDraftId) {
        if (-not $ReleaseMatching -or $ReleaseMatching.id -ne $ResumeDraftId -or -not $ReleaseMatching.draft) {
            throw 'The specified private draft could not be verified'
        }
        $ReleaseDraft = Invoke-RestMethod -Method Patch -Uri "$ReleaseApi/releases/$ResumeDraftId" -Headers $ReleaseHeaders `
            -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($ReleasePayload))
    } else {
        $ReleaseDraft = Invoke-RestMethod -Method Post -Uri "$ReleaseApi/releases" -Headers $ReleaseHeaders `
            -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($ReleasePayload))
    }
    $ReleasePriorAssets = Invoke-RestMethod -Uri "$ReleaseApi/releases/$($ReleaseDraft.id)/assets" -Headers $ReleaseHeaders
    # Keep an incomplete upload private. Never replace an existing release.
    foreach ($ReleaseAsset in $ReleaseAssets) {
        $ReleaseFile = Get-Item -LiteralPath $ReleaseAsset
        $ReleaseHash = (Get-FileHash -LiteralPath $ReleaseFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $ReleasePrior = $ReleasePriorAssets | Where-Object { $_.name -eq $ReleaseFile.Name }
        if ($ReleasePrior) {
            if ($ReleasePrior.size -ne $ReleaseFile.Length -or $ReleasePrior.state -ne 'uploaded' -or
                $ReleasePrior.digest -ne ('sha256:' + $ReleaseHash)) { throw 'Existing draft asset does not match the verified local file' }
            Write-Host "Verified previously uploaded $($ReleaseFile.Name)"
            continue
        }
        $ReleaseUpload = $ReleaseDraft.upload_url -replace '\{.*\}$', ''
        $ReleaseUpload += '?name=' + [Uri]::EscapeDataString($ReleaseFile.Name)
        Write-Host "Uploading $($ReleaseFile.Name) ($([Math]::Round($ReleaseFile.Length / 1MB, 1)) MB)"
        $ReleaseUploaded = Invoke-RestMethod -Method Post -Uri $ReleaseUpload -Headers $ReleaseHeaders `
            -ContentType 'application/octet-stream' -InFile $ReleaseFile.FullName -TimeoutSec 1800
        if ($ReleaseUploaded.size -ne $ReleaseFile.Length -or $ReleaseUploaded.state -ne 'uploaded') {
            throw 'Release upload verification failed; draft remains unpublished'
        }
        if ($ReleaseUploaded.digest -and $ReleaseUploaded.digest -ne ('sha256:' + $ReleaseHash)) {
            throw 'Release asset checksum mismatch; draft remains unpublished'
        }
    }
    $ReleaseUploadedAssets = Invoke-RestMethod -Uri "$ReleaseApi/releases/$($ReleaseDraft.id)/assets" -Headers $ReleaseHeaders
    if (@($ReleaseUploadedAssets).Count -ne $ReleaseAssets.Count) { throw 'Incomplete release; draft remains unpublished' }
    $ReleasePublished = Invoke-RestMethod -Method Patch -Uri "$ReleaseApi/releases/$($ReleaseDraft.id)" `
        -Headers $ReleaseHeaders -ContentType 'application/json' -Body '{"draft":false,"make_latest":"true"}'
    if ($ReleasePublished.draft -or $ReleasePublished.tag_name -ne $Tag) { throw 'Release publication could not be confirmed' }
    Write-Host "Published $($ReleasePublished.html_url)"
    $ReleasePublished.assets | Select-Object name,size,browser_download_url
} finally {
    $ReleaseCredentials.Clear()
    $ReleaseHeaders.Clear()
    $ReleaseCredentialLines = $null
}
