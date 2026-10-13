# TATANGA ev hatti: sunucudaki Vinted gozlemcisinin isteklerini bu PC'nin ev internetinden cikarir.
# Sunucuda 127.0.0.1:1080'de bir SOCKS kapisi acar (ters SSH tuneli). Baska hicbir sey yapmaz:
#   - bu PC'de Vinted'e giris yapilmaz, hesap kullanilmaz;
#   - tunel yalnizca sunucunun kendi icinden (127.0.0.1) kullanilabilir, internete acik degildir;
#   - PC kapanirsa tunel kapanir, gozlemci bunu 1-5 dk icinde fark edip sunucu hattina doner (mod "tercih").
# Baglanti koparsa 30 sn sonra yeniden dener. Gunluk: <tatanga>\istatistik\ev_hatti.log
#
# Calistirma ve kalici kurulum: KURULUM.md

$Server = "root@195.201.146.224"
$Log = Join-Path (Resolve-Path "$PSScriptRoot\..\..\..").Path "istatistik\ev_hatti.log"

function Write-Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $Log -Value $line -Encoding utf8
}

Write-Log "ev hatti basladi"
while ($true) {
    $start = Get-Date
    # -N: komut calistirma yok; -R 127.0.0.1:1080: sunucuda yalnizca yerel SOCKS kapisi (dinamik ters yonlendirme)
    & ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
        -R 127.0.0.1:1080 $Server 2>&1 | ForEach-Object { Write-Log "ssh: $_" }
    $minutes = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
    Write-Log "tunel kapandi (kod $LASTEXITCODE, $minutes dk acik kaldi); 30 sn sonra yeniden"
    Start-Sleep -Seconds 30
}
