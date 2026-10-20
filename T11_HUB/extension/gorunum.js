// En ucuzu bul sonuc gorunumu - TEK KAYNAK: hem eklenti penceresi hem TATANGA "Arastirmalar" ayni fonksiyonu kullanir.
// d: /api/eklenti/ara cevabi (ya da kayitli arastirmadan ayni bicimde kurulmus nesne). sunucu: TATANGA kok adresi.
(function (g) {
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function satir(r) {
    const vr = r.ayni_varyant === true ? " · <b style='color:#28a745'>ayni varyant</b>" : r.ayni_varyant === false ? " · <span style='color:#ffa500'>baska varyant</span>" : "";
    const uy = r.beden_uyumu === true ? " · <b style='color:#28a745'>beden uyuyor</b>" : r.beden_uyumu === false ? " · <span style='color:#ffa500'>beden farkli</span>" : "";
    const kay = r.kaynak === "canli" ? "<span class='tt-etiket tt-canli'>canli</span>" : "<span class='tt-etiket tt-arsiv'>arsiv</span>";
    return `<div class="tt-satir">${r.gorsel ? `<img src="${esc(r.gorsel)}" referrerpolicy="no-referrer">` : ""}
      <div style="flex:1;min-width:0"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.baslik)}</a>
        <div class="tt-mut"><span class="tt-etiket tt-${esc(r.eslesme)}">${esc(r.eslesme)}</span>${kay}${esc(r.platform)} ${esc(r.ulke || "")} · ${esc(r.kondisyon || "")}${r.beden ? " · " + esc(r.beden) : ""}${vr}${uy}</div></div>
      <div class="tt-fiyat">${Number(r.toplam_eur).toFixed(2)} €<div class="tt-mut" style="font-weight:400">${esc(r.fiyat)} ${esc(r.para)}</div></div></div>`;
  }

  g.ttSonucHtml = function (d, sunucu) {
    const q = d.sorgu || {}, e = d.en_ucuz, s = d.gercek_satis;
    let h = d.arastirma_id ? `<div class="tt-kutu" style="padding:5px 8px">TATANGA listesine kaydedildi (#${d.arastirma_id}) ·
      <a href="${esc(sunucu)}/arastirmalar" target="_blank" class="tt-link">Arastirmalar'da ac</a></div>` : "";
    h += `<div class="tt-mut">Taninan: <b>${esc(q.marka || "?")}</b> ${esc(q.model || q.seri || "")} ${q.beden ? "· beden " + esc(q.beden) : ""}${(q.varyant || []).length ? " · varyant " + esc(q.varyant.join(" ")) : ""} · eslesme: ${esc(d.eslesme_seviyesi)}</div>`;
    if (e) {
      h += `<div class="tt-kutu tt-vurgu"><div class="tt-mut">En ucuz (alis + ucret + kargo)</div>
        <div class="tt-buyuk">${Number(e.toplam_eur).toFixed(2)} €</div>
        <a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.baslik)}</a>
        <div class="tt-mut">${esc(e.platform)} ${esc(e.ulke || "")} · ${esc(e.eslesme)} · ${e.kaynak === "canli" ? "canli" : "arsiv"}${d.tasarruf_eur != null ? ` · bu sayfaya gore <b style="color:${d.tasarruf_eur > 0 ? "#28a745" : "#dc3545"}">${d.tasarruf_eur > 0 ? d.tasarruf_eur.toFixed(2) + " € ucuz" : (-d.tasarruf_eur).toFixed(2) + " € pahali"}</b>` : ""}</div></div>`;
    } else if (d.ayni_varyant_yok) {
      h += `<div class="tt-kutu" style="border-color:#ffa500">Ayni varyant (<b>${esc((q.varyant || []).join(" "))}</b>) bulunamadi.
        Asagidakiler ayni MODELIN baska varyantlari (renk/desen farkli) — fiyat karsilastirmasi icin dikkatli kullan.</div>`;
    } else {
      h += `<div class="tt-kutu">Ayni/benzer ilan bulunamadi.</div>`;
    }
    if (s) h += `<div class="tt-kutu"><b>Gercek Vinted satisi:</b> medyan ${s.medyan} € · alt ceyrek ${s.p25} € · ${s.n} satis (${esc(s.guven)})</div>`;
    const pe = Object.entries(d.platform_en_ucuz || {});
    if (pe.length) h += `<div class="tt-mut">Platform bazinda en ucuz: ${pe.map(([k, v]) => `<a href="${esc(v.url)}" target="_blank" rel="noopener" class="tt-mutlink">${esc(k)} ${Number(v.toplam_eur).toFixed(0)} €</a>`).join(" · ")}</div>`;
    const kk = d.kaynaklar || {};
    if (Object.keys(kk).length) h += `<div class="tt-mut">Kaynak: ${Object.entries(kk).map(([k, v]) => esc(k) + " " + esc(v)).join(" · ")}</div>`;
    h += (d.sonuclar || []).slice(0, 40).map(satir).join("");
    h += `<div class="tt-mut" style="margin-top:8px">${esc(d.not || "")} ${d.gorsel_not ? "· " + esc(d.gorsel_not) : ""}
          · elenen: cocuk ${d.elenen ? d.elenen.cocuk : 0}, dusuk kondisyon ${d.elenen ? d.elenen.kondisyon : 0}, yem fiyat ${d.elenen ? d.elenen.yem_fiyat : 0}, urun degil ${d.elenen ? (d.elenen.urun_degil || 0) : 0}</div>`;
    return h;
  };

  g.ttStil = `
  .tt-mut{color:#9aa4ae;font-size:12px}.tt-kutu{border:1px solid #2b3038;border-radius:8px;padding:8px;margin:8px 0}
  .tt-vurgu{border-color:#09b1ba;background:rgba(9,177,186,.08)}.tt-buyuk{font-size:20px;font-weight:700;color:#09b1ba}
  .tt-satir{display:flex;gap:8px;padding:6px 0;border-bottom:1px solid #2b3038}
  .tt-satir img{width:46px;height:56px;object-fit:cover;border-radius:4px;background:#222;flex:none}
  .tt-satir a,.tt-kutu a{color:#e4e6eb;text-decoration:none}.tt-fiyat{font-weight:700;white-space:nowrap}
  .tt-etiket{font-size:10px;border-radius:99px;padding:0 6px;border:1px solid #2b3038;margin-right:4px}
  .tt-model{color:#28a745;border-color:#28a745}.tt-gorsel{color:#09b1ba;border-color:#09b1ba}.tt-kelime{color:#ffa500;border-color:#ffa500}
  .tt-canli{color:#e4e6eb;border-color:#6f42c1;background:rgba(111,66,193,.25)}.tt-arsiv{color:#9aa4ae}
  .tt-link{color:#09b1ba}.tt-mutlink{color:#9aa4ae}`;
})(typeof window !== "undefined" ? window : self);
