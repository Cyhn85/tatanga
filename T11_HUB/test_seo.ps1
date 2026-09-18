Write-Host "=== SEO CONTENT GENERATION TEST ==="

# Sunucu kontrol
$r = Invoke-WebRequest -Uri "http://localhost:8501/api/stats" -UseBasicParsing
Write-Host "Sunucu: OK"

# Ilk urunu bul
$prods = Invoke-WebRequest -Uri "http://localhost:8501/api/products?limit=1" -UseBasicParsing | ConvertFrom-Json
$firstId = $prods.products[0].id
$firstTitle = $prods.products[0].title
Write-Host "Urun: $firstId - $firstTitle"

# SEO uret - cssberlin icin
$body = '{"platform":"cssberlin"}'
$seoResp = Invoke-WebRequest -Uri "http://localhost:8501/api/product/$firstId/generate-seo" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
Write-Host "SEO baslatildi: $($seoResp.Content)"

# 10 saniye bekle (Groq API cagri)
Write-Host "10 saniye bekleniyor (AI icerik uretiyor)..."
Start-Sleep -Seconds 10

# Sonucu kontrol
$pDetail = Invoke-WebRequest -Uri "http://localhost:8501/api/product/$firstId" -UseBasicParsing | ConvertFrom-Json
Write-Host ""
Write-Host "SEO Baslik: $($pDetail.seo_title)"
Write-Host "SEO Aciklama: $($pDetail.seo_description)"
Write-Host "SEO Keywords: $($pDetail.seo_keywords)"
Write-Host "SEO Tags: $($pDetail.seo_tags)"

Write-Host ""
Write-Host "=== TAMAMLANDI ==="
