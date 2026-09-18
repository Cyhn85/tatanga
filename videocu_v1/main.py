"""
VIDEOCU v1 - Main Application
Modern PyQt5 GUI ile tam özellikli YouTube otomasyon sistemi
"""

import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTextEdit, QProgressBar,
    QGroupBox, QListWidget, QTabWidget, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from pathlib import Path
import logging

import config
from database import Database
from modules.trend_analyzer import TrendAnalyzer, YOUTUBE_CATEGORIES_DE
from modules.social_trend_analyzer import SocialTrendAnalyzer
from modules.cross_analyzer import CrossAnalyzer
import asyncio

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_DIR / "videocu.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class VideocuMainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.trend_analyzer = TrendAnalyzer(youtube_api_key=config.YOUTUBE_API_KEY)
        self.social_analyzer = SocialTrendAnalyzer(
            tiktok_ms_token=config.MS_TOKEN,
            instagram_username=config.INSTAGRAM_USERNAME,
            instagram_password=config.INSTAGRAM_PASSWORD
        )
        self.cross_analyzer = CrossAnalyzer()
        self.current_trends = []
        self.selected_trend = None
        self.social_trends = {'youtube': [], 'tiktok': [], 'instagram': [], 'cross': []}
        self.init_ui()
        logger.info("VIDEOCU v1 started")

    def init_ui(self):
        """Initialize UI components"""
        self.setWindowTitle("🎬 VIDEOCU - Otonom YouTube İş Yöneticisi v1")
        self.setGeometry(100, 100, 1400, 900)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Header
        header = self.create_header()
        main_layout.addWidget(header)

        # Tabs for 5 panels
        tabs = QTabWidget()
        tabs.addTab(self.create_panel1_trend(), "📊 Trend Araştırma")
        tabs.addTab(self.create_panel5_social(), "📱 Sosyal Medya Trendleri")
        tabs.addTab(self.create_panel2_content(), "🤖 İçerik Üretimi")
        tabs.addTab(self.create_panel3_video(), "🎬 Video Montaj")
        tabs.addTab(self.create_panel4_upload(), "📤 YouTube Yükleme")
        main_layout.addWidget(tabs)

        # Status bar
        self.statusBar().showMessage("Hazır")

        # Apply stylesheet
        self.setStyleSheet(self.get_stylesheet())

    def create_header(self):
        """Create header section"""
        header = QGroupBox()
        layout = QVBoxLayout()

        # Title
        title = QLabel("🎬 VIDEOCU")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Otonom YouTube İş Yöneticisi - Almanya Odaklı Trend Analizi ve Video Üretimi")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; font-size: 14px;")
        layout.addWidget(subtitle)

        # API Status
        api_status = self.get_api_status_widget()
        layout.addWidget(api_status)

        header.setLayout(layout)
        return header

    def get_api_status_widget(self):
        """Create API status widget"""
        widget = QWidget()
        layout = QHBoxLayout()

        status = config.validate_api_keys()

        for service, is_active in status.items():
            icon = "✅" if is_active else "❌"
            label = QLabel(f"{icon} {service.capitalize()}")
            label.setStyleSheet("padding: 5px; margin: 2px;")
            layout.addWidget(label)

        widget.setLayout(layout)
        return widget

    def create_panel1_trend(self):
        """Panel 1: Trend Research"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Settings
        settings_group = QGroupBox("Ayarlar")
        settings_layout = QHBoxLayout()

        # Region selector
        settings_layout.addWidget(QLabel("Bölge:"))
        self.region_combo = QComboBox()
        self.region_combo.addItems(["🇩🇪 Germany (DE)", "🇬🇧 UK (GB)", "🇺🇸 USA (US)", "🇹🇷 Turkey (TR)"])
        settings_layout.addWidget(self.region_combo)

        # Category selector
        settings_layout.addWidget(QLabel("Kategori:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Hepsi", "Gaming", "Technology", "Education", "Entertainment"])
        settings_layout.addWidget(self.category_combo)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Action buttons
        button_layout = QHBoxLayout()
        self.trend_search_btn = QPushButton("🔍 Trend Ara")
        self.trend_search_btn.clicked.connect(self.on_trend_search)
        self.trend_analyze_btn = QPushButton("📊 Analiz Et")
        self.trend_analyze_btn.clicked.connect(self.on_trend_analyze)
        button_layout.addWidget(self.trend_search_btn)
        button_layout.addWidget(self.trend_analyze_btn)
        layout.addLayout(button_layout)

        # Results
        results_group = QGroupBox("Sonuçlar")
        results_layout = QVBoxLayout()

        self.trend_results_table = QTableWidget()
        self.trend_results_table.setColumnCount(4)
        self.trend_results_table.setHorizontalHeaderLabels(["Trend", "Görüntülenme", "Skor", "Kategori"])
        results_layout.addWidget(self.trend_results_table)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Status
        self.trend_status = QLabel("İşlem bekleniyor...")
        layout.addWidget(self.trend_status)

        panel.setLayout(layout)
        return panel

    def create_panel2_content(self):
        """Panel 2: Content Generation"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Trend selection
        trend_group = QGroupBox("Seçili Trend")
        trend_layout = QVBoxLayout()

        self.selected_trend_label = QLabel("Henüz trend seçilmedi")
        trend_layout.addWidget(self.selected_trend_label)

        trend_group.setLayout(trend_layout)
        layout.addWidget(trend_group)

        # Settings
        settings_group = QGroupBox("Ayarlar")
        settings_layout = QHBoxLayout()

        settings_layout.addWidget(QLabel("Dil:"))
        self.language_combo = QComboBox()
        self.language_combo.addItems(["🇩🇪 Deutsch", "🇬🇧 English", "🇹🇷 Türkçe"])
        settings_layout.addWidget(self.language_combo)

        settings_layout.addWidget(QLabel("Süre:"))
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["30 saniye", "60 saniye", "90 saniye", "120 saniye"])
        self.duration_combo.setCurrentIndex(1)
        settings_layout.addWidget(self.duration_combo)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Action buttons
        button_layout = QHBoxLayout()
        self.script_btn = QPushButton("✍️ Script Oluştur")
        self.script_btn.clicked.connect(self.on_generate_script)
        self.voice_btn = QPushButton("🎤 Ses Üret")
        self.voice_btn.clicked.connect(self.on_generate_voice)
        self.image_btn = QPushButton("🖼️ Görsel Üret")
        self.image_btn.clicked.connect(self.on_generate_images)
        button_layout.addWidget(self.script_btn)
        button_layout.addWidget(self.voice_btn)
        button_layout.addWidget(self.image_btn)
        layout.addLayout(button_layout)

        # Status
        status_group = QGroupBox("Durum")
        status_layout = QVBoxLayout()

        self.content_status_text = QTextEdit()
        self.content_status_text.setReadOnly(True)
        self.content_status_text.setMaximumHeight(150)
        status_layout.addWidget(self.content_status_text)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        panel.setLayout(layout)
        return panel

    def create_panel3_video(self):
        """Panel 3: Video Editing"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Action buttons
        button_layout = QHBoxLayout()
        self.video_create_btn = QPushButton("▶️ Video Oluştur")
        self.video_create_btn.clicked.connect(self.on_create_video)
        self.video_preview_btn = QPushButton("👁️ Önizle")
        self.video_preview_btn.clicked.connect(self.on_preview_video)
        self.video_save_btn = QPushButton("💾 Kaydet")
        self.video_save_btn.clicked.connect(self.on_save_video)
        button_layout.addWidget(self.video_create_btn)
        button_layout.addWidget(self.video_preview_btn)
        button_layout.addWidget(self.video_save_btn)
        layout.addLayout(button_layout)

        # Progress
        progress_group = QGroupBox("İlerleme")
        progress_layout = QVBoxLayout()

        self.video_progress = QProgressBar()
        self.video_progress.setValue(0)
        progress_layout.addWidget(self.video_progress)

        self.video_status = QLabel("İşlem bekleniyor...")
        progress_layout.addWidget(self.video_status)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Log
        log_group = QGroupBox("İşlem Günlüğü")
        log_layout = QVBoxLayout()

        self.video_log = QTextEdit()
        self.video_log.setReadOnly(True)
        log_layout.addWidget(self.video_log)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        panel.setLayout(layout)
        return panel

    def create_panel4_upload(self):
        """Panel 4: YouTube Upload"""
        panel = QWidget()
        layout = QVBoxLayout()

        # Video info
        info_group = QGroupBox("Video Bilgileri")
        info_layout = QVBoxLayout()

        info_layout.addWidget(QLabel("Başlık:"))
        self.upload_title = QLineEdit()
        info_layout.addWidget(self.upload_title)

        info_layout.addWidget(QLabel("Açıklama:"))
        self.upload_description = QTextEdit()
        self.upload_description.setMaximumHeight(100)
        info_layout.addWidget(self.upload_description)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Upload settings
        settings_group = QGroupBox("Yayın Ayarları")
        settings_layout = QHBoxLayout()

        settings_layout.addWidget(QLabel("Yayın Zamanı:"))
        self.upload_time_combo = QComboBox()
        self.upload_time_combo.addItems(["Şimdi", "1 saat sonra", "3 saat sonra", "Özel zaman"])
        settings_layout.addWidget(self.upload_time_combo)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Upload button
        self.upload_btn = QPushButton("🚀 YouTube'a Yükle")
        self.upload_btn.clicked.connect(self.on_upload_youtube)
        layout.addWidget(self.upload_btn)

        # Upload status
        upload_status_group = QGroupBox("Yükleme Durumu")
        upload_status_layout = QVBoxLayout()

        self.upload_progress = QProgressBar()
        self.upload_progress.setValue(0)
        upload_status_layout.addWidget(self.upload_progress)

        self.upload_status = QLabel("İşlem bekleniyor...")
        upload_status_layout.addWidget(self.upload_status)

        upload_status_group.setLayout(upload_status_layout)
        layout.addWidget(upload_status_group)

        panel.setLayout(layout)
        return panel

    def create_panel5_social(self):
        """Panel 5: Social Media Trends (YouTube Categories + TikTok + Instagram)"""
        panel = QWidget()
        layout = QVBoxLayout()

        # YouTube Category Selection
        category_group = QGroupBox("YouTube Kategori Seçimi")
        category_layout = QHBoxLayout()

        category_layout.addWidget(QLabel("Kategori:"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("Tüm Kategoriler", "all")
        for cat_id, cat_name in YOUTUBE_CATEGORIES_DE.items():
            self.category_combo.addItem(cat_name, cat_id)
        category_layout.addWidget(self.category_combo)

        self.youtube_category_btn = QPushButton("📹 YouTube Kategori Trendleri")
        self.youtube_category_btn.clicked.connect(self.on_youtube_category_search)
        category_layout.addWidget(self.youtube_category_btn)

        category_group.setLayout(category_layout)
        layout.addWidget(category_group)

        # Social Media Buttons
        social_buttons_group = QGroupBox("Sosyal Medya Trendleri")
        social_buttons_layout = QHBoxLayout()

        self.tiktok_btn = QPushButton("🎵 TikTok Trendleri")
        self.tiktok_btn.clicked.connect(self.on_tiktok_search)
        social_buttons_layout.addWidget(self.tiktok_btn)

        self.instagram_btn = QPushButton("📸 Instagram Reels")
        self.instagram_btn.clicked.connect(self.on_instagram_search)
        social_buttons_layout.addWidget(self.instagram_btn)

        self.cross_analysis_btn = QPushButton("🔥 Kesişim Analizi")
        self.cross_analysis_btn.clicked.connect(self.on_cross_analysis)
        social_buttons_layout.addWidget(self.cross_analysis_btn)

        social_buttons_group.setLayout(social_buttons_layout)
        layout.addWidget(social_buttons_group)

        # Results Table
        results_group = QGroupBox("Trend Sonuçları")
        results_layout = QVBoxLayout()

        self.social_results_table = QTableWidget()
        self.social_results_table.setColumnCount(7)
        self.social_results_table.setHorizontalHeaderLabels([
            "Platform", "Başlık", "Yazar/Kanal", "Görüntülenme",
            "Beğeni", "Yorum", "Skor"
        ])
        self.social_results_table.setColumnWidth(0, 80)
        self.social_results_table.setColumnWidth(1, 300)
        self.social_results_table.setColumnWidth(2, 150)
        results_layout.addWidget(self.social_results_table)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Potential Trends
        potential_group = QGroupBox("💎 Potansiyel Viral Trendler")
        potential_layout = QVBoxLayout()

        self.potential_trends_table = QTableWidget()
        self.potential_trends_table.setColumnCount(5)
        self.potential_trends_table.setHorizontalHeaderLabels([
            "Keyword", "Platform Sayısı", "Platformlar", "Frekans", "Skor"
        ])
        self.potential_trends_table.setMaximumHeight(200)
        potential_layout.addWidget(self.potential_trends_table)

        potential_group.setLayout(potential_layout)
        layout.addWidget(potential_group)

        # Status
        self.social_status = QLabel("Sosyal medya trendleri bekleniyor...")
        layout.addWidget(self.social_status)

        panel.setLayout(layout)
        return panel

    # Event handlers
    def on_trend_search(self):
        """Trend araştırma başlat (GERÇEK)"""
        try:
            self.trend_status.setText("⏳ Almanya'dan trendler araştırılıyor...")
            self.statusBar().showMessage("Google Trends sorgulanıyor...")
            QApplication.processEvents()  # UI güncelle

            # Region code al
            region_text = self.region_combo.currentText()
            region_code = region_text.split('(')[1].split(')')[0] if '(' in region_text else 'DE'

            # Google Trends'den trendleri al
            logger.info(f"Fetching trends for {region_code}...")
            trends = self.trend_analyzer.get_trending_searches_germany(limit=10)

            if not trends:
                QMessageBox.warning(self, "Uyarı", "Trend bulunamadı!")
                self.trend_status.setText("❌ Trend bulunamadı")
                return

            # Tabloya ekle
            self.trend_results_table.setRowCount(len(trends))

            for i, trend in enumerate(trends):
                # Trend keyword
                self.trend_results_table.setItem(i, 0, QTableWidgetItem(trend['keyword']))

                # Simulated views
                views = trend.get('avg_interest', 0) * 1000
                self.trend_results_table.setItem(i, 1, QTableWidgetItem(f"{views:,}"))

                # Score
                score = trend.get('score', 0)
                self.trend_results_table.setItem(i, 2, QTableWidgetItem(f"{score}/100"))

                # Category (boş - sonra eklenecek)
                self.trend_results_table.setItem(i, 3, QTableWidgetItem("-"))

                # Veritabanına kaydet
                self.db.insert_trend(
                    keyword=trend['keyword'],
                    region=region_code,
                    score=score,
                    views=views,
                    metadata=trend
                )

            self.current_trends = trends
            self.trend_status.setText(f"✅ {len(trends)} trend bulundu!")
            self.statusBar().showMessage("Hazır")

            logger.info(f"✅ Found {len(trends)} trends")

        except Exception as e:
            logger.error(f"❌ Trend search error: {e}")
            QMessageBox.critical(self, "Hata", f"Trend araştırma hatası:\n{str(e)}")
            self.trend_status.setText("❌ Hata oluştu")

    def on_trend_analyze(self):
        """Trend analizi yap (GERÇEK)"""
        try:
            # Seçili satırı al
            selected_rows = self.trend_results_table.selectedItems()
            if not selected_rows:
                QMessageBox.warning(self, "Uyarı", "Lütfen bir trend seçin!")
                return

            row = selected_rows[0].row()
            keyword = self.trend_results_table.item(row, 0).text()

            self.trend_status.setText(f"📊 '{keyword}' analiz ediliyor...")
            QApplication.processEvents()

            # Analiz et
            analysis = self.trend_analyzer.analyze_trend_potential(keyword, region='DE')

            # Sonuçları göster
            result_text = f"""
