# Synthetic, privacy-safe structural equivalent of the observed 10:44:39 call.
# No FotoMag project paths, Git worktree queries, or customer files.
$ErrorActionPreference = 'Continue'
$repo = Join-Path $env:TEMP 'FM_DC_LAB_SYNTHETIC'
$git = Get-Command git.exe -ErrorAction SilentlyContinue
Write-Output ('LAB_ROOT=' + $repo)
if ($git) {
    Write-Output ('LAB_GIT_PATH=' + $git.Source)
    & $git.Source --version 2>&1 | Select-Object -First 5 | ForEach-Object { 'LAB_GIT=' + [string]$_ }
    Write-Output ('LAB_GIT_EXIT=' + $LASTEXITCODE)
}
$entry = Get-Item -LiteralPath $env:TEMP -ErrorAction SilentlyContinue
if ($entry) { Write-Output ('LAB_DIR_FOUND=' + $entry.PSIsContainer) }
Write-Output 'LAB_SCRIPT_COMPLETE'
