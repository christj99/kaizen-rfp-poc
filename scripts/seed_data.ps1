# Seed the demo DB to a known state from committed fixtures.
#
# Sequence:
#   1. Wait for Postgres
#   2. If past_proposals empty: run the RAG indexer (~10s)
#   3. Load fixtures: TRUNCATE user tables + INSERT from sample_data/seed/*.json

. "$PSScriptRoot\_common.ps1"

# Native python/docker progress goes to stderr; keep that from aborting the script.
$ErrorActionPreference = 'Continue'

Import-DotEnv
$py = Get-VenvPython

Wait-Postgres

Write-Host "[seed_data] checking past-proposal corpus..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    $ppCount = (& $py -c "from services.api.db.client import db_cursor
with db_cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM past_proposals')
    print(cur.fetchone()[0])") | Select-Object -Last 1
    [int]::TryParse($ppCount.Trim(), [ref]$null) | Out-Null
    $count = 0
    [int]::TryParse($ppCount.Trim(), [ref]$count) | Out-Null

    if ($count -eq 0) {
        Write-Host "[seed_data] past_proposals empty - running indexer..." -ForegroundColor Cyan
        & $py -m services.api.rag.indexer
        if ($LASTEXITCODE -ne 0) { throw "indexer failed (exit $LASTEXITCODE)" }
    } else {
        Write-Host "[seed_data] past_proposals already populated ($count proposals); skipping reindex." -ForegroundColor Cyan
    }

    Write-Host "[seed_data] loading fixtures..." -ForegroundColor Cyan
    & $py -m scripts.load_seed_fixtures
    if ($LASTEXITCODE -ne 0) { throw "fixture load failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Write-Host "[seed_data] done." -ForegroundColor Green
