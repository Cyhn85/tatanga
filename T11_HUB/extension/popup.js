// Popup: sayfadan urun bilgisini okur, TATANGA'ya gonderir, sonucu gosterir. Hicbir platforma giris/islem yapmaz.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let SUNUCU = "http://localhost:8501", OKUNAN = {}, TAB = null;

async function sunucu() {
  const { sunucu } = await chrome.storage.sync.get("sunucu");
  return (sunucu || "http://localhost:8501").replace(/\/$/, "");
}

async function oku() {
  [TAB] = await chrome.tabs.query({ active: true, currentWindow: true });
  const { bekleyen } = await chrome.storage.session.get("bekleyen");
  try {
    const [r] = await chrome.scripting.executeScript({ target: { tabId: TAB.id }, files: ["extract.js"] });
    OKUNAN = r.result || {};
  } catch (e) {
    OKUNAN = { url: TAB.url, baslik: TAB.title };      // chrome:// gibi sayfalarda betik calismaz
  }
  let sagTik = false;
  if (bekleyen && bekleyen.tabId === TAB.id && Date.now() - bekleyen.ts < 60000) {
    sagTik = true;
    if (bekleyen.gorsel_url) OKUNAN.gorsel_url = bekleyen.gorsel_url;   // sag tikla secilen gorsel oncelikli
    await chrome.storage.session.remove("bekleyen");
    chrome.action.setBadgeText({ text: "", tabId: TAB.id });
  }
  $("baslik").value = OKUNAN.baslik || "";
  $("marka").value = OKUNAN.marka || "";
  $("fiyat").value = OKUNAN.fiyat || "";
  return sagTik;
}

function satir(r) {
  const vr = r.ayni_varyant === true ? " · <b style='color:#28a745'>ayni varyant</b>" : r.ayni_varyant === false ? " · <span style='color:#ffa500'>baska varyant</span>" : "";
  const uy = r.beden_uyumu === true ? " · <b style='color:#28a745'>beden uyuyor</b>" : r.beden_uyumu === false ? " · <span style='color:#ffa500'>beden farkli</span>" : "";
  return `<div class="satir">${r.gorsel ? `<img src="${esc(r.gorsel)}" referrerpolicy="no-referrer">` : ""}
    <div style="flex:1;min-width:0"><a href="${esc(r.url)}" target="_blank">${esc(r.baslik)}</a>
      <div class="mut"><span class="etiket ${r.eslesme}">${r.eslesme}</span>${esc(r.platform)} ${esc(r.ulke || "")} · ${esc(r.kondisyon || "")}${r.beden ? " · " + esc(r.beden) : ""}${vr}${uy}</div></div>
    <div class="fiyat">${r.toplam_eur.toFixed(2)} €<div class="mut" style="font-weight:400">${esc(r.fiyat)} ${esc(r.para)}</div></div></div>`;
}

