#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay.de API Uploader
Trading API kullanarak ürün yükleme
"""

import sys
import time
import json
import base64
import re
import requests
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import EBAY

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
TOKEN_FILE = TEMP_DIR / "ebay_token.json"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # Handle encoding issues for Windows console
    try:
        print(f"[{timestamp}] {message}", flush=True)
    except UnicodeEncodeError:
        safe_msg = message.encode('ascii', 'replace').decode('ascii')
        print(f"[{timestamp}] {safe_msg}", flush=True)

class EbayUploader:
    """eBay.de API ile ürün yükleme"""

    def __init__(self, sandbox=False):
        if sandbox:
            self.api_config = EBAY['api']['sandbox']
            self.api_url = "https://api.sandbox.ebay.com/ws/api.dll"
            self.auth_url = "https://auth.sandbox.ebay.com/oauth2/authorize"
            self.token_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
            self.site_id = "77"  # Germany
        else:
            self.api_config = EBAY['api']['production']
            self.api_url = "https://api.ebay.com/ws/api.dll"
            self.auth_url = "https://auth.ebay.com/oauth2/authorize"
            self.token_url = "https://api.ebay.com/identity/v1/oauth2/token"
            self.site_id = "77"  # Germany

        self.app_id = self.api_config['app_id']
        self.dev_id = self.api_config['dev_id']
        self.cert_id = self.api_config['cert_id']
        self.user_token = None
        self.redirect_uri = "CeyhunSa-CSSBerli-PRD-60ddfec-xxqatvcsu"  # RuName

        # Token'ı yükle
        self.load_token()

    def save_token(self, token_data):
        """Token'ı kaydet"""
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)
        log(f"Token kaydedildi: {TOKEN_FILE}")

    def load_token(self):
        """Token'i yukle"""
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
                self.user_token = token_data.get('access_token')

                # Token suresi dolmus mu kontrol et
                expires_at = token_data.get('expires_at', 0)
                if time.time() > expires_at:
                    log("Token suresi dolmus, yenileme gerekli")
                    # Refresh token varsa yenile
                    refresh_token = token_data.get('refresh_token')
                    if refresh_token:
                        self.refresh_access_token(refresh_token)
                else:
                    log("Mevcut token yuklendi")
        else:
            log("Token dosyasi bulunamadi")

    def get_authorization_url(self):
        """OAuth yetkilendirme URL'i oluştur"""
        scopes = [
            "https://api.ebay.com/oauth/api_scope",
            "https://api.ebay.com/oauth/api_scope/sell.inventory",
            "https://api.ebay.com/oauth/api_scope/sell.marketing",
            "https://api.ebay.com/oauth/api_scope/sell.account",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment"
        ]

        params = {
            "client_id": self.app_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "prompt": "login"
        }

        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(self, auth_code):
        """Authorization code'u access token'a çevir"""
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.redirect_uri
        }

        response = requests.post(self.token_url, headers=headers, data=data)

        if response.status_code == 200:
            token_data = response.json()
            # Süre bilgisi ekle
            token_data['expires_at'] = time.time() + token_data.get('expires_in', 7200)
            self.user_token = token_data['access_token']
            self.save_token(token_data)
            return True
        else:
            log(f"Token alma hatası: {response.status_code}")
            log(response.text)
            return False

    def refresh_access_token(self, refresh_token):
        """Access token'ı yenile"""
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        response = requests.post(self.token_url, headers=headers, data=data)

        if response.status_code == 200:
            token_data = response.json()
            token_data['expires_at'] = time.time() + token_data.get('expires_in', 7200)
            token_data['refresh_token'] = refresh_token  # Refresh token'ı koru
            self.user_token = token_data['access_token']
            self.save_token(token_data)
            log("Token yenilendi")
            return True
        else:
            log(f"Token yenileme hatası: {response.status_code}")
            return False

    def call_trading_api(self, call_name, request_xml):
        """Trading API call"""
        if not self.user_token:
            log("User token yok! Önce yetkilendirme yapın.")
            return None

        headers = {
            "X-EBAY-API-SITEID": self.site_id,
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1155",
            "X-EBAY-API-CALL-NAME": call_name,
            "X-EBAY-API-IAF-TOKEN": self.user_token,
            "Content-Type": "text/xml"
        }

        response = requests.post(self.api_url, headers=headers, data=request_xml.encode('utf-8'))
        return response.text

    def get_ebay_official_time(self):
        """eBay sunucu zamanını al (API test)"""
        xml = """<?xml version="1.0" encoding="utf-8"?>
<GeteBayOfficialTimeRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
</GeteBayOfficialTimeRequest>""".format(token=self.user_token)

        # Bu API için farklı auth kullan
        headers = {
            "X-EBAY-API-SITEID": self.site_id,
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1155",
            "X-EBAY-API-CALL-NAME": "GeteBayOfficialTime",
            "X-EBAY-API-APP-NAME": self.app_id,
            "X-EBAY-API-DEV-NAME": self.dev_id,
            "X-EBAY-API-CERT-NAME": self.cert_id,
            "Content-Type": "text/xml"
        }

        response = requests.post(self.api_url, headers=headers, data=xml.encode('utf-8'))
        return response.text

    def upload_picture(self, image_path):
        """Yerel resmi eBay EPS'e yükle ve URL al"""
        if not self.user_token:
            return None

        # Resim dosyasını oku ve base64 encode et
        img_path = Path(image_path)
        if not img_path.exists():
            log(f"Resim bulunamadi: {image_path}")
            return None

        with open(img_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode()

        # Dosya uzantısından format belirle
        ext = img_path.suffix.lower()
        pic_format = {'.jpg': 'JPG', '.jpeg': 'JPG', '.png': 'PNG', '.gif': 'GIF'}.get(ext, 'JPG')

        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<UploadSiteHostedPicturesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{self.user_token}</eBayAuthToken>
    </RequesterCredentials>
    <PictureName>{img_path.name}</PictureName>
    <PictureData>{image_data}</PictureData>
    <PictureFormat>{pic_format}</PictureFormat>
</UploadSiteHostedPicturesRequest>"""

        response = self.call_trading_api("UploadSiteHostedPictures", xml)

        if response:
            # URL'i çıkar
            url_match = re.search(r'<FullURL>(.*?)</FullURL>', response)
            if url_match:
                picture_url = url_match.group(1)
                log(f"Resim yuklendi: {img_path.name}")
                return picture_url
            else:
                ack_match = re.search(r'<Ack>(.*?)</Ack>', response)
                log(f"Resim yukleme basarisiz: {ack_match.group(1) if ack_match else 'Unknown'}")
                errors = re.findall(r'<ShortMessage>(.*?)</ShortMessage>', response)
                for err in errors:
                    log(f"  - {err}")

        return None

    def create_seo_description(self, product):
        """SEO optimized HTML açıklama oluştur"""
        # XML için & karakterini escape et
        def escape_xml(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        brand = escape_xml(product.get('brand', ''))
        title = escape_xml(product.get('title', ''))
        size = escape_xml(product.get('size', ''))
        color = escape_xml(product.get('color', ''))
        condition = escape_xml(product.get('condition', 'Gebraucht'))
        original_desc = escape_xml(product.get('description', ''))

        # Condition açıklaması
        condition_text = {
            'Neu': 'Neu und ungetragen mit Etikett.',
            'Neu mit Etikett': 'Neu und ungetragen mit Etikett.',
            'Neu ohne Etikett': 'Neu und ungetragen, ohne Etikett.',
            'Sehr gut': 'Sehr gut erhalten, keine sichtbaren Maengel.',
            'Gut': 'Gut erhalten, minimale Gebrauchsspuren moeglich.',
            'Gebraucht': 'Gebraucht, normale Gebrauchsspuren.'
        }.get(condition, 'Gebraucht.')

        html = f"""<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
<h2 style="color: #333; border-bottom: 2px solid #e74c3c; padding-bottom: 10px;">{brand} {title}</h2>

<table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
<tr style="background: #f8f9fa;">
    <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Marke</td>
    <td style="padding: 10px; border: 1px solid #dee2e6;">{brand}</td>
</tr>
<tr>
    <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Groesse</td>
    <td style="padding: 10px; border: 1px solid #dee2e6;">{size}</td>
</tr>
<tr style="background: #f8f9fa;">
    <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Farbe</td>
    <td style="padding: 10px; border: 1px solid #dee2e6;">{color}</td>
</tr>
<tr>
    <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Zustand</td>
    <td style="padding: 10px; border: 1px solid #dee2e6;">{condition}</td>
</tr>
</table>

<div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
<h3 style="margin-top: 0; color: #333;">Beschreibung</h3>
<p>{condition_text}</p>
<p>{original_desc}</p>
</div>

<div style="background: #e8f4f8; padding: 15px; border-radius: 5px; margin: 20px 0;">
<h3 style="margin-top: 0; color: #333;">Versand & Rueckgabe</h3>
<ul style="margin: 0; padding-left: 20px;">
<li>Versand innerhalb von 1-3 Werktagen nach Zahlungseingang</li>
<li>30 Tage Rueckgaberecht</li>
<li>Tierfreier Nichtraucherhaushalt</li>
</ul>
</div>

<p style="color: #666; font-size: 12px; text-align: center; margin-top: 30px;">
Bei Fragen stehe ich Ihnen gerne zur Verfuegung!
</p>
</div>"""

        return html

    def upload_product(self, product):
        """Ürün yükle"""
        if not self.user_token:
            log("Token yok! Önce authorize edin.")
            return False

        # XML icin & karakterini escape et
        def escape_xml(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        title = escape_xml(product.get('seo', {}).get('ebay', {}).get('title', product.get('title', ''))[:80])
        description = product.get('seo', {}).get('ebay', {}).get('description', product.get('description', ''))
        price = product.get('platform_prices', {}).get('ebay', product.get('price', 0))
        images = product.get('local_images', [])
        category = product.get('ebay_category_id', '11450')  # Default: Herrenbekleidung
        brand = escape_xml(product.get('brand', 'Unbranded'))
        condition = product.get('condition', 'Gebraucht')
        size = escape_xml(product.get('size', 'L'))
        color = escape_xml(product.get('color', 'Blau'))
        department = product.get('department', 'Herren')

        # Condition ID map (fuer Bekleidung/Fashion)
        # Kategorie 15687 (T-Shirts) akzeptiert nur: 1000, 1500, 3000
        condition_map = {
            'Neu': '1000',
            'Neu mit Etikett': '1000',
            'Neu ohne Etikett': '1500',
            'Neu mit Fehlern': '1500',
            'Gebraucht': '3000',
            'Sehr gut': '3000',  # Fuer Bekleidung = Gebraucht
            'Gut': '3000',
            'Akzeptabel': '3000'
        }
        condition_id = condition_map.get(condition, '3000')

        # SEO açıklama oluştur (eğer seo'da ebay description yoksa)
        if not product.get('seo', {}).get('ebay', {}).get('description'):
            description = self.create_seo_description(product)

        # Resimleri yükle
        picture_urls = ""
        uploaded_count = 0
        for img_path in images[:12]:  # Max 12 resim
            if img_path.startswith('http'):
                # Harici URL
                picture_urls += f"<PictureURL>{img_path}</PictureURL>"
                uploaded_count += 1
            elif Path(img_path).exists():
                # Yerel dosya - eBay EPS'e yükle
                ebay_url = self.upload_picture(img_path)
                if ebay_url:
                    picture_urls += f"<PictureURL>{ebay_url}</PictureURL>"
                    uploaded_count += 1

        if uploaded_count == 0:
            log("UYARI: Hic resim yuklenemedi!")

        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{self.user_token}</eBayAuthToken>
    </RequesterCredentials>
    <ErrorLanguage>de_DE</ErrorLanguage>
    <WarningLevel>High</WarningLevel>
    <Item>
        <Title><![CDATA[{title}]]></Title>
        <Description><![CDATA[{description}]]></Description>
        <PrimaryCategory>
            <CategoryID>{category}</CategoryID>
        </PrimaryCategory>
        <StartPrice currencyID="EUR">{price}</StartPrice>
        <ConditionID>{condition_id}</ConditionID>
        <Country>DE</Country>
        <Currency>EUR</Currency>
        <DispatchTimeMax>3</DispatchTimeMax>
        <ListingDuration>GTC</ListingDuration>
        <ListingType>FixedPriceItem</ListingType>
        <PictureDetails>
            {picture_urls}
        </PictureDetails>
        <PostalCode>10115</PostalCode>
        <Quantity>1</Quantity>
        <ReturnPolicy>
            <ReturnsAcceptedOption>ReturnsAccepted</ReturnsAcceptedOption>
            <ReturnsWithinOption>Days_30</ReturnsWithinOption>
            <Description>30 Tage Rückgaberecht. Bitte kontaktieren Sie mich vor der Rücksendung.</Description>
        </ReturnPolicy>
        <ShippingDetails>
            <ShippingType>Flat</ShippingType>
            <ShippingServiceOptions>
                <ShippingServicePriority>1</ShippingServicePriority>
                <ShippingService>DE_DHLPaket</ShippingService>
                <ShippingServiceCost currencyID="EUR">4.99</ShippingServiceCost>
            </ShippingServiceOptions>
        </ShippingDetails>
        <Site>Germany</Site>
        <ItemSpecifics>
            <NameValueList>
                <Name>Marke</Name>
                <Value>{brand}</Value>
            </NameValueList>
            <NameValueList>
                <Name>Größe</Name>
                <Value>{size}</Value>
            </NameValueList>
            <NameValueList>
                <Name>Farbe</Name>
                <Value>{color}</Value>
            </NameValueList>
            <NameValueList>
                <Name>Abteilung</Name>
                <Value>{department}</Value>
            </NameValueList>
            <NameValueList>
                <Name>Stil</Name>
                <Value>Freizeit</Value>
            </NameValueList>
            <NameValueList>
                <Name>Produktart</Name>
                <Value>Jacke</Value>
            </NameValueList>
            <NameValueList>
                <Name>Außenmaterial</Name>
                <Value>Baumwolle</Value>
            </NameValueList>
            <NameValueList>
                <Name>Schrittlänge</Name>
                <Value>Normale Größe</Value>
            </NameValueList>
        </ItemSpecifics>
    </Item>
</AddItemRequest>"""

        log(f"Ürün yükleniyor: {title}")

        response = self.call_trading_api("AddItem", xml)

        if response:
            # Ack durumunu kontrol et
            ack_match = re.search(r'<Ack>(.*?)</Ack>', response)
            ack_status = ack_match.group(1) if ack_match else "Unknown"
            log(f"API Response: Ack={ack_status}")

            if ack_status in ['Success', 'Warning']:
                # ItemID'yi çıkar
                item_id_match = re.search(r'<ItemID>(\d+)</ItemID>', response)
                if item_id_match:
                    item_id = item_id_match.group(1)
                    log(f"BAŞARILI! ItemID: {item_id}")
                    log(f"URL: https://www.ebay.de/itm/{item_id}")

                    # Uyarıları göster
                    if ack_status == 'Warning':
                        warnings = re.findall(r'<ShortMessage>(.*?)</ShortMessage>', response, re.DOTALL)
                        for w in warnings:
                            log(f"Uyarı: {w}")

                    return item_id
                else:
                    log(f"Ack={ack_status} ama ItemID bulunamadı")
                    log(response[:800])
            else:
                # Tum hata mesajlarini cikar
                errors = re.findall(r'<ShortMessage>(.*?)</ShortMessage>', response, re.DOTALL)
                long_errors = re.findall(r'<LongMessage>(.*?)</LongMessage>', response, re.DOTALL)
                error_codes = re.findall(r'<ErrorCode>(\d+)</ErrorCode>', response)

                if errors:
                    for i, err in enumerate(errors):
                        code = error_codes[i] if i < len(error_codes) else "?"
                        log(f"Hata {code}: {err}")
                    if long_errors:
                        for lerr in long_errors[:3]:
                            log(f"Detay: {lerr[:200]}")
                else:
                    log("Yukleme basarisiz")
                    log(response[:1000])

        return None

    def verify_add_item(self, product):
        """Ürün yüklemesini test et (gerçek yükleme yapmaz)"""
        # VerifyAddItem aynı XML'i kullanır ama yüklemez
        pass

def authorize_flow():
    """OAuth yetkilendirme flow'u"""
    uploader = EbayUploader(sandbox=False)

    print("=" * 60)
    print("EBAY OAUTH YETKILENDIRME")
    print("=" * 60)
    print()

    # Yetkilendirme URL'i olustur
    auth_url = uploader.get_authorization_url()

    print("Asagidaki URL'i tarayicida acin ve eBay hesabinizla giris yapin:")
    print()
    print(auth_url)
    print()

    # Tarayicida ac
    webbrowser.open(auth_url)

    print("Giris yaptiktan sonra yonlendirildiginiz URL'deki 'code' parametresini girin:")
    print("(URL'de ?code=XXXX seklinde gorunur)")
    print()

    auth_code = input("Authorization Code: ").strip()

    if auth_code:
        if uploader.exchange_code_for_token(auth_code):
            print()
            print("TOKEN BASARIYLA ALINDI!")
            print("Artik urun yukleyebilirsiniz.")
        else:
            print("Token alma basarisiz!")
    else:
        print("Kod girilmedi!")

def test_api():
    """API baglantisini test et"""
    uploader = EbayUploader(sandbox=False)

    print("=" * 60)
    print("EBAY API TEST")
    print("=" * 60)

    if not uploader.user_token:
        print("Token yok! Once 'authorize' calistirin.")
        return

    print("eBay sunucu zamani aliniyor...")
    response = uploader.get_ebay_official_time()
    print(response[:500])

def test_upload():
    """Test urun yukle"""
    uploader = EbayUploader(sandbox=False)

    print("=" * 60)
    print("EBAY TEST UPLOAD")
    print("=" * 60)

    if not uploader.user_token:
        print("Token yok! Once 'authorize' calistirin.")
        return

    # Test ürün
    test_product = {
        'title': 'Test Herren T-Shirt Größe L',
        'description': 'Herren T-Shirt in sehr gutem Zustand. Größe L, Farbe Blau. Versand möglich.',
        'seo': {
            'ebay': {
                'title': 'Tommy Hilfiger Herren T-Shirt Größe L Blau',
                'description': '<p>Biete hier ein sehr gut erhaltenes Tommy Hilfiger T-Shirt an.</p><ul><li>Größe: L</li><li>Farbe: Blau</li><li>Zustand: Sehr gut</li></ul>'
            }
        },
        'platform_prices': {
            'ebay': 29.99
        },
        'ebay_category_id': '15687',  # Herrenbekleidung > T-Shirts
        'brand': 'Tommy Hilfiger',
        'condition': 'Sehr gut',
        'size': 'L',
        'color': 'Blau',
        'department': 'Herren',
        'local_images': [
            'https://i.ebayimg.com/images/g/placeholder/s-l1600.jpg'  # Test image
        ]
    }

    item_id = uploader.upload_product(test_product)

    if item_id:
        print(f"\nUrun basariyla yuklendi!")
        print(f"https://www.ebay.de/itm/{item_id}")
    else:
        print("\nYukleme basarisiz!")

def main():
    """Ana menu"""
    print("=" * 60)
    print("EBAY.DE UPLOADER")
    print("=" * 60)
    print()
    print("1. OAuth Yetkilendirme")
    print("2. API Test")
    print("3. Test Urun Yukle")
    print("0. Cikis")
    print()

    choice = input("Seciminiz: ").strip()

    if choice == "1":
        authorize_flow()
    elif choice == "2":
        test_api()
    elif choice == "3":
        test_upload()
    else:
        print("Çıkış...")

if __name__ == "__main__":
    main()
