Write-Host "=== TATANGA HUB - ENDPOINT TESTS ==="
Write-Host ""

$tests = @(
    @{Name="Dashboard"; Url="http://localhost:8501/"},
    @{Name="Scraper Page"; Url="http://localhost:8501/scraper"},
    @{Name="Products Page"; Url="http://localhost:8501/products"},
    @{Name="Watchlist Page"; Url="http://localhost:8501/watchlist"},
    @{Name="Monitor Page"; Url="http://localhost:8501/monitor"},
    @{Name="Images Page"; Url="http://localhost:8501/images"},
    @{Name="Settings Page"; Url="http://localhost:8501/settings"},
    @{Name="API Stats"; Url="http://localhost:8501/api/stats"},
    @{Name="API Watchlist"; Url="http://localhost:8501/api/watchlist"},
    @{Name="API Scheduler"; Url="http://localhost:8501/api/scheduler"},
    @{Name="API Products"; Url="http://localhost:8501/api/products"},
    @{Name="API Activity"; Url="http://localhost:8501/api/activity"}
)

foreach ($test in $tests) {
    try {
        $r = Invoke-WebRequest -Uri $test.Url -UseBasicParsing -TimeoutSec 10
        $status = $r.StatusCode
        $len = $r.Content.Length
        Write-Host "[OK] $($test.Name): $status ($len bytes)" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] $($test.Name): $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== CANLI KAZIMA TESTI ==="

# Vinted kazima
$body = '{"keyword":"Nike Jacke","platforms":["vinted"],"max_pages":1}'
$r = Invoke-WebRequest -Uri "http://localhost:8501/api/scrape/start" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
Write-Host "Kazima baslatildi: $($r.Content)"

Start-Sleep -Seconds 8

# Job durumu
$jobData = $r.Content | ConvertFrom-Json
$jobId = $jobData.job_id
$r2 = Invoke-WebRequest -Uri "http://localhost:8501/api/scrape/status/$jobId" -UseBasicParsing
Write-Host "Kazima sonucu: $($r2.Content)"

Write-Host ""
Write-Host "=== TAMAMLANDI ==="
