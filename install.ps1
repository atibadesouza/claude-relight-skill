# Relight + MediaGen installer (Windows).
# Order matters: ffmpeg -> falkit (editable) -> skill deps -> link skills -> seed keys -> verify import.
$ErrorActionPreference = "Stop"
$userSkills   = Join-Path $env:USERPROFILE ".claude\skills"
$relightSkill = Join-Path $PSScriptRoot ".claude\skills\relight"
$mediagenSkill= Join-Path $PSScriptRoot ".claude\skills\mediagen"

Write-Host "1/7 Installing ffmpeg (winget)..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
} else { Write-Host "  ffmpeg already present." }

Write-Host "2/7 Installing shared falkit core (editable) - required by BOTH skills..."
python -m pip install -e (Join-Path $PSScriptRoot "falkit-core")

Write-Host "3/7 Installing MediaGen Python deps..."
python -m pip install -r (Join-Path $mediagenSkill "requirements.txt")

Write-Host "4/7 Ensuring Relight Python deps..."
python -m pip install -r (Join-Path $relightSkill "requirements.txt")

Write-Host "5/7 Linking skills into ~/.claude/skills ..."
New-Item -ItemType Directory -Force -Path $userSkills | Out-Null
foreach ($pair in @(@($relightSkill, "relight"), @($mediagenSkill, "mediagen"))) {
    $src = $pair[0]; $name = $pair[1]; $link = Join-Path $userSkills $name
    if (Test-Path $link) { Write-Host "  $name link exists, skipping." }
    else {
        try { New-Item -ItemType SymbolicLink -Path $link -Target $src | Out-Null; Write-Host "  Symlinked $name." }
        catch { Write-Warning "  Symlink failed for $name (enable Developer Mode or run as admin). Copying instead."; Copy-Item $src $link -Recurse }
    }
}

Write-Host "6/7 Seeding key files ..."
# Shared key (used by both skills via falkit).
$falEnv = Join-Path $env:USERPROFILE ".claude\fal.env"
if (-not (Test-Path $falEnv)) {
    Copy-Item (Join-Path $PSScriptRoot "fal.env.example") $falEnv
    Write-Host "  Created $falEnv - edit it and paste your FAL_KEY (shared by all skills)."
} else { Write-Host "  $falEnv already exists." }
# Relight's own .env still works as a back-compat fallback.
$relightEnv = Join-Path $relightSkill ".env"
if (-not (Test-Path $relightEnv)) { Copy-Item (Join-Path $relightSkill ".env.example") $relightEnv }

Write-Host "7/7 Verifying falkit import under this interpreter..."
python -c "import sys, falkit; print('  falkit OK under', sys.executable)"
if ($LASTEXITCODE -ne 0) { throw "falkit is not importable under '$(python -c 'import sys;print(sys.executable)')'. Ensure your scripts run under this interpreter." }

Write-Host "`nDone. Edit $falEnv (paste your FAL_KEY), then verify Relight with:"
Write-Host "  python `"$relightSkill\scripts\preflight.py`""
