// Sag tik menusu: bir gorsele ya da sayfaya "TATANGA'da en ucuzunu bul". Secilen gorsel kullanilir.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "tt-gorsel", title: "TATANGA'da en ucuzunu bul (bu gorselle)", contexts: ["image"] });
  chrome.contextMenus.create({ id: "tt-sayfa", title: "TATANGA'da en ucuzunu bul (bu sayfa)", contexts: ["page", "link"] });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  // sonucu popup gosterir: istegi saklayip popup'i aciyoruz
  await chrome.storage.session.set({ bekleyen: { tabId: tab.id, gorsel_url: info.srcUrl || null, ts: Date.now() } });
  try { await chrome.action.openPopup(); }
  catch (e) { chrome.action.setBadgeText({ text: "1", tabId: tab.id }); }  // openPopup desteklenmiyorsa ikon uzerinde isaret
});
