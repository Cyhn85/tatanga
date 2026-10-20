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

async function ara() {
  $("sonuc").innerHTML = '<div class="mut">Canli araniyor: Vinted + eBay (insan hizinda, ~20 sn) + KA/Sellpy arsivi...</div>';
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
  const q = d.sorgu || {};
  let h = ttSonucHtml(d, SUNUCU);
  h += `<div style="margin-top:8px;display:flex;gap:6px"><button id="canli">TATANGA'da kazima baslat</button>
        <a href="${esc(SUNUCU)}/arastirmalar" target="_blank"><button>Arastirmalar</button></a></div>`;
  $("sonuc").innerHTML = h;
  $("canli").onclick = async () => {
    const anahtar = ((q.marka || "") + " " + (q.model || q.seri || "")).trim() || $("baslik").value;
    const r = await (await fetch(SUNUCU + "/api/eklenti/canli", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ anahtar }) })).json();
    $("canli").textContent = r.status === "started" ? "Tarama basladi (TATANGA > Urunler)" : (r.error || "hata");
  };
}

document.addEventListener("DOMContentLoaded", async () => {
  const st = document.createElement("style");     // MV3: satir ici <script> yasak; ortak stil buradan eklenir
  st.textContent = ttStil;
  document.head.appendChild(st);
  SUNUCU = await sunucu();
  $("ayar").onclick = () => chrome.runtime.openOptionsPage();
  $("ara").onclick = ara;
  // sag tik menusunden gelindiyse hemen ara; ikona tiklandiysa once okunan bilgiyi goster (kullanici duzeltebilir)
  if (await oku()) ara();
});
