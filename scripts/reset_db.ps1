# Drop all tables and reapply schema.sql. Postgres container must already be up.

. "$PSScriptRoot\_common.ps1"

Import-DotEnv
$py = Get-VenvPython

Wait-Postgres
Write-Host "[reset_db] dropping and recreating schema..." -ForegroundColor Cyan
& $py (Join-Path $RepoRoot 'services\api\db\migrate.py') --reset
if ($LASTEXITCODE -ne 0) { throw "migration reset failed (exit $LASTEXITCODE)" }
Write-Host "[reset_db] done." -ForegroundColor Green
