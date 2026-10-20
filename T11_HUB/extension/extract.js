// Sayfadaki urun bilgisini okur (sayfaya enjekte edilir, sonucu dondurur). Hicbir sey degistirmez/gondermez.
// Kaynak sirasi: JSON-LD Product -> Open Graph / product meta -> itemprop -> sayfa basligi + en buyuk gorsel.
(() => {
  const meta = (sel) => { const m = document.querySelector(sel); return m ? (m.getAttribute("content") || "").trim() : ""; };
  let ld = null;
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const walk = (o) => {
        if (!o || ld) return;
        if (Array.isArray(o)) return o.forEach(walk);
        const t = o["@type"];
        if (t === "Product" || (Array.isArray(t) && t.includes("Product"))) { ld = o; return; }
        if (o["@graph"]) walk(o["@graph"]);
      };
      walk(JSON.parse(s.textContent));
    } catch (e) { /* bozuk JSON-LD: atla */ }
    if (ld) break;
  }
  const offer = ld && (Array.isArray(ld.offers) ? ld.offers[0] : ld.offers);
  const brand = ld && (typeof ld.brand === "string" ? ld.brand : ld.brand && ld.brand.name);
  let image = ld && (Array.isArray(ld.image) ? ld.image[0] : (ld.image && ld.image.url) || ld.image);
  image = image || meta('meta[property="og:image"]') || meta('meta[name="twitter:image"]');
  if (!image) {
    let best = null, area = 0;
    for (const img of document.images) {
      const a = img.naturalWidth * img.naturalHeight;
      if (a > area && img.naturalWidth >= 200) { area = a; best = img.currentSrc || img.src; }
    }
    image = best;
  }
  const price = (offer && (offer.price || offer.lowPrice)) || meta('meta[property="product:price:amount"]') ||
                meta('meta[property="og:price:amount"]') || meta('[itemprop="price"]') ||
                ((document.querySelector('[itemprop="price"]') || {}).textContent || "").replace(/[^\d.,]/g, "");
  const currency = (offer && offer.priceCurrency) || meta('meta[property="product:price:currency"]') ||
                   meta('meta[property="og:price:currency"]') || "EUR";
  const title = (ld && ld.name) || meta('meta[property="og:title"]') || document.title;
  return { url: location.href, baslik: (title || "").slice(0, 300), marka: brand || meta('meta[property="product:brand"]') || null,
           fiyat: price ? String(price) : null, para: currency, gorsel_url: image || null };
})();
