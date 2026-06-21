# Relight skill installer (Windows).
$ErrorActionPreference = "Stop"
$repoSkill = Join-Path $PSScriptRoot ".claude\skills\relight"
$userSkills = Join-Path $env:USERPROFILE ".claude\skills"
$link = Join-Path $userSkills "relight"

Write-Host "1/4 Installing ffmpeg (winget)..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
} else { Write-Host "  ffmpeg already present." }

Write-Host "2/4 Installing Python deps..."
python -m pip install -r (Join-Path $repoSkill "requirements.txt")

Write-Host "3/4 Linking skill into ~/.claude/skills ..."
New-Item -ItemType Directory -Force -Path $userSkills | Out-Null
if (Test-Path $link) { Write-Host "  Link/folder already exists, skipping." }
else {
    try {
        New-Item -ItemType SymbolicLink -Path $link -Target $repoSkill | Out-Null
        Write-Host "  Symlinked."
    } catch {
        Write-Warning "  Symlink failed (enable Developer Mode or run as admin). Copying instead."
        Copy-Item $repoSkill $link -Recurse
    }
}

Write-Host "4/4 Seeding .env ..."
$envFile = Join-Path $repoSkill ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $repoSkill ".env.example") $envFile
    Write-Host "  Created $envFile - edit it and paste your FAL_KEY."
} else { Write-Host "  .env already exists." }

Write-Host "`nDone. Edit $envFile, then run:"
Write-Host "  python `"$repoSkill\scripts\preflight.py`""
