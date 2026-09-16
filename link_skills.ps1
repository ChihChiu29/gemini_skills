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

$Skills = @("stock-lows-analyzer", "leasehackr-ev-deals")

# The target folders where the CLI checks for skills
$TargetBases = @(
    ".antigravity",
    ".agents",
    ".agent",
    ".jetski"
)

foreach ($skill in $Skills) {
    $SkillSource = Join-Path $ProjectRoot "skill_src\$skill"
    if (-not (Test-Path $SkillSource)) {
        Write-Error "Could not find skill source at: $SkillSource"
        exit 1
    }

    Write-Host "`nLinking skill: $skill" -ForegroundColor Cyan

    foreach ($base in $TargetBases) {
        $SkillsDir = Join-Path $ProjectRoot "$base\skills"
        $LinkPath = Join-Path $SkillsDir $skill

        Write-Host "  Setting up skill directory: $base/skills" -ForegroundColor Yellow

        # Ensure parent folder exists
        if (-not (Test-Path $SkillsDir)) {
            New-Item -ItemType Directory -Path $SkillsDir -Force | Out-Null
            Write-Host "    [+] Created directory: $base/skills" -ForegroundColor Gray
        }

        # If something already exists at the link path, clean it up safely
        if (Test-Path $LinkPath) {
            Write-Host "    [-] Found existing item at $base/skills/$skill. Cleaning up..." -ForegroundColor Magenta
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
            Write-Host "    [✓] Linked skill successfully to $base/skills/$skill" -ForegroundColor Green
        } catch {
            $err = $_.Exception.Message
            Write-Host "    [!] Failed to create junction for $base - $err" -ForegroundColor Red
        }
    }
}

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "  Setup complete! All skill links configured." -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan

