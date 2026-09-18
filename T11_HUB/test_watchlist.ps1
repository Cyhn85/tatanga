Write-Host "=== WATCHLIST + WATERMARK TEST ==="

# Ilk urunu bul
$prods = Invoke-WebRequest -Uri "http://localhost:8501/api/products?limit=3" -UseBasicParsing | ConvertFrom-Json
$firstId = $prods.products[0].id
$firstTitle = $prods.products[0].title
Write-Host "Ilk urun: $firstId - $firstTitle"

# Watchlist'e ekle
$body = @{product_id = $firstId} | ConvertTo-Json
$r = Invoke-WebRequest -Uri "http://localhost:8501/api/watchlist/add" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
Write-Host "Watchlist ekleme: $($r.Content)"

# Watchlist kontrol
$w = Invoke-WebRequest -Uri "http://localhost:8501/api/watchlist" -UseBasicParsing | ConvertFrom-Json
Write-Host "Watchlist items: $($w.count)"

# BG removal + watermark test
Write-Host ""
Write-Host "=== BG REMOVAL + WATERMARK TEST ==="
$bgBody = "{}"
$bgr = Invoke-WebRequest -Uri "http://localhost:8501/api/product/$firstId/remove-bg" -Method POST -UseBasicParsing
Write-Host "BG Removal baslatildi: $($bgr.Content)"

# 15 saniye bekle (rembg model indirmesi + isleme)
Write-Host "15 saniye bekleniyor (gorsel isleniyor)..."
Start-Sleep -Seconds 15

# Islenmis gorsel var mi kontrol
$pDetail = Invoke-WebRequest -Uri "http://localhost:8501/api/product/$firstId" -UseBasicParsing | ConvertFrom-Json
Write-Host "BG Removed: $($pDetail.bg_removed)"
Write-Host "Processed images: $($pDetail.processed_images_json)"

# Desktop output kontrol
$outputDir = "$env:USERPROFILE\Desktop\CSS_Berlin_Output"
if (Test-Path $outputDir) {
    $files = Get-ChildItem $outputDir -Recurse -File
    Write-Host "Desktop output: $($files.Count) dosya"
    foreach ($f in $files) {
        Write-Host "  -> $($f.FullName) ($($f.Length) bytes)"
    }
} else {
    Write-Host "Desktop output klasoru henuz olusturulmadi"
}

Write-Host ""
Write-Host "=== TAMAMLANDI ==="
