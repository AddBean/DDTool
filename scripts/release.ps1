param(
    [Parameter(Mandatory = $true)]
    [string] $Version
)

$ErrorActionPreference = "Stop"

if ($Version -notmatch '^v\d+\.\d+\.\d+([-.][0-9A-Za-z.-]+)?$') {
    throw "Version must look like v1.2.3 or v1.2.3-beta.1"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (git status --porcelain) {
    throw "The working tree is not clean. Commit or stash changes first."
}
if ((git branch --show-current).Trim() -ne "main") {
    throw "Releases must be created from the main branch."
}

git tag -a $Version -m "Release $Version"
if ($LASTEXITCODE -ne 0) {
    throw "Could not create tag $Version"
}

git push origin $Version
if ($LASTEXITCODE -ne 0) {
    throw "Could not push tag $Version"
}

Write-Host "Pushed $Version. GitHub Actions will build and publish the release."