async function ara() {
  $("sonuc").innerHTML = '<div class="mut">TATANGA araniyor...</div>';
  const govde = { url: OKUNAN.url, baslik: $("baslik").value, marka: $("marka").value || null, fiyat: $("fiyat").value || null,
                  para: OKUNAN.para || "EUR", gorsel_url: OKUNAN.gorsel_url || null };
  if ($("ekran").checked) {
    try { govde.gorsel = await chrome.tabs.captureVisibleTab(TAB.windowId, { format: "jpeg", quality: 80 }); govde.gorsel_url = null; }
    catch (e) { /* izin yoksa sayfanin gorseliyle devam */ }
  }
  let d;
  try {
    const r = await fetch(SUNUCU + "/api/eklenti/ara", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    d = await r.json();
  } catch (e) {
    $("sonuc").innerHTML = `<div class="kutu" style="border-color:#dc3545">TATANGA'ya ulasilamadi (${esc(SUNUCU)}). TATANGA acik mi?</div>`;
    return;
  }
  if (d.status !== "ok") { $("sonuc").innerHTML = `<div class="kutu">${esc(d.error || "hata")}</div>`; return; }
  const q = d.sorgu, e = d.en_ucuz, s = d.gercek_satis;
  let h = d.arastirma_id ? `<div class="kutu" style="padding:5px 8px">TATANGA listesine kaydedildi (#${d.arastirma_id}) ·
    <a href="${esc(SUNUCU)}/arastirmalar" target="_blank" style="color:#09b1ba">Arastirmalar'da ac</a></div>` : "";
  h += `<div class="mut">Taninan: <b>${esc(q.marka || "?")}</b> ${esc(q.model || q.seri || "")} ${q.beden ? "· beden " + esc(q.beden) : ""} · eslesme: ${esc(d.eslesme_seviyesi)}</div>`;
  if (e) {
    h += `<div class="kutu vurgu"><div class="mut">En ucuz (alis + ucret + kargo)</div>
      <div style="font-size:20px;font-weight:700;color:#09b1ba">${e.toplam_eur.toFixed(2)} €</div>
      <a href="${esc(e.url)}" target="_blank" style="color:#e4e6eb">${esc(e.baslik)}</a>
      <div class="mut">${esc(e.platform)} ${esc(e.ulke || "")} · ${esc(e.eslesme)}${d.tasarruf_eur != null ? ` · bu sayfaya gore <b style="color:${d.tasarruf_eur > 0 ? "#28a745" : "#dc3545"}">${d.tasarruf_eur > 0 ? d.tasarruf_eur.toFixed(2) + " € ucuz" : (-d.tasarruf_eur).toFixed(2) + " € pahali"}</b>` : ""}</div></div>`;
  } else if (d.ayni_varyant_yok) {
    h += `<div class="kutu" style="border-color:#ffa500">Ayni varyant (<b>${esc((q.varyant || []).join(" "))}</b>) arsivde yok.
      Asagidakiler ayni MODELIN baska varyantlari (renk/desen farkli) — fiyat karsilastirmasi icin dikkatli kullan.
      Guncel ilanlar icin "Canli tara".</div>`;
  } else {
    h += `<div class="kutu">Arsivde ayni/benzer ilan bulunamadi.</div>`;
  }
  if (s) h += `<div class="kutu"><b>Gercek Vinted satisi:</b> medyan ${s.medyan} € · alt ceyrek ${s.p25} € · ${s.n} satis (${esc(s.guven)})</div>`;
  const pe = Object.entries(d.platform_en_ucuz || {});
  if (pe.length) h += `<div class="mut">Platform bazinda en ucuz: ${pe.map(([k, v]) => `<a href="${esc(v.url)}" target="_blank" style="color:#9aa4ae">${esc(k)} ${v.toplam_eur.toFixed(0)} €</a>`).join(" · ")}</div>`;
  h += (d.sonuclar || []).slice(0, 20).map(satir).join("");
  h += `<div class="mut" style="margin-top:8px">${esc(d.not)} ${d.gorsel_not ? "· " + esc(d.gorsel_not) : ""}
        · elenen: cocuk ${d.elenen ? d.elenen.cocuk : 0}, dusuk kondisyon ${d.elenen ? d.elenen.kondisyon : 0}</div>
        <div style="margin-top:8px;display:flex;gap:6px"><button id="canli">Canli tara (guncel ilanlar)</button>
        <a href="${esc(SUNUCU)}/products?ara=${encodeURIComponent((q.marka || "") + " " + (q.model || ""))}" target="_blank"><button>TATANGA'da ac</button></a></div>`;
  $("sonuc").innerHTML = h;
  $("canli").onclick = async () => {
    const anahtar = ((q.marka || "") + " " + (q.model || q.seri || "")).trim() || $("baslik").value;
    const r = await (await fetch(SUNUCU + "/api/eklenti/canli", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ anahtar }) })).json();
    $("canli").textContent = r.status === "started" ? "Tarama basladi (TATANGA > Urunler)" : (r.error || "hata");
  };
}

document.addEventListener("DOMContentLoaded", async () => {
  SUNUCU = await sunucu();
  $("ayar").onclick = () => chrome.runtime.openOptionsPage();
  $("ara").onclick = ara;
  // sag tik menusunden gelindiyse hemen ara; ikona tiklandiysa once okunan bilgiyi goster (kullanici duzeltebilir)
  if (await oku()) ara();
});
