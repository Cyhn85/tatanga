"""
VIDEOCU v1 - Telegram Bot Interface
Manual control interface for Chef AI system

Features:
- Natural language video creation
- Real-time status updates
- Production monitoring
- Result delivery
"""

import logging
import os
import asyncio
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Music Wizard State Constants
(
    WAITING_AUDIO,           # Entry: waiting for voice/audio
    CHOOSE_ACTION,           # Has active project: add to existing or new?
    AWAITING_PROJECT_NAME,   # Enter project name
    SELECT_STYLE,            # Choose music style
    INPUT_TYPE,              # Choose layer type (melody/rhythm/beatbox/voice)
    PROJECT_MENU,            # Main dashboard: compose/add more/manage
    MANAGE_LAYERS,           # Layer management
    LAYER_EDIT,              # Edit single layer
    COMPOSING,               # Processing composition
) = range(9)

# Import VIDEOCU components
from modules.chef_ai import ChefAI
from modules.skill_library import SkillLibrary, initialize_default_skills
from modules.agent_memory import AgentMemory
from modules.colab import ColabBridge
from modules.agents.video_agent import VideoProducerAgent
from modules.agents.social_agent import SocialMediaManagerAgent
from modules.agents.composer_agent import ComposerAgent
from modules.orchestrator import VideoProducer

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Escape Telegram markdown special characters"""
    if not text:
        return text
    chars = ['_', '*', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in chars:
        text = text.replace(char, '\\' + char)
    return text


class VideocuBot:
    """
    Telegram Bot for VIDEOCU v1

    Provides manual control interface to Chef AI system
    """

    def __init__(self,
                 telegram_token: str,
                 gemini_api_key: str,
                 authorized_users: Optional[list] = None):
        """
        Initialize VIDEOCU Bot

        Args:
            telegram_token: Telegram Bot API token
            gemini_api_key: Gemini API key for Chef AI
            authorized_users: List of authorized user IDs (None = all users)
        """
        self.token = telegram_token
        self.authorized_users = authorized_users or []

        # Initialize Chef AI system
        logger.info("🤖 Initializing Chef AI system...")
        self.chef_ai = ChefAI(gemini_api_key=gemini_api_key)

        # Initialize Skill Library
        self.skill_library = SkillLibrary()
        initialize_default_skills(self.skill_library)

        # Initialize Agent Memory
        self.agent_memory = AgentMemory()

        # Initialize VideoProducer with config
        producer_config = {
            'gemini_api_key': gemini_api_key,
            'elevenlabs_api_key': os.getenv('ELEVENLABS_API_KEY', ''),
            'pexels_api_key': os.getenv('PEXELS_API_KEY', ''),
            'output_dir': 'output'
        }
        self.video_producer = VideoProducer(producer_config)

        # Register agents with Chef AI
        video_agent = VideoProducerAgent(
            orchestrator=self.video_producer,
            skill_library=self.skill_library
        )
        social_agent = SocialMediaManagerAgent(
            youtube_uploader=None,  # Will be added later
            skill_library=self.skill_library
        )

        self.chef_ai.register_agent('video_producer', video_agent)
        self.chef_ai.register_agent('social_media_manager', social_agent)

        # Initialize Composer Agent for music projects
        self.composer_agent = ComposerAgent(
            memory=self.agent_memory,
            output_dir='output/compositions'
        )

        # Initialize Colab Bridge for GPU operations
        self.colab_bridge = ColabBridge()
        colab_status = "✅ Bağlı" if self.colab_bridge.is_available() else "⚠️ Bağlı değil"
        logger.info(f"   🖥️ Colab Bridge: {colab_status}")

        # Create voice inputs directory
        self.voice_inputs_dir = Path('output/voice_inputs')
        self.voice_inputs_dir.mkdir(parents=True, exist_ok=True)

        # Active productions tracking
        self.active_productions = {}  # {chat_id: task_info}

        # Music project state tracking
        self.music_project_state = {}  # {user_id: {'pending_audio': path, 'action': 'new/add'}}

        # GPU task tracking
        self.gpu_tasks = {}  # {user_id: {'task_id': id, 'operation': op, 'started_at': time}}

        logger.info("✅ VIDEOCU Bot initialized")
        logger.info(f"   🎼 Composer Agent: {self.composer_agent.get_capabilities()}")

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized"""
        if not self.authorized_users:
            return True  # All users authorized if list is empty
        return user_id in self.authorized_users

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user

        if not self._is_authorized(user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        welcome_text = f"""
👨‍🍳 **VIDEOCU v1 - AI Video Production System**

Merhaba {user.first_name}!

Ben VIDEOCU, AI destekli video üretim sisteminizin Telegram arayüzüyüm.

**Neler Yapabilirim:**
📹 Profesyonel video üretimi (kısa/uzun form)
🎵 Melodi çıkarma ve müzik aranjmanı
📱 Sosyal medya optimizasyonu
🤖 Akıllı içerik stratejisi

**Nasıl Kullanılır:**
Sadece ne istediğinizi doğal dille yazın!

**Örnekler:**
• "Mars kolonizasyonu hakkında 60 saniyelik YouTube videosu yap"
• "Yeni ürün lansmanı için viral TikTok videosu oluştur"
• "Fotoğraflarımdan 30 saniyelik anı videosu yap"

**Komutlar:**
/create_video - Video üretim asistanı
/create_music - Müzik üretim asistanı
/status - Sistem durumu
/help - Detaylı yardım

Haydi başlayalım! 🚀
"""

        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        help_text = """
📚 **VIDEOCU v1 - Komut Listesi**

**Video Üretimi:**
/create_video - Video üretim asistanı başlat
Veya direkt yazın: "60 saniyelik Python tutorial videosu yap"

**Müzik Üretimi:**
/create_music - Müzik üretim asistanı
Melodi çıkarma ve aranjman

**Sistem:**
/status - Sistem durumu ve istatistikler
/cancel - Aktif işlemi iptal et

**Doğal Dil Kullanımı:**
Herhangi bir komut kullanmadan direkt yazabilirsiniz:

✅ "Mars hakkında eğitici YouTube videosu"
✅ "Çok aranan şarkı sözlerinden TikTok videosu"
✅ "Fotoğraflarımdan anı videosu yap"
✅ "Mırıldandığım melodiden jazz parçası oluştur"

**Detaylı Parametreler:**
• Platform: YouTube, TikTok, Instagram
• Süre: 15-900 saniye
• Dil: Türkçe (de), İngilizce (en), Türkçe (tr)
• Stil: informativ, unterhaltsam, dramatisch, humorvoll

**Örnek:**
"60 saniyelik Mars kolonizasyonu hakkında dramatik YouTube videosu yap, Türkçe narasyonlu"

Sorularınız için: @videocu_support
"""

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        # Get system status
        chef_status = self.chef_ai.get_status()
        skill_stats = self.skill_library.get_stats()
        memory_stats = self.agent_memory.get_stats()

        status_text = f"""
📊 **VIDEOCU v1 - Sistem Durumu**

**Chef AI:**
• AI Aktif: {'✅' if chef_status['ai_enabled'] else '❌'}
• Kayıtlı Agentlar: {len(chef_status['registered_agents'])}
• Desteklenen Görevler: {len(chef_status['supported_tasks'])}

**Skill Library:**
• Toplam Beceriler: {skill_stats['total_skills']}
• Kategoriler: {skill_stats['categories']}
• Video Production: {skill_stats['category_breakdown'].get('video_production', 0)}
• Music Creation: {skill_stats['category_breakdown'].get('music_creation', 0)}
• Social Media: {skill_stats['category_breakdown'].get('social_media', 0)}

**Agent Memory:**
• Toplam Görevler: {memory_stats['total_tasks']}
• Tamamlanan: {memory_stats['completed_tasks']}
• Toplanan Metrikler: {memory_stats['total_metrics']}
• Öğrenilen Stratejiler: {memory_stats['best_practices_count']}

**Aktif Üretimler:**
• Şu anda: {len(self.active_productions)} üretim

**Sistem Sağlığı:** {'🟢 Çevrimiçi' if chef_status['ai_enabled'] else '🟡 Sınırlı Mod'}
"""

        await update.message.reply_text(status_text, parse_mode='Markdown')

    async def create_video_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /create_video command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        keyboard = [
            [
                InlineKeyboardButton("📺 YouTube (16:9)", callback_data="video_youtube"),
                InlineKeyboardButton("📱 TikTok (9:16)", callback_data="video_tiktok")
            ],
            [
                InlineKeyboardButton("📸 Instagram Reel", callback_data="video_instagram"),
                InlineKeyboardButton("🎬 Özel Format", callback_data="video_custom")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📹 **Video Üretim Asistanı**\n\n"
            "Hangi platform için video üretmek istiyorsunuz?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def create_music_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /create_music command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        await update.message.reply_text(
            "🎵 **Müzik Üretim Asistanı**\n\n"
            "Müzik üretimi için iki yöntem:\n\n"
            "1️⃣ **Melodi Çıkarma:** Sesli kayıt gönderin (mırıldanma/söyleme)\n"
            "2️⃣ **Direkt Aranjman:** Müziğin tarzını ve konusunu yazın\n\n"
            "Örnek: 'Mırıldandığım melodiden jazz tarzı bir parça yap'",
            parse_mode='Markdown'
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("video_"):
            platform = query.data.replace("video_", "")

            platform_names = {
                'youtube': 'YouTube (16:9)',
                'tiktok': 'TikTok (9:16)',
                'instagram': 'Instagram Reel (9:16)',
                'custom': 'Özel Format'
            }

            await query.edit_message_text(
                f"✅ Platform seçildi: {platform_names.get(platform, platform)}\n\n"
                f"Şimdi video konusunu yazın:\n\n"
                f"Örnek: 'Mars kolonizasyonu hakkında 60 saniyelik eğitici video'",
                parse_mode='Markdown'
            )

            # Store platform choice in context
            context.user_data['selected_platform'] = platform

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language messages"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        user_prompt = update.message.text
        chat_id = update.effective_chat.id

        # Send processing message
        processing_msg = await update.message.reply_text(
            "👨‍🍳 Chef AI analiz ediyor...\n⏳ Lütfen bekleyin..."
        )

        try:
            # Execute order through Chef AI
            logger.info(f"📥 Received prompt from user {update.effective_user.id}: {user_prompt[:50]}...")

            result = self.chef_ai.execute_order(
                raw_prompt=user_prompt,
                user_id=str(update.effective_user.id)
            )

            # Store in active productions
            self.active_productions[chat_id] = {
                'task_id': result['task_id'],
                'started_at': datetime.now(),
                'prompt': user_prompt
            }

            # Record in agent memory
            self.agent_memory.record_task(result)

            if result['status'] == 'failed':
                await processing_msg.edit_text(
                    f"❌ **Üretim Başarısız**\n\n"
                    f"Hata: {result.get('error', 'Bilinmeyen hata')}\n\n"
                    f"Task ID: `{result['task_id']}`",
                    parse_mode='Markdown'
                )
                return

            # Get analysis details
            analysis = result.get('analysis', {})
            task_type = analysis.get('task_type', 'unknown')
            platform = analysis.get('platform', 'N/A')

            # Update with progress
            await processing_msg.edit_text(
                f"✅ **Görev Analiz Edildi**\n\n"
                f"📋 Görev Tipi: {task_type}\n"
                f"🎯 Platform: {platform}\n"
                f"🆔 Task ID: `{result['task_id']}`\n\n"
                f"⚙️ Agentlar çalışıyor...",
                parse_mode='Markdown'
            )

            # Check result
            task_result = result.get('result', {})
            if task_result.get('success'):
                agent_results = task_result.get('agent_results', {})

                # Build success message
                success_text = "🎉 **Üretim Tamamlandı!**\n\n"

                # Video producer results
                if 'video_producer' in agent_results:
                    video_result = agent_results['video_producer']
                    if video_result.get('success'):
                        video_path = video_result.get('video_path', 'N/A')
                        production_id = video_result.get('production_id', 'N/A')
                        success_text += f"📹 Video: `{video_path}`\n"
                        success_text += f"🆔 Production ID: `{production_id}`\n\n"

                # Social media results
                if 'social_media_manager' in agent_results:
                    social_result = agent_results['social_media_manager']
                    if social_result.get('success'):
                        metadata = social_result.get('metadata', {})
                        success_text += f"📱 **SEO Metadata:**\n"
                        success_text += f"• Başlık: {metadata.get('title', 'N/A')[:50]}...\n"
                        success_text += f"• Tags: {len(metadata.get('tags', []))} adet\n\n"

                success_text += f"⏱ Tamamlanma: {datetime.now().strftime('%H:%M:%S')}"

                await processing_msg.edit_text(success_text, parse_mode='Markdown')

                # Send video file if exists and small enough
                video_path = agent_results.get('video_producer', {}).get('video_path')
                if video_path and os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    if file_size < 50 * 1024 * 1024:  # 50MB limit for Telegram
                        try:
                            await update.message.reply_video(
                                video=open(video_path, 'rb'),
                                caption=f"🎬 {user_prompt[:100]}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send video: {e}")

            else:
                await processing_msg.edit_text(
                    f"⚠️ **Üretim Tamamlandı Ancak Hatalarla**\n\n"
                    f"Task ID: `{result['task_id']}`\n"
                    f"Detaylar için /status komutunu kullanın",
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Message handling failed: {e}")
            await processing_msg.edit_text(
                f"❌ **Bir Hata Oluştu**\n\n"
                f"Hata: {escape_markdown(str(e))}\n\n"
                f"Lütfen tekrar deneyin veya /help komutunu kullanın",
                parse_mode='Markdown'
            )

        finally:
            # Remove from active productions
            if chat_id in self.active_productions:
                del self.active_productions[chat_id]

    # ========== Music Project Handlers ==========

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages for music composition"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        user_id = str(update.effective_user.id)
        voice = update.message.voice

        # Send processing message
        processing_msg = await update.message.reply_text(
            "🎵 Ses dosyası alınıyor..."
        )

        try:
            # Download voice file
            file = await context.bot.get_file(voice.file_id)
            user_dir = self.voice_inputs_dir / user_id
            user_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = user_dir / f"voice_{timestamp}.ogg"

            await file.download_to_drive(str(file_path))

            logger.info(f"Voice message downloaded: {file_path} ({voice.duration}s)")

            # Store pending audio
            self.music_project_state[user_id] = {
                'pending_audio': str(file_path),
                'duration': voice.duration
            }

            # Check for active project
            active_project = self.composer_agent.get_active_project(user_id)

            # Check Colab GPU availability
            colab_available = self.colab_bridge.is_available()
            gpu_button = []
            if colab_available:
                gpu_button = [InlineKeyboardButton("🚀 GPU ile İşle (AI)", callback_data="music_gpu_process")]

            if active_project:
                # Offer to add to existing project
                keyboard = [
                    [
                        InlineKeyboardButton("➕ Mevcut Projeye Ekle", callback_data="music_add_existing"),
                        InlineKeyboardButton("🆕 Yeni Proje", callback_data="music_new_project")
                    ],
                    gpu_button
                ] if gpu_button else [
                    [
                        InlineKeyboardButton("➕ Mevcut Projeye Ekle", callback_data="music_add_existing"),
                        InlineKeyboardButton("🆕 Yeni Proje", callback_data="music_new_project")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                gpu_info = "\n🖥️ *GPU hazır* \\- AI melodi çıkarma/müzik üretimi için" if colab_available else ""

                await processing_msg.edit_text(
                    f"🎵 **Ses dosyası alındı\\!** \\({voice.duration}s\\)\n\n"
                    f"Aktif projeniz var: **{escape_markdown(active_project['project_name'])}**\n"
                    f"Stil: {escape_markdown(active_project['style'])}{gpu_info}\n\n"
                    f"Ne yapmak istersiniz?",
                    reply_markup=reply_markup,
                    parse_mode='MarkdownV2'
                )
            else:
                # Offer to create new project
                keyboard = [
                    [InlineKeyboardButton("🆕 Yeni Proje Oluştur", callback_data="music_new_project")],
                    gpu_button
                ] if gpu_button else [
                    [InlineKeyboardButton("🆕 Yeni Proje Oluştur", callback_data="music_new_project")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                gpu_info = "\n\n🖥️ *GPU hazır* \\- AI ile melodi çıkarma veya müzik üretimi yapabilirsiniz" if colab_available else ""

                await processing_msg.edit_text(
                    f"🎵 **Ses dosyası alındı\\!** \\({voice.duration}s\\){gpu_info}\n\n"
                    f"Ne yapmak istersiniz?",
                    reply_markup=reply_markup,
                    parse_mode='MarkdownV2'
                )

        except Exception as e:
            logger.error(f"Voice message handling failed: {e}")
            await processing_msg.edit_text(
                f"❌ Ses dosyası işlenemedi: {escape_markdown(str(e))}",
                parse_mode='Markdown'
            )

    async def handle_audio_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio file messages for music composition"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        user_id = str(update.effective_user.id)
        audio = update.message.audio

        # Send processing message
        processing_msg = await update.message.reply_text(
            "🎵 Ses dosyası alınıyor..."
        )

        try:
            # Download audio file
            file = await context.bot.get_file(audio.file_id)
            user_dir = self.voice_inputs_dir / user_id
            user_dir.mkdir(parents=True, exist_ok=True)

            # Get file extension
            ext = Path(audio.file_name).suffix if audio.file_name else '.mp3'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_path = user_dir / f"audio_{timestamp}{ext}"

            await file.download_to_drive(str(file_path))

            logger.info(f"Audio file downloaded: {file_path}")

            # Store pending audio
            self.music_project_state[user_id] = {
                'pending_audio': str(file_path),
                'duration': audio.duration or 0
            }

            # Same flow as voice message
            active_project = self.composer_agent.get_active_project(user_id)

            if active_project:
                keyboard = [
                    [
                        InlineKeyboardButton("➕ Mevcut Projeye Ekle", callback_data="music_add_existing"),
                        InlineKeyboardButton("🆕 Yeni Proje", callback_data="music_new_project")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await processing_msg.edit_text(
                    f"🎵 **Ses dosyası alındı!**\n\n"
                    f"Aktif projeniz var: **{active_project['project_name']}**\n\n"
                    f"Ne yapmak istersiniz?",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("🆕 Yeni Proje Oluştur", callback_data="music_new_project")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await processing_msg.edit_text(
                    f"🎵 **Ses dosyası alındı!**\n\n"
                    f"Yeni bir müzik projesi oluşturmak ister misiniz?",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Audio message handling failed: {e}")
            await processing_msg.edit_text(
                f"❌ Ses dosyası işlenemedi: {escape_markdown(str(e))}",
                parse_mode='Markdown'
            )

    async def music_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle music project button callbacks"""
        query = update.callback_query
        await query.answer()

        user_id = str(update.effective_user.id)
        data = query.data

        if data == "music_gpu_process":
            # GPU AI Processing - show options
            state = self.music_project_state.get(user_id, {})
            pending_audio = state.get('pending_audio')

            if not pending_audio:
                await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
                return

            keyboard = [
                [
                    InlineKeyboardButton("🎵 Melodi Çıkar", callback_data="gpu_extract_melody"),
                    InlineKeyboardButton("🔀 Stem Ayır", callback_data="gpu_separate_stems")
                ],
                [
                    InlineKeyboardButton("🎹 AI Müzik Üret", callback_data="gpu_generate_music"),
                    InlineKeyboardButton("🎨 Stil Dönüştür", callback_data="gpu_transform_melody")
                ],
                [
                    InlineKeyboardButton("🔙 Geri", callback_data="music_back")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "🚀 **GPU AI İşlemleri**\n\n"
                "Ne yapmak istiyorsunuz?\n\n"
                "🎵 **Melodi Çıkar**: Mırıldanma/ıslıktan MIDI nota\n"
                "🔀 **Stem Ayır**: Vokal ve enstrümanı ayır\n"
                "🎹 **AI Müzik Üret**: Prompt'tan müzik oluştur\n"
                "🎨 **Stil Dönüştür**: Melodiyi profesyonel sese dönüştür",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data == "music_new_project":
            # Ask for project name
            context.user_data['awaiting_project_name'] = True

            await query.edit_message_text(
                "📝 **Yeni Müzik Projesi**\n\n"
                "Proje adını yazın:",
                parse_mode='Markdown'
            )

        elif data == "music_add_existing":
            # Add to existing project
            state = self.music_project_state.get(user_id, {})
            pending_audio = state.get('pending_audio')

            if not pending_audio:
                await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
                return

            active_project = self.composer_agent.get_active_project(user_id)
            if not active_project:
                await query.edit_message_text("❌ Aktif proje bulunamadı")
                return

            # Show input type selection
            keyboard = [
                [
                    InlineKeyboardButton("🎵 Melodi", callback_data="input_melody"),
                    InlineKeyboardButton("🥁 Ritim", callback_data="input_rhythm")
                ],
                [
                    InlineKeyboardButton("🎸 Sample", callback_data="input_sample"),
                    InlineKeyboardButton("🎹 Arka Plan", callback_data="input_background")
                ],
                [
                    InlineKeyboardButton("🎤 Beatbox → 808", callback_data="beatbox_808"),
                    InlineKeyboardButton("🎤 Beatbox → 909", callback_data="beatbox_909")
                ],
                [
                    InlineKeyboardButton("🗣️ Çıplak Ses (Ham)", callback_data="input_raw_voice")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🎼 **{active_project['project_name']}** projesine ekleniyor\n\n"
                f"Bu ses ne olarak eklensin?\n\n"
                f"💡 **Beatbox:** Ağızla yapılan sesleri profesyonel davula dönüştürür\n"
                f"🗣️ **Çıplak Ses:** Sesi olduğu gibi ekler (efekt seçebilirsiniz)",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data.startswith("input_"):
            # Handle input type selection
            input_type = data.replace("input_", "")
            state = self.music_project_state.get(user_id, {})
            pending_audio = state.get('pending_audio')

            if not pending_audio:
                await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
                return

            active_project = self.composer_agent.get_active_project(user_id)
            if not active_project:
                await query.edit_message_text("❌ Aktif proje bulunamadı")
                return

            # Process the audio input
            await query.edit_message_text(
                f"⏳ Ses işleniyor ({input_type})..."
            )

            result = self.composer_agent.process_audio_input(
                project_id=active_project['project_id'],
                audio_path=pending_audio,
                input_type=input_type
            )

            # Clear pending state
            if user_id in self.music_project_state:
                del self.music_project_state[user_id]

            if result.get('success'):
                # Get project summary
                summary = self.composer_agent.get_project_summary(active_project['project_id'])
                input_count = summary.get('input_count', 1)

                keyboard = [
                    [
                        InlineKeyboardButton("🎹 Bestele", callback_data=f"compose_{active_project['project_id']}"),
                        InlineKeyboardButton("➕ Ses Ekle", callback_data="music_add_more")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    f"✅ **{input_type.title()}** eklendi!\n\n"
                    f"📋 Proje: **{active_project['project_name']}**\n"
                    f"🎵 Katman sayısı: {input_count}\n\n"
                    f"Devam etmek için seçin:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ Ses işlenemedi: {result.get('error', 'Bilinmeyen hata')}"
                )

        elif data.startswith("compose_"):
            # Start composition
            project_id = data.replace("compose_", "")

            await query.edit_message_text(
                "🎹 **Beste oluşturuluyor...**\n\n"
                "⏳ Bu işlem birkaç dakika sürebilir",
                parse_mode='Markdown'
            )

            result = self.composer_agent.compose_project(project_id)

            if result.get('success'):
                await query.edit_message_text(
                    f"🎉 **Beste Tamamlandı!**\n\n"
                    f"📋 Proje: **{result.get('project_name')}**\n"
                    f"⏱ Süre: {result.get('duration', 0):.1f}s\n"
                    f"🎵 Katmanlar: {result.get('layers', 0)}\n\n"
                    f"Ses dosyası gönderiliyor...",
                    parse_mode='Markdown'
                )

                # Send audio file
                audio_path = result.get('audio_path')
                if audio_path and os.path.exists(audio_path):
                    try:
                        await context.bot.send_audio(
                            chat_id=update.effective_chat.id,
                            audio=open(audio_path, 'rb'),
                            title=result.get('project_name', 'Composition'),
                            caption=f"🎵 {result.get('project_name')}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send audio: {e}")
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"Dosya yolu: `{audio_path}`",
                            parse_mode='Markdown'
                        )
            else:
                await query.edit_message_text(
                    f"❌ Beste başarısız: {result.get('error', 'Bilinmeyen hata')}"
                )

        elif data == "music_add_more":
            await query.edit_message_text(
                "🎵 **Yeni ses eklemek için:**\n\n"
                "Ses mesajı veya ses dosyası gönderin",
                parse_mode='Markdown'
            )

        elif data.startswith("beatbox_"):
            # Handle beatbox transformation
            kit = data.replace("beatbox_", "")  # 808 or 909
            state = self.music_project_state.get(user_id, {})
            pending_audio = state.get('pending_audio')

            if not pending_audio:
                await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
                return

            active_project = self.composer_agent.get_active_project(user_id)
            if not active_project:
                await query.edit_message_text("❌ Aktif proje bulunamadı")
                return

            # Process beatbox
            await query.edit_message_text(
                f"🎤 **Beatbox işleniyor...**\n\n"
                f"Kit: {kit.upper()}\n"
                f"⏳ Sesler algılanıyor ve dönüştürülüyor...",
                parse_mode='Markdown'
            )

            result = self.composer_agent.process_beatbox_input(
                project_id=active_project['project_id'],
                audio_path=pending_audio,
                kit=kit
            )

            # Clear pending state
            if user_id in self.music_project_state:
                del self.music_project_state[user_id]

            if result.get('success'):
                # Show detected sounds
                classifications = result.get('classifications', {})
                summary_text = ", ".join([f"{k}: {v}" for k, v in classifications.items() if v > 0])

                keyboard = [
                    [
                        InlineKeyboardButton("🎹 Bestele", callback_data=f"compose_{active_project['project_id']}"),
                        InlineKeyboardButton("➕ Ses Ekle", callback_data="music_add_more")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    f"✅ **Beatbox → {kit.upper()} Dönüşümü Tamamlandı!**\n\n"
                    f"📋 Proje: **{active_project['project_name']}**\n"
                    f"🎤 Algılanan sesler: {result.get('onset_count', 0)}\n"
                    f"🥁 Dağılım: {summary_text}\n"
                    f"⏱ Süre: {result.get('duration', 0):.1f}s\n\n"
                    f"✨ Orijinal ritim korunarak profesyonel {kit.upper()} kit'e dönüştürüldü!",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ Beatbox işlenemedi: {result.get('error', 'Bilinmeyen hata')}"
                )

        elif data == "input_raw_voice":
            # Handle raw voice - ask for timing and effect
            state = self.music_project_state.get(user_id, {})
            pending_audio = state.get('pending_audio')

            if not pending_audio:
                await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
                return

            active_project = self.composer_agent.get_active_project(user_id)
            if not active_project:
                await query.edit_message_text("❌ Aktif proje bulunamadı")
                return

            # Ask for effect selection
            keyboard = [
                [
                    InlineKeyboardButton("🔊 Ham (Efekt Yok)", callback_data="voice_effect_none"),
                    InlineKeyboardButton("🌀 Reverb", callback_data="voice_effect_reverb")
                ],
                [
                    InlineKeyboardButton("🔁 Delay/Echo", callback_data="voice_effect_delay"),
                    InlineKeyboardButton("🎤 AutoTune", callback_data="voice_effect_autotune")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🗣️ **Çıplak Ses Ekleniyor**\n\n"
                f"Projeye eklenecek: **{active_project['project_name']}**\n\n"
                f"Efekt seçin:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data.startswith("voice_effect_"):
            # Handle voice effect selection
            effect = data.replace("voice_effect_", "")
            state = self.music_project_state.get(user_id, {})
            pending_audio = state.get('pending_audio')

            if not pending_audio:
                await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
                return

            active_project = self.composer_agent.get_active_project(user_id)
            if not active_project:
                await query.edit_message_text("❌ Aktif proje bulunamadı")
                return

            # Process raw voice
            await query.edit_message_text(
                f"🗣️ Çıplak ses işleniyor ({effect})..."
            )

            result = self.composer_agent.add_raw_voice(
                project_id=active_project['project_id'],
                audio_path=pending_audio,
                start_time=0.0,  # Default to start
                effect=effect,
                label=f"Çıplak Ses ({effect})"
            )

            # Clear pending state
            if user_id in self.music_project_state:
                del self.music_project_state[user_id]

            if result.get('success'):
                # Get project summary
                summary = self.composer_agent.get_project_summary(active_project['project_id'])
                input_count = summary.get('input_count', 1)

                keyboard = [
                    [
                        InlineKeyboardButton("🎹 Bestele", callback_data=f"compose_{active_project['project_id']}"),
                        InlineKeyboardButton("➕ Ses Ekle", callback_data="music_add_more")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                effect_name = {
                    'none': 'Ham (efektsiz)',
                    'reverb': 'Reverb',
                    'delay': 'Delay/Echo',
                    'autotune': 'AutoTune'
                }.get(effect, effect)

                await query.edit_message_text(
                    f"✅ **Çıplak Ses Eklendi!**\n\n"
                    f"📋 Proje: **{active_project['project_name']}**\n"
                    f"🗣️ Efekt: {effect_name}\n"
                    f"⏱ Süre: {result.get('duration', 0):.1f}s\n"
                    f"🎵 Toplam katman: {input_count}",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ Ses işlenemedi: {result.get('error', 'Bilinmeyen hata')}"
                )

        elif data.startswith("style_"):
            # Style selection for new project
            style = data.replace("style_", "")
            context.user_data['selected_style'] = style

            await query.edit_message_text(
                f"✅ Stil seçildi: **{style}**\n\n"
                f"📝 Şimdi proje adını yazın:",
                parse_mode='Markdown'
            )

        # ========== GPU Processing Callbacks ==========
        elif data == "gpu_extract_melody":
            await self._process_gpu_task(query, user_id, 'extract_melody', context)

        elif data == "gpu_separate_stems":
            await self._process_gpu_task(query, user_id, 'separate_stems', context)

        elif data == "gpu_generate_music":
            # Show style selection for music generation
            keyboard = [
                [
                    InlineKeyboardButton("🎤 Hip-Hop", callback_data="gpu_gen_hip-hop"),
                    InlineKeyboardButton("🎸 Pop", callback_data="gpu_gen_pop")
                ],
                [
                    InlineKeyboardButton("🎹 Electronic", callback_data="gpu_gen_electronic"),
                    InlineKeyboardButton("☕ Lo-Fi", callback_data="gpu_gen_lofi")
                ],
                [
                    InlineKeyboardButton("🎻 Orchestral", callback_data="gpu_gen_orchestral"),
                    InlineKeyboardButton("🎷 Jazz", callback_data="gpu_gen_jazz")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "🎹 **AI Müzik Üretimi**\n\n"
                "Stil seçin:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data.startswith("gpu_gen_"):
            style = data.replace("gpu_gen_", "")
            await self._process_gpu_task(query, user_id, 'generate_music', context, style=style)

        elif data == "gpu_transform_melody":
            # Show style selection for melody transformation
            keyboard = [
                [
                    InlineKeyboardButton("🎸 Pop", callback_data="gpu_trans_pop"),
                    InlineKeyboardButton("🎤 Hip-Hop", callback_data="gpu_trans_hip-hop")
                ],
                [
                    InlineKeyboardButton("🎹 Electronic", callback_data="gpu_trans_electronic"),
                    InlineKeyboardButton("🎻 Orchestral", callback_data="gpu_trans_orchestral")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "🎨 **Melodi Stil Dönüşümü**\n\n"
                "Hedef stil seçin:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif data.startswith("gpu_trans_"):
            style = data.replace("gpu_trans_", "")
            await self._process_gpu_task(query, user_id, 'transform_melody', context, style=style)

        elif data == "music_back":
            # Go back to main music menu
            state = self.music_project_state.get(user_id, {})
            if state.get('pending_audio'):
                keyboard = [
                    [InlineKeyboardButton("🆕 Yeni Proje Oluştur", callback_data="music_new_project")],
                    [InlineKeyboardButton("🚀 GPU ile İşle (AI)", callback_data="music_gpu_process")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    "🎵 **Ses dosyası hazır**\n\nNe yapmak istersiniz?",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("🎵 Yeni ses gönderin")

    async def _process_gpu_task(self, query, user_id: str, operation: str,
                                 context: ContextTypes.DEFAULT_TYPE, style: str = None):
        """Process a GPU task via Colab"""
        state = self.music_project_state.get(user_id, {})
        pending_audio = state.get('pending_audio')

        if operation != 'generate_music' and not pending_audio:
            await query.edit_message_text("❌ Bekleyen ses dosyası bulunamadı")
            return

        # Check Colab availability
        if not self.colab_bridge.is_available():
            gradio_url = os.getenv('COLAB_GRADIO_URL', '')
            await query.edit_message_text(
                "❌ **Colab GPU erişilemez**\n\n"
                "Colab notebook'u açıp `launch_gradio()` çalıştırın.\n"
                f"Gradio URL: `{gradio_url or 'Ayarlanmamış'}`",
                parse_mode='Markdown'
            )
            return

        # Show processing message
        operation_names = {
            'extract_melody': '🎵 Melodi Çıkarma',
            'separate_stems': '🔀 Stem Ayırma',
            'generate_music': '🎹 AI Müzik Üretimi',
            'transform_melody': '🎨 Stil Dönüşümü'
        }

        await query.edit_message_text(
            f"🚀 **GPU İşlemi Başlıyor**\n\n"
            f"İşlem: {operation_names.get(operation, operation)}\n"
            f"{'Stil: ' + style if style else ''}\n\n"
            f"⏳ Bu işlem 30-120 saniye sürebilir...",
            parse_mode='Markdown'
        )

        try:
            # Perform operation
            if operation == 'extract_melody':
                result = self.colab_bridge.extract_melody(pending_audio)
            elif operation == 'separate_stems':
                result = self.colab_bridge.separate_stems(pending_audio)
            elif operation == 'generate_music':
                from modules.colab.colab_bridge import get_style_prompt
                prompt = get_style_prompt(style) if style else "upbeat electronic music"
                result = self.colab_bridge.generate_music(prompt, duration=30)
            elif operation == 'transform_melody':
                from modules.colab.colab_bridge import get_style_prompt
                style_prompt = get_style_prompt(style) if style else "professional pop"
                result = self.colab_bridge.transform_melody(pending_audio, style_prompt, duration=30)
            else:
                result = {'success': False, 'error': f'Unknown operation: {operation}'}

            if result.get('success'):
                # Show results based on operation
                if operation == 'extract_melody':
                    await query.edit_message_text(
                        f"✅ **Melodi Çıkarma Tamamlandı!**\n\n"
                        f"🎵 Nota sayısı: {result.get('note_count', 'N/A')}\n"
                        f"🎼 Anahtar: {result.get('key', 'N/A')}\n"
                        f"⏱️ Tempo: {result.get('tempo', 'N/A')} BPM\n"
                        f"⏳ Süre: {result.get('duration', 'N/A')}\n\n"
                        f"MIDI dosyası hazır!",
                        parse_mode='Markdown'
                    )
                elif operation == 'separate_stems':
                    stems = result.get('stems', {})
                    await query.edit_message_text(
                        f"✅ **Stem Ayırma Tamamlandı!**\n\n"
                        f"🎤 Vokal: {'Hazır' if stems.get('vocals') else 'Yok'}\n"
                        f"🎸 Enstrümental: {'Hazır' if stems.get('no_vocals') else 'Yok'}",
                        parse_mode='Markdown'
                    )
                elif operation == 'generate_music':
                    audio_path = result.get('audio_path')
                    await query.edit_message_text(
                        f"✅ **AI Müzik Üretildi!**\n\n"
                        f"🎵 Stil: {style}\n"
                        f"⏱️ Süre: {result.get('duration', 30)}s",
                        parse_mode='Markdown'
                    )
                    # Try to send audio file
                    if audio_path and os.path.exists(audio_path):
                        try:
                            await context.bot.send_audio(
                                chat_id=query.message.chat_id,
                                audio=open(audio_path, 'rb'),
                                title=f"AI Music - {style}",
                                caption=f"🎹 AI Generated: {style}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send audio: {e}")
                elif operation == 'transform_melody':
                    audio_path = result.get('audio_path')
                    await query.edit_message_text(
                        f"✅ **Stil Dönüşümü Tamamlandı!**\n\n"
                        f"🎨 Hedef stil: {style}",
                        parse_mode='Markdown'
                    )
                    # Try to send audio file
                    if audio_path and os.path.exists(audio_path):
                        try:
                            await context.bot.send_audio(
                                chat_id=query.message.chat_id,
                                audio=open(audio_path, 'rb'),
                                title=f"Transformed - {style}",
                                caption=f"🎨 Style Transfer: {style}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send audio: {e}")
            else:
                await query.edit_message_text(
                    f"❌ **İşlem Başarısız**\n\n"
                    f"Hata: {result.get('error', 'Bilinmeyen hata')}",
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"GPU task failed: {e}")
            await query.edit_message_text(
                f"❌ **GPU İşlemi Başarısız**\n\n"
                f"Hata: {str(e)}",
                parse_mode='Markdown'
            )

    async def handle_project_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle project name input"""
        if not context.user_data.get('awaiting_project_name'):
            return False  # Not waiting for project name

        user_id = str(update.effective_user.id)
        project_name = update.message.text

        # Clear flag
        context.user_data['awaiting_project_name'] = False

        # Show style selection
        keyboard = [
            [
                InlineKeyboardButton("🎷 Jazz", callback_data="create_jazz"),
                InlineKeyboardButton("🎤 Pop", callback_data="create_pop"),
                InlineKeyboardButton("🎧 Club", callback_data="create_club")
            ],
            [
                InlineKeyboardButton("🎻 Classical", callback_data="create_classical"),
                InlineKeyboardButton("🌙 Ambient", callback_data="create_ambient"),
                InlineKeyboardButton("🎸 Rock", callback_data="create_rock")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Store project name
        context.user_data['pending_project_name'] = project_name

        await update.message.reply_text(
            f"📝 Proje adı: **{project_name}**\n\n"
            f"🎵 Müzik stilini seçin:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return True

    async def create_project_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle project creation with style"""
        query = update.callback_query
        await query.answer()

        user_id = str(update.effective_user.id)
        style = query.data.replace("create_", "")
        project_name = context.user_data.get('pending_project_name', 'Untitled Project')

        # Create the project
        project = self.composer_agent.create_project(
            user_id=user_id,
            project_name=project_name,
            style=style
        )

        if not project:
            await query.edit_message_text("❌ Proje oluşturulamadı")
            return

        # Add pending audio if exists
        state = self.music_project_state.get(user_id, {})
        pending_audio = state.get('pending_audio')

        if pending_audio and os.path.exists(pending_audio):
            # Process as melody by default
            result = self.composer_agent.process_audio_input(
                project_id=project['project_id'],
                audio_path=pending_audio,
                input_type='melody'
            )

            # Clear pending state
            if user_id in self.music_project_state:
                del self.music_project_state[user_id]

            keyboard = [
                [
                    InlineKeyboardButton("🎹 Bestele", callback_data=f"compose_{project['project_id']}"),
                    InlineKeyboardButton("➕ Ses Ekle", callback_data="music_add_more")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🎼 **Proje Oluşturuldu!**\n\n"
                f"📋 Ad: **{project_name}**\n"
                f"🎵 Stil: {style}\n"
                f"🆔 ID: `{project['project_id']}`\n\n"
                f"✅ Ses dosyası **Ana Melodi** olarak eklendi\n\n"
                f"Devam etmek için:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"🎼 **Proje Oluşturuldu!**\n\n"
                f"📋 Ad: **{project_name}**\n"
                f"🎵 Stil: {style}\n"
                f"🆔 ID: `{project['project_id']}`\n\n"
                f"Şimdi ses mesajı veya ses dosyası gönderin",
                parse_mode='Markdown'
            )

    async def compose_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /compose command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        user_id = str(update.effective_user.id)
        active_project = self.composer_agent.get_active_project(user_id)

        if not active_project:
            await update.message.reply_text(
                "❌ Aktif müzik projeniz yok.\n\n"
                "Yeni proje için ses mesajı gönderin",
                parse_mode='Markdown'
            )
            return

        # Get project summary
        summary = self.composer_agent.get_project_summary(active_project['project_id'])

        if summary.get('input_count', 0) == 0:
            await update.message.reply_text(
                f"❌ **{active_project['project_name']}** projesinde henüz ses yok.\n\n"
                f"Önce ses mesajı gönderin",
                parse_mode='Markdown'
            )
            return

        # Start composing
        processing_msg = await update.message.reply_text(
            f"🎹 **{active_project['project_name']}** besteleniyor...\n\n"
            f"⏳ Bu işlem birkaç dakika sürebilir",
            parse_mode='Markdown'
        )

        result = self.composer_agent.compose_project(active_project['project_id'])

        if result.get('success'):
            await processing_msg.edit_text(
                f"🎉 **Beste Tamamlandı!**\n\n"
                f"📋 Proje: **{result.get('project_name')}**\n"
                f"⏱ Süre: {result.get('duration', 0):.1f}s\n"
                f"🎵 Katmanlar: {result.get('layers', 0)}",
                parse_mode='Markdown'
            )

            # Send audio file
            audio_path = result.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                try:
                    await update.message.reply_audio(
                        audio=open(audio_path, 'rb'),
                        title=result.get('project_name', 'Composition'),
                        caption=f"🎵 {result.get('project_name')}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send audio: {e}")
        else:
            await processing_msg.edit_text(
                f"❌ Beste başarısız: {result.get('error', 'Bilinmeyen hata')}"
            )

    async def myprojects_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /myprojects command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        user_id = str(update.effective_user.id)
        projects = self.agent_memory.get_user_projects(user_id, limit=5)

        if not projects:
            await update.message.reply_text(
                "📂 Henüz müzik projeniz yok.\n\n"
                "Yeni proje için ses mesajı gönderin",
                parse_mode='Markdown'
            )
            return

        text = "📂 **Müzik Projeleriniz**\n\n"

        for p in projects:
            status_emoji = {
                'draft': '📝',
                'composing': '⏳',
                'completed': '✅',
                'failed': '❌'
            }.get(p['status'], '❓')

            text += f"{status_emoji} **{p['project_name']}**\n"
            text += f"   Stil: {p['style']} | Durum: {p['status']}\n"
            text += f"   ID: `{p['project_id']}`\n\n"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim / Unauthorized access")
            return

        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)

        # Clear music project state
        if user_id in self.music_project_state:
            del self.music_project_state[user_id]
            context.user_data.clear()
            await update.message.reply_text(
                "🛑 Müzik projesi işlemi iptal edildi",
                parse_mode='Markdown'
            )
            return

        if chat_id in self.active_productions:
            task_info = self.active_productions[chat_id]
            del self.active_productions[chat_id]

            await update.message.reply_text(
                f"🛑 **Üretim İptal Edildi**\n\n"
                f"Task ID: `{task_info['task_id']}`\n"
                f"İptal zamanı: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "ℹ️ Aktif üretim bulunamadı",
                parse_mode='Markdown'
            )

    # ========== MUSIC WIZARD (ConversationHandler) ==========

    async def start_music_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry point for music wizard via /create_music command"""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ Yetkisiz erişim")
            return ConversationHandler.END

        await update.message.reply_text(
            "🎵 **Müzik Sihirbazı Başladı!**\n\n"
            "Ses mesajı veya ses dosyası gönderin.\n"
            "İptal için /cancel yazın",
            parse_mode='Markdown'
        )
        return WAITING_AUDIO

    async def music_voice_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry point via voice message - wraps existing handler"""
        if not self._is_authorized(update.effective_user.id):
            return ConversationHandler.END

        # Use existing voice handler logic
        await self.handle_voice_message(update, context)
        user_id = str(update.effective_user.id)

        # Check if user has active project
        active_project = self.composer_agent.get_active_project(user_id)
        if active_project:
            return CHOOSE_ACTION
        # Aktif proje yok ama buton gösteriliyor, CHOOSE_ACTION döner
        return CHOOSE_ACTION

    async def music_audio_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry point via audio file - wraps existing handler"""
        if not self._is_authorized(update.effective_user.id):
            return ConversationHandler.END

        # Use existing audio handler logic
        await self.handle_audio_message(update, context)
        user_id = str(update.effective_user.id)

        # Check if user has active project
        active_project = self.composer_agent.get_active_project(user_id)
        if active_project:
            return CHOOSE_ACTION
        # Aktif proje yok ama buton gösteriliyor, CHOOSE_ACTION döner
        return CHOOSE_ACTION

    async def choose_action_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle action choice: add to existing or create new project"""
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "music_add_existing":
            # Show input type selection (reuse existing logic)
            await self.music_callback(update, context)
            return INPUT_TYPE
        elif data == "music_new_project":
            # Ask for project name
            await query.edit_message_text(
                "📝 **Yeni Proje**\n\nProjein adını yazın:",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_project_name'] = True
            return AWAITING_PROJECT_NAME

        return CHOOSE_ACTION

    async def wizard_receive_project_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive project name in wizard flow"""
        project_name = update.message.text.strip()

        if len(project_name) < 2:
            await update.message.reply_text("❌ Proje adı en az 2 karakter olmalı")
            return AWAITING_PROJECT_NAME

        context.user_data['pending_project_name'] = project_name
        context.user_data['awaiting_project_name'] = False

        # Show style selection
        keyboard = [
            [
                InlineKeyboardButton("🎷 Jazz", callback_data="create_jazz"),
                InlineKeyboardButton("🎸 Pop", callback_data="create_pop")
            ],
            [
                InlineKeyboardButton("🎹 Club", callback_data="create_club"),
                InlineKeyboardButton("🎻 Classical", callback_data="create_classical")
            ],
            [
                InlineKeyboardButton("🌊 Ambient", callback_data="create_ambient"),
                InlineKeyboardButton("🎤 HipHop", callback_data="create_hiphop")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📋 Proje: **{project_name}**\n\n"
            f"Müzik tarzını seçin:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return SELECT_STYLE

    async def wizard_select_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle style selection in wizard"""
        query = update.callback_query
        await query.answer()

        style = query.data.replace("create_", "")
        user_id = str(update.effective_user.id)
        project_name = context.user_data.get('pending_project_name', 'Yeni Proje')

        # Create project using existing logic
        project = self.composer_agent.create_project(user_id, project_name, style)

        if not project:
            await query.edit_message_text("❌ Proje oluşturulamadı")
            return ConversationHandler.END

        # Process pending audio if exists
        state = self.music_project_state.get(user_id, {})
        pending_audio = state.get('pending_audio')

        if pending_audio and os.path.exists(pending_audio):
            result = self.composer_agent.process_audio_input(
                project_id=project['project_id'],
                audio_path=pending_audio,
                input_type='melody'
            )
            if user_id in self.music_project_state:
                del self.music_project_state[user_id]

        # Show project dashboard
        return await self.show_project_dashboard(query, context, project['project_id'])

    async def wizard_input_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle input type selection in wizard"""
        # Reuse existing music_callback logic
        await self.music_callback(update, context)
        return PROJECT_MENU

    async def wizard_project_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle project menu actions"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = str(update.effective_user.id)

        if data.startswith("compose_"):
            # Start composition
            project_id = data.replace("compose_", "")
            await query.edit_message_text("🎹 Besteleniyor... Lütfen bekleyin")

            result = self.composer_agent.compose_project(project_id)

            if result.get('success'):
                audio_path = result.get('audio_path')
                if audio_path and os.path.exists(audio_path):
                    await query.message.reply_audio(
                        audio=open(audio_path, 'rb'),
                        title=result.get('project_name', 'Composition'),
                        caption=f"🎵 {result.get('project_name')} - {result.get('duration', 0):.1f}s"
                    )
                await query.edit_message_text(
                    f"✅ **Beste Tamamlandı!**\n\n"
                    f"📋 Proje: {result.get('project_name')}\n"
                    f"⏱ Süre: {result.get('duration', 0):.1f}s\n"
                    f"🎵 Katmanlar: {result.get('layers', 0)}",
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            else:
                await query.edit_message_text(f"❌ Hata: {result.get('error')}")
                return PROJECT_MENU

        elif data == "music_add_more":
            await query.edit_message_text(
                "🎵 Yeni ses eklemek için ses mesajı veya dosya gönderin",
                parse_mode='Markdown'
            )
            return WAITING_AUDIO

        elif data.startswith("manage_"):
            project_id = data.replace("manage_", "")
            return await self.show_layer_management(query, context, project_id)

        elif data.startswith("preview_"):
            project_id = data.replace("preview_", "")
            return await self.generate_preview(query, context, project_id)

        return PROJECT_MENU

    async def show_project_dashboard(self, query, context, project_id: str) -> int:
        """Display project dashboard with layer list"""
        user_id = str(query.from_user.id)
        project = self.composer_agent.get_active_project(user_id)

        if not project:
            await query.edit_message_text("❌ Proje bulunamadı")
            return ConversationHandler.END

        summary = self.composer_agent.get_project_summary(project_id)
        timeline = summary.get('timeline', {})
        layers = timeline.get('layers', [])

        # Build layer list text
        layer_text = ""
        for i, layer in enumerate(layers, 1):
            layer_type = layer.get('type', 'unknown').upper()
            start = layer.get('start', 0)
            end = layer.get('end', 0)
            layer_text += f"{i}. {layer_type} [{start:.0f}s-{end:.0f}s]\n"

        if not layer_text:
            layer_text = "Henüz katman yok\n"

        keyboard = [
            [
                InlineKeyboardButton("🎹 Bestele", callback_data=f"compose_{project_id}"),
                InlineKeyboardButton("➕ Ses Ekle", callback_data="music_add_more")
            ],
            [
                InlineKeyboardButton("📊 Katmanlar", callback_data=f"manage_{project_id}"),
                InlineKeyboardButton("👁️ Önizle", callback_data=f"preview_{project_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"🎼 **{project['project_name']}**\n"
            f"Stil: {project['style']} | Katman: {summary.get('input_count', 0)}\n\n"
            f"**KATMANLAR:**\n{layer_text}\n"
            f"Ne yapmak istersiniz?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return PROJECT_MENU

    async def show_layer_management(self, query, context, project_id: str) -> int:
        """Show layer management options"""
        summary = self.composer_agent.get_project_summary(project_id)
        timeline = summary.get('timeline', {})
        layers = timeline.get('layers', [])

        keyboard = []
        for i, layer in enumerate(layers):
            input_id = layer.get('input_id', f'layer_{i}')
            layer_type = layer.get('type', 'unknown')
            keyboard.append([
                InlineKeyboardButton(
                    f"🎵 {i+1}. {layer_type.upper()}",
                    callback_data=f"layer_edit_{input_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("◀️ Geri", callback_data=f"back_to_menu_{project_id}")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📊 **Katman Yönetimi**\n\n"
            "Düzenlemek istediğiniz katmanı seçin:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return MANAGE_LAYERS

    async def generate_preview(self, query, context, project_id: str) -> int:
        """Generate and send preview"""
        await query.edit_message_text("👁️ Önizleme oluşturuluyor...")

        result = self.composer_agent.compose_project(project_id)

        if result.get('success'):
            audio_path = result.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                await query.message.reply_audio(
                    audio=open(audio_path, 'rb'),
                    title=f"Önizleme - {result.get('project_name')}",
                    caption="👁️ Önizleme (tam versiyon)"
                )
        else:
            await query.message.reply_text(f"❌ Önizleme oluşturulamadı: {result.get('error')}")

        # Return to project menu
        user_id = str(query.from_user.id)
        project = self.composer_agent.get_active_project(user_id)
        if project:
            return await self.show_project_dashboard(query, context, project['project_id'])
        return PROJECT_MENU

    async def cancel_music_wizard(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the music wizard"""
        user_id = str(update.effective_user.id)

        # Clear states
        if user_id in self.music_project_state:
            del self.music_project_state[user_id]
        context.user_data.clear()

        await update.message.reply_text(
            "🛑 **Müzik Sihirbazı İptal Edildi**\n\n"
            "Tekrar başlamak için ses mesajı gönderin veya /create_music yazın",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    def _create_music_conversation_handler(self) -> ConversationHandler:
        """Create the music wizard conversation handler"""
        return ConversationHandler(
            entry_points=[
                CommandHandler("create_music", self.start_music_wizard),
                MessageHandler(filters.VOICE, self.music_voice_entry),
                MessageHandler(filters.AUDIO, self.music_audio_entry),
            ],
            states={
                WAITING_AUDIO: [
                    MessageHandler(filters.VOICE, self.music_voice_entry),
                    MessageHandler(filters.AUDIO, self.music_audio_entry),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music_ai_prompt),
                ],
                CHOOSE_ACTION: [
                    CallbackQueryHandler(self.choose_action_callback, pattern="^music_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music_ai_prompt),
                ],
                AWAITING_PROJECT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.wizard_receive_project_name)
                ],
                SELECT_STYLE: [
                    CallbackQueryHandler(self.wizard_select_style, pattern="^create_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music_ai_prompt),
                ],
                INPUT_TYPE: [
                    CallbackQueryHandler(self.wizard_input_type,
                        pattern="^input_|^beatbox_|^voice_effect_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music_ai_prompt),
                ],
                PROJECT_MENU: [
                    CallbackQueryHandler(self.wizard_project_menu,
                        pattern="^compose_|^music_add|^manage_|^preview_|^back_to_menu_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music_ai_prompt),
                ],
                MANAGE_LAYERS: [
                    CallbackQueryHandler(self.wizard_project_menu, pattern="^layer_|^back_to_menu_"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music_ai_prompt),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_music_wizard),
                CommandHandler("myprojects", self.myprojects_command),
            ],
            name="music_wizard",
            allow_reentry=True,
        )

    async def handle_music_ai_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle AI prompts within music wizard - prompt-based control"""
        if not self._is_authorized(update.effective_user.id):
            return ConversationHandler.END

        user_id = str(update.effective_user.id)
        user_prompt = update.message.text.strip()

        # Get active project
        active_project = self.composer_agent.get_active_project(user_id)

        # Send processing message
        processing_msg = await update.message.reply_text(
            "🤖 AI analiz ediyor...\n⏳ Lütfen bekleyin..."
        )

        try:
            # Build context for AI
            context_info = ""
            if active_project:
                layers = active_project.get('layers', [])
                context_info = f"""
Aktif Proje: {active_project.get('name')}
Stil: {active_project.get('style')}
Katmanlar: {len(layers)}
Katman Detayları: {', '.join([f"{l.get('type', 'unknown')}({l.get('name', 'unnamed')})" for l in layers]) if layers else 'Yok'}
"""

            # Use Chef AI to understand intent
            ai_prompt = f"""
Kullanıcı müzik projesi üzerinde çalışıyor. Prompt'u analiz et ve ne yapmak istediğini belirle.

{context_info}

Kullanıcı mesajı: "{user_prompt}"

Olası işlemler:
1. generate_music: AI ile yeni müzik üret (prompt: trap beat, lo-fi, jazz vb.)
2. add_layer: Projeye katman ekle
3. compose: Projeyi bestele/mixle
4. change_style: Stili değiştir
5. extract_melody: Melodiyi çıkar
6. separate_stems: Vokal/enstrüman ayır
7. question: Genel soru/yardım

JSON formatında cevap ver:
{{"action": "...", "params": {{}}, "message": "kullanıcıya gösterilecek mesaj"}}
"""

            result = self.chef_ai.execute_order(
                raw_prompt=ai_prompt,
                user_id=user_id
            )

            # Parse AI response
            analysis = result.get('analysis', {})
            ai_response = result.get('result', {}).get('response', '')

            # Try to extract action from AI
            action = None
            params = {}

            # Simple keyword detection as fallback
            prompt_lower = user_prompt.lower()

            if any(k in prompt_lower for k in ['üret', 'generate', 'oluştur', 'yap', 'beat', 'müzik']):
                action = 'generate_music'
                # Extract style from prompt
                params['prompt'] = user_prompt
                params['duration'] = 30

            elif any(k in prompt_lower for k in ['bestele', 'compose', 'mixle', 'bitir']):
                action = 'compose'

            elif any(k in prompt_lower for k in ['melodi', 'melody', 'nota']):
                action = 'extract_melody'

            elif any(k in prompt_lower for k in ['vokal', 'vocal', 'ayır', 'separate']):
                action = 'separate_stems'

            elif any(k in prompt_lower for k in ['düzelt', 'quantize', 'grid', 'dalgalı', 'düzgün', 'hizala']):
                action = 'quantize_midi'

            elif any(k in prompt_lower for k in ['piyano', 'piano', 'bas', 'synth', 'çal', 'enstrüman', 'instrument', 'gitar', 'organ']):
                action = 'midi_to_audio'
                # Extract instrument from prompt
                if 'piyano' in prompt_lower or 'piano' in prompt_lower:
                    params['instrument'] = 'piano'
                elif 'bas' in prompt_lower:
                    params['instrument'] = 'bass'
                elif 'synth' in prompt_lower:
                    params['instrument'] = 'synth'
                elif 'gitar' in prompt_lower or 'guitar' in prompt_lower:
                    params['instrument'] = 'guitar'
                elif 'organ' in prompt_lower:
                    params['instrument'] = 'organ'
                else:
                    params['instrument'] = 'piano'

            elif any(k in prompt_lower for k in ['transpose', 'ton', 'yükselt', 'alçalt', 'perde']):
                action = 'transpose_midi'
                # Extract semitones
                import re
                match = re.search(r'[-+]?\d+', prompt_lower)
                if match:
                    params['semitones'] = int(match.group())
                elif 'yükselt' in prompt_lower:
                    params['semitones'] = 2
                elif 'alçalt' in prompt_lower:
                    params['semitones'] = -2
                else:
                    params['semitones'] = 0

            # Execute action
            if action == 'generate_music' and active_project:
                await processing_msg.edit_text("🎵 AI ile müzik üretiliyor...\n⏳ Bu 30-60 saniye sürebilir...")

                # Use ColabBridge for GPU generation
                gen_result = self.colab_bridge.generate_music(
                    prompt=params.get('prompt', user_prompt),
                    duration=params.get('duration', 30)
                )

                if gen_result.get('success'):
                    audio_path = gen_result.get('audio_path')
                    if audio_path and os.path.exists(audio_path):
                        # Add to project as layer
                        add_result = self.composer_agent.process_audio_input(
                            project_id=active_project['project_id'],
                            audio_path=audio_path,
                            input_type='sample'
                        )

                        await update.message.reply_audio(
                            audio=open(audio_path, 'rb'),
                            title="AI Generated",
                            caption=f"🎵 AI ile üretildi: {user_prompt[:50]}..."
                        )
                        await processing_msg.edit_text(
                            f"✅ Müzik üretildi ve projeye eklendi!\n\n"
                            f"📋 Proje: {active_project.get('name')}\n"
                            f"🎯 Prompt: {user_prompt[:100]}"
                        )
                        return PROJECT_MENU
                else:
                    await processing_msg.edit_text(f"❌ Üretim hatası: {gen_result.get('error', 'Bilinmeyen')}")
                    return PROJECT_MENU

            elif action == 'compose' and active_project:
                await processing_msg.edit_text("🎹 Besteleniyor...")
                comp_result = self.composer_agent.compose_project(active_project['project_id'])

                if comp_result.get('success'):
                    audio_path = comp_result.get('audio_path')
                    if audio_path and os.path.exists(audio_path):
                        await update.message.reply_audio(
                            audio=open(audio_path, 'rb'),
                            title=comp_result.get('project_name', 'Composition'),
                            caption=f"🎵 {comp_result.get('project_name')} - {comp_result.get('duration', 0):.1f}s"
                        )
                    await processing_msg.edit_text("✅ Beste tamamlandı!")
                    return ConversationHandler.END
                else:
                    await processing_msg.edit_text(f"❌ Hata: {comp_result.get('error')}")
                    return PROJECT_MENU

            elif action == 'extract_melody':
                # First check pending_audio, then layers
                audio_path = None
                state = self.music_project_state.get(user_id, {})
                pending_audio = state.get('pending_audio')

                if pending_audio and os.path.exists(pending_audio):
                    audio_path = pending_audio
                elif active_project:
                    layers = active_project.get('layers', [])
                    if layers:
                        last_layer = layers[-1]
                        audio_path = last_layer.get('audio_path')

                if audio_path and os.path.exists(audio_path):
                    await processing_msg.edit_text("🎼 Melodi çıkarılıyor... (GPU işlemi)")
                    melody_result = self.colab_bridge.extract_melody(audio_path)
                    if melody_result.get('success'):
                        # MIDI dosyası varsa gönder
                        midi_path = melody_result.get('midi_path')
                        if midi_path and os.path.exists(midi_path):
                            # MIDI path'i state'e kaydet (sonraki işlemler için)
                            state['last_midi_path'] = midi_path
                            self.music_project_state[user_id] = state

                            await update.message.reply_document(
                                document=open(midi_path, 'rb'),
                                filename=f"melody_{user_id}.mid",
                                caption=f"🎼 **Melodi MIDI Dosyası**\n\n"
                                        f"🎵 Nota sayısı: {melody_result.get('note_count', 0)}\n"
                                        f"🎹 Ton: {melody_result.get('key', 'N/A')}\n"
                                        f"🥁 Tempo: {melody_result.get('tempo', 'N/A')} BPM\n\n"
                                        f"💡 Şimdi dene:\n"
                                        f"• 'notalari düzelt'\n"
                                        f"• 'piyano ile çal'\n"
                                        f"• 'tonu 2 yükselt'",
                                parse_mode='Markdown'
                            )
                        # Sonraki adımlar için menü göster
                        keyboard = [
                            [InlineKeyboardButton("🎹 Bu melodiyi dönüştür", callback_data="music_transform")],
                            [InlineKeyboardButton("🎵 Yeni müzik üret", callback_data="music_generate")],
                            [InlineKeyboardButton("📁 Projeye ekle", callback_data="music_add_layer")],
                        ]
                        await processing_msg.edit_text(
                            f"✅ Melodi çıkarıldı!\n\n"
                            f"🎵 Nota sayısı: {melody_result.get('note_count', 0)}\n"
                            f"🎹 Ton: {melody_result.get('key', 'N/A')}\n"
                            f"🥁 Tempo: {melody_result.get('tempo', 'N/A')} BPM\n\n"
                            f"Şimdi ne yapmak istersiniz?",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    else:
                        await processing_msg.edit_text(f"❌ Melodi çıkarma hatası: {melody_result.get('error', 'Bilinmeyen')}")
                else:
                    await processing_msg.edit_text("❌ İşlenecek ses dosyası bulunamadı. Önce bir ses gönderin.")
                return PROJECT_MENU if active_project else CHOOSE_ACTION

            elif action == 'separate_stems':
                # First check pending_audio, then layers
                audio_path = None
                state = self.music_project_state.get(user_id, {})
                pending_audio = state.get('pending_audio')

                if pending_audio and os.path.exists(pending_audio):
                    audio_path = pending_audio
                elif active_project:
                    layers = active_project.get('layers', [])
                    if layers:
                        last_layer = layers[-1]
                        audio_path = last_layer.get('audio_path')

                if audio_path and os.path.exists(audio_path):
                    await processing_msg.edit_text("🎚️ Vokal/Enstrüman ayrılıyor... (GPU işlemi)")
                    stem_result = self.colab_bridge.separate_stems(audio_path)
                    if stem_result.get('success'):
                        stems = stem_result.get('stems', {})
                        if stems.get('vocals'):
                            await update.message.reply_audio(
                                audio=open(stems['vocals'], 'rb'),
                                title="Vocals",
                                caption="🎤 Vokal"
                            )
                        if stems.get('no_vocals'):
                            await update.message.reply_audio(
                                audio=open(stems['no_vocals'], 'rb'),
                                title="Instrumental",
                                caption="🎸 Enstrümantal"
                            )
                        await processing_msg.edit_text("✅ Stem ayrımı tamamlandı!")
                    else:
                        await processing_msg.edit_text(f"❌ Stem ayırma hatası: {stem_result.get('error', 'Bilinmeyen')}")
                else:
                    await processing_msg.edit_text("❌ İşlenecek ses dosyası bulunamadı. Önce bir ses gönderin.")
                return PROJECT_MENU if active_project else CHOOSE_ACTION

            elif action == 'quantize_midi':
                # MIDI notalarini düzelt
                state = self.music_project_state.get(user_id, {})
                midi_path = state.get('last_midi_path')

                if not midi_path or not os.path.exists(midi_path):
                    await processing_msg.edit_text(
                        "❌ MIDI dosyası bulunamadı.\n\n"
                        "💡 Önce ses gönderin ve 'melodiyi çıkar' deyin."
                    )
                    return PROJECT_MENU if active_project else CHOOSE_ACTION

                await processing_msg.edit_text("🎹 Notalar düzeltiliyor... (GPU işlemi)")
                result = self.colab_bridge.quantize_midi(midi_path)

                if result.get('success'):
                    new_midi = result.get('midi_path')
                    # State'i güncelle
                    state['last_midi_path'] = new_midi
                    self.music_project_state[user_id] = state

                    await update.message.reply_document(
                        document=open(new_midi, 'rb'),
                        filename=f"quantized_{user_id}.mid",
                        caption=f"🎹 **Notalar Düzeltildi!**\n\n"
                                f"📊 Toplam nota: {result.get('note_count', 0)}\n"
                                f"✅ Düzeltilen: {result.get('corrections', 0)}\n\n"
                                f"💡 Şimdi 'piyano ile çal' diyebilirsiniz!",
                        parse_mode='Markdown'
                    )
                    await processing_msg.edit_text("✅ Notalar düzeltildi!")
                else:
                    await processing_msg.edit_text(f"❌ Hata: {result.get('error', 'Bilinmeyen')}")
                return PROJECT_MENU if active_project else CHOOSE_ACTION

            elif action == 'midi_to_audio':
                # MIDI'yi enstrüman ile çal
                state = self.music_project_state.get(user_id, {})
                midi_path = state.get('last_midi_path')
                instrument = params.get('instrument', 'piano')

                if not midi_path or not os.path.exists(midi_path):
                    await processing_msg.edit_text(
                        "❌ MIDI dosyası bulunamadı.\n\n"
                        "💡 Önce ses gönderin ve 'melodiyi çıkar' deyin."
                    )
                    return PROJECT_MENU if active_project else CHOOSE_ACTION

                instrument_names = {
                    'piano': 'Piyano 🎹',
                    'bass': 'Bas 🎸',
                    'synth': 'Synth 🎛️',
                    'guitar': 'Gitar 🎸',
                    'organ': 'Org 🎹'
                }
                await processing_msg.edit_text(f"🎵 {instrument_names.get(instrument, instrument)} ile çalınıyor... (GPU işlemi)")
                result = self.colab_bridge.midi_to_audio(midi_path, instrument)

                if result.get('success'):
                    audio_path = result.get('audio_path')
                    await update.message.reply_audio(
                        audio=open(audio_path, 'rb'),
                        title=f"MIDI - {instrument.title()}",
                        caption=f"🎵 **{instrument_names.get(instrument, instrument)}**\n\n"
                                f"⏱️ Süre: {result.get('duration', 0):.1f}s\n\n"
                                f"💡 Başka enstrüman için: 'bas ile çal', 'gitar ile çal'",
                        parse_mode='Markdown'
                    )
                    await processing_msg.edit_text(f"✅ {instrument_names.get(instrument, instrument)} ile çalındı!")
                else:
                    await processing_msg.edit_text(f"❌ Hata: {result.get('error', 'Bilinmeyen')}")
                return PROJECT_MENU if active_project else CHOOSE_ACTION

            elif action == 'transpose_midi':
                # MIDI tonunu değiştir
                state = self.music_project_state.get(user_id, {})
                midi_path = state.get('last_midi_path')
                semitones = params.get('semitones', 0)

                if not midi_path or not os.path.exists(midi_path):
                    await processing_msg.edit_text(
                        "❌ MIDI dosyası bulunamadı.\n\n"
                        "💡 Önce ses gönderin ve 'melodiyi çıkar' deyin."
                    )
                    return PROJECT_MENU if active_project else CHOOSE_ACTION

                if semitones == 0:
                    await processing_msg.edit_text(
                        "❓ Kaç ton değiştirmek istiyorsunuz?\n\n"
                        "💡 Örnek:\n"
                        "• 'tonu 2 yükselt'\n"
                        "• 'tonu 3 alçalt'\n"
                        "• 'transpose +5'"
                    )
                    return PROJECT_MENU if active_project else CHOOSE_ACTION

                direction = "yukarı ⬆️" if semitones > 0 else "aşağı ⬇️"
                await processing_msg.edit_text(f"🎼 Ton {abs(semitones)} yarım adım {direction} taşınıyor...")
                result = self.colab_bridge.transpose_midi(midi_path, semitones)

                if result.get('success'):
                    new_midi = result.get('midi_path')
                    # State'i güncelle
                    state['last_midi_path'] = new_midi
                    self.music_project_state[user_id] = state

                    await update.message.reply_document(
                        document=open(new_midi, 'rb'),
                        filename=f"transposed_{user_id}.mid",
                        caption=f"🎼 **Ton Değiştirildi!**\n\n"
                                f"📊 {semitones:+d} yarım adım\n"
                                f"🎵 Nota sayısı: {result.get('note_count', 0)}\n\n"
                                f"💡 Şimdi 'piyano ile çal' diyebilirsiniz!",
                        parse_mode='Markdown'
                    )
                    await processing_msg.edit_text(f"✅ Ton {abs(semitones)} yarım adım {direction} taşındı!")
                else:
                    await processing_msg.edit_text(f"❌ Hata: {result.get('error', 'Bilinmeyen')}")
                return PROJECT_MENU if active_project else CHOOSE_ACTION

            else:
                # General question - use Chef AI response
                await processing_msg.edit_text(
                    f"🤖 **AI Yanıtı:**\n\n"
                    f"{ai_response if ai_response else 'Anlamadım. Şunları deneyebilirsiniz:'}\n\n"
                    f"💡 **Örnek komutlar:**\n"
                    f"• 'trap beat üret'\n"
                    f"• 'lo-fi müzik oluştur'\n"
                    f"• 'projeyi bestele'\n"
                    f"• 'melodiyi çıkar'\n"
                    f"• 'vokal ve enstrümanı ayır'",
                    parse_mode='Markdown'
                )
                return PROJECT_MENU if active_project else CHOOSE_ACTION

        except Exception as e:
            logger.error(f"AI prompt error: {e}")
            await processing_msg.edit_text(
                f"❌ Hata oluştu: {str(e)}\n\n"
                f"💡 Butonları kullanmayı deneyin veya /cancel ile çıkın."
            )
            return PROJECT_MENU if active_project else CHOOSE_ACTION

    # ========== END MUSIC WIZARD ==========

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages - check for project name first, then normal handling"""
        # Check if waiting for project name
        if await self.handle_project_name(update, context):
            return  # Handled as project name

        # Otherwise, process as normal message
        await self.handle_message(update, context)

    def run(self):
        """Start the bot"""
        logger.info("🤖 Starting VIDEOCU Telegram Bot...")

        # Create application
        application = Application.builder().token(self.token).build()

        # Register command handlers (non-music)
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("create_video", self.create_video_command))
        application.add_handler(CommandHandler("compose", self.compose_command))
        application.add_handler(CommandHandler("myprojects", self.myprojects_command))

        # Register video callback handler
        application.add_handler(CallbackQueryHandler(self.button_callback, pattern="^video_"))

        # Register MUSIC WIZARD ConversationHandler
        music_wizard = self._create_music_conversation_handler()
        application.add_handler(music_wizard)
        logger.info("   🎵 Music Wizard (ConversationHandler): Active")

        # Register text message handler (for non-wizard messages)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        # Start bot
        logger.info("✅ Bot started. Press Ctrl+C to stop.")
        logger.info("   🎤 Voice/Audio now handled by Music Wizard")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


# Main entry point
if __name__ == "__main__":
    import sys

    # UTF-8 encoding for Windows
    if sys.platform == 'win32':
        import locale
        if locale.getpreferredencoding() != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('output/telegram_bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Get credentials from environment
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found in environment")
        sys.exit(1)

    if not GEMINI_API_KEY:
        logger.warning("⚠️ GEMINI_API_KEY not found. Chef AI will use fallback mode.")

    # Get authorized users (comma-separated IDs)
    authorized_users_str = os.getenv('TELEGRAM_AUTHORIZED_USERS', '')
    authorized_users = []
    if authorized_users_str:
        try:
            authorized_users = [int(uid.strip()) for uid in authorized_users_str.split(',')]
        except ValueError:
            logger.warning("⚠️ Invalid TELEGRAM_AUTHORIZED_USERS format. Allowing all users.")

    print("\n" + "="*70)
    print("🤖 VIDEOCU v1 - TELEGRAM BOT")
    print("="*70)
    print(f"✅ Telegram Token: {'*' * 20}{TELEGRAM_TOKEN[-8:]}")
    print(f"✅ Gemini API: {'Enabled' if GEMINI_API_KEY else 'Disabled (fallback mode)'}")
    print(f"✅ Authorized Users: {len(authorized_users) if authorized_users else 'All users'}")
    print("="*70)
    print("Starting bot...")
    print("="*70 + "\n")

    # Create and run bot
    bot = VideocuBot(
        telegram_token=TELEGRAM_TOKEN,
        gemini_api_key=GEMINI_API_KEY,
        authorized_users=authorized_users
    )

    bot.run()