🔍 Trend Analizi: {keyword}

📊 Skor: {analysis['score']}/100
📈 Yön: {analysis['trend_direction']}
💡 Tavsiye: {analysis['recommendation']}

"""
            if 'metrics' in analysis:
                metrics = analysis['metrics']
                result_text += f"""Detaylar:
  • Ortalama İlgi: {metrics['avg_interest']}
  • Güncel İlgi: {metrics['current_interest']}
  • Maksimum İlgi: {metrics['max_interest']}
"""

            QMessageBox.information(self, "Trend Analizi", result_text)

            # Trendi seç (FAZ 3 için)
            self.selected_trend = {
                'keyword': keyword,
                'analysis': analysis
            }
            self.selected_trend_label.setText(f"📊 Seçili: {keyword} (Skor: {analysis['score']}/100)")

            self.trend_status.setText("✅ Analiz tamamlandı")
            logger.info(f"✅ Analyzed: {keyword} - Score: {analysis['score']}")

        except Exception as e:
            logger.error(f"❌ Trend analyze error: {e}")
            QMessageBox.critical(self, "Hata", f"Analiz hatası:\n{str(e)}")
            self.trend_status.setText("❌ Hata oluştu")

    def on_generate_script(self):
        """Script oluştur"""
        self.content_status_text.append("⏳ Script oluşturuluyor...")
        QMessageBox.information(self, "Bilgi", "FAZ 3'te gerçek script üretimi eklenecek")

    def on_generate_voice(self):
        """Ses üret"""
        self.content_status_text.append("⏳ Ses üretiliyor...")
        QMessageBox.information(self, "Bilgi", "FAZ 3'te gerçek ses üretimi eklenecek")

    def on_generate_images(self):
        """Görsel üret"""
        self.content_status_text.append("⏳ Görseller üretiliyor...")
        QMessageBox.information(self, "Bilgi", "FAZ 3'te gerçek görsel üretimi eklenecek")

    def on_create_video(self):
        """Video oluştur"""
        self.video_status.setText("⏳ Video oluşturuluyor...")
        QMessageBox.information(self, "Bilgi", "FAZ 4'te gerçek video montajı eklenecek")

    def on_preview_video(self):
        """Video önizle"""
        QMessageBox.information(self, "Bilgi", "FAZ 4'te önizleme eklenecek")

    def on_save_video(self):
        """Video kaydet"""
        QMessageBox.information(self, "Bilgi", "FAZ 4'te kaydetme eklenecek")

    def on_upload_youtube(self):
        """YouTube'a yükle"""
        self.upload_status.setText("⏳ YouTube'a yükleniyor...")
        QMessageBox.information(self, "Bilgi", "FAZ 5'te gerçek yükleme eklenecek")

    def on_youtube_category_search(self):
        """YouTube kategori bazlı trendleri ara"""
        try:
            category_id = self.category_combo.currentData()
            category_name = self.category_combo.currentText()

            if category_id == "all":
                self.social_status.setText("⏳ Tüm kategorilerden trendler alınıyor...")
                QMessageBox.information(self, "Bilgi", "Tüm kategoriler çok fazla API quota kullanır. Lütfen belirli bir kategori seçin.")
                return

            self.social_status.setText(f"⏳ {category_name} kategorisinden trendler alınıyor...")
            QApplication.processEvents()

            # YouTube API ile kategori trendlerini al
            videos = self.trend_analyzer.get_youtube_trending_by_category(
                category_id=category_id,
                region_code='DE',
                max_results=10
            )

            if not videos:
                QMessageBox.warning(self, "Uyarı", "Trend bulunamadı!")
                self.social_status.setText("❌ Trend bulunamadı")
                return

            # Store results
            self.social_trends['youtube'] = videos

            # Display in table
            self._display_social_results(videos)

            self.social_status.setText(f"✅ {len(videos)} YouTube trend bulundu!")
            logger.info(f"✅ Found {len(videos)} YouTube trends in category {category_name}")

        except Exception as e:
            logger.error(f"❌ YouTube category search error: {e}")
            QMessageBox.critical(self, "Hata", f"YouTube arama hatası:\n{str(e)}")
            self.social_status.setText("❌ Hata oluştu")

    def on_tiktok_search(self):
        """TikTok trendlerini ara"""
        try:
            self.social_status.setText("⏳ TikTok trendleri alınıyor...")
            QApplication.processEvents()

            # Create async event loop for TikTok
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

            async def fetch_tiktok():
                return await self.social_analyzer.get_tiktok_trending(count=30, region='DE')

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            videos = loop.run_until_complete(fetch_tiktok())
            loop.close()

            if not videos:
                QMessageBox.warning(self, "Uyarı", "TikTok trendleri bulunamadı!\n\nNot: TikTok API bot tespiti yapabilir. Lütfen tekrar deneyin.")
                self.social_status.setText("❌ Trend bulunamadı")
                return

            # Store results
            self.social_trends['tiktok'] = videos

            # Display in table
            self._display_social_results(videos)

            self.social_status.setText(f"✅ {len(videos)} TikTok trend bulundu!")
            logger.info(f"✅ Found {len(videos)} TikTok trends")

        except Exception as e:
            logger.error(f"❌ TikTok search error: {e}")
            QMessageBox.critical(self, "Hata", f"TikTok arama hatası:\n{str(e)}\n\nNot: TikTok API bot tespiti yapıyor olabilir.")
            self.social_status.setText("❌ Hata oluştu")

    def on_instagram_search(self):
        """Instagram Reels trendlerini ara"""
        try:
            self.social_status.setText("⏳ Instagram Reels alınıyor...")
            QApplication.processEvents()

            # Instagram Reels fetch
            hashtags = ["reelsdeutschland", "deutschland", "viral", "trending"]
            reels = self.social_analyzer.get_instagram_trending_by_hashtags(
                hashtags=hashtags,
                amount_per_tag=15
            )

            if not reels:
                QMessageBox.warning(self, "Uyarı", "Instagram Reels bulunamadı!\n\nNot: Instagram giriş bilgileri gereklidir (.env dosyasını kontrol edin).")
                self.social_status.setText("❌ Reels bulunamadı")
                return

            # Store results
            self.social_trends['instagram'] = reels

            # Display in table
            self._display_social_results(reels)

            self.social_status.setText(f"✅ {len(reels)} Instagram Reel bulundu!")
            logger.info(f"✅ Found {len(reels)} Instagram Reels")

        except Exception as e:
            logger.error(f"❌ Instagram search error: {e}")
            QMessageBox.critical(self, "Hata", f"Instagram arama hatası:\n{str(e)}")
            self.social_status.setText("❌ Hata oluştu")

    def on_cross_analysis(self):
        """Çapraz platform analizi yap"""
        try:
            self.social_status.setText("⏳ Kesişim analizi yapılıyor...")
            QApplication.processEvents()

            # Get Google Trends for cross-analysis
            google_trends = self.current_trends if self.current_trends else []

            # Get social media data
            youtube_videos = self.social_trends.get('youtube', [])
            tiktok_videos = self.social_trends.get('tiktok', [])
            instagram_reels = self.social_trends.get('instagram', [])

            if not (youtube_videos or tiktok_videos or instagram_reels):
                QMessageBox.warning(self, "Uyarı", "Önce sosyal medya trendlerini arayın!")
                self.social_status.setText("❌ Veri yok")
                return

            # Perform cross-analysis
            result = self.cross_analyzer.analyze_cross_platform_trends(
                google_trends=google_trends,
                youtube_videos=youtube_videos,
                tiktok_videos=tiktok_videos,
                instagram_reels=instagram_reels
            )

            # Display cross-platform keywords
            cross_keywords = result.get('cross_platform_keywords', [])
            if cross_keywords:
                self.potential_trends_table.setRowCount(len(cross_keywords))
                for i, kw in enumerate(cross_keywords):
                    self.potential_trends_table.setItem(i, 0, QTableWidgetItem(kw['keyword']))
                    self.potential_trends_table.setItem(i, 1, QTableWidgetItem(str(kw['platform_count'])))
                    self.potential_trends_table.setItem(i, 2, QTableWidgetItem(', '.join(kw['platforms'])))
                    self.potential_trends_table.setItem(i, 3, QTableWidgetItem(str(kw['frequency'])))
                    self.potential_trends_table.setItem(i, 4, QTableWidgetItem(str(kw['score'])))

            # Display potential trends in main table
            potential_trends = result.get('potential_trends', [])
            if potential_trends:
                self._display_social_results(potential_trends)

            # Show summary
            stats = result.get('platform_stats', {})
            summary = f"""Kesişim Analizi Tamamlandı!

📊 İçerik İstatistikleri:
• Google Trends: {stats.get('google_trends', 0)} trend
• YouTube: {stats.get('youtube_videos', 0)} video
• TikTok: {stats.get('tiktok_videos', 0)} video
• Instagram: {stats.get('instagram_reels', 0)} reel
• Toplam: {stats.get('total_content', 0)} içerik

🔥 Kesişim Sonuçları:
• {len(cross_keywords)} çapraz platform keyword
• {len(potential_trends)} potansiyel viral trend

💎 En Trend Konu: {result.get('top_trending_topic', 'Yok')}
"""
            QMessageBox.information(self, "Kesişim Analizi", summary)

            self.social_status.setText(f"✅ Analiz tamamlandı! {len(cross_keywords)} kesişim bulundu")
            logger.info(f"✅ Cross-analysis complete: {len(cross_keywords)} keywords, {len(potential_trends)} potential trends")

        except Exception as e:
            logger.error(f"❌ Cross-analysis error: {e}")
            QMessageBox.critical(self, "Hata", f"Kesişim analizi hatası:\n{str(e)}")
            self.social_status.setText("❌ Hata oluştu")

    def _display_social_results(self, videos):
        """Display social media results in table"""
        self.social_results_table.setRowCount(len(videos))

        for i, video in enumerate(videos):
            platform = video.get('platform', 'unknown').upper()
            self.social_results_table.setItem(i, 0, QTableWidgetItem(platform))

            title = video.get('title', '')[:50]
            self.social_results_table.setItem(i, 1, QTableWidgetItem(title))

            author = video.get('author', '') or video.get('channel', '')
            self.social_results_table.setItem(i, 2, QTableWidgetItem(author))

            views = video.get('views', 0)
            self.social_results_table.setItem(i, 3, QTableWidgetItem(f"{views:,}"))

            likes = video.get('likes', 0)
            self.social_results_table.setItem(i, 4, QTableWidgetItem(f"{likes:,}"))

            comments = video.get('comments', 0)
            self.social_results_table.setItem(i, 5, QTableWidgetItem(f"{comments:,}"))

            score = video.get('score', 0)
            self.social_results_table.setItem(i, 6, QTableWidgetItem(f"{score:,}"))

    def get_stylesheet(self):
        """Return application stylesheet"""
        return """
        QMainWindow {
            background-color: #f5f5f5;
        }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #ddd;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            background-color: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            font-weight: bold;
            font-size: 14px;
        }
        QPushButton:hover {
            background-color: #5568d3;
        }
        QPushButton:pressed {
            background-color: #4451b8;
        }
        QComboBox, QLineEdit {
            padding: 8px;
            border: 2px solid #ddd;
            border-radius: 5px;
            background-color: white;
        }
        QTextEdit {
            border: 2px solid #ddd;
            border-radius: 5px;
            background-color: white;
            padding: 5px;
        }
        QTableWidget {
            border: 2px solid #ddd;
            border-radius: 5px;
            background-color: white;
        }
        QProgressBar {
            border: 2px solid #ddd;
            border-radius: 5px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #667eea;
        }
        """


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = VideocuMainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
