# Re-index the sample past proposals into Postgres + pgvector.
# Safe to run multiple times — indexer wipes past_proposals first.

. "$PSScriptRoot\_common.ps1"

Import-DotEnv
$py = Get-VenvPython

Wait-Postgres
Write-Host "[seed_data] re-indexing past proposals..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $py -m services.api.rag.indexer
    if ($LASTEXITCODE -ne 0) { throw "indexer failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}
Write-Host "[seed_data] done." -ForegroundColor Green
