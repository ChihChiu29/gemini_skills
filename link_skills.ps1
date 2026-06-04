# link_skills.ps1 - Automated skill linking script for Chih's Antigravity CLI Skills
# This script sets up the project-specific skill directories so the agent can discover the skill.

$ErrorActionPreference = "Stop"

# Write headers with premium colors
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Antigravity Skill Linker for Windows" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan

$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}

$SkillSource = Join-Path $ProjectRoot "skill_src\stock-lows-analyzer"
if (-not (Test-Path $SkillSource)) {
    Write-Error "Could not find skill source at: $SkillSource"
    exit 1
}

# The target folders where the CLI checks for skills
$TargetBases = @(
    ".antigravity",
    ".agents",
    ".agent",
    ".jetski"
)

foreach ($base in $TargetBases) {
    $SkillsDir = Join-Path $ProjectRoot "$base\skills"
    $LinkPath = Join-Path $SkillsDir "stock-lows-analyzer"

    Write-Host "`nSetting up skill directory: $base/skills" -ForegroundColor Yellow

    # Ensure parent folder exists
    if (-not (Test-Path $SkillsDir)) {
        New-Item -ItemType Directory -Path $SkillsDir -Force | Out-Null
        Write-Host "  [+] Created directory: $base/skills" -ForegroundColor Gray
    }

    # If something already exists at the link path, clean it up safely
    if (Test-Path $LinkPath) {
        Write-Host "  [-] Found existing item at $base/skills/stock-lows-analyzer. Cleaning up..." -ForegroundColor Magenta
        $item = Get-Item $LinkPath -Force
        if ($item.Attributes -match "ReparsePoint") {
            # Safely remove symbolic link or junction without deleting target content
            [System.IO.Directory]::Delete($LinkPath)
        } else {
            Remove-Item -Path $LinkPath -Recurse -Force | Out-Null
        }
    }

    # Create directory junction (does not require Administrator privileges)
    try {
        New-Item -ItemType Junction -Path $LinkPath -Value $SkillSource | Out-Null
        Write-Host "  [✓] Linked skill successfully to $base/skills/stock-lows-analyzer" -ForegroundColor Green
    } catch {
        Write-Host "  [!] Failed to create junction for $base: $_" -ForegroundColor Red
    }
}

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "  Setup complete! All skill links configured." -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
