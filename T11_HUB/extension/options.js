document.addEventListener("DOMContentLoaded", async () => {
  const { sunucu } = await chrome.storage.sync.get("sunucu");
  document.getElementById("sunucu").value = sunucu || "http://localhost:8501";
  document.getElementById("kaydet").onclick = async () => {
    const v = document.getElementById("sunucu").value.trim().replace(/\/$/, "") || "http://localhost:8501";
    if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(v)) {
      const ok = await chrome.permissions.request({ origins: [v + "/*"] });   // farkli adres icin izin iste
      if (!ok) { document.getElementById("durum").textContent = "Izin verilmedi"; return; }
    }
    await chrome.storage.sync.set({ sunucu: v });
    document.getElementById("durum").textContent = "Kaydedildi";
  };
});
