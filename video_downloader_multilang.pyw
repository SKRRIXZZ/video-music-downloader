import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess
import threading
import time
import os
import sys
import io
import json
import tempfile
import queue
import shutil
import uuid
import ctypes
import urllib.request
import collections
from datetime import datetime

try:
    import yt_dlp
    YTDLP_OK = True
except ImportError:
    YTDLP_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import pystray
    TRAY_AVAILABLE = PIL_OK
except ImportError:
    TRAY_AVAILABLE = False

try:
    import winreg
    WINREG_OK = True
except ImportError:
    WINREG_OK = False


def _set_app_id(app_id):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

_set_app_id("VideoDownloader.Custom.App.8")


SIGNAL_FILE = os.path.join(tempfile.gettempdir(),
                           "video_downloader_singleton.signal")
_mutex_handle = None
ERROR_ALREADY_EXISTS = 183

AUTORUN_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTORUN_NAME = "VideoDownloader"
REG_PATH     = r"Software\VideoDownloader"


def acquire_single_instance():
    global _mutex_handle
    try:
        kernel32 = ctypes.windll.kernel32
        _mutex_handle = kernel32.CreateMutexW(
            None, False, "VideoDownloader_SingleInstance_Mutex")
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def signal_existing_instance():
    try:
        with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
            f.write("1")
    except Exception:
        pass


def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


APP_DIR = _app_dir()


def _find_ffmpeg():
    sys_path = shutil.which("ffmpeg")
    if sys_path:
        return sys_path
    local = os.path.join(APP_DIR, "ffmpeg.exe")
    if os.path.exists(local):
        return local
    return None


FFMPEG_PATH = _find_ffmpeg()
HAS_FFMPEG = FFMPEG_PATH is not None


# ============ НАСТРОЙКИ ============
def _reg_read(name):
    if not WINREG_OK:
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0,
                             winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, name)
            return val
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _reg_write(name, value):
    if not WINREG_OK:
        return False
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))
            return True
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def load_settings():
    raw = _reg_read("settings")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def save_settings(data):
    try:
        _reg_write("settings", json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


_LOG_BUFFER = collections.deque(maxlen=500)


def log_event(text):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        _LOG_BUFFER.append(f"[{ts}] {text}")
    except Exception:
        pass


def get_log_text():
    if not _LOG_BUFFER:
        return "(журнал пуст)"
    return "\n".join(_LOG_BUFFER)


def clear_log_memory():
    _LOG_BUFFER.clear()


def fmt_size(b):
    if not b:
        return "—"
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if b < 1024:
            return f"{b:.1f} {unit}" if unit != "Б" else f"{int(b)} Б"
        b /= 1024
    return f"{b:.1f} ТБ"


def fmt_eta(s):
    if not s or s <= 0:
        return ""
    s = int(s)
    if s >= 3600:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}ч {m:02d}м"
    m = s // 60
    sec = s % 60
    return f"{m}:{sec:02d}"


def fmt_speed(bps):
    if not bps or bps <= 0:
        return ""
    return fmt_size(bps) + "/с"


def default_folder_for(mode):
    if mode == "audio":
        p = os.path.join(os.path.expanduser("~"), "Music")
        if os.path.isdir(p):
            return p
    else:
        p = os.path.join(os.path.expanduser("~"), "Videos")
        if os.path.isdir(p):
            return p
    return os.path.join(os.path.expanduser("~"), "Downloads")


# ============ ТЕМЫ ============
THEMES = {
    "dark": {
        "bg": "#1c1f26", "bg_dark": "#13161b",
        "fg": "#e8eaf0", "fg_dim": "#8b8f9c",
        "white": "#ffffff", "selected_fg": "#ffffff",
        "green": "#4ade80", "green_b": "#86efac",
        "orange": "#fbbf24", "orange_b": "#fde047",
        "red": "#f87171", "red_b": "#fca5a5",
        "blue": "#5a8fc9", "blue_hov": "#6a9fd9", "blue_b": "#7aa8dc",
        "purple": "#a274c9", "purple_hov": "#b284d9", "purple_b": "#c294e9",
        "up_clr": "#6b6f7c",
        "preset_bg": "#262a33", "preset_hover": "#31363f",
        "preset_active": "#16a34a",
        "action_bg": "#262a33", "action_hover": "#31363f",
        "action_active": "#16a34a",
        "btn_start": "#16a34a", "btn_start_hov": "#22c55e",
        "btn_cancel": "#7f1d1d", "btn_cancel_hov": "#991b1b",
        "entry_bg": "#13161b", "entry_border": "#31363f",
        "thumb_bg": "#1e2229",
    },
    "light": {
        "bg": "#f6f8fb", "bg_dark": "#ffffff",
        "fg": "#1a1f29", "fg_dim": "#6b7280",
        "white": "#ffffff", "selected_fg": "#ffffff",
        "green": "#10b981", "green_b": "#059669",
        "orange": "#f59e0b", "orange_b": "#d97706",
        "red": "#ef4444", "red_b": "#dc2626",
        "blue": "#2563eb", "blue_hov": "#3b82f6", "blue_b": "#3b82f6",
        "purple": "#7c3aed", "purple_hov": "#8b5cf6", "purple_b": "#8b5cf6",
        "up_clr": "#9aa1ad",
        "preset_bg": "#e8ecf3", "preset_hover": "#d8dee8",
        "preset_active": "#059669",
        "action_bg": "#e8ecf3", "action_hover": "#d8dee8",
        "action_active": "#059669",
        "btn_start": "#059669", "btn_start_hov": "#047857",
        "btn_cancel": "#dc2626", "btn_cancel_hov": "#b91c1c",
        "entry_bg": "#ffffff", "entry_border": "#cbd5e1",
        "thumb_bg": "#eef2f7",
    },
}


FORMATS_VIDEO = [
    ("🎬  Лучшее",  "best"), ("📺  1080p", "1080"),
    ("📺  720p",    "720"),  ("📺  480p",  "480"),
    ("📺  360p",    "360"),
]

FORMATS_AUDIO = [
    ("🎵  Лучшее",   "abest"), ("🎧  320 kbps", "a320"),
    ("🎧  192 kbps", "a192"),  ("🎧  128 kbps", "a128"),
    ("💿  FLAC",     "flac"),  ("💿  WAV",      "wav"),
]

FORMAT_LABEL_KEYS = {
    "🎬  Лучшее":   "fmt_best",
    "📺  1080p":    "fmt_1080",
    "📺  720p":     "fmt_720",
    "📺  480p":     "fmt_480",
    "📺  360p":     "fmt_360",
    "🎵  Лучшее":   "fmt_abest",
    "🎧  320 kbps": "fmt_a320",
    "🎧  192 kbps": "fmt_a192",
    "🎧  128 kbps": "fmt_a128",
    "💿  FLAC":     "fmt_flac",
    "💿  WAV":      "fmt_wav",
}

MAX_COMPLETED_VISIBLE = 3
THUMB_W = 72
THUMB_H = 40


# ============ ЛОКАЛИЗАЦИЯ ============
UI_LANGS = {
    'en': 'English', 'ru': 'Русский', 'de': 'Deutsch', 'fr': 'Français',
    'es': 'Español', 'it': 'Italiano', 'pt': 'Português', 'nl': 'Nederlands',
    'pl': 'Polski', 'tr': 'Türkçe', 'cs': 'Čeština', 'hu': 'Magyar',
    'ro': 'Română', 'uk': 'Українська', 'sv': 'Svenska', 'fi': 'Suomi',
    'ja': '日本語', 'ko': '한국어', 'zh': '中文', 'ar': 'العربية'
}


def _mk(ru, en, **kw):
    d = {'ru': ru, 'en': en}
    d.update(kw)
    return d


UI_TR = {
    'Скачиватель': _mk(
        'Скачиватель', 'Downloader',
        de='Downloader', fr='Téléchargeur', es='Descargador',
        it='Downloader', pt='Baixador', nl='Downloader',
        pl='Pobieracz', tr='İndirici', cs='Stahovač', hu='Letöltő',
        ro='Descărcător', uk='Завантажувач', sv='Nedladdare', fi='Lataaja',
        ja='ダウンローダー', ko='다운로더', zh='下载器', ar='منزّل'),

    'Скачиватель видео': _mk(
        'Скачиватель видео', 'Video Downloader',
        de='Video-Downloader', fr='Téléchargeur vidéo',
        es='Descargador de vídeo', it='Downloader video',
        pt='Baixador de vídeo', nl='Video-downloader',
        pl='Pobieracz wideo', tr='Video indirici',
        cs='Stahovač videa', hu='Videó letöltő',
        ro='Descărcător video', uk='Завантажувач відео',
        sv='Videonedladdare', fi='Videon lataaja',
        ja='動画ダウンローダー', ko='동영상 다운로더',
        zh='视频下载器', ar='منزّل الفيديو'),

    'Скачиватель музыки': _mk(
        'Скачиватель музыки', 'Music Downloader',
        de='Musik-Downloader', fr='Téléchargeur de musique',
        es='Descargador de música', it='Downloader musicale',
        pt='Baixador de música', nl='Muziek-downloader',
        pl='Pobieracz muzyki', tr='Müzik indirici',
        cs='Stahovač hudby', hu='Zene letöltő',
        ro='Descărcător muzică', uk='Завантажувач музики',
        sv='Musiknedladdare', fi='Musiikin lataaja',
        ja='音楽ダウンローダー', ko='음악 다운로더',
        zh='音乐下载器', ar='منزّل الموسيقى'),

    'Что скачиваем?': _mk(
        'Что скачиваем?', 'What to download?',
        de='Was herunterladen?', fr='Que télécharger ?',
        es='¿Qué descargar?', it='Cosa scaricare?',
        pt='O que descarregar?', nl='Wat downloaden?',
        pl='Co pobrać?', tr='Ne indirilecek?',
        cs='Co stáhnout?', hu='Mit töltsünk le?',
        ro='Ce descărcăm?', uk='Що завантажуємо?',
        sv='Vad ska laddas ner?', fi='Mitä ladataan?',
        ja='何をダウンロード？', ko='무엇을 다운로드?',
        zh='下载什么？', ar='ماذا ننزّل؟'),

    'Видео': _mk(
        'Видео', 'Video',
        de='Video', fr='Vidéo', es='Vídeo', it='Video',
        pt='Vídeo', nl='Video', pl='Wideo', tr='Video',
        cs='Video', hu='Videó', ro='Video', uk='Відео',
        sv='Video', fi='Video',
        ja='動画', ko='동영상', zh='视频', ar='فيديو'),

    'Музыка': _mk(
        'Музыка', 'Music',
        de='Musik', fr='Musique', es='Música', it='Musica',
        pt='Música', nl='Muziek', pl='Muzyka', tr='Müzik',
        cs='Hudba', hu='Zene', ro='Muzică', uk='Музика',
        sv='Musik', fi='Musiikki',
        ja='音楽', ko='음악', zh='音乐', ar='موسيقى'),

    'Выберите тип загрузки — потом можно переключить': _mk(
        'Выберите тип загрузки — потом можно переключить',
        'Choose a download type — you can switch later',
        de='Wählen Sie einen Download-Typ — später umschaltbar',
        fr='Choisissez un type — vous pourrez changer plus tard',
        es='Elija un tipo — puede cambiar después',
        it='Scegli un tipo — puoi cambiare dopo',
        pt='Escolha um tipo — pode mudar depois',
        nl='Kies een type — later om te schakelen',
        pl='Wybierz typ — później można zmienić',
        tr='Bir tür seçin — sonra değiştirilebilir',
        cs='Vyberte typ — později lze přepnout',
        hu='Válasszon típust — később módosítható',
        ro='Alege un tip — poți schimba mai târziu',
        uk='Виберіть тип — потім можна змінити',
        sv='Välj en typ — kan bytas senare',
        fi='Valitse tyyppi — voi vaihtaa myöhemmin',
        ja='種類を選択 — 後で切替可能',
        ko='유형을 선택하세요 — 나중에 변경 가능',
        zh='选择类型 — 稍后可切换', ar='اختر نوعًا — يمكن التبديل لاحقًا'),

    'Ссылка': _mk(
        'Ссылка', 'Link',
        de='Link', fr='Lien', es='Enlace', it='Link',
        pt='Ligação', nl='Link', pl='Link', tr='Bağlantı',
        cs='Odkaz', hu='Link', ro='Link', uk='Посилання',
        sv='Länk', fi='Linkki',
        ja='リンク', ko='링크', zh='链接', ar='رابط'),

    'Формат и качество': _mk(
        'Формат и качество', 'Format and quality',
        de='Format und Qualität', fr='Format et qualité',
        es='Formato y calidad', it='Formato e qualità',
        pt='Formato e qualidade', nl='Formaat en kwaliteit',
        pl='Format i jakość', tr='Biçim ve kalite',
        cs='Formát a kvalita', hu='Formátum és minőség',
        ro='Format și calitate', uk='Формат і якість',
        sv='Format och kvalitet', fi='Muoto ja laatu',
        ja='形式と品質', ko='형식 및 품질', zh='格式与质量', ar='الصيغة والجودة'),

    'Папка сохранения': _mk(
        'Папка сохранения', 'Save folder',
        de='Speicherordner', fr='Dossier de destination',
        es='Carpeta de destino', it='Cartella di destinazione',
        pt='Pasta de destino', nl='Doelmap',
        pl='Folder zapisu', tr='Kayıt klasörü',
        cs='Cílová složka', hu='Mentési mappa',
        ro='Folder de salvare', uk='Папка збереження',
        sv='Spara mapp', fi='Tallennuskansio',
        ja='保存先フォルダ', ko='저장 폴더', zh='保存文件夹', ar='مجلد الحفظ'),

    'Обзор': _mk(
        'Обзор', 'Browse',
        de='Durchsuchen', fr='Parcourir', es='Examinar',
        it='Sfoglia', pt='Procurar', nl='Bladeren',
        pl='Przeglądaj', tr='Gözat', cs='Procházet',
        hu='Tallózás', ro='Răsfoire', uk='Огляд',
        sv='Bläddra', fi='Selaa',
        ja='参照', ko='찾아보기', zh='浏览', ar='استعراض'),

    'Скачать': _mk(
        'Скачать', 'Download',
        de='Herunterladen', fr='Télécharger', es='Descargar',
        it='Scarica', pt='Descarregar', nl='Downloaden',
        pl='Pobierz', tr='İndir', cs='Stáhnout',
        hu='Letöltés', ro='Descarcă', uk='Завантажити',
        sv='Ladda ner', fi='Lataa',
        ja='ダウンロード', ko='다운로드', zh='下载', ar='تنزيل'),

    'Активные загрузки': _mk(
        'Активные загрузки', 'Active downloads',
        de='Aktive Downloads', fr='Téléchargements en cours',
        es='Descargas activas', it='Download attivi',
        pt='Transferências ativas', nl='Actieve downloads',
        pl='Aktywne pobierania', tr='Etkin indirmeler',
        cs='Aktivní stahování', hu='Aktív letöltések',
        ro='Descărcări active', uk='Активні завантаження',
        sv='Aktiva nedladdningar', fi='Aktiiviset lataukset',
        ja='アクティブなダウンロード', ko='활성 다운로드',
        zh='活动下载', ar='التنزيلات النشطة'),

    'Пока ничего не качается': _mk(
        'Пока ничего не качается', 'Nothing is downloading yet',
        de='Noch wird nichts heruntergeladen',
        fr='Rien en cours de téléchargement',
        es='Nada se está descargando', it='Niente in download',
        pt='Nada a descarregar', nl='Nog niets aan het downloaden',
        pl='Nic nie jest pobierane', tr='Henüz indirme yok',
        cs='Zatím nic nestahuje', hu='Még nincs letöltés',
        ro='Nimic nu se descarcă', uk='Поки нічого не завантажується',
        sv='Inget laddas ner ännu', fi='Mitään ei ladata vielä',
        ja='まだダウンロードしていません', ko='아직 다운로드 없음',
        zh='暂无下载', ar='لا يوجد تنزيل بعد'),

    'Завершённые': _mk(
        'Завершённые', 'Completed',
        de='Abgeschlossen', fr='Terminés', es='Completados',
        it='Completati', pt='Concluídos', nl='Voltooid',
        pl='Zakończone', tr='Tamamlanan', cs='Dokončeno',
        hu='Befejezett', ro='Finalizate', uk='Завершені',
        sv='Klara', fi='Valmiit',
        ja='完了', ko='완료됨', zh='已完成', ar='مكتمل'),

    'Очистить всё': _mk(
        'Очистить всё', 'Clear all',
        de='Alles löschen', fr='Tout effacer', es='Borrar todo',
        it='Cancella tutto', pt='Limpar tudo', nl='Alles wissen',
        pl='Wyczyść wszystko', tr='Tümünü temizle',
        cs='Vymazat vše', hu='Összes törlése',
        ro='Golește tot', uk='Очистити все',
        sv='Rensa allt', fi='Tyhjennä kaikki',
        ja='すべてクリア', ko='모두 지우기', zh='全部清除', ar='مسح الكل'),

    'Готов к работе': _mk(
        'Готов к работе', 'Ready',
        de='Bereit', fr='Prêt', es='Listo',
        it='Pronto', pt='Pronto', nl='Gereed',
        pl='Gotowe', tr='Hazır', cs='Připraveno',
        hu='Kész', ro='Gata', uk='Готовий',
        sv='Redo', fi='Valmis',
        ja='準備完了', ko='준비됨', zh='就绪', ar='جاهز'),

    'Свернуть': _mk(
        'Свернуть', 'Minimize',
        de='Minimieren', fr='Réduire', es='Minimizar',
        it='Riduci', pt='Minimizar', nl='Minimaliseren',
        pl='Zwiń', tr='Küçült', cs='Minimalizovat',
        hu='Kicsinyítés', ro='Minimizează', uk='Згорнути',
        sv='Minimera', fi='Pienennä',
        ja='最小化', ko='최소화', zh='最小化', ar='تصغير'),

    'История': _mk(
        'История', 'History',
        de='Verlauf', fr='Historique', es='Historial',
        it='Cronologia', pt='Histórico', nl='Geschiedenis',
        pl='Historia', tr='Geçmiş', cs='Historie',
        hu='Előzmények', ro='Istoric', uk='Історія',
        sv='Historik', fi='Historia',
        ja='履歴', ko='기록', zh='历史', ar='السجل'),

    'Журнал': _mk(
        'Журнал', 'Log',
        de='Protokoll', fr='Journal', es='Registro',
        it='Registro', pt='Registo', nl='Logboek',
        pl='Dziennik', tr='Günlük', cs='Protokol',
        hu='Napló', ro='Jurnal', uk='Журнал',
        sv='Logg', fi='Loki',
        ja='ログ', ko='로그', zh='日志', ar='السجل'),

    'Экспорт': _mk(
        'Экспорт', 'Export',
        de='Export', fr='Exporter', es='Exportar',
        it='Esporta', pt='Exportar', nl='Exporteren',
        pl='Eksportuj', tr='Dışa aktar', cs='Export',
        hu='Exportálás', ro='Exportă', uk='Експорт',
        sv='Exportera', fi='Vie',
        ja='エクスポート', ko='내보내기', zh='导出', ar='تصدير'),

    'Импорт': _mk(
        'Импорт', 'Import',
        de='Import', fr='Importer', es='Importar',
        it='Importa', pt='Importar', nl='Importeren',
        pl='Importuj', tr='İçe aktar', cs='Import',
        hu='Importálás', ro='Importă', uk='Імпорт',
        sv='Importera', fi='Tuo',
        ja='インポート', ko='가져오기', zh='导入', ar='استيراد'),

    'Закрыть': _mk(
        'Закрыть', 'Close',
        de='Schließen', fr='Fermer', es='Cerrar',
        it='Chiudi', pt='Fechar', nl='Sluiten',
        pl='Zamknij', tr='Kapat', cs='Zavřít',
        hu='Bezárás', ro='Închide', uk='Закрити',
        sv='Stäng', fi='Sulje',
        ja='閉じる', ko='닫기', zh='关闭', ar='إغلاق'),

    'Отмена': _mk(
        'Отмена', 'Cancel',
        de='Abbrechen', fr='Annuler', es='Cancelar',
        it='Annulla', pt='Cancelar', nl='Annuleren',
        pl='Anuluj', tr='İptal', cs='Zrušit',
        hu='Mégse', ro='Anulare', uk='Скасувати',
        sv='Avbryt', fi='Peruuta',
        ja='キャンセル', ko='취소', zh='取消', ar='إلغاء'),

    'Да': _mk(
        'Да', 'Yes',
        de='Ja', fr='Oui', es='Sí', it='Sì',
        pt='Sim', nl='Ja', pl='Tak', tr='Evet',
        cs='Ano', hu='Igen', ro='Da', uk='Так',
        sv='Ja', fi='Kyllä',
        ja='はい', ko='예', zh='是', ar='نعم'),

    'Понятно': _mk(
        'Понятно', 'OK',
        de='Verstanden', fr='OK', es='Entendido',
        it='OK', pt='OK', nl='Begrepen',
        pl='OK', tr='Tamam', cs='OK',
        hu='Rendben', ro='OK', uk='Зрозуміло',
        sv='OK', fi='OK',
        ja='了解', ko='확인', zh='好的', ar='حسنًا'),

    'Обновить': _mk(
        'Обновить', 'Refresh',
        de='Aktualisieren', fr='Actualiser', es='Actualizar',
        it='Aggiorna', pt='Atualizar', nl='Vernieuwen',
        pl='Odśwież', tr='Yenile', cs='Obnovit',
        hu='Frissítés', ro='Reîmprospătează', uk='Оновити',
        sv='Uppdatera', fi='Päivitä',
        ja='更新', ko='새로고침', zh='刷新', ar='تحديث'),

    'Очистить': _mk(
        'Очистить', 'Clear',
        de='Leeren', fr='Effacer', es='Borrar',
        it='Cancella', pt='Limpar', nl='Wissen',
        pl='Wyczyść', tr='Temizle', cs='Vymazat',
        hu='Törlés', ro='Golește', uk='Очистити',
        sv='Rensa', fi='Tyhjennä',
        ja='クリア', ko='지우기', zh='清除', ar='مسح'),

    'Сменить режим': _mk(
        'Сменить режим', 'Switch mode',
        de='Modus wechseln', fr='Changer de mode',
        es='Cambiar modo', it='Cambia modalità',
        pt='Mudar modo', nl='Modus wijzigen',
        pl='Zmień tryb', tr='Mod değiştir',
        cs='Změnit režim', hu='Mód váltása',
        ro='Schimbă modul', uk='Змінити режим',
        sv='Byt läge', fi='Vaihda tila',
        ja='モード切替', ko='모드 전환', zh='切换模式', ar='تبديل الوضع'),

    'Переключить на видео': _mk(
        'Переключить на видео', 'Switch to video',
        de='Zu Video wechseln', fr='Passer à la vidéo',
        es='Cambiar a vídeo', it='Passa al video',
        pt='Mudar para vídeo', nl='Naar video schakelen',
        pl='Przełącz na wideo', tr='Videoya geç',
        cs='Přepnout na video', hu='Вáltás videóra',
        ro='Comută pe video', uk='Перемкнути на відео',
        sv='Byt till video', fi='Vaihda videoon',
        ja='動画に切替', ko='동영상으로 전환', zh='切换到视频', ar='التبديل إلى الفيديو'),

    'Переключить на музыку': _mk(
        'Переключить на музыку', 'Switch to music',
        de='Zu Musik wechseln', fr='Passer à la musique',
        es='Cambiar a música', it='Passa alla musica',
        pt='Mudar para música', nl='Naar muziek schakelen',
        pl='Przełącz na muzykę', tr='Müziğe geç',
        cs='Přepnout na hudbu', hu='Váltás zenére',
        ro='Comută pe muzică', uk='Перемкнути на музику',
        sv='Byt till musik', fi='Vaihda musiikkiin',
        ja='音楽に切替', ko='음악으로 전환', zh='切换到音乐', ar='التبديل إلى الموسيقى'),

    'Открыть папку назначения': _mk(
        'Открыть папку назначения', 'Open destination folder',
        de='Zielordner öffnen', fr='Ouvrir le dossier de destination',
        es='Abrir carpeta de destino', it='Apri cartella di destinazione',
        pt='Abrir pasta de destino', nl='Doelmap openen',
        pl='Otwórz folder docelowy', tr='Hedef klasörü aç',
        cs='Otevřít cílovou složku', hu='Célmappa megnyitása',
        ro='Deschide folderul destinație', uk='Відкрити папку призначення',
        sv='Öppna målmap', fi='Avaa kohdekansio',
        ja='保存先フォルダを開く', ko='대상 폴더 열기',
        zh='打开目标文件夹', ar='فتح مجلد الوجهة'),

    'Вставить из буфера и сразу скачать': _mk(
        'Вставить из буфера и сразу скачать',
        'Paste from clipboard and download immediately',
        de='Aus Zwischenablage einfügen und sofort herunterladen',
        fr='Coller depuis le presse-papiers et télécharger',
        es='Pegar del portapapeles y descargar de inmediato',
        it='Incolla dagli appunti e scarica subito',
        pt='Colar da área de transferência e descarregar',
        nl='Plakken uit klembord en direct downloaden',
        pl='Wklej ze schowka i pobierz od razu',
        tr='Panodan yapıştır ve hemen indir',
        cs='Vložit ze schránky a ihned stáhnout',
        hu='Beillesztés vágólapról és azonnali letöltés',
        ro='Lipește din clipboard și descarcă imediat',
        uk='Вставити з буфера та одразу завантажити',
        sv='Klistra in från urklipp och ladda ner direkt',
        fi='Liitä leikepöydältä ja lataa heti',
        ja='クリップボードから貼り付けてすぐダウンロード',
        ko='클립보드에서 붙여넣고 바로 다운로드',
        zh='从剪贴板粘贴并立即下载',
        ar='لصق من الحافظة والتنزيل فورًا'),

    # ---- Статусы ----
    'Вставьте ссылку': _mk(
        'Вставьте ссылку', 'Insert a link',
        de='Link einfügen', fr='Insérez un lien',
        es='Inserte un enlace', it='Inserisci un link',
        pt='Insira uma ligação', nl='Voer een link in',
        pl='Wklej link', tr='Bağlantı girin',
        cs='Vložte odkaz', hu='Illesszen be linket',
        ro='Introduceți un link', uk='Вставте посилання',
        sv='Klistra in en länk', fi='Liitä linkki',
        ja='リンクを貼り付け', ko='링크를 입력하세요',
        zh='粘贴链接', ar='أدخل رابطًا'),

    'Ссылка должна начинаться с http': _mk(
        'Ссылка должна начинаться с http',
        'Link must start with http',
        de='Link muss mit http beginnen',
        fr='Le lien doit commencer par http',
        es='El enlace debe empezar por http',
        it='Il link deve iniziare con http',
        pt='A ligação deve começar por http',
        nl='Link moet beginnen met http',
        pl='Link musi zaczynać się od http',
        tr='Bağlantı http ile başlamalı',
        cs='Odkaz musí začínat http',
        hu='A linknek http-vel kell kezdődnie',
        ro='Linkul trebuie să înceapă cu http',
        uk='Посилання має починатися з http',
        sv='Länken måste börja med http',
        fi='Linkin on alettava http',
        ja='リンクは http で始まる必要があります',
        ko='링크는 http로 시작해야 합니다',
        zh='链接必须以 http 开头', ar='يجب أن يبدأ الرابط بـ http'),

    'Неверная папка': _mk(
        'Неверная папка', 'Invalid folder',
        de='Ungültiger Ordner', fr='Dossier invalide',
        es='Carpeta no válida', it='Cartella non valida',
        pt='Pasta inválida', nl='Ongeldige map',
        pl='Nieprawidłowy folder', tr='Geçersiz klasör',
        cs='Neplatná složka', hu='Érvénytelen mappa',
        ro='Folder invalid', uk='Невірна папка',
        sv='Ogiltig mapp', fi='Virheellinen kansio',
        ja='無効なフォルダ', ko='잘못된 폴더', zh='无效文件夹', ar='مجلد غير صالح'),

    'Добавлено в очередь': _mk(
        'Добавлено в очередь', 'Added to queue',
        de='Zur Warteschlange hinzugefügt', fr='Ajouté à la file',
        es='Añadido a la cola', it='Aggiunto alla coda',
        pt='Adicionado à fila', nl='Toegevoegd aan wachtrij',
        pl='Dodano do kolejki', tr='Kuyruğa eklendi',
        cs='Přidáno do fronty', hu='Hozzáadva a sorhoz',
        ro='Adăugat în coadă', uk='Додано в чергу',
        sv='Tillagd i kön', fi='Lisätty jonoon',
        ja='キューに追加しました', ko='대기열에 추가됨',
        zh='已加入队列', ar='تمت الإضافة إلى قائمة الانتظار'),

    'Буфер обмена пуст': _mk(
        'Буфер обмена пуст', 'Clipboard is empty',
        de='Zwischenablage ist leer', fr='Presse-papiers vide',
        es='Portapapeles vacío', it='Appunti vuoti',
        pt='Área de transferência vazia', nl='Klembord is leeg',
        pl='Schowek jest pusty', tr='Pano boş',
        cs='Schránka je prázdná', hu='A vágólap üres',
        ro='Clipboardul este gol', uk='Буфер порожній',
        sv='Urklippet är tomt', fi='Leikepöytä on tyhjä',
        ja='クリップボードが空です', ko='클립보드가 비어 있습니다',
        zh='剪贴板为空', ar='الحافظة فارغة'),

    'Папка не задана': _mk(
        'Папка не задана', 'Folder is not set',
        de='Ordner nicht angegeben', fr='Dossier non défini',
        es='Carpeta no definida', it='Cartella non impostata',
        pt='Pasta não definida', nl='Map niet ingesteld',
        pl='Folder nie ustawiony', tr='Klasör ayarlanmadı',
        cs='Složka není nastavena', hu='Mappa nincs megadva',
        ro='Folderul nu este setat', uk='Папку не вказано',
        sv='Mapp är inte angiven', fi='Kansiota ei ole asetettu',
        ja='フォルダが設定されていません', ko='폴더가 설정되지 않음',
        zh='未设置文件夹', ar='لم يتم تحديد المجلد'),

    'Папка не существует': _mk(
        'Папка не существует', 'Folder does not exist',
        de='Ordner existiert nicht', fr="Le dossier n'existe pas",
        es='La carpeta no existe', it='La cartella non esiste',
        pt='A pasta não existe', nl='Map bestaat niet',
        pl='Folder nie istnieje', tr='Klasör yok',
        cs='Složka neexistuje', hu='A mappa nem létezik',
        ro='Folderul nu există', uk='Папка не існує',
        sv='Mappen finns inte', fi='Kansiota ei ole olemassa',
        ja='フォルダが存在しません', ko='폴더가 존재하지 않습니다',
        zh='文件夹不存在', ar='المجلد غير موجود'),

    'Папка не задана.': _mk(
        'Папка не задана.', 'Folder is not set.',
        de='Ordner nicht angegeben.', fr='Dossier non défini.',
        es='Carpeta no definida.', it='Cartella non impostata.',
        pt='Pasta não definida.', nl='Map niet ingesteld.',
        pl='Folder nie ustawiony.', tr='Klasör ayarlanmadı.',
        cs='Složka není nastavena.', hu='Mappa nincs megadva.',
        ro='Folderul nu este setat.', uk='Папку не вказано.',
        sv='Mapp är inte angiven.', fi='Kansiota ei ole asetettu.',
        ja='フォルダが設定されていません。', ko='폴더가 설정되지 않았습니다.',
        zh='未设置文件夹。', ar='لم يتم تحديد المجلد.'),

    'в очереди': _mk(
        'в очереди', 'queued',
        de='in Warteschlange', fr='en attente',
        es='en cola', it='in coda',
        pt='em fila', nl='in wachtrij',
        pl='w kolejce', tr='kuyrukta',
        cs='ve frontě', hu='sorban',
        ro='în coadă', uk='в черзі',
        sv='i kö', fi='jonossa',
        ja='キュー内', ko='대기 중', zh='排队中', ar='في قائمة الانتظار'),

    'подготовка…': _mk(
        'подготовка…', 'preparing…',
        de='Vorbereitung…', fr='préparation…',
        es='preparando…', it='preparazione…',
        pt='a preparar…', nl='voorbereiden…',
        pl='przygotowanie…', tr='hazırlanıyor…',
        cs='příprava…', hu='előkészítés…',
        ro='se pregătește…', uk='підготовка…',
        sv='förbereder…', fi='valmistellaan…',
        ja='準備中…', ko='준비 중…', zh='准备中…', ar='جارٍ التحضير…'),

    'обработка…': _mk(
        'обработка…', 'processing…',
        de='Verarbeitung…', fr='traitement…',
        es='procesando…', it='elaborazione…',
        pt='a processar…', nl='verwerken…',
        pl='przetwarzanie…', tr='işleniyor…',
        cs='zpracování…', hu='feldolgozás…',
        ro='se procesează…', uk='обробка…',
        sv='bearbetar…', fi='käsitellään…',
        ja='処理中…', ko='처리 중…', zh='处理中…', ar='جارٍ المعالجة…'),

    'в очереди…': _mk(
        'в очереди…', 'queued…',
        de='in Warteschlange…', fr='en attente…',
        es='en cola…', it='in coda…',
        pt='em fila…', nl='in wachtrij…',
        pl='w kolejce…', tr='kuyrukta…',
        cs='ve frontě…', hu='sorban…',
        ro='în coadă…', uk='в черзі…',
        sv='i kö…', fi='jonossa…',
        ja='キュー内…', ko='대기 중…', zh='排队中…', ar='في قائمة الانتظار…'),

    # ---- FFmpeg предупреждения ----
    '⚠ FFmpeg не найден — MP3 / FLAC / WAV недоступны': _mk(
        '⚠ FFmpeg не найден — MP3 / FLAC / WAV недоступны',
        '⚠ FFmpeg not found — MP3 / FLAC / WAV unavailable',
        de='⚠ FFmpeg nicht gefunden — MP3 / FLAC / WAV nicht verfügbar',
        fr='⚠ FFmpeg introuvable — MP3 / FLAC / WAV indisponibles',
        es='⚠ FFmpeg no encontrado — MP3 / FLAC / WAV no disponibles',
        it='⚠ FFmpeg non trovato — MP3 / FLAC / WAV non disponibili',
        pt='⚠ FFmpeg não encontrado — MP3 / FLAC / WAV indisponíveis',
        nl='⚠ FFmpeg niet gevonden — MP3 / FLAC / WAV niet beschikbaar',
        pl='⚠ Nie znaleziono FFmpeg — MP3 / FLAC / WAV niedostępne',
        tr='⚠ FFmpeg bulunamadı — MP3 / FLAC / WAV kullanılamaz',
        cs='⚠ FFmpeg nenalezen — MP3 / FLAC / WAV nedostupné',
        hu='⚠ FFmpeg nem található — MP3 / FLAC / WAV nem elérhető',
        ro='⚠ FFmpeg nu a fost găsit — MP3 / FLAC / WAV indisponibile',
        uk='⚠ FFmpeg не знайдено — MP3 / FLAC / WAV недоступні',
        sv='⚠ FFmpeg hittades inte — MP3 / FLAC / WAV otillgängliga',
        fi='⚠ FFmpeg ei löytynyt — MP3 / FLAC / WAV ei saatavilla',
        ja='⚠ FFmpeg が見つかりません — MP3 / FLAC / WAV は利用できません',
        ko='⚠ FFmpeg를 찾을 수 없음 — MP3 / FLAC / WAV 사용 불가',
        zh='⚠ 未找到 FFmpeg — MP3 / FLAC / WAV 不可用',
        ar='⚠ لم يتم العثور على FFmpeg — MP3 / FLAC / WAV غير متاحة'),

    '⚠ FFmpeg не найден — лучшее качество недоступно': _mk(
        '⚠ FFmpeg не найден — лучшее качество недоступно',
        '⚠ FFmpeg not found — best quality unavailable',
        de='⚠ FFmpeg nicht gefunden — beste Qualität nicht verfügbar',
        fr='⚠ FFmpeg introuvable — meilleure qualité indisponible',
        es='⚠ FFmpeg no encontrado — mejor calidad no disponible',
        it='⚠ FFmpeg non trovato — qualità migliore non disponibile',
        pt='⚠ FFmpeg não encontrado — melhor qualidade indisponível',
        nl='⚠ FFmpeg niet gevonden — beste kwaliteit niet beschikbaar',
        pl='⚠ Nie znaleziono FFmpeg — najlepsza jakość niedostępna',
        tr='⚠ FFmpeg bulunamadı — en iyi kalite kullanılamaz',
        cs='⚠ FFmpeg nenalezen — nejlepší kvalita nedostupná',
        hu='⚠ FFmpeg nem található — a legjobb minőség nem elérhető',
        ro='⚠ FFmpeg nu a fost găsit — cea mai bună calitate indisponibilă',
        uk='⚠ FFmpeg не знайдено — найкраща якість недоступна',
        sv='⚠ FFmpeg hittades inte — bästa kvaliteten otillgänglig',
        fi='⚠ FFmpeg ei löytynyt — paras laatu ei saatavilla',
        ja='⚠ FFmpeg が見つかりません — 最高品質は利用できません',
        ko='⚠ FFmpeg를 찾을 수 없음 — 최고 품질 사용 불가',
        zh='⚠ 未找到 FFmpeg — 最佳质量不可用',
        ar='⚠ لم يتم العثور على FFmpeg — أفضل جودة غير متاحة'),

    'Не установлен yt-dlp': _mk(
        'Не установлен yt-dlp', 'yt-dlp not installed',
        de='yt-dlp nicht installiert', fr='yt-dlp non installé',
        es='yt-dlp no instalado', it='yt-dlp non installato',
        pt='yt-dlp não instalado', nl='yt-dlp niet geïnstalleerd',
        pl='yt-dlp nie jest zainstalowany', tr='yt-dlp yüklü değil',
        cs='yt-dlp není nainstalován', hu='yt-dlp nincs telepítve',
        ro='yt-dlp nu este instalat', uk='yt-dlp не встановлено',
        sv='yt-dlp är inte installerat', fi='yt-dlp ei ole asennettu',
        ja='yt-dlp がインストールされていません', ko='yt-dlp가 설치되지 않음',
        zh='yt-dlp 未安装', ar='yt-dlp غير مثبّت'),

    'Внутри .exe нет модуля yt-dlp.': _mk(
        'Внутри .exe нет модуля yt-dlp.',
        'The .exe does not contain the yt-dlp module.',
        de='Die .exe enthält das yt-dlp-Modul nicht.',
        fr="L'exe ne contient pas le module yt-dlp.",
        es='El .exe no contiene el módulo yt-dlp.',
        it="L'exe non contiene il modulo yt-dlp.",
        pt='O .exe não contém o módulo yt-dlp.',
        nl='De .exe bevat de yt-dlp-module niet.',
        pl='Plik .exe nie zawiera modułu yt-dlp.',
        tr='.exe yt-dlp modülünü içermiyor.',
        cs='Soubor .exe neobsahuje modul yt-dlp.',
        hu='Az .exe nem tartalmazza a yt-dlp modult.',
        ro='Fișierul .exe nu conține modulul yt-dlp.',
        uk='У .exe немає модуля yt-dlp.',
        sv='.exe innehåller inte yt-dlp-modulen.',
        fi='.exe ei sisällä yt-dlp-moduulia.',
        ja='.exe に yt-dlp モジュールが含まれていません。',
        ko='.exe에 yt-dlp 모듈이 없습니다.',
        zh='.exe 中不包含 yt-dlp 模块。',
        ar='ملف .exe لا يحتوي على وحدة yt-dlp.'),

    'FFmpeg не найден': _mk(
        'FFmpeg не найден', 'FFmpeg not found',
        de='FFmpeg nicht gefunden', fr='FFmpeg introuvable',
        es='FFmpeg no encontrado', it='FFmpeg non trovato',
        pt='FFmpeg não encontrado', nl='FFmpeg niet gevonden',
        pl='Nie znaleziono FFmpeg', tr='FFmpeg bulunamadı',
        cs='FFmpeg nenalezen', hu='FFmpeg nem található',
        ro='FFmpeg nu a fost găsit', uk='FFmpeg не знайдено',
        sv='FFmpeg hittades inte', fi='FFmpeg ei löytynyt',
        ja='FFmpeg が見つかりません', ko='FFmpeg를 찾을 수 없음',
        zh='未找到 FFmpeg', ar='لم يتم العثور على FFmpeg'),

    'Рядом с приложением нет ffmpeg.exe.': _mk(
        'Рядом с приложением нет ffmpeg.exe.',
        'ffmpeg.exe is not next to the application.',
        de='ffmpeg.exe befindet sich nicht neben der Anwendung.',
        fr="ffmpeg.exe n'est pas à côté de l'application.",
        es='ffmpeg.exe no está junto a la aplicación.',
        it="ffmpeg.exe non è accanto all'applicazione.",
        pt='ffmpeg.exe não está junto da aplicação.',
        nl='ffmpeg.exe staat niet naast de toepassing.',
        pl='ffmpeg.exe nie znajduje się obok aplikacji.',
        tr='ffmpeg.exe uygulamanın yanında değil.',
        cs='ffmpeg.exe není vedle aplikace.',
        hu='Az ffmpeg.exe nincs az alkalmazás mellett.',
        ro='ffmpeg.exe nu este lângă aplicație.',
        uk='ffmpeg.exe немає поряд із застосунком.',
        sv='ffmpeg.exe finns inte bredvid programmet.',
        fi='ffmpeg.exe ei ole sovelluksen vieressä.',
        ja='ffmpeg.exe がアプリの隣にありません。',
        ko='ffmpeg.exe가 앱 옆에 없습니다.',
        zh='ffmpeg.exe 不在应用旁边。',
        ar='ملف ffmpeg.exe ليس بجانب التطبيق.'),

    'Без FFmpeg недоступны MP3, FLAC, WAV и лучшее качество.': _mk(
        'Без FFmpeg недоступны MP3, FLAC, WAV и лучшее качество.',
        'Without FFmpeg, MP3, FLAC, WAV and best quality are unavailable.',
        de='Ohne FFmpeg sind MP3, FLAC, WAV und beste Qualität nicht verfügbar.',
        fr='Sans FFmpeg, MP3, FLAC, WAV et la meilleure qualité sont indisponibles.',
        es='Sin FFmpeg, MP3, FLAC, WAV y mejor calidad no están disponibles.',
        it='Senza FFmpeg, MP3, FLAC, WAV e qualità migliore non sono disponibili.',
        pt='Sem FFmpeg, MP3, FLAC, WAV e melhor qualidade ficam indisponíveis.',
        nl='Zonder FFmpeg zijn MP3, FLAC, WAV en beste kwaliteit niet beschikbaar.',
        pl='Bez FFmpeg MP3, FLAC, WAV i najlepsza jakość są niedostępne.',
        tr='FFmpeg olmadan MP3, FLAC, WAV ve en iyi kalite kullanılamaz.',
        cs='Bez FFmpeg nejsou MP3, FLAC, WAV a nejlepší kvalita dostupné.',
        hu='FFmpeg nélkül az MP3, FLAC, WAV és a legjobb minőség nem elérhető.',
        ro='Fără FFmpeg, MP3, FLAC, WAV și cea mai bună calitate sunt indisponibile.',
        uk='Без FFmpeg недоступні MP3, FLAC, WAV і найкраща якість.',
        sv='Utan FFmpeg är MP3, FLAC, WAV och bästa kvalitet otillgängliga.',
        fi='Ilman FFmpegiä MP3, FLAC, WAV ja paras laatu eivät ole käytettävissä.',
        ja='FFmpeg がないと MP3、FLAC、WAV、最高品質は利用できません。',
        ko='FFmpeg 없이는 MP3, FLAC, WAV 및 최고 품질을 사용할 수 없습니다.',
        zh='没有 FFmpeg，MP3、FLAC、WAV 和最佳质量不可用。',
        ar='بدون FFmpeg، لن تتوفر صيغ MP3 و FLAC و WAV وأفضل جودة.'),

    # ---- Диалоги подтверждения ----
    'Удалить запись?': _mk(
        'Удалить запись?', 'Delete entry?',
        de='Eintrag löschen?', fr="Supprimer l'entrée ?",
        es='¿Eliminar la entrada?', it='Eliminare la voce?',
        pt='Eliminar a entrada?', nl='Item verwijderen?',
        pl='Usunąć wpis?', tr='Kayıt silinsin mi?',
        cs='Smazat záznam?', hu='Törli a bejegyzést?',
        ro='Ștergi înregistrarea?', uk='Видалити запис?',
        sv='Ta bort post?', fi='Poistetaanko merkintä?',
        ja='エントリを削除しますか？', ko='항목을 삭제하시겠습니까?',
        zh='删除记录？', ar='حذف الإدخال؟'),

    'Удалить запись из истории?': _mk(
        'Удалить запись из истории?', 'Delete entry from history?',
        de='Eintrag aus dem Verlauf löschen?',
        fr="Supprimer l'entrée de l'historique ?",
        es='¿Eliminar la entrada del historial?',
        it='Eliminare la voce dalla cronologia?',
        pt='Eliminar a entrada do histórico?',
        nl='Item uit geschiedenis verwijderen?',
        pl='Usunąć wpis z historii?',
        tr='Kayıt geçmişten silinsin mi?',
        cs='Smazat záznam z historie?',
        hu='Törli a bejegyzést az előzményekből?',
        ro='Ștergi înregistrarea din istoric?',
        uk='Видалити запис з історії?',
        sv='Ta bort post från historiken?',
        fi='Poistetaanko merkintä historiasta?',
        ja='履歴からエントリを削除しますか？',
        ko='기록에서 항목을 삭제하시겠습니까?',
        zh='从历史中删除记录？', ar='حذف الإدخال من السجل؟'),

    'Файл отсутствует.': _mk(
        'Файл отсутствует.', 'File is missing.',
        de='Datei fehlt.', fr='Fichier manquant.',
        es='Falta el archivo.', it='File mancante.',
        pt='Ficheiro em falta.', nl='Bestand ontbreekt.',
        pl='Plik nie istnieje.', tr='Dosya eksik.',
        cs='Soubor chybí.', hu='A fájl hiányzik.',
        ro='Fișierul lipsește.', uk='Файл відсутній.',
        sv='Filen saknas.', fi='Tiedosto puuttuu.',
        ja='ファイルがありません。', ko='파일이 없습니다.',
        zh='文件缺失。', ar='الملف مفقود.'),

    'Очистить всю историю?': _mk(
        'Очистить всю историю?', 'Clear the entire history?',
        de='Gesamten Verlauf löschen?',
        fr="Effacer tout l'historique ?",
        es='¿Borrar todo el historial?',
        it='Cancellare tutta la cronologia?',
        pt='Limpar todo o histórico?',
        nl='Hele geschiedenis wissen?',
        pl='Wyczyścić całą historię?',
        tr='Tüm geçmiş temizlensin mi?',
        cs='Vymazat celou historii?',
        hu='Törli a teljes előzményt?',
        ro='Ștergi tot istoricul?',
        uk='Очистити всю історію?',
        sv='Rensa hela historiken?',
        fi='Tyhjennetäänkö koko historia?',
        ja='履歴をすべて消去しますか？',
        ko='전체 기록을 지우시겠습니까?',
        zh='清空全部历史？', ar='مسح السجل بالكامل؟'),

    'Все записи будут удалены.': _mk(
        'Все записи будут удалены.', 'All entries will be deleted.',
        de='Alle Einträge werden gelöscht.',
        fr='Toutes les entrées seront supprimées.',
        es='Se eliminarán todas las entradas.',
        it='Tutte le voci saranno eliminate.',
        pt='Todas as entradas serão eliminadas.',
        nl='Alle items worden verwijderd.',
        pl='Wszystkie wpisy zostaną usunięte.',
        tr='Tüm kayıtlar silinecek.',
        cs='Všechny záznamy budou smazány.',
        hu='Minden bejegyzés törlődik.',
        ro='Toate înregistrările vor fi șterse.',
        uk='Усі записи буде видалено.',
        sv='Alla poster tas bort.',
        fi='Kaikki merkinnät poistetaan.',
        ja='すべてのエントリが削除されます。',
        ko='모든 항목이 삭제됩니다.',
        zh='所有记录将被删除。', ar='سيتم حذف جميع الإدخالات.'),

    'Только из истории': _mk(
        'Только из истории', 'History only',
        de='Nur aus dem Verlauf', fr="Historique seulement",
        es='Solo del historial', it='Solo dalla cronologia',
        pt='Apenas do histórico', nl='Alleen geschiedenis',
        pl='Tylko z historii', tr='Yalnızca geçmişten',
        cs='Pouze z historie', hu='Csak az előzményekből',
        ro='Doar din istoric', uk='Лише з історії',
        sv='Endast historik', fi='Vain historiasta',
        ja='履歴のみ', ko='기록만', zh='仅从历史', ar='من السجل فقط'),

    'Удалить с диска': _mk(
        'Удалить с диска', 'Delete from disk',
        de='Von der Festplatte löschen',
        fr='Supprimer du disque',
        es='Eliminar del disco', it='Elimina dal disco',
        pt='Eliminar do disco', nl='Van schijf verwijderen',
        pl='Usuń z dysku', tr='Diskten sil',
        cs='Smazat z disku', hu='Törlés a lemezről',
        ro='Șterge de pe disc', uk='Видалити з диска',
        sv='Ta bort från disk', fi='Poista levyltä',
        ja='ディスクから削除', ko='디스크에서 삭제',
        zh='从磁盘删除', ar='حذف من القرص'),

    'Удалить и файл': _mk(
        'Удалить и файл', 'Delete file too',
        de='Auch Datei löschen', fr='Supprimer aussi le fichier',
        es='Eliminar también el archivo', it='Elimina anche il file',
        pt='Eliminar também o ficheiro', nl='Bestand ook verwijderen',
        pl='Usuń także plik', tr='Dosyayı da sil',
        cs='Smazat i soubor', hu='Fájl törlése is',
        ro='Șterge și fișierul', uk='Видалити і файл',
        sv='Ta bort filen också', fi='Poista myös tiedosto',
        ja='ファイルも削除', ko='파일도 삭제',
        zh='同时删除文件', ar='حذف الملف أيضًا'),

    'Очистить историю?': _mk(
        'Очистить историю?', 'Clear history?',
        de='Verlauf löschen?', fr="Effacer l'historique ?",
        es='¿Borrar el historial?', it='Cancellare la cronologia?',
        pt='Limpar o histórico?', nl='Geschiedenis wissen?',
        pl='Wyczyścić historię?', tr='Geçmiş temizlensin mi?',
        cs='Vymazat historii?', hu='Törli az előzményeket?',
        ro='Ștergi istoricul?', uk='Очистити історію?',
        sv='Rensa historiken?', fi='Tyhjennetäänkö historia?',
        ja='履歴を消去しますか？', ko='기록을 지우시겠습니까?',
        zh='清空历史？', ar='مسح السجل؟'),

    'Все записи о загрузках будут удалены.': _mk(
        'Все записи о загрузках будут удалены.',
        'All download entries will be deleted.',
        de='Alle Download-Einträge werden gelöscht.',
        fr='Toutes les entrées de téléchargement seront supprimées.',
        es='Se eliminarán todas las entradas de descarga.',
        it='Tutte le voci di download saranno eliminate.',
        pt='Todas as entradas de transferência serão eliminadas.',
        nl='Alle downloaditems worden verwijderd.',
        pl='Wszystkie wpisy pobierania zostaną usunięte.',
        tr='Tüm indirme kayıtları silinecek.',
        cs='Všechny záznamy o stahování budou smazány.',
        hu='Minden letöltési bejegyzés törlődik.',
        ro='Toate înregistrările de descărcare vor fi șterse.',
        uk='Усі записи про завантаження буде видалено.',
        sv='Alla nedladdningsposter tas bort.',
        fi='Kaikki latausmerkinnät poistetaan.',
        ja='すべてのダウンロード履歴が削除されます。',
        ko='모든 다운로드 기록이 삭제됩니다.',
        zh='所有下载记录将被删除。', ar='سيتم حذف جميع سجلات التنزيل.'),

    '(пусто)': _mk(
        '(пусто)', '(empty)',
        de='(leer)', fr='(vide)', es='(vacío)', it='(vuoto)',
        pt='(vazio)', nl='(leeg)', pl='(puste)', tr='(boş)',
        cs='(prázdné)', hu='(üres)', ro='(gol)', uk='(порожньо)',
        sv='(tom)', fi='(tyhjä)',
        ja='（空）', ko='(비어 있음)', zh='（空）', ar='(فارغ)'),

    # ---- Экспорт / Импорт ----
    'Куда сохранить настройки?': _mk(
        'Куда сохранить настройки?', 'Where to save the settings?',
        de='Wohin sollen die Einstellungen gespeichert werden?',
        fr='Où enregistrer les paramètres ?',
        es='¿Dónde guardar la configuración?',
        it='Dove salvare le impostazioni?',
        pt='Onde guardar as definições?',
        nl='Waar moeten de instellingen worden opgeslagen?',
        pl='Gdzie zapisać ustawienia?',
        tr='Ayarlar nereye kaydedilsin?',
        cs='Kam uložit nastavení?',
        hu='Hová mentse a beállításokat?',
        ro='Unde să salvez setările?',
        uk='Куди зберегти налаштування?',
        sv='Var ska inställningarna sparas?',
        fi='Minne asetukset tallennetaan?',
        ja='設定を保存する場所は？', ko='설정을 어디에 저장할까요?',
        zh='保存设置到哪里？', ar='أين يتم حفظ الإعدادات؟'),

    'Куда сохранять?': _mk(
        'Куда сохранять?', 'Where to save?',
        de='Wohin speichern?', fr='Où enregistrer ?',
        es='¿Dónde guardar?', it='Dove salvare?',
        pt='Onde guardar?', nl='Waar opslaan?',
        pl='Gdzie zapisać?', tr='Nereye kaydedilsin?',
        cs='Kam uložit?', hu='Hová mentse?',
        ro='Unde să salvez?', uk='Куди зберегти?',
        sv='Var ska sparas?', fi='Minne tallennetaan?',
        ja='保存先は？', ko='어디에 저장할까요?',
        zh='保存到哪里？', ar='أين يتم الحفظ؟'),

    'Выберите файл с настройками': _mk(
        'Выберите файл с настройками', 'Select the settings file',
        de='Wählen Sie die Einstellungsdatei',
        fr='Sélectionnez le fichier de paramètres',
        es='Seleccione el archivo de configuración',
        it='Seleziona il file delle impostazioni',
        pt='Selecione o ficheiro de definições',
        nl='Selecteer het instellingenbestand',
        pl='Wybierz plik ustawień',
        tr='Ayar dosyasını seçin',
        cs='Vyberte soubor nastavení',
        hu='Válassza ki a beállításfájlt',
        ro='Selectați fișierul de setări',
        uk='Виберіть файл із налаштуваннями',
        sv='Välj inställningsfilen',
        fi='Valitse asetustiedosto',
        ja='設定ファイルを選択', ko='설정 파일 선택',
        zh='选择设置文件', ar='حدد ملف الإعدادات'),

    'Экспорт завершён': _mk(
        'Экспорт завершён', 'Export completed',
        de='Export abgeschlossen', fr='Exportation terminée',
        es='Exportación completada', it='Esportazione completata',
        pt='Exportação concluída', nl='Export voltooid',
        pl='Eksport zakończony', tr='Dışa aktarma tamamlandı',
        cs='Export dokončen', hu='Exportálás befejezve',
        ro='Export finalizat', uk='Експорт завершено',
        sv='Export klar', fi='Vienti valmis',
        ja='エクスポート完了', ko='내보내기 완료',
        zh='导出完成', ar='اكتمل التصدير'),

    'Настройки сохранены в файл:': _mk(
        'Настройки сохранены в файл:', 'Settings saved to file:',
        de='Einstellungen gespeichert in Datei:',
        fr='Paramètres enregistrés dans le fichier :',
        es='Configuración guardada en el archivo:',
        it='Impostazioni salvate nel file:',
        pt='Definições guardadas no ficheiro:',
        nl='Instellingen opgeslagen in bestand:',
        pl='Ustawienia zapisane w pliku:',
        tr='Ayarlar dosyaya kaydedildi:',
        cs='Nastavení uloženo do souboru:',
        hu='Beállítások mentve a fájlba:',
        ro='Setările au fost salvate în fișierul:',
        uk='Налаштування збережено у файл:',
        sv='Inställningar sparade i fil:',
        fi='Asetukset tallennettu tiedostoon:',
        ja='設定をファイルに保存しました：',
        ko='설정이 파일에 저장되었습니다:',
        zh='设置已保存到文件：', ar='تم حفظ الإعدادات في الملف:'),

    'Ошибка экспорта': _mk(
        'Ошибка экспорта', 'Export error',
        de='Exportfehler', fr="Erreur d'exportation",
        es='Error de exportación', it='Errore di esportazione',
        pt='Erro de exportação', nl='Exportfout',
        pl='Błąd eksportu', tr='Dışa aktarma hatası',
        cs='Chyba exportu', hu='Exportálási hiba',
        ro='Eroare de export', uk='Помилка експорту',
        sv='Exportfel', fi='Vientivirhe',
        ja='エクスポートエラー', ko='내보내기 오류',
        zh='导出错误', ar='خطأ في التصدير'),

    'Не удалось сохранить настройки:': _mk(
        'Не удалось сохранить настройки:', 'Failed to save settings:',
        de='Einstellungen konnten nicht gespeichert werden:',
        fr="Échec de l'enregistrement des paramètres :",
        es='No se pudo guardar la configuración:',
        it='Salvataggio impostazioni non riuscito:',
        pt='Falha ao guardar as definições:',
        nl='Instellingen opslaan mislukt:',
        pl='Nie udało się zapisać ustawień:',
        tr='Ayarlar kaydedilemedi:',
        cs='Nepodařilo se uložit nastavení:',
        hu='Nem sikerült menteni a beállításokat:',
        ro='Salvarea setărilor a eșuat:',
        uk='Не вдалося зберегти налаштування:',
        sv='Kunde inte spara inställningarna:',
        fi='Asetusten tallennus epäonnistui:',
        ja='設定の保存に失敗しました：',
        ko='설정을 저장하지 못했습니다:',
        zh='保存设置失败：', ar='فشل حفظ الإعدادات:'),

    'Импорт завершён': _mk(
        'Импорт завершён', 'Import completed',
        de='Import abgeschlossen', fr='Importation terminée',
        es='Importación completada', it='Importazione completata',
        pt='Importação concluída', nl='Import voltooid',
        pl='Import zakończony', tr='İçe aktarma tamamlandı',
        cs='Import dokončen', hu='Importálás befejezve',
        ro='Import finalizat', uk='Імпорт завершено',
        sv='Import klar', fi='Tuonti valmis',
        ja='インポート完了', ko='가져오기 완료',
        zh='导入完成', ar='اكتمل الاستيراد'),

    'Настройки успешно загружены и применены.': _mk(
        'Настройки успешно загружены и применены.',
        'Settings loaded and applied successfully.',
        de='Einstellungen erfolgreich geladen und angewendet.',
        fr='Paramètres chargés et appliqués avec succès.',
        es='Configuración cargada y aplicada correctamente.',
        it='Impostazioni caricate e applicate correttamente.',
        pt='Definições carregadas e aplicadas com sucesso.',
        nl='Instellingen met succes geladen en toegepast.',
        pl='Ustawienia zostały pomyślnie wczytane i zastosowane.',
        tr='Ayarlar başarıyla yüklendi ve uygulandı.',
        cs='Nastavení bylo úspěšně načteno a použito.',
        hu='A beállítások sikeresen betöltve és alkalmazva.',
        ro='Setările au fost încărcate și aplicate cu succes.',
        uk='Налаштування успішно завантажено та застосовано.',
        sv='Inställningarna lästes in och tillämpades.',
        fi='Asetukset ladattiin ja otettiin käyttöön.',
        ja='設定を正常に読み込み、適用しました。',
        ko='설정을 성공적으로 불러와 적용했습니다.',
        zh='设置已成功加载并应用。',
        ar='تم تحميل الإعدادات وتطبيقها بنجاح.'),

    'Ошибка чтения': _mk(
        'Ошибка чтения', 'Read error',
        de='Lesefehler', fr='Erreur de lecture',
        es='Error de lectura', it='Errore di lettura',
        pt='Erro de leitura', nl='Leesfout',
        pl='Błąd odczytu', tr='Okuma hatası',
        cs='Chyba čtení', hu='Olvasási hiba',
        ro='Eroare de citire', uk='Помилка читання',
        sv='Läsfel', fi='Lukuvirhe',
        ja='読み取りエラー', ko='읽기 오류',
        zh='读取错误', ar='خطأ في القراءة'),

    'Файл повреждён или не является JSON:': _mk(
        'Файл повреждён или не является JSON:',
        'The file is corrupted or not JSON:',
        de='Die Datei ist beschädigt oder kein JSON:',
        fr="Le fichier est corrompu ou n'est pas du JSON :",
        es='El archivo está dañado o no es JSON:',
        it='Il file è danneggiato o non è JSON:',
        pt='O ficheiro está corrompido ou não é JSON:',
        nl='Het bestand is beschadigd of geen JSON:',
        pl='Plik jest uszkodzony lub nie jest JSON:',
        tr='Dosya bozuk veya JSON değil:',
        cs='Soubor je poškozený nebo není JSON:',
        hu='A fájl sérült vagy nem JSON:',
        ro='Fișierul este corupt sau nu este JSON:',
        uk='Файл пошкоджено або це не JSON:',
        sv='Filen är skadad eller inte JSON:',
        fi='Tiedosto on vioittunut tai ei ole JSON:',
        ja='ファイルが破損しているか JSON ではありません：',
        ko='파일이 손상되었거나 JSON이 아닙니다:',
        zh='文件已损坏或不是 JSON：', ar='الملف تالف أو ليس JSON:'),

    'Ошибка импорта': _mk(
        'Ошибка импорта', 'Import error',
        de='Importfehler', fr="Erreur d'importation",
        es='Error de importación', it='Errore di importazione',
        pt='Erro de importação', nl='Importfout',
        pl='Błąd importu', tr='İçe aktarma hatası',
        cs='Chyba importu', hu='Importálási hiba',
        ro='Eroare de import', uk='Помилка імпорту',
        sv='Importfel', fi='Tuontivirhe',
        ja='インポートエラー', ko='가져오기 오류',
        zh='导入错误', ar='خطأ في الاستيراد'),

    'Не удалось загрузить настройки:': _mk(
        'Не удалось загрузить настройки:', 'Failed to load settings:',
        de='Einstellungen konnten nicht geladen werden:',
        fr='Échec du chargement des paramètres :',
        es='No se pudo cargar la configuración:',
        it='Caricamento impostazioni non riuscito:',
        pt='Falha ao carregar as definições:',
        nl='Instellingen laden mislukt:',
        pl='Nie udało się wczytać ustawień:',
        tr='Ayarlar yüklenemedi:',
        cs='Nepodařilo se načíst nastavení:',
        hu='Nem sikerült betölteni a beállításokat:',
        ro='Încărcarea setărilor a eșuat:',
        uk='Не вдалося завантажити налаштування:',
        sv='Kunde inte läsa in inställningarna:',
        fi='Asetusten lataus epäonnistui:',
        ja='設定の読み込みに失敗しました：',
        ko='설정을 불러오지 못했습니다:',
        zh='加载设置失败：', ar='فشل تحميل الإعدادات:'),

    'Это не файл настроек VideoDownloader.': _mk(
        'Это не файл настроек VideoDownloader.',
        'This is not a VideoDownloader settings file.',
        de='Dies ist keine VideoDownloader-Einstellungsdatei.',
        fr="Ce n'est pas un fichier de paramètres VideoDownloader.",
        es='Este no es un archivo de configuración de VideoDownloader.',
        it='Questo non è un file di impostazioni di VideoDownloader.',
        pt='Este não é um ficheiro de definições do VideoDownloader.',
        nl='Dit is geen VideoDownloader-instellingenbestand.',
        pl='To nie jest plik ustawień VideoDownloader.',
        tr='Bu bir VideoDownloader ayar dosyası değil.',
        cs='Toto není soubor nastavení VideoDownloader.',
        hu='Ez nem egy VideoDownloader beállításfájl.',
        ro='Acesta nu este un fișier de setări VideoDownloader.',
        uk='Це не файл налаштувань VideoDownloader.',
        sv='Detta är inte en VideoDownloader-inställningsfil.',
        fi='Tämä ei ole VideoDownloader-asetustiedosto.',
        ja='これは VideoDownloader の設定ファイルではありません。',
        ko='VideoDownloader 설정 파일이 아닙니다.',
        zh='这不是 VideoDownloader 设置文件。',
        ar='هذا ليس ملف إعدادات VideoDownloader.'),

    'Файл не содержит корректных настроек': _mk(
        'Файл не содержит корректных настроек',
        'The file does not contain valid settings',
        de='Die Datei enthält keine gültigen Einstellungen',
        fr='Le fichier ne contient pas de paramètres valides',
        es='El archivo no contiene configuración válida',
        it='Il file non contiene impostazioni valide',
        pt='O ficheiro não contém definições válidas',
        nl='Het bestand bevat geen geldige instellingen',
        pl='Plik nie zawiera prawidłowych ustawień',
        tr='Dosya geçerli ayarlar içermiyor',
        cs='Soubor neobsahuje platná nastavení',
        hu='A fájl nem tartalmaz érvényes beállításokat',
        ro='Fișierul nu conține setări valide',
        uk='Файл не містить коректних налаштувань',
        sv='Filen innehåller inga giltiga inställningar',
        fi='Tiedosto ei sisällä kelvollisia asetuksia',
        ja='ファイルに有効な設定が含まれていません',
        ko='파일에 유효한 설정이 없습니다',
        zh='文件不包含有效的设置', ar='الملف لا يحتوي على إعدادات صالحة'),

    '✅ Настройки экспортированы': _mk(
        '✅ Настройки экспортированы', '✅ Settings exported',
        de='✅ Einstellungen exportiert', fr='✅ Paramètres exportés',
        es='✅ Configuración exportada', it='✅ Impostazioni esportate',
        pt='✅ Definições exportadas', nl='✅ Instellingen geëxporteerd',
        pl='✅ Ustawienia wyeksportowane', tr='✅ Ayarlar dışa aktarıldı',
        cs='✅ Nastavení exportováno', hu='✅ Beállítások exportálva',
        ro='✅ Setări exportate', uk='✅ Налаштування експортовано',
        sv='✅ Inställningar exporterade', fi='✅ Asetukset viety',
        ja='✅ 設定をエクスポートしました', ko='✅ 설정을 내보냈습니다',
        zh='✅ 设置已导出', ar='✅ تم تصدير الإعدادات'),

    '✅ Настройки импортированы': _mk(
        '✅ Настройки импортированы', '✅ Settings imported',
        de='✅ Einstellungen importiert', fr='✅ Paramètres importés',
        es='✅ Configuración importada', it='✅ Impostazioni importate',
        pt='✅ Definições importadas', nl='✅ Instellingen geïmporteerd',
        pl='✅ Ustawienia zaimportowane', tr='✅ Ayarlar içe aktarıldı',
        cs='✅ Nastavení importováno', hu='✅ Beállítások importálva',
        ro='✅ Setări importate', uk='✅ Налаштування імпортовано',
        sv='✅ Inställningar importerade', fi='✅ Asetukset tuotu',
        ja='✅ 設定をインポートしました', ko='✅ 설정을 가져왔습니다',
        zh='✅ 设置已导入', ar='✅ تم استيراد الإعدادات'),

    # ---- Трей ----
    'Открыть окно': _mk(
        'Открыть окно', 'Open window',
        de='Fenster öffnen', fr='Ouvrir la fenêtre',
        es='Abrir ventana', it='Apri finestra',
        pt='Abrir janela', nl='Venster openen',
        pl='Otwórz okno', tr='Pencereyi aç', cs='Otevřít okno',
        hu='Ablak megnyitása', ro='Deschide fereastra', uk='Відкрити вікно',
        sv='Öppna fönster', fi='Avaa ikkuna',
        ja='ウィンドウを開く', ko='창 열기', zh='打开窗口', ar='فتح النافذة'),

    'Автозапуск с Windows': _mk(
        'Автозапуск с Windows', 'Autorun with Windows',
        de='Autostart mit Windows', fr='Démarrage avec Windows',
        es='Inicio con Windows', it='Avvio con Windows',
        pt='Arranque com Windows', nl='Opstarten met Windows',
        pl='Autostart z Windows', tr='Windows ile başlat',
        cs='Autostart s Windows', hu='Indítás a Windows-szal',
        ro='Pornire cu Windows', uk='Автозапуск з Windows',
        sv='Autostart med Windows', fi='Käynnistys Windowsin kanssa',
        ja='Windows起動時に実行', ko='Windows 시작 시 실행',
        zh='随 Windows 启动', ar='التشغيل مع ويندوز'),

    'Через реестр': _mk(
        'Через реестр', 'Via registry',
        de='Über Registry', fr='Via le registre',
        es='Vía registro', it='Tramite registro',
        pt='Via registo', nl='Via register',
        pl='Przez rejestr', tr='Kayıt defteri ile',
        cs='Přes registr', hu='Rendszerleíró adatbázison át',
        ro='Prin registru', uk='Через реєстр',
        sv='Via registret', fi='Rekisterin kautta',
        ja='レジストリ経由', ko='레지스트리를 통해',
        zh='通过注册表', ar='عبر السجل'),

    'Через папку Startup': _mk(
        'Через папку Startup', 'Via Startup folder',
        de='Über Startup-Ordner', fr='Via dossier Démarrage',
        es='Vía carpeta Inicio', it='Tramite cartella Esecuzione automatica',
        pt='Via pasta Inicializar', nl='Via opstartmap',
        pl='Przez folder Startup', tr='Başlangıç klasörü ile',
        cs='Přes složku Po spuštění', hu='Indító mappán keresztül',
        ro='Prin folderul Startup', uk='Через папку Startup',
        sv='Via Startup-mappen', fi='Kautta Startup-kansion',
        ja='Startupフォルダ経由', ko='시작프로그램 폴더를 통해',
        zh='通过 Startup 文件夹', ar='عبر مجلد بدء التشغيل'),

    'Отключить автозагрузку': _mk(
        'Отключить автозагрузку', 'Disable autorun',
        de='Autostart deaktivieren', fr='Désactiver le démarrage auto',
        es='Desactivar inicio automático', it='Disabilita avvio automatico',
        pt='Desativar arranque automático', nl='Autostart uitschakelen',
        pl='Wyłącz autostart', tr='Otomatik başlatmayı devre dışı bırak',
        cs='Zakázat autostart', hu='Autostart kikapcsolása',
        ro='Dezactivează pornirea automată', uk='Вимкнути автозапуск',
        sv='Inaktivera autostart', fi='Poista automaattikäynnistys',
        ja='自動起動を無効化', ko='자동 실행 비활성화',
        zh='禁用自启动', ar='تعطيل التشغيل التلقائي'),

    'Запускать свёрнутым в трей': _mk(
        'Запускать свёрнутым в трей', 'Start minimized to tray',
        de='Minimiert im Infobereich starten',
        fr='Démarrer réduit dans la barre',
        es='Iniciar minimizado en la bandeja',
        it='Avvia ridotto nella barra',
        pt='Iniciar minimizado na bandeja',
        nl='Geminimaliseerd starten',
        pl='Uruchamiaj zminimalizowany w zasobniku',
        tr='Tepsiye küçültülmüş başlat',
        cs='Spouštět minimalizovaně',
        hu='Indítás a tálcára kicsinyítve',
        ro='Pornește minimizat în tavă',
        uk='Запускати згорнутим у трей',
        sv='Starta minimerad i aktivitetsfältet',
        fi='Käynnistä pienennettynä',
        ja='トレイに最小化して起動',
        ko='트레이로 최소화하여 시작',
        zh='最小化到托盘启动', ar='بدء التشغيل مصغرًا'),

    'Приложение свёрнуто в трей.': _mk(
        'Приложение свёрнуто в трей.', 'Application minimized to tray.',
        de='Anwendung im Infobereich minimiert.',
        fr='Application réduite dans la barre.',
        es='Aplicación minimizada en la bandeja.',
        it='Applicazione ridotta nella barra.',
        pt='Aplicação minimizada para a bandeja.',
        nl='Applicatie geminimaliseerd naar systeemvak.',
        pl='Aplikacja zminimalizowana do zasobnika.',
        tr='Uygulama tepsiye küçültüldü.',
        cs='Aplikace minimalizována do oznamovací oblasti.',
        hu='Az alkalmazás a tálcára kicsinyítve.',
        ro='Aplicație minimizată în tavă.',
        uk='Застосунок згорнуто в трей.',
        sv='Programmet minimeras till aktivitetsfältet.',
        fi='Sovellus pienennetty ilmaisinalueelle.',
        ja='アプリをトレイに最小化しました。',
        ko='앱이 트레이로 최소화되었습니다.',
        zh='应用已最小化到托盘。', ar='تم تصغير التطبيق إلى شريط النظام.'),

    'Выход': _mk(
        'Выход', 'Exit',
        de='Beenden', fr='Quitter', es='Salir', it='Esci',
        pt='Sair', nl='Afsluiten', pl='Wyjście', tr='Çıkış',
        cs='Konec', hu='Kilépés', ro='Ieșire', uk='Вихід',
        sv='Avsluta', fi='Poistu',
        ja='終了', ko='종료', zh='退出', ar='خروج'),

    # ---- Форматы ----
    'fmt_best': _mk('🎬  Лучшее', '🎬  Best',
        de='🎬  Beste', fr='🎬  Meilleure', es='🎬  Mejor',
        it='🎬  Migliore', pt='🎬  Melhor', nl='🎬  Beste',
        pl='🎬  Najlepsza', tr='🎬  En iyi', cs='🎬  Nejlepší',
        hu='🎬  Legjobb', ro='🎬  Cea mai bună', uk='🎬  Найкраще',
        sv='🎬  Bästa', fi='🎬  Paras',
        ja='🎬  最高', ko='🎬  최고', zh='🎬  最佳', ar='🎬  الأفضل'),
    'fmt_1080': _mk('📺  1080p', '📺  1080p', de='📺  1080p', fr='📺  1080p',
        es='📺  1080p', it='📺  1080p', pt='📺  1080p', nl='📺  1080p',
        pl='📺  1080p', tr='📺  1080p', cs='📺  1080p', hu='📺  1080p',
        ro='📺  1080p', uk='📺  1080p', sv='📺  1080p', fi='📺  1080p',
        ja='📺  1080p', ko='📺  1080p', zh='📺  1080p', ar='📺  1080p'),
    'fmt_720': _mk('📺  720p', '📺  720p', de='📺  720p', fr='📺  720p',
        es='📺  720p', it='📺  720p', pt='📺  720p', nl='📺  720p',
        pl='📺  720p', tr='📺  720p', cs='📺  720p', hu='📺  720p',
        ro='📺  720p', uk='📺  720p', sv='📺  720p', fi='📺  720p',
        ja='📺  720p', ko='📺  720p', zh='📺  720p', ar='📺  720p'),
    'fmt_480': _mk('📺  480p', '📺  480p', de='📺  480p', fr='📺  480p',
        es='📺  480p', it='📺  480p', pt='📺  480p', nl='📺  480p',
        pl='📺  480p', tr='📺  480p', cs='📺  480p', hu='📺  480p',
        ro='📺  480p', uk='📺  480p', sv='📺  480p', fi='📺  480p',
        ja='📺  480p', ko='📺  480p', zh='📺  480p', ar='📺  480p'),
    'fmt_360': _mk('📺  360p', '📺  360p', de='📺  360p', fr='📺  360p',
        es='📺  360p', it='📺  360p', pt='📺  360p', nl='📺  360p',
        pl='📺  360p', tr='📺  360p', cs='📺  360p', hu='📺  360p',
        ro='📺  360p', uk='📺  360p', sv='📺  360p', fi='📺  360p',
        ja='📺  360p', ko='📺  360p', zh='📺  360p', ar='📺  360p'),
    'fmt_abest': _mk('🎵  Лучшее', '🎵  Best',
        de='🎵  Beste', fr='🎵  Meilleure', es='🎵  Mejor',
        it='🎵  Migliore', pt='🎵  Melhor', nl='🎵  Beste',
        pl='🎵  Najlepsza', tr='🎵  En iyi', cs='🎵  Nejlepší',
        hu='🎵  Legjobb', ro='🎵  Cea mai bună', uk='🎵  Найкраще',
        sv='🎵  Bästa', fi='🎵  Paras',
        ja='🎵  最高', ko='🎵  최고', zh='🎵  最佳', ar='🎵  الأفضل'),
    'fmt_a320': _mk('🎧  320 kbps', '🎧  320 kbps', de='🎧  320 kbps',
        fr='🎧  320 kbps', es='🎧  320 kbps', it='🎧  320 kbps',
        pt='🎧  320 kbps', nl='🎧  320 kbps', pl='🎧  320 kbps',
        tr='🎧  320 kbps', cs='🎧  320 kbps', hu='🎧  320 kbps',
        ro='🎧  320 kbps', uk='🎧  320 kbps', sv='🎧  320 kbps',
        fi='🎧  320 kbps', ja='🎧  320 kbps', ko='🎧  320 kbps',
        zh='🎧  320 kbps', ar='🎧  320 kbps'),
    'fmt_a192': _mk('🎧  192 kbps', '🎧  192 kbps', de='🎧  192 kbps',
        fr='🎧  192 kbps', es='🎧  192 kbps', it='🎧  192 kbps',
        pt='🎧  192 kbps', nl='🎧  192 kbps', pl='🎧  192 kbps',
        tr='🎧  192 kbps', cs='🎧  192 kbps', hu='🎧  192 kbps',
        ro='🎧  192 kbps', uk='🎧  192 kbps', sv='🎧  192 kbps',
        fi='🎧  192 kbps', ja='🎧  192 kbps', ko='🎧  192 kbps',
        zh='🎧  192 kbps', ar='🎧  192 kbps'),
    'fmt_a128': _mk('🎧  128 kbps', '🎧  128 kbps', de='🎧  128 kbps',
        fr='🎧  128 kbps', es='🎧  128 kbps', it='🎧  128 kbps',
        pt='🎧  128 kbps', nl='🎧  128 kbps', pl='🎧  128 kbps',
        tr='🎧  128 kbps', cs='🎧  128 kbps', hu='🎧  128 kbps',
        ro='🎧  128 kbps', uk='🎧  128 kbps', sv='🎧  128 kbps',
        fi='🎧  128 kbps', ja='🎧  128 kbps', ko='🎧  128 kbps',
        zh='🎧  128 kbps', ar='🎧  128 kbps'),
    'fmt_flac': _mk('💿  FLAC', '💿  FLAC', de='💿  FLAC', fr='💿  FLAC',
        es='💿  FLAC', it='💿  FLAC', pt='💿  FLAC', nl='💿  FLAC',
        pl='💿  FLAC', tr='💿  FLAC', cs='💿  FLAC', hu='💿  FLAC',
        ro='💿  FLAC', uk='💿  FLAC', sv='💿  FLAC', fi='💿  FLAC',
        ja='💿  FLAC', ko='💿  FLAC', zh='💿  FLAC', ar='💿  FLAC'),
    'fmt_wav': _mk('💿  WAV', '💿  WAV', de='💿  WAV', fr='💿  WAV',
        es='💿  WAV', it='💿  WAV', pt='💿  WAV', nl='💿  WAV',
        pl='💿  WAV', tr='💿  WAV', cs='💿  WAV', hu='💿  WAV',
        ro='💿  WAV', uk='💿  WAV', sv='💿  WAV', fi='💿  WAV',
        ja='💿  WAV', ko='💿  WAV', zh='💿  WAV', ar='💿  WAV'),

    'Переключить на светлую тему': _mk(
        'Переключить на светлую тему', 'Switch to light theme',
        de='Zum hellen Design wechseln', fr='Passer au thème clair',
        es='Cambiar al tema claro', it='Passa al tema chiaro',
        pt='Mudar para tema claro', nl='Naar licht thema schakelen',
        pl='Przełącz na jasny motyw', tr='Açık temaya geç',
        cs='Přepnout na světlé téma', hu='Váltás világos témára',
        ro='Comută pe tema deschisă', uk='Перемкнути на світлу тему',
        sv='Byt till ljust tema', fi='Vaihda vaaleaan teemaan',
        ja='ライトテーマに切り替え', ko='라이트 테마로 전환',
        zh='切换到浅色主题', ar='التبديل إلى السمة الفاتحة'),

    'Переключить на тёмную тему': _mk(
        'Переключить на тёмную тему', 'Switch to dark theme',
        de='Zum dunklen Design wechseln', fr='Passer au thème sombre',
        es='Cambiar al tema oscuro', it='Passa al tema scuro',
        pt='Mudar para tema escuro', nl='Naar donker thema schakelen',
        pl='Przełącz na ciemny motyw', tr='Koyu temaya geç',
        cs='Přepnout na tmavé téma', hu='Váltás sötét témára',
        ro='Comută pe tema închisă', uk='Перемкнути на темну тему',
        sv='Byt till mörkt tema', fi='Vaihda tummaan teemaan',
        ja='ダークテーマに切り替え', ko='다크 테마로 전환',
        zh='切换到深色主题', ar='التبديل إلى السمة الداكنة'),

    'Сменить язык интерфейса': _mk(
        'Сменить язык интерфейса', 'Change interface language',
        de='Sprache der Oberfläche ändern',
        fr="Changer la langue de l'interface",
        es='Cambiar el idioma de la interfaz',
        it="Cambia la lingua dell'interfaccia",
        pt='Alterar o idioma da interface',
        nl='Interfacetaal wijzigen',
        pl='Zmień język interfejsu',
        tr='Arayüz dilini değiştir',
        cs='Změnit jazyk rozhraní',
        hu='Felület nyelvének módosítása',
        ro='Schimbă limba interfeței',
        uk='Змінити мову інтерфейсу',
        sv='Byt gränssnittsspråk',
        fi='Vaihda käyttöliittymän kieli',
        ja='インターフェース言語を変更',
        ko='인터페이스 언어 변경',
        zh='更改界面语言', ar='تغيير لغة الواجهة'),

    'Не удалось включить автозапуск.': _mk(
        'Не удалось включить автозапуск.', 'Failed to enable autorun.',
        de='Autostart konnte nicht aktiviert werden.',
        fr="Échec de l'activation du démarrage automatique.",
        es='No se pudo activar el inicio automático.',
        it="Impossibile attivare l'avvio automatico.",
        pt='Falha ao ativar o arranque automático.',
        nl='Autostart kon niet worden ingeschakeld.',
        pl='Nie udało się włączyć autostartu.',
        tr='Otomatik başlatma etkinleştirilemedi.',
        cs='Autostart se nepodařilo povolit.',
        hu='Nem sikerült engedélyezni az autostartot.',
        ro='Activarea pornirii automate a eșuat.',
        uk='Не вдалося увімкнути автозапуск.',
        sv='Kunde inte aktivera autostart.',
        fi='Automaattikäynnistyksen aktivointi epäonnistui.',
        ja='自動起動を有効にできませんでした。',
        ko='자동 실행을 활성화하지 못했습니다.',
        zh='无法启用自启动。', ar='فشل تمكين التشغيل التلقائي.'),

    'Не удалось создать файл в папке Startup.': _mk(
        'Не удалось создать файл в папке Startup.',
        'Failed to create file in the Startup folder.',
        de='Datei im Startup-Ordner konnte nicht erstellt werden.',
        fr='Échec de la création du fichier dans le dossier Démarrage.',
        es='No se pudo crear el archivo en la carpeta Inicio.',
        it='Impossibile creare il file nella cartella Esecuzione automatica.',
        pt='Falha ao criar o ficheiro na pasta Inicializar.',
        nl='Kan bestand niet aanmaken in de opstartmap.',
        pl='Nie udało się utworzyć pliku w folderze Startup.',
        tr='Başlangıç klasöründe dosya oluşturulamadı.',
        cs='Nepodařilo se vytvořit soubor ve složce Po spuštění.',
        hu='Nem sikerült létrehozni a fájlt az Indító mappában.',
        ro='Crearea fișierului în folderul Startup a eșuat.',
        uk='Не вдалося створити файл у папці Startup.',
        sv='Kunde inte skapa fil i Startup-mappen.',
        fi='Tiedoston luonti Startup-kansioon epäonnistui.',
        ja='Startup フォルダにファイルを作成できませんでした。',
        ko='시작프로그램 폴더에 파일을 만들지 못했습니다.',
        zh='无法在 Startup 文件夹中创建文件。',
        ar='فشل إنشاء ملف في مجلد بدء التشغيل.'),

    'Автозапуск недоступен': _mk(
        'Автозапуск недоступен', 'Autorun is unavailable',
        de='Autostart nicht verfügbar', fr='Démarrage auto indisponible',
        es='Inicio automático no disponible',
        it='Avvio automatico non disponibile',
        pt='Arranque automático indisponível',
        nl='Autostart niet beschikbaar',
        pl='Autostart niedostępny',
        tr='Otomatik başlatma kullanılamıyor',
        cs='Autostart není dostupný',
        hu='Az autostart nem érhető el',
        ro='Pornirea automată nu este disponibilă',
        uk='Автозапуск недоступний',
        sv='Autostart är inte tillgänglig',
        fi='Automaattikäynnistys ei ole käytettävissä',
        ja='自動起動は利用できません',
        ko='자동 실행을 사용할 수 없습니다',
        zh='自启动不可用', ar='التشغيل التلقائي غير متاح'),

    'Не удалось открыть:': _mk(
        'Не удалось открыть:', 'Failed to open:',
        de='Konnte nicht geöffnet werden:', fr="Échec de l'ouverture :",
        es='No se pudo abrir:', it='Impossibile aprire:',
        pt='Falha ao abrir:', nl='Kan niet openen:',
        pl='Nie udało się otworzyć:', tr='Açılamadı:',
        cs='Nepodařilo se otevřít:', hu='Nem sikerült megnyitni:',
        ro='Deschiderea a eșuat:', uk='Не вдалося відкрити:',
        sv='Kunde inte öppna:', fi='Avaus epäonnistui:',
        ja='開けませんでした：', ko='열지 못했습니다:',
        zh='无法打开：', ar='فشل الفتح:'),
}


def _tr(key, lang):
    entry = UI_TR.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get('en') or entry.get('ru') or key


class Tooltip:
    def __init__(self, widget, key, app=None, delay=450):
        self.widget = widget
        self.app = app
        self.key = key
        self.delay = delay
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def set_key(self, key):
        self.key = key

    def _get_text(self):
        if self.app is None or self.key is None:
            return ""
        return self.app._t(self.key)

    def refresh(self):
        was_visible = self.tip is not None
        self._cancel()
        self._hide()
        if not was_visible:
            return
        try:
            px, py = self.widget.winfo_pointerxy()
            wx = self.widget.winfo_rootx()
            wy = self.widget.winfo_rooty()
            ww = self.widget.winfo_width()
            wh = self.widget.winfo_height()
            if wx <= px <= wx + ww and wy <= py <= wy + wh:
                self._show()
        except Exception:
            pass

    def _on_enter(self, event=None):
        self._cancel()
        try:
            self.after_id = self.widget.after(self.delay, self._show)
        except Exception:
            pass

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _show(self):
        if self.tip:
            return
        text = self._get_text()
        if not text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_attributes("-topmost", True)
        self.tip.configure(bg="#e0a030")
        inner = tk.Frame(self.tip, bg="#1a1a1a")
        inner.pack(padx=1, pady=1)
        tk.Label(inner, text=text, bg="#1a1a1a", fg="#ffffff",
                 font=("Segoe UI", 9), justify="left",
                 padx=12, pady=8, wraplength=420).pack()
        self.tip.update_idletasks()
        tw = self.tip.winfo_width()
        th = self.tip.winfo_height()
        sw = self.tip.winfo_screenwidth()
        sh = self.tip.winfo_screenheight()
        if x + tw > sw - 6:
            x = sw - tw - 6
        if x < 6:
            x = 6
        if y + th > sh - 6:
            y = self.widget.winfo_rooty() - th - 6
        self.tip.wm_geometry(f"+{x}+{y}")

    def _hide(self):
        if self.tip:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class Task:
    def __init__(self, url, fmt, folder, mode):
        self.id = str(uuid.uuid4())[:8]
        self.url = url
        self.fmt = fmt
        self.folder = folder
        self.mode = mode
        self.title = url
        self.status = "ожидание"
        self.filename = ""
        self.error = ""
        self.created = time.time()
        self.target_percent = 0.0
        self.target_speed = 0.0
        self.target_eta = 0.0
        self.total_bytes = 0
        self.done_bytes = 0
        self.display_percent = 0.0
        self.display_speed = 0.0
        self.display_eta = 0.0
        self.frame = None
        self.progress_rect = None
        self.progress_canvas = None
        self.title_lbl = None
        self.status_lbl = None
        self.thumb_lbl = None
        self.thumb_photo = None
        self.thumb_loaded = False
        self._locked_status = False
        self._status_key = None
        self._status_color = None


class App:
    def __init__(self):
        self.settings = load_settings()
        self._autorun_launch = "--minimized" in sys.argv

        self.theme_name = self.settings.get("theme", "dark")
        if self.theme_name not in THEMES:
            self.theme_name = "dark"
        self.T = {}
        self.T.update(THEMES[self.theme_name])

        self._ui_lang = self.settings.get("ui_lang", "en")
        if self._ui_lang not in UI_LANGS:
            self._ui_lang = "en"

        self.root = tk.Tk()
        self.root.title(self._t('Скачиватель'))
        self.root.configure(bg=self.T["bg"])
        self.root.resizable(False, False)
        try:
            self.root.overrideredirect(True)
        except Exception:
            pass

        self._base_w_select = 620
        self._base_h_select = 420
        self._base_w_main = 780
        self._base_h_main = 820

        self._place_centered(self._base_w_select, self._base_h_select)

        if self._autorun_launch and TRAY_AVAILABLE:
            try:
                self.root.withdraw()
            except Exception:
                pass

        self.current_mode = None
        self.tray_icon = None
        self._warning_dlg = None
        self._log_dlg = None
        self._confirm_dlg = None
        self._icon_photo = None
        self._styled = []
        self._i18n_widgets = []
        self._theme_btn = None
        self._theme_btn_main = None
        self._lang_btn = None
        self._lang_btn_main = None
        self._theme_tooltip = None
        self._lang_tooltip = None
        self._switch_tooltip = None
        self._tooltips = []
        self.stop_flag = False
        self._last_error_time = 0

        self.queue = queue.Queue()
        self.active_tasks = {}
        self.history = list(self.settings.get("history", []))[:30]
        self._last_progress_update = {}
        self._completed_widgets = []

        self.container = tk.Frame(self.root, bg=self.T["bg"])
        self.container.pack(fill="both", expand=True)
        self._reg(self.container, "frame")

        self.mode_select_frame = None
        self.main_frame = None

        self._build_mode_select()
        self._build_main()

        self.root.after(100, self._force_window_focus)
        self.root.after(500, self._force_window_focus)

        self.queue_worker_thread = threading.Thread(
            target=self._queue_worker, daemon=True, name="dl-worker")
        self.queue_worker_thread.start()

        self.root.after(80, self._animate_progress)

        self._setup_tray()
        self.root.after(400, self._update_tray_status)

        self.root.after(200, self._apply_icon)
        self.root.after(500, self._poll_signal)
        self.root.after(1500, self._periodic_tray_refresh)

        log_event("=== Приложение запущено ===")

        if not YTDLP_OK:
            self.root.after(500, lambda: self._show_warning_dialog(
                'Не установлен yt-dlp',
                'Внутри .exe нет модуля yt-dlp.'))

        if not HAS_FFMPEG:
            self.root.after(700, lambda: self._show_warning_dialog(
                'FFmpeg не найден',
                'Рядом с приложением нет ffmpeg.exe.\n\n' +
                'Без FFmpeg недоступны MP3, FLAC, WAV и лучшее качество.'))

        if self._autorun_launch and TRAY_AVAILABLE:
            self._show_main(self.settings.get("last_mode", "video"),
                            from_startup=True)
        else:
            self._show_mode_select()

    # ============ i18n ============
    def _t(self, key, **fmt):
        text = _tr(key, self._ui_lang)
        if fmt:
            try:
                return text.format(**fmt)
            except Exception:
                return text
        return text

    def _reg_i18n(self, widget, key):
        self._i18n_widgets.append((widget, key))

    def _rebuild_all_texts(self):
        for w, key in self._i18n_widgets:
            try:
                if w.winfo_exists():
                    w.config(text=self._t(key))
            except Exception:
                pass

        # Обновляем заголовок главного экрана под текущий режим
        try:
            if self.current_mode == "audio":
                self.title_lbl.config(text=self._t('Скачиватель музыки'))
            elif self.current_mode == "video":
                self.title_lbl.config(text=self._t('Скачиватель видео'))
        except Exception:
            pass

        # Обновляем тултип режима
        try:
            if self._switch_tooltip is not None and self.current_mode:
                if self.current_mode == "audio":
                    self._switch_tooltip.set_key("Переключить на видео")
                else:
                    self._switch_tooltip.set_key("Переключить на музыку")
        except Exception:
            pass

        # Обновляем FFmpeg-предупреждение
        try:
            self._refresh_ffmpeg_warn()
        except Exception:
            pass

        try:
            self.root.title(self._t('Скачиватель'))
        except Exception:
            pass

        # Пересобираем радиокнопки форматов
        try:
            if self.current_mode is not None:
                self._rebuild_formats(self.current_mode, keep_selection=True)
        except Exception:
            pass

        # Обновляем тултипы темы
        try:
            for tip in self._tooltips:
                if getattr(tip, "widget", None) in (self._theme_btn,
                                                     self._theme_btn_main):
                    tip.set_key(self._theme_tooltip_key())
        except Exception:
            pass

        # Обновляем статус текущих задач
        try:
            for task in self.active_tasks.values():
                if task._status_key and task.status_lbl and task.status_lbl.winfo_exists():
                    color = task._status_color or self.T["fg_dim"]
                    task.status_lbl.config(text=self._t(task._status_key),
                                            fg=color)
        except Exception:
            pass

        # Обновляем главный статус
        try:
            if self.current_mode is not None and not self.active_tasks:
                self.status.config(text=self._t('Готов к работе'),
                                   fg=self.T["fg_dim"])
        except Exception:
            pass

        try:
            self._render_completed()
        except Exception:
            pass

        try:
            if TRAY_AVAILABLE and self.tray_icon is not None:
                self._rebuild_tray_menu()
        except Exception:
            pass

    def _refresh_ffmpeg_warn(self):
        if not self.current_mode:
            return
        if HAS_FFMPEG:
            try:
                self.ffmpeg_warn.pack_forget()
            except Exception:
                pass
            return
        if self.current_mode == "audio":
            key = '⚠ FFmpeg не найден — MP3 / FLAC / WAV недоступны'
        else:
            key = '⚠ FFmpeg не найден — лучшее качество недоступно'
        try:
            self.ffmpeg_warn.config(text=self._t(key))
            if not self.ffmpeg_warn.winfo_ismapped():
                self.ffmpeg_warn.pack(pady=(2, 0))
        except Exception:
            pass

    def _set_ui_lang(self, code):
        if code not in UI_LANGS:
            return
        self._ui_lang = code
        self.settings["ui_lang"] = code
        save_settings(self.settings)
        self._update_lang_button()
        self._rebuild_all_texts()
        self._fit_window()

    def _update_lang_button(self):
        text = f"🌐 {self._ui_lang.upper()}"
        for btn in (self._lang_btn, self._lang_btn_main):
            try:
                if btn is not None and btn.winfo_exists():
                    btn.config(text=text)
            except Exception:
                pass

    def _show_lang_menu(self):
        T = self.T
        m = tk.Menu(self.root, tearoff=0,
                    bg=T["bg_dark"], fg=T["fg"],
                    activebackground=T["preset_active"],
                    activeforeground=T["selected_fg"],
                    bd=0, relief="flat",
                    font=("Segoe UI", 10))
        for code, name in UI_LANGS.items():
            prefix = "✓  " if code == self._ui_lang else "     "
            m.add_command(label=prefix + name,
                          command=lambda c=code: self._set_ui_lang(c))
        try:
            src = self._lang_btn_main if (self._lang_btn_main and
                                           self._lang_btn_main.winfo_ismapped()) \
                  else self._lang_btn
            x = src.winfo_rootx()
            y = src.winfo_rooty() + src.winfo_height() + 2
            m.tk_popup(x, y)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    def _lang_press(self, e):
        self._lang_click_x = e.x_root
        self._lang_click_y = e.y_root

    def _lang_release(self, e):
        try:
            if (abs(e.x_root - self._lang_click_x) < 5 and
                    abs(e.y_root - self._lang_click_y) < 5):
                self._show_lang_menu()
        except Exception:
            pass

    # ============ Автоподгонка окна ============
    def _fit_window(self):
        try:
            self.root.update_idletasks()
            req_w = self.root.winfo_reqwidth()
            req_h = self.root.winfo_reqheight()

            cur_w = self.root.winfo_width()
            cur_h = self.root.winfo_height()
            cur_x = self.root.winfo_x()
            cur_y = self.root.winfo_y()

            base_w = (self._base_w_select if self.current_mode is None
                      else self._base_w_main)
            base_h = (self._base_h_select if self.current_mode is None
                      else self._base_h_main)

            w = max(base_w, req_w + 8)
            h = max(base_h, req_h + 8)

            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            if w > sw - 40:
                w = sw - 40
            if h > sh - 60:
                h = sh - 60

            new_x = cur_x + (cur_w - w) // 2
            new_y = cur_y + (cur_h - h) // 2
            if new_x < 0: new_x = 0
            if new_y < 0: new_y = 0
            if new_x + w > sw: new_x = sw - w
            if new_y + h > sh: new_y = sh - h

            self.root.geometry(f"{w}x{h}+{new_x}+{new_y}")
            self.root.update_idletasks()
        except Exception:
            pass

    # ============ EXPORT/IMPORT ============
    def _collect_all_settings(self):
        data = dict(self.settings)
        data["theme"] = self.theme_name
        data["history"] = self.history[:30]
        data["ui_lang"] = self._ui_lang
        if self.current_mode:
            data[f"format_{self.current_mode}"] = self.fmt_var.get()
            data[f"folder_{self.current_mode}"] = self.folder_var.get()
            data["last_mode"] = self.current_mode
        data.pop("autorun_method", None)
        return data

    def _export_settings(self):
        try:
            data = self._collect_all_settings()
            default_name = "VideoDownloader_settings.json"

            path = filedialog.asksaveasfilename(
                title=self._t('Куда сохранить настройки?'),
                defaultextension=".json",
                initialdir=os.path.expanduser("~"),
                initialfile=default_name,
                filetypes=[("JSON", "*.json"), ("*.*", "*.*")])
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log_event(f"Настройки экспортированы: {path}")
            self.status.config(text=self._t('✅ Настройки экспортированы'),
                               fg=self.T["green"])
            self._show_warning_dialog(
                'Экспорт завершён',
                self._t('Настройки сохранены в файл:') + f"\n\n{path}")
        except Exception as e:
            log_event(f"Ошибка экспорта: {e}")
            self._show_warning_dialog(
                'Ошибка экспорта',
                self._t('Не удалось сохранить настройки:') + f"\n{e}")
        finally:
            self.root.after(100, self._force_window_focus)

    def _import_settings(self):
        try:
            path = filedialog.askopenfilename(
                title=self._t('Выберите файл с настройками'),
                initialdir=os.path.expanduser("~"),
                filetypes=[("JSON", "*.json"), ("*.*", "*.*")])
            if not path:
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(self._t('Файл не содержит корректных настроек'))

            if not any(k in data for k in
                       ("theme", "history", "last_mode",
                        "format_video", "format_audio")):
                raise ValueError(self._t('Это не файл настроек VideoDownloader.'))

            self._apply_imported_settings(data)
            log_event(f"Настройки импортированы: {path}")
            self.status.config(text=self._t('✅ Настройки импортированы'),
                               fg=self.T["green"])
            self._show_warning_dialog(
                'Импорт завершён',
                'Настройки успешно загружены и применены.')
        except json.JSONDecodeError as e:
            self._show_warning_dialog(
                'Ошибка чтения',
                self._t('Файл повреждён или не является JSON:') + f"\n{e}")
        except Exception as e:
            log_event(f"Ошибка импорта: {e}")
            self._show_warning_dialog(
                'Ошибка импорта',
                self._t('Не удалось загрузить настройки:') + f"\n{e}")
        finally:
            self.root.after(100, self._force_window_focus)

    def _apply_imported_settings(self, data):
        self.settings.update(data)

        new_theme = data.get("theme", self.theme_name)
        if new_theme not in THEMES:
            new_theme = "dark"
        if new_theme != self.theme_name:
            self.theme_name = new_theme
            self.T.clear()
            self.T.update(THEMES[new_theme])
            self._repaint_all()
            self._update_theme_button()

        new_lang = data.get("ui_lang", self._ui_lang)
        if new_lang in UI_LANGS:
            self._ui_lang = new_lang
            self._update_lang_button()

        if "history" in data and isinstance(data["history"], list):
            self.history = data["history"][:30]
            self._render_completed()

        current = self.current_mode
        if current is None:
            current = data.get("last_mode", "video")
            if current not in ("video", "audio"):
                current = "video"

        saved_fmt = data.get(f"format_{current}", "")
        if saved_fmt:
            self.settings[f"format_{current}"] = saved_fmt

        saved_folder = data.get(f"folder_{current}", "")
        if saved_folder:
            self.settings[f"folder_{current}"] = saved_folder

        if self.current_mode is not None:
            self._rebuild_formats(self.current_mode)
            f = self.settings.get(f"folder_{self.current_mode}", "")
            if f and os.path.isdir(f):
                self.folder_var.set(f)

        self._persist_settings()
        self._rebuild_all_texts()
        self._fit_window()

    # ============ АВТОЗАГРУЗКА ============
    def _autostart_command(self):
        if getattr(sys, 'frozen', False):
            exe = sys.executable
            script = ""
        else:
            exe = sys.executable
            if exe.lower().endswith("python.exe"):
                alt = exe[:-10] + "pythonw.exe"
                if os.path.exists(alt):
                    exe = alt
            script = os.path.abspath(sys.argv[0])
        cmd = f'"{exe}"'
        if script:
            cmd += f' "{script}"'
        if self.settings.get("start_minimized", False):
            cmd += " --minimized"
        return cmd

    def _startup_dir(self):
        return os.path.join(os.environ.get("APPDATA", ""),
                            "Microsoft", "Windows", "Start Menu",
                            "Programs", "Startup")

    def _startup_bat_path(self):
        return os.path.join(self._startup_dir(), "VideoDownloader.bat")

    def _is_registry_autorun(self):
        if not WINREG_OK:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY,
                                 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, AUTORUN_NAME)
                return val == self._autostart_command()
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def _set_registry_autorun(self, enable):
        if not WINREG_OK:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY,
                                 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    winreg.SetValueEx(key, AUTORUN_NAME, 0,
                                      winreg.REG_SZ, self._autostart_command())
                else:
                    try:
                        winreg.DeleteValue(key, AUTORUN_NAME)
                    except FileNotFoundError:
                        pass
                return True
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def _is_startup_autorun(self):
        return os.path.exists(self._startup_bat_path())

    def _set_startup_autorun(self, enable):
        try:
            path = self._startup_bat_path()
            if enable:
                cmd = self._autostart_command()
                with open(path, "w", encoding="utf-8") as f:
                    f.write("@echo off\r\n")
                    f.write(f'start "" {cmd}\r\n')
            else:
                if os.path.exists(path):
                    os.remove(path)
            return True
        except Exception:
            return False

    def _current_autorun_method(self):
        if self._is_registry_autorun():
            return "registry"
        if self._is_startup_autorun():
            return "startup"
        return "none"

    def _set_autorun_method(self, method):
        current = self._current_autorun_method()
        if current == method:
            self.settings["autorun_method"] = method
            save_settings(self.settings)
            return method

        self._set_registry_autorun(False)
        self._set_startup_autorun(False)

        if method == "registry":
            if not self._set_registry_autorun(True):
                if self._set_startup_autorun(True):
                    method = "startup"
                else:
                    method = "none"
                    self.root.after(0, lambda: self._show_warning_dialog(
                        'Автозапуск недоступен',
                        'Не удалось включить автозапуск.'))
        elif method == "startup":
            if not self._set_startup_autorun(True):
                method = "none"
                self.root.after(0, lambda: self._show_warning_dialog(
                    'Автозапуск недоступен',
                    'Не удалось создать файл в папке Startup.'))

        self.settings["autorun_method"] = method
        save_settings(self.settings)
        return method

    def _tray_set_registry(self, icon=None, item=None):
        self.root.after(0, lambda: self._set_autorun_method("registry"))

    def _tray_set_startup(self, icon=None, item=None):
        self.root.after(0, lambda: self._set_autorun_method("startup"))

    def _tray_disable_autorun(self, icon=None, item=None):
        self.root.after(0, lambda: self._set_autorun_method("none"))

    def _toggle_start_minimized(self, icon=None, item=None):
        self.settings["start_minimized"] = not self.settings.get("start_minimized", False)
        save_settings(self.settings)
        cur = self._current_autorun_method()
        if cur != "none":
            self.root.after(0, lambda c=cur: self._set_autorun_method(c))

    # ============ Трей ============
    def _load_font(self, size):
        for name in ("arialbd.ttf", "segoeuib.ttf", "arial.ttf", "segoeui.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _make_icon_image(self, state="idle", count=0):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if state == "downloading":
            color = "#e0a030"
        elif state == "error":
            color = "#e05555"
        else:
            color = "#6fbf73"
        d.ellipse((2, 2, size - 2, size - 2), fill=color)
        if state == "downloading" and count > 0:
            text = str(count) if count < 100 else "99"
            font_size = 36 if count < 10 else (28 if count < 100 else 22)
            font = self._load_font(font_size)
            try:
                bbox = d.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = (size - tw) / 2 - bbox[0]
                ty = (size - th) / 2 - bbox[1]
                d.text((tx, ty), text, font=font, fill="white")
            except Exception:
                d.ellipse((24, 24, 40, 40), fill="white")
        elif state == "error":
            d.line((20, 20, 44, 44), fill="white", width=7)
            d.line((44, 20, 20, 44), fill="white", width=7)
        else:
            d.line((32, 14, 32, 40), fill="white", width=6)
            d.line((32, 40, 18, 26), fill="white", width=6)
            d.line((32, 40, 46, 26), fill="white", width=6)
            d.line((16, 48, 48, 48), fill="white", width=5)
        return img

    def _update_tray_status(self):
        if not self.tray_icon:
            return
        n = len(self.active_tasks)
        try:
            if n > 0:
                img = self._make_icon_image(state="downloading", count=n)
                title = f"{self._t('Скачиватель')} — {n}"
            else:
                if (time.time() - self._last_error_time) < 6:
                    img = self._make_icon_image(state="error")
                    title = self._t('Скачиватель')
                else:
                    img = self._make_icon_image(state="idle")
                    title = self._t('Скачиватель')
            self.tray_icon.icon = img
            try:
                self.tray_icon.title = title
            except Exception:
                pass
        except Exception as e:
            log_event(f"Трей: не удалось обновить иконку: {e}")

    def _periodic_tray_refresh(self):
        try:
            self._update_tray_status()
        except Exception:
            pass
        if not self.stop_flag:
            try:
                self.root.after(1500, self._periodic_tray_refresh)
            except Exception:
                pass

    # ============ Анимация прогресса ============
    def _animate_progress(self):
        if self.stop_flag:
            return
        for task in list(self.active_tasks.values()):
            try:
                diff = task.target_percent - task.display_percent
                if abs(diff) < 0.05:
                    task.display_percent = task.target_percent
                else:
                    task.display_percent += diff * 0.18

                sdiff = task.target_speed - task.display_speed
                if abs(sdiff) < 100:
                    task.display_speed = task.target_speed
                else:
                    task.display_speed += sdiff * 0.22

                ediff = task.target_eta - task.display_eta
                if abs(ediff) < 1:
                    task.display_eta = task.target_eta
                else:
                    task.display_eta += ediff * 0.18

                if task.progress_canvas and task.progress_canvas.winfo_exists():
                    w = task.progress_canvas.winfo_width()
                    if w > 1:
                        ratio = max(0.0, min(1.0, task.display_percent / 100.0))
                        task.progress_canvas.coords(
                            task.progress_rect, 0, 0, w * ratio, 5)

                if task.status_lbl and task.status_lbl.winfo_exists():
                    if getattr(task, "_locked_status", False):
                        continue
                    parts = [f"{task.display_percent:.1f}%"]
                    if task.display_speed > 0:
                        parts.append(fmt_speed(task.display_speed))
                    if task.display_eta > 0:
                        parts.append(fmt_eta(task.display_eta))
                    task.status_lbl.config(text=" • ".join(parts))
            except Exception:
                pass
        try:
            self.root.after(80, self._animate_progress)
        except Exception:
            pass

    # ============ Фокус ============
    def _force_window_focus(self):
        try:
            hwnd = self.root.winfo_id()
            root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)
            if root_hwnd:
                hwnd = root_hwnd
            fg = ctypes.windll.user32.GetForegroundWindow()
            if fg != hwnd:
                cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                fg_thread = ctypes.windll.user32.GetWindowThreadProcessId(fg, None)
                ctypes.windll.user32.AttachThreadInput(fg_thread, cur_thread, True)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(fg_thread, cur_thread, False)
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _refocus_entry(self):
        try:
            self._force_window_focus()
            self.url_entry.focus_force()
            self.url_entry.icursor("end")
        except Exception:
            pass

    # ============ Центрирование ============
    def _place_centered(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _resize_to(self, w, h):
        try:
            self.root.geometry(f"{w}x{h}")
            self.root.update_idletasks()
        except Exception:
            pass

    def _center_dialog(self, dlg, parent_first=True):
        try:
            dlg.update_idletasks()
            dw = dlg.winfo_reqwidth()
            dh = dlg.winfo_reqheight()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            dx = dy = None
            if parent_first and self.root.state() != "withdrawn":
                rx = self.root.winfo_rootx()
                ry = self.root.winfo_rooty()
                rw = self.root.winfo_width()
                rh = self.root.winfo_height()
                if rw > 100 and rh > 100 and rx > -1 and ry > -1:
                    dx = rx + (rw - dw) // 2
                    dy = ry + (rh - dh) // 2
            if dx is None or dy is None or dx < 0 or dy < 0:
                dx = (sw - dw) // 2
                dy = (sh - dh) // 2
            if dx < 0: dx = 0
            if dy < 0: dy = 0
            if dx + dw > sw: dx = sw - dw
            if dy + dh > sh: dy = sh - dh
            dlg.geometry(f"{dw}x{dh}+{dx}+{dy}")
        except Exception:
            pass

    # ============ Хедер ============
    def _build_header_buttons(self, header, main_screen=False):
        T = self.T

        theme_btn = tk.Label(header, text="", bg=T["bg"], fg=T["fg_dim"],
                             font=("Segoe UI", 16), cursor="hand2")
        theme_btn.pack(side="right", padx=(8, 0 if main_screen else 6))
        self._reg(theme_btn, "theme_btn")
        theme_btn.bind("<Button-1>", lambda e: self._toggle_theme())
        theme_btn.bind("<Enter>",
                        lambda e: theme_btn.config(fg=self.T["green"]))
        theme_btn.bind("<Leave>",
                        lambda e: theme_btn.config(fg=self.T["fg_dim"]))

        lang_btn = tk.Label(header, text=f"🌐 {self._ui_lang.upper()}",
                             bg=T["bg"], fg=T["fg_dim"],
                             font=("Segoe UI", 10, "bold"), cursor="hand2",
                             padx=6, pady=2)
        lang_btn.pack(side="right", padx=(8, 0))
        self._reg(lang_btn, "lang_btn")
        lang_btn.bind("<ButtonPress-1>", self._lang_press, add="+")
        lang_btn.bind("<ButtonRelease-1>", self._lang_release, add="+")
        lang_btn.bind("<Enter>",
                       lambda e: lang_btn.config(fg=self.T["green"]), add="+")
        lang_btn.bind("<Leave>",
                       lambda e: lang_btn.config(fg=self.T["fg_dim"]), add="+")

        tip_theme = Tooltip(theme_btn, self._theme_tooltip_key(), app=self)
        tip_lang = Tooltip(lang_btn, 'Сменить язык интерфейса', app=self)
        self._tooltips.append(tip_theme)
        self._tooltips.append(tip_lang)

        if main_screen:
            self._theme_btn_main = theme_btn
            self._lang_btn_main = lang_btn
        else:
            self._theme_btn = theme_btn
            self._lang_btn = lang_btn
            self._theme_tooltip = tip_theme
            self._lang_tooltip = tip_lang

        return theme_btn, lang_btn

    def _theme_tooltip_key(self):
        if self.theme_name == "dark":
            return 'Переключить на светлую тему'
        return 'Переключить на тёмную тему'

    def _update_theme_button(self):
        text = "☾" if self.theme_name == "dark" else "☀"
        for b in (self._theme_btn, self._theme_btn_main):
            try:
                if b is not None and b.winfo_exists():
                    b.config(text=text)
            except Exception:
                pass
        try:
            if self._theme_tooltip is not None:
                self._theme_tooltip.set_key(self._theme_tooltip_key())
                self._theme_tooltip.refresh()
        except Exception:
            pass

    # ============ Экран выбора ============
    def _build_mode_select(self):
        T = self.T
        f = tk.Frame(self.container, bg=T["bg"])
        self.mode_select_frame = f
        self._reg(f, "frame")

        head = tk.Frame(f, bg=T["bg"])
        head.pack(fill="x", padx=18, pady=(14, 0))
        self._reg(head, "frame")

        icon = tk.Label(head, text="⬇", bg=T["bg"], fg=T["blue"],
                        font=("Segoe UI", 22, "bold"))
        icon.pack(side="left", padx=(0, 8))
        self._reg(icon, "icon_blue")

        title = tk.Label(head, text=self._t('Что скачиваем?'),
                          bg=T["bg"], fg=T["fg"],
                          font=("Segoe UI", 16, "bold"))
        title.pack(side="left")
        self._reg(title, "label")
        self._reg_i18n(title, 'Что скачиваем?')

        self._build_header_buttons(head, main_screen=False)
        self._enable_drag(head)

        hint = tk.Label(f, text=self._t('Выберите тип загрузки — потом можно переключить'),
                         bg=T["bg"], fg=T["fg_dim"],
                         font=("Segoe UI", 9))
        hint.pack(pady=(8, 20))
        self._reg(hint, "label_dim")
        self._reg_i18n(hint, 'Выберите тип загрузки — потом можно переключить')

        buttons_row = tk.Frame(f, bg=T["bg"])
        buttons_row.pack(expand=True)

        video_btn = tk.Frame(buttons_row, bg=T["blue"], cursor="hand2")
        video_btn.pack(side="left", padx=10, ipadx=20, ipady=20)
        inner_v = tk.Frame(video_btn, bg=T["blue"])
        inner_v.pack(padx=10, pady=10)
        tk.Label(inner_v, text="🎬", bg=T["blue"], fg="white",
                 font=("Segoe UI", 44)).pack()
        vtitle = tk.Label(inner_v, text=self._t('Видео'),
                           bg=T["blue"], fg="white",
                           font=("Segoe UI", 16, "bold"))
        vtitle.pack(pady=(4, 2))
        self._reg_i18n(vtitle, 'Видео')
        tk.Label(inner_v, text="YouTube, Rutube,\nVK, TikTok",
                 bg=T["blue"], fg="white", font=("Segoe UI", 8),
                 justify="center").pack()

        audio_btn = tk.Frame(buttons_row, bg=T["purple"], cursor="hand2")
        audio_btn.pack(side="left", padx=10, ipadx=20, ipady=20)
        inner_a = tk.Frame(audio_btn, bg=T["purple"])
        inner_a.pack(padx=10, pady=10)
        tk.Label(inner_a, text="🎵", bg=T["purple"], fg="white",
                 font=("Segoe UI", 44)).pack()
        atitle = tk.Label(inner_a, text=self._t('Музыка'),
                           bg=T["purple"], fg="white",
                           font=("Segoe UI", 16, "bold"))
        atitle.pack(pady=(4, 2))
        self._reg_i18n(atitle, 'Музыка')
        tk.Label(inner_a, text="Треки, плейлисты\nMP3 / FLAC / WAV",
                 bg=T["purple"], fg="white", font=("Segoe UI", 8),
                 justify="center").pack()

        def _click_video(e=None):
            self._show_main("video")

        def _click_audio(e=None):
            self._show_main("audio")

        for wdg in (video_btn, inner_v):
            wdg.bind("<Button-1>", _click_video)
        for child in inner_v.winfo_children():
            child.bind("<Button-1>", _click_video)
        for wdg in (audio_btn, inner_a):
            wdg.bind("<Button-1>", _click_audio)
        for child in inner_a.winfo_children():
            child.bind("<Button-1>", _click_audio)

        def _hover_in(w, hover):
            for c in (w,) + tuple(w.winfo_children()):
                try: c.config(bg=hover)
                except Exception: pass

        def _hover_out(w, base):
            for c in (w,) + tuple(w.winfo_children()):
                try: c.config(bg=base)
                except Exception: pass

        video_btn.bind("<Enter>", lambda e: _hover_in(video_btn, T["blue_hov"]))
        video_btn.bind("<Leave>", lambda e: _hover_out(video_btn, T["blue"]))
        audio_btn.bind("<Enter>", lambda e: _hover_in(audio_btn, T["purple_hov"]))
        audio_btn.bind("<Leave>", lambda e: _hover_out(audio_btn, T["purple"]))

        bottom = tk.Frame(f, bg=T["bg"])
        bottom.pack(fill="x", pady=(20, 12))
        close_lbl = tk.Label(bottom, text=self._t('Закрыть'), bg=T["bg"],
                              fg=T["fg_dim"],
                              font=("Segoe UI", 9, "underline"),
                              cursor="hand2")
        close_lbl.pack()
        self._reg(close_lbl, "label_dim")
        self._reg_i18n(close_lbl, 'Закрыть')
        close_lbl.bind("<Button-1>", lambda e: self.close_app())
        close_lbl.bind("<Enter>", lambda e: close_lbl.config(fg=T["red"]))
        close_lbl.bind("<Leave>", lambda e: close_lbl.config(fg=T["fg_dim"]))

    # ============ Главный экран ============
    def _build_main(self):
        T = self.T
        f = tk.Frame(self.container, bg=T["bg"])
        self.main_frame = f
        self._reg(f, "frame")

        header = tk.Frame(f, bg=T["bg"])
        header.pack(pady=(14, 0), fill="x", padx=18)
        self._reg(header, "frame")

        self.title_icon = tk.Label(header, text="⬇", bg=T["bg"], fg=T["blue"],
                                    font=("Segoe UI", 24, "bold"))
        self.title_icon.pack(side="left", padx=(0, 10))
        self._reg(self.title_icon, "icon_blue")

        self.title_lbl = tk.Label(header, text=self._t('Скачиватель видео'),
                                   bg=T["bg"], fg=T["fg"],
                                   font=("Segoe UI", 18, "bold"))
        self.title_lbl.pack(side="left")
        self._reg(self.title_lbl, "label")

        self._build_header_buttons(header, main_screen=True)

        self.switch_btn = tk.Label(header, text="🎵", bg=T["bg"], fg=T["fg_dim"],
                                    font=("Segoe UI", 16), cursor="hand2")
        self.switch_btn.pack(side="right", padx=(6, 6))
        self._reg(self.switch_btn, "theme_btn")
        self.switch_btn.bind("<Button-1>", lambda e: self._show_mode_select())
        self.switch_btn.bind("<Enter>",
                             lambda e: self.switch_btn.config(fg=T["purple"]))
        self.switch_btn.bind("<Leave>",
                             lambda e: self.switch_btn.config(fg=T["fg_dim"]))
        self._switch_tooltip = Tooltip(self.switch_btn, "Сменить режим", app=self)
        self._tooltips.append(self._switch_tooltip)

        self._enable_drag(header)

        url_frame = tk.Frame(f, bg=T["bg"])
        url_frame.pack(pady=(14, 4), padx=18, fill="x")
        self._reg(url_frame, "frame")

        self._url_lbl = tk.Label(url_frame, text=self._t('Ссылка'),
                                  bg=T["bg"], fg=T["fg_dim"],
                                  font=("Segoe UI", 9))
        self._url_lbl.pack(anchor="w")
        self._reg(self._url_lbl, "label_dim")
        self._reg_i18n(self._url_lbl, 'Ссылка')

        entry_row = tk.Frame(url_frame, bg=T["bg"])
        entry_row.pack(fill="x", pady=(3, 0))
        self._reg(entry_row, "frame")

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            entry_row, textvariable=self.url_var,
            bg=T["entry_bg"], fg=T["fg"], insertbackground=T["fg"],
            font=("Segoe UI", 11), relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=T["entry_border"],
            highlightcolor=T["blue"])
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=8)

        self.url_entry.bind("<Control-Return>",
                            lambda e: self._on_download_click())
        self.url_entry.bind("<Control-v>", self._paste_url)
        self.url_entry.bind("<Control-V>", self._paste_url)
        self.url_entry.bind("<Control-c>", self._copy_url)
        self.url_entry.bind("<Control-C>", self._copy_url)
        self.url_entry.bind("<Control-x>", self._cut_url)
        self.url_entry.bind("<Control-X>", self._cut_url)
        self.url_entry.bind("<Control-a>", self._select_all_url)
        self.url_entry.bind("<Control-A>", self._select_all_url)
        self.url_entry.bind("<Button-1>",
                            lambda e: self.root.after(10, self._refocus_entry))

        paste_btn = tk.Label(entry_row, text="📋", bg=T["action_bg"],
                             fg=T["fg"], font=("Segoe UI", 12),
                             cursor="hand2", padx=10, pady=6)
        paste_btn.pack(side="left", padx=(6, 0))
        self._reg(paste_btn, "action_btn")
        paste_btn.bind("<Button-1>", lambda e: self._paste_and_download())
        paste_btn.bind("<Enter>",
                       lambda e: paste_btn.config(bg=T["action_hover"]))
        paste_btn.bind("<Leave>",
                       lambda e: paste_btn.config(bg=T["action_bg"]))
        self._tooltips.append(Tooltip(
            paste_btn, 'Вставить из буфера и сразу скачать', app=self))

        fmt_frame = tk.Frame(f, bg=T["bg"])
        fmt_frame.pack(pady=(12, 4), padx=18, fill="x")
        self._reg(fmt_frame, "frame")

        self._fmt_lbl = tk.Label(fmt_frame, text=self._t('Формат и качество'),
                                  bg=T["bg"], fg=T["fg_dim"],
                                  font=("Segoe UI", 9))
        self._fmt_lbl.pack(anchor="w", pady=(0, 3))
        self._reg(self._fmt_lbl, "label_dim")
        self._reg_i18n(self._fmt_lbl, 'Формат и качество')

        self.fmt_row = tk.Frame(fmt_frame, bg=T["bg"])
        self.fmt_row.pack(fill="x")
        self._reg(self.fmt_row, "frame")

        self.fmt_var = tk.StringVar()
        self._fmt_regs = []

        folder_frame = tk.Frame(f, bg=T["bg"])
        folder_frame.pack(pady=(8, 4), padx=18, fill="x")
        self._reg(folder_frame, "frame")

        self._folder_lbl = tk.Label(folder_frame, text=self._t('Папка сохранения'),
                                     bg=T["bg"], fg=T["fg_dim"],
                                     font=("Segoe UI", 9))
        self._folder_lbl.pack(anchor="w")
        self._reg(self._folder_lbl, "label_dim")
        self._reg_i18n(self._folder_lbl, 'Папка сохранения')

        folder_row = tk.Frame(folder_frame, bg=T["bg"])
        folder_row.pack(fill="x", pady=(3, 0))
        self._reg(folder_row, "frame")

        self.folder_var = tk.StringVar()
        self.folder_entry = tk.Entry(
            folder_row, textvariable=self.folder_var,
            bg=T["entry_bg"], fg=T["fg"], insertbackground=T["fg"],
            font=("Segoe UI", 10), relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground=T["entry_border"],
            highlightcolor=T["blue"])
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.folder_entry.bind("<FocusOut>", lambda e: self._persist_settings())
        self.folder_entry.bind("<Control-v>", self._paste_url)
        self.folder_entry.bind("<Control-V>", self._paste_url)

        browse_btn = tk.Label(folder_row, text=self._t('Обзор'),
                               bg=T["action_bg"], fg=T["fg"],
                               font=("Segoe UI", 9, "bold"),
                               cursor="hand2", padx=14, pady=6)
        browse_btn.pack(side="left", padx=(6, 0))
        self._reg(browse_btn, "action_btn")
        self._reg_i18n(browse_btn, 'Обзор')
        browse_btn.bind("<Button-1>", lambda e: self._browse_folder())
        browse_btn.bind("<Enter>",
                        lambda e: browse_btn.config(bg=T["action_hover"]))
        browse_btn.bind("<Leave>",
                        lambda e: browse_btn.config(bg=T["action_bg"]))

        open_folder_btn = tk.Label(folder_row, text="📂", bg=T["action_bg"],
                                    fg=T["fg"], font=("Segoe UI", 11),
                                    cursor="hand2", padx=10, pady=6)
        open_folder_btn.pack(side="left", padx=(6, 0))
        self._reg(open_folder_btn, "action_btn")
        open_folder_btn.bind("<Button-1>",
                             lambda e: self._open_destination_folder())
        open_folder_btn.bind("<Enter>",
                             lambda e: open_folder_btn.config(bg=T["action_hover"]))
        open_folder_btn.bind("<Leave>",
                             lambda e: open_folder_btn.config(bg=T["action_bg"]))
        self._tooltips.append(Tooltip(
            open_folder_btn, 'Открыть папку назначения', app=self))

        self.ffmpeg_warn = tk.Label(f, text="", bg=T["bg"], fg=T["orange"],
                                     font=("Segoe UI", 9))
        self._reg(self.ffmpeg_warn, "label_orange")

        self.download_btn = tk.Button(
            f, text=self._t('Скачать'),
            bg=T["btn_start"], fg=T["white"],
            activebackground=T["btn_start_hov"],
            activeforeground=T["white"],
            font=("Segoe UI", 12, "bold"), relief="flat",
            padx=30, pady=10, cursor="hand2", bd=0,
            command=self._on_download_click)
        self.download_btn.pack(pady=(12, 10))
        self._reg(self.download_btn, "btn_start")
        self._reg_i18n(self.download_btn, 'Скачать')

        active_header = tk.Frame(f, bg=T["bg"])
        active_header.pack(fill="x", padx=18)
        self._reg(active_header, "frame")

        self._active_hdr_lbl = tk.Label(active_header,
                                          text=self._t('Активные загрузки'),
                                          bg=T["bg"], fg=T["fg_dim"],
                                          font=("Segoe UI", 9))
        self._active_hdr_lbl.pack(side="left")
        self._reg(self._active_hdr_lbl, "label_dim")
        self._reg_i18n(self._active_hdr_lbl, 'Активные загрузки')

        self.active_count_lbl = tk.Label(active_header, text="",
                                         bg=T["bg"], fg=T["fg_dim"],
                                         font=("Segoe UI", 9))
        self.active_count_lbl.pack(side="right")
        self._reg(self.active_count_lbl, "label_dim")

        self.active_area = tk.Frame(f, bg=T["bg"])
        self.active_area.pack(fill="x", padx=18, pady=(4, 6))
        self._reg(self.active_area, "frame")

        self.active_empty_lbl = tk.Label(
            self.active_area, text=self._t('Пока ничего не качается'),
            bg=T["bg"], fg=T["fg_dim"], font=("Segoe UI", 10))
        self.active_empty_lbl.pack(pady=14)
        self._reg(self.active_empty_lbl, "label_dim")
        self._reg_i18n(self.active_empty_lbl, 'Пока ничего не качается')

        self.completed_header = tk.Frame(f, bg=T["bg"])
        self._reg(self.completed_header, "frame")

        self._completed_hdr_lbl = tk.Label(self.completed_header,
                                             text=self._t('Завершённые'),
                                             bg=T["bg"], fg=T["fg_dim"],
                                             font=("Segoe UI", 9))
        self._completed_hdr_lbl.pack(side="left")
        self._reg(self._completed_hdr_lbl, "label_dim")
        self._reg_i18n(self._completed_hdr_lbl, 'Завершённые')

        self.completed_count_lbl = tk.Label(self.completed_header, text="",
                                            bg=T["bg"], fg=T["fg_dim"],
                                            font=("Segoe UI", 9))
        self.completed_count_lbl.pack(side="right")

        self.completed_clear_btn = tk.Label(
            self.completed_header, text=self._t('Очистить всё'),
            bg=T["bg"], fg=T["fg_dim"],
            font=("Segoe UI", 8, "underline"), cursor="hand2")
        self.completed_clear_btn.pack(side="right", padx=(0, 12))
        self._reg(self.completed_clear_btn, "label_dim")
        self._reg_i18n(self.completed_clear_btn, 'Очистить всё')
        self.completed_clear_btn.bind("<Button-1>",
                                       lambda e: self._clear_all_completed())
        self.completed_clear_btn.bind("<Enter>",
            lambda e: self.completed_clear_btn.config(fg=T["red"]))
        self.completed_clear_btn.bind("<Leave>",
            lambda e: self.completed_clear_btn.config(fg=T["fg_dim"]))

        self.completed_area = tk.Frame(f, bg=T["bg"])
        self._reg(self.completed_area, "frame")

        self.status = tk.Label(f, text=self._t('Готов к работе'),
                               bg=T["bg"], fg=T["fg_dim"],
                               font=("Segoe UI", 10, "bold"))
        self.status.pack(pady=(8, 0))
        self._reg(self.status, "label_dim")

        bottom_bar = tk.Frame(f, bg=T["bg"])
        bottom_bar.pack(pady=(10, 12), side="bottom")
        self._reg(bottom_bar, "frame")

        self.minimize_link = tk.Label(
            bottom_bar, text=self._t('Свернуть'), bg=T["bg"], fg=T["fg_dim"],
            font=("Segoe UI", 9, "underline"), cursor="hand2")
        self.minimize_link.pack(side="left")
        self._reg(self.minimize_link, "label_dim")
        self._reg_i18n(self.minimize_link, 'Свернуть')
        self.minimize_link.bind("<Button-1>", lambda e: self.hide_to_tray())
        self.minimize_link.bind("<Enter>",
                                lambda e: self.minimize_link.config(fg=T["green"]))
        self.minimize_link.bind("<Leave>",
                                lambda e: self.minimize_link.config(fg=T["fg_dim"]))

        tk.Label(bottom_bar, text="  •  ", bg=T["bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.hist_lbl = tk.Label(bottom_bar, text=self._t('История'),
                                  bg=T["bg"], fg=T["fg_dim"],
                                  font=("Segoe UI", 9, "underline"),
                                  cursor="hand2")
        self.hist_lbl.pack(side="left")
        self._reg(self.hist_lbl, "label_dim")
        self._reg_i18n(self.hist_lbl, 'История')
        self.hist_lbl.bind("<Button-1>", lambda e: self._open_history_window())
        self.hist_lbl.bind("<Enter>", lambda e: self.hist_lbl.config(fg=T["blue"]))
        self.hist_lbl.bind("<Leave>",
                            lambda e: self.hist_lbl.config(fg=T["fg_dim"]))

        tk.Label(bottom_bar, text="  •  ", bg=T["bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.log_lbl = tk.Label(bottom_bar, text=self._t('Журнал'),
                                 bg=T["bg"], fg=T["fg_dim"],
                                 font=("Segoe UI", 9, "underline"),
                                 cursor="hand2")
        self.log_lbl.pack(side="left")
        self._reg(self.log_lbl, "label_dim")
        self._reg_i18n(self.log_lbl, 'Журнал')
        self.log_lbl.bind("<Button-1>", lambda e: self._open_log_window())
        self.log_lbl.bind("<Enter>", lambda e: self.log_lbl.config(fg=T["green"]))
        self.log_lbl.bind("<Leave>",
                           lambda e: self.log_lbl.config(fg=T["fg_dim"]))

        tk.Label(bottom_bar, text="  •  ", bg=T["bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.exp_lbl = tk.Label(bottom_bar, text="💾 " + self._t('Экспорт'),
                                 bg=T["bg"], fg=T["fg_dim"],
                                 font=("Segoe UI", 9, "underline"),
                                 cursor="hand2")
        self.exp_lbl.pack(side="left")
        self._reg(self.exp_lbl, "label_dim")
        self.exp_lbl.bind("<Button-1>", lambda e: self._export_settings())
        self.exp_lbl.bind("<Enter>", lambda e: self.exp_lbl.config(fg=T["purple"]))
        self.exp_lbl.bind("<Leave>",
                           lambda e: self.exp_lbl.config(fg=T["fg_dim"]))

        tk.Label(bottom_bar, text="  •  ", bg=T["bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.imp_lbl = tk.Label(bottom_bar, text="📥 " + self._t('Импорт'),
                                 bg=T["bg"], fg=T["fg_dim"],
                                 font=("Segoe UI", 9, "underline"),
                                 cursor="hand2")
        self.imp_lbl.pack(side="left")
        self._reg(self.imp_lbl, "label_dim")
        self.imp_lbl.bind("<Button-1>", lambda e: self._import_settings())
        self.imp_lbl.bind("<Enter>", lambda e: self.imp_lbl.config(fg=T["purple"]))
        self.imp_lbl.bind("<Leave>",
                           lambda e: self.imp_lbl.config(fg=T["fg_dim"]))

        tk.Label(bottom_bar, text="  •  ", bg=T["bg"], fg=T["fg_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.close_btn = tk.Label(
            bottom_bar, text=self._t('Закрыть'), bg=T["bg"], fg=T["fg_dim"],
            font=("Segoe UI", 9, "underline"), cursor="hand2")
        self.close_btn.pack(side="left")
        self._reg(self.close_btn, "label_dim")
        self._reg_i18n(self.close_btn, 'Закрыть')
        self.close_btn.bind("<Button-1>", lambda e: self.close_app())
        self.close_btn.bind("<Enter>",
                            lambda e: self.close_btn.config(fg=T["red"]))
        self.close_btn.bind("<Leave>",
                            lambda e: self.close_btn.config(fg=T["fg_dim"]))

        self.main_frame.bind("<Button-1>", self._on_main_click, add="+")

    # ============ Хелпер для статуса главного окна ============
    def _set_status(self, key, color_key="fg_dim"):
        try:
            self.status.config(text=self._t(key), fg=self.T[color_key])
        except Exception:
            pass

    # ============ Редактирование поля ============
    def _paste_url(self, event=None):
        try:
            text = self.root.clipboard_get()
        except Exception:
            return "break"
        widget = event.widget if event is not None else self.url_entry
        if not isinstance(widget, tk.Entry):
            widget = self.url_entry
        try:
            try:
                s = widget.index("sel.first")
                e = widget.index("sel.last")
                widget.delete(s, e)
            except Exception:
                pass
            widget.insert("insert", text.strip())
        except Exception:
            pass
        return "break"

    def _copy_url(self, event=None):
        try:
            widget = event.widget if event is not None else self.url_entry
            try:
                text = widget.selection_get()
            except Exception:
                text = widget.get()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            pass
        return "break"

    def _cut_url(self, event=None):
        try:
            widget = event.widget if event is not None else self.url_entry
            try:
                s = widget.index("sel.first")
                e = widget.index("sel.last")
                text = widget.get()[s:e]
                widget.delete(s, e)
            except Exception:
                text = widget.get()
                widget.delete(0, "end")
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            pass
        return "break"

    def _select_all_url(self, event=None):
        try:
            widget = event.widget if event is not None else self.url_entry
            if isinstance(widget, tk.Entry):
                widget.select_range(0, "end")
                widget.icursor("end")
        except Exception:
            pass
        return "break"

    def _on_main_click(self, event):
        try:
            w = event.widget
            while w is not None:
                if isinstance(w, (tk.Entry, tk.Button, tk.Radiobutton,
                                   tk.Scrollbar, tk.Text)):
                    return
                w = w.master
        except Exception:
            pass
        self._refocus_entry()

    # ============ Переключение экранов ============
    def _show_mode_select(self):
        self.current_mode = None
        try:
            self.main_frame.pack_forget()
        except Exception:
            pass
        self.mode_select_frame.pack(fill="both", expand=True)
        self._resize_to(self._base_w_select, self._base_h_select)
        self._update_theme_button()
        self._fit_window()

    def _show_main(self, mode, from_startup=False):
        self.current_mode = mode
        self.settings["last_mode"] = mode
        save_settings(self.settings)

        if mode == "audio":
            self.title_lbl.config(text=self._t('Скачиватель музыки'))
            self.title_icon.config(text="♪", fg=self.T["purple"])
            self._apply_style(self.title_icon, "icon_purple")
            self.switch_btn.config(text="🎬")
            self._switch_tooltip.set_key("Переключить на видео")
        else:
            self.title_lbl.config(text=self._t('Скачиватель видео'))
            self.title_icon.config(text="⬇", fg=self.T["blue"])
            self._apply_style(self.title_icon, "icon_blue")
            self.switch_btn.config(text="🎵")
            self._switch_tooltip.set_key("Переключить на музыку")

        self._rebuild_formats(mode)

        saved_folder = self.settings.get(f"folder_{mode}", "")
        if not saved_folder or not os.path.isdir(saved_folder):
            saved_folder = default_folder_for(mode)
        self.folder_var.set(saved_folder)

        self._refresh_ffmpeg_warn()

        try:
            self.mode_select_frame.pack_forget()
        except Exception:
            pass
        self.main_frame.pack(fill="both", expand=True)
        self._resize_to(self._base_w_main, self._base_h_main)

        self._set_status('Готов к работе', "fg_dim")
        self._render_completed()

        self._fit_window()

        if not from_startup:
            self.root.after(150, self._refocus_entry)

    def _rebuild_formats(self, mode, keep_selection=False):
        T = self.T
        prev_selection = self.fmt_var.get() if keep_selection else ""
        for rb in self._fmt_regs:
            try:
                rb.destroy()
            except Exception:
                pass
        self._fmt_regs = []

        formats = FORMATS_AUDIO if mode == "audio" else FORMATS_VIDEO
        default_fmt = formats[0][1]
        saved = self.settings.get(f"format_{mode}", "")
        if saved and any(f[1] == saved for f in formats):
            default_fmt = saved
        if prev_selection and any(f[1] == prev_selection for f in formats):
            default_fmt = prev_selection
        self.fmt_var.set(default_fmt)

        for label, value in formats:
            display = self._t(FORMAT_LABEL_KEYS.get(label, label))
            rb = tk.Radiobutton(
                self.fmt_row, text=display, variable=self.fmt_var, value=value,
                indicatoron=0, bd=0, relief="flat",
                bg=T["action_bg"], fg=T["fg"],
                activebackground=T["action_hover"],
                activeforeground=T["fg"],
                selectcolor=T["action_active"],
                font=("Segoe UI", 9, "bold"),
                padx=10, pady=6, cursor="hand2",
                command=self._persist_settings)
            rb.pack(side="left", padx=2, pady=2)
            self._reg(rb, "action_btn")
            self._fmt_regs.append(rb)

    def _toggle_theme(self):
        new_name = "light" if self.theme_name == "dark" else "dark"
        self.theme_name = new_name
        self.settings["theme"] = new_name
        save_settings(self.settings)
        self.T.clear()
        self.T.update(THEMES[new_name])
        self._repaint_all()
        self._update_theme_button()
        self._render_completed()
        self.root.after(50, self._fit_window)

    def _reg(self, widget, role):
        self._styled.append((widget, role))

    def _apply_style(self, widget, role):
        T = self.T
        try:
            if role == "frame":
                widget.config(bg=T["bg"])
            elif role == "label":
                widget.config(bg=T["bg"], fg=T["fg"])
            elif role == "label_dim":
                widget.config(bg=T["bg"], fg=T["fg_dim"])
            elif role == "label_orange":
                widget.config(bg=T["bg"], fg=T["orange"])
            elif role == "icon_blue":
                widget.config(bg=T["bg"], fg=T["blue"])
            elif role == "icon_purple":
                widget.config(bg=T["bg"], fg=T["purple"])
            elif role == "theme_btn":
                widget.config(bg=T["bg"], fg=T["fg_dim"])
            elif role == "lang_btn":
                widget.config(bg=T["bg"], fg=T["fg_dim"])
            elif role == "action_btn":
                widget.config(bg=T["action_bg"], fg=T["fg"],
                              activebackground=T["action_hover"],
                              activeforeground=T["fg"],
                              selectcolor=T["action_active"])
            elif role == "btn_start":
                widget.config(bg=T["btn_start"], fg=T["white"],
                              activebackground=T["btn_start_hov"],
                              activeforeground=T["white"])
        except Exception:
            pass

    def _repaint_all(self):
        try:
            self.root.configure(bg=self.T["bg"])
        except Exception:
            pass
        for widget, role in self._styled:
            try:
                if widget.winfo_exists():
                    self._apply_style(widget, role)
            except Exception:
                pass
        for task in self.active_tasks.values():
            self._repaint_task_row(task)

    def _repaint_task_row(self, task):
        T = self.T
        try:
            if task.frame and task.frame.winfo_exists():
                task.frame.config(bg=T["bg_dark"],
                                    highlightbackground=T["entry_border"])
            if task.title_lbl and task.title_lbl.winfo_exists():
                task.title_lbl.config(bg=T["bg_dark"], fg=T["fg"])
            if task.status_lbl and task.status_lbl.winfo_exists():
                task.status_lbl.config(bg=T["bg_dark"], fg=T["fg_dim"])
            if task.progress_canvas and task.progress_canvas.winfo_exists():
                task.progress_canvas.config(bg=T["preset_bg"])
                bar_color = T["purple"] if task.mode == "audio" else T["blue"]
                task.progress_canvas.itemconfig(task.progress_rect,
                                                 fill=bar_color)
            if task.thumb_lbl and task.thumb_lbl.winfo_exists():
                if not task.thumb_loaded:
                    task.thumb_lbl.config(bg=T["thumb_bg"])
        except Exception:
            pass

    # ============ Drag ============
    def _enable_drag(self, widget):
        widget.bind("<Button-1>", self._drag_window_start, add="+")
        widget.bind("<B1-Motion>", self._drag_window_move, add="+")
        for child in widget.winfo_children():
            self._enable_drag(child)

    def _drag_window_start(self, e):
        self._drag_offset_x = e.x_root - self.root.winfo_x()
        self._drag_offset_y = e.y_root - self.root.winfo_y()

    def _drag_window_move(self, e):
        x = e.x_root - self._drag_offset_x
        y = e.y_root - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    # ============ Настройки ============
    def _persist_settings(self):
        try:
            data = dict(self.settings)
            data["theme"] = self.theme_name
            data["history"] = self.history[:30]
            data["ui_lang"] = self._ui_lang
            if self.current_mode:
                data[f"format_{self.current_mode}"] = self.fmt_var.get()
                data[f"folder_{self.current_mode}"] = self.folder_var.get()
                data["last_mode"] = self.current_mode
            self.settings = data
            save_settings(data)
        except Exception:
            pass

    def _browse_folder(self):
        initial = self.folder_var.get()
        if not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        folder = filedialog.askdirectory(initialdir=initial,
                                         title=self._t('Куда сохранять?'))
        if folder:
            self.folder_var.set(folder)
            self._persist_settings()
        self.root.after(100, self._force_window_focus)

    def _open_destination_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            self._set_status('Папка не задана', "orange")
            return
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception:
                self._set_status('Папка не существует', "red")
                return
        try:
            os.startfile(folder)
        except Exception as e:
            try:
                self.status.config(text=self._t('Не удалось открыть:') + f" {e}",
                                   fg=self.T["red"])
            except Exception:
                pass

    def _paste_and_download(self):
        try:
            text = self.root.clipboard_get()
        except Exception:
            text = ""
        if not text:
            self._set_status('Буфер обмена пуст', "orange")
            return
        if self.current_mode is None:
            self._show_main("video")
        self.url_var.set(text.strip())
        self._on_download_click()

    def _on_download_click(self):
        if not YTDLP_OK:
            self._show_warning_dialog(
                'Не установлен yt-dlp',
                'Внутри .exe нет модуля yt-dlp.')
            return
        if self.current_mode is None:
            return
        url = self.url_var.get().strip()
        if not url:
            self._set_status('Вставьте ссылку', "orange")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            self._set_status('Ссылка должна начинаться с http', "orange")
            return
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception:
                self._set_status('Неверная папка', "red")
                return

        fmt = self.fmt_var.get()
        task = Task(url, fmt, folder, self.current_mode)

        self.active_tasks[task.id] = task
        self._add_task_row(task)
        self._update_active_header()

        self.url_var.set("")
        self._set_status('Добавлено в очередь', "blue")
        self.root.after(50, self._refocus_entry)

        self.queue.put(task)
        log_event(f"Задача {task.id} [{self.current_mode}]: {url} [{fmt}]")
        self._update_tray_status()

    # ============ UI задач ============
    def _add_task_row(self, task):
        if self.active_empty_lbl.winfo_exists():
            self.active_empty_lbl.pack_forget()

        T = self.T
        row = tk.Frame(self.active_area, bg=T["bg_dark"],
                       highlightthickness=1,
                       highlightbackground=T["entry_border"])
        row.pack(fill="x", pady=3)
        task.frame = row

        thumb_wrap = tk.Frame(row, bg=T["bg_dark"])
        thumb_wrap.pack(side="left", padx=(8, 8), pady=8)

        task.thumb_lbl = tk.Label(
            thumb_wrap,
            text=("🎵" if task.mode == "audio" else "🎬"),
            bg=T["thumb_bg"], fg=T["fg"],
            font=("Segoe UI", 20),
            width=4, height=2)
        task.thumb_lbl.pack()

        right = tk.Frame(row, bg=T["bg_dark"])
        right.pack(side="left", fill="both", expand=True,
                   padx=(0, 8), pady=(8, 6))

        top = tk.Frame(right, bg=T["bg_dark"])
        top.pack(fill="x")

        mode_icon = "🎵" if task.mode == "audio" else "🎬"
        task.title_lbl = tk.Label(
            top, text=f"{mode_icon}  {self._shorten(task.url, 60)}",
            bg=T["bg_dark"], fg=T["fg"],
            font=("Segoe UI", 10, "bold"), anchor="w", justify="left")
        task.title_lbl.pack(side="left", fill="x", expand=True)

        cancel = tk.Label(top, text="✕", bg=T["bg_dark"], fg=T["fg_dim"],
                          font=("Segoe UI", 12), cursor="hand2")
        cancel.pack(side="right")
        cancel.bind("<Enter>", lambda e: cancel.config(fg=T["red"]))
        cancel.bind("<Leave>", lambda e: cancel.config(fg=T["fg_dim"]))
        cancel.bind("<Button-1>", lambda e, t=task: self._cancel_task(t))

        prog_wrap = tk.Frame(right, bg=T["bg_dark"])
        prog_wrap.pack(fill="x", pady=(6, 4))
        task.progress_canvas = tk.Canvas(
            prog_wrap, height=5, width=1, bg=T["preset_bg"],
            highlightthickness=0, bd=0)
        task.progress_canvas.pack(fill="x")
        bar_color = T["purple"] if task.mode == "audio" else T["blue"]
        task.progress_rect = task.progress_canvas.create_rectangle(
            0, 0, 0, 5, fill=bar_color, outline="")

        task.status_lbl = tk.Label(
            right, text=self._t('в очереди'), bg=T["bg_dark"], fg=T["fg_dim"],
            font=("Segoe UI", 9), anchor="w")
        task.status_lbl.pack(fill="x")
        task._locked_status = True
        task._status_key = 'в очереди'
        task._status_color = T["fg_dim"]

    def _shorten(self, text, maxlen):
        if len(text) <= maxlen:
            return text
        return text[:maxlen - 1] + "…"

    def _update_active_header(self):
        n = len(self.active_tasks)
        if n == 0:
            self.active_count_lbl.config(text="")
            if not self.active_empty_lbl.winfo_ismapped():
                self.active_empty_lbl.pack(pady=14)
            self._set_status('Готов к работе', "fg_dim")
        else:
            self.active_count_lbl.config(text=f"{n}")
            if self.active_empty_lbl.winfo_ismapped():
                self.active_empty_lbl.pack_forget()
        self._update_tray_status()

    def _remove_task_row(self, task):
        try:
            if task.frame and task.frame.winfo_exists():
                task.frame.destroy()
        except Exception:
            pass
        task.frame = None

    def _cancel_task(self, task):
        task.status = "отменено"
        log_event(f"Задача {task.id} отменена")
        self._remove_task_row(task)
        self.active_tasks.pop(task.id, None)
        self._update_active_header()
        self._update_tray_status()

    # ============ Превью ============
    def _apply_thumbnail(self, task_id, thumb_url):
        if not PIL_OK or not thumb_url:
            return
        task = self.active_tasks.get(task_id)
        if not task or task.thumb_loaded:
            return
        task.thumb_loaded = True

        def _worker():
            try:
                req = urllib.request.Request(
                    thumb_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
                self.root.after(0, lambda: self._set_thumb(task_id, img))
            except Exception as e:
                log_event(f"Не удалось скачать превью: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _set_thumb(self, task_id, pil_img):
        task = self.active_tasks.get(task_id)
        if not task or not task.thumb_lbl or not task.thumb_lbl.winfo_exists():
            return
        try:
            photo = ImageTk.PhotoImage(pil_img)
            task.thumb_lbl.config(image=photo, text="",
                                   width=THUMB_W, height=THUMB_H)
            task.thumb_photo = photo
        except Exception:
            pass

    # ============ Worker ============
    def _queue_worker(self):
        while True:
            task = self.queue.get()
            if task is None:
                break
            try:
                if task.status == "отменено":
                    continue
                self._do_download(task)
            except Exception as e:
                try:
                    self.root.after(0, self._task_error, task.id, str(e))
                except Exception:
                    pass
            finally:
                self.queue.task_done()

    def _progress_hook(self, task_id, d):
        now = time.time()
        last = self._last_progress_update.get(task_id, 0)
        if now - last < 0.15:
            return
        self._last_progress_update[task_id] = now

        status = d.get("status")
        task = self.active_tasks.get(task_id)
        if task is None:
            return

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            raw_speed = d.get("speed") or 0
            percent = (done / total * 100) if total > 0 else 0

            alpha = 0.25
            if raw_speed > 0:
                if task.target_speed > 0:
                    task.target_speed = alpha * raw_speed + (1 - alpha) * task.target_speed
                else:
                    task.target_speed = raw_speed

            if task.target_speed > 0 and total > 0:
                remaining = max(0, total - done)
                task.target_eta = remaining / task.target_speed
            else:
                task.target_eta = d.get("eta") or 0

            self.root.after(0, self._update_task_progress, task_id, percent)
        elif status == "finished":
            task._locked_status = True
            self.root.after(0, self._update_task_status_i18n,
                            task_id, 'обработка…', 100)

    def _do_download(self, task):
        fmt = task.fmt
        mode = task.mode
        opts = {
            "outtmpl": os.path.join(task.folder, "%(title)s.%(ext)s"),
            "progress_hooks": [
                lambda d, tid=task.id: self._progress_or_info_with_id(tid, d)
            ],
            "noplaylist": mode != "audio",
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
        }

        if FFMPEG_PATH:
            opts["ffmpeg_location"] = FFMPEG_PATH

        if mode == "audio":
            self._configure_audio_opts(opts, fmt)
        else:
            self._configure_video_opts(opts, fmt)

        task._locked_status = True
        self.root.after(0, self._update_task_status_i18n,
                        task.id, 'подготовка…', 0)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(task.url, download=True)

        if info:
            title = info.get("title") or task.url
            filename = ""
            req = info.get("requested_downloads") or []
            if req:
                filename = req[0].get("filepath", "") or ""
            if not filename:
                filename = info.get("_filename", "") or ""
            task.title = title
            task.filename = filename
            self.root.after(0, self._update_task_title, task.id, title)

        self.root.after(0, self._task_finished, task.id)

    def _configure_video_opts(self, opts, fmt):
        if fmt == "best":
            if HAS_FFMPEG:
                opts["format"] = "bestvideo+bestaudio/best"
                opts["merge_output_format"] = "mp4"
            else:
                opts["format"] = "best[ext=mp4]/best"
        else:
            try:
                height = int(fmt)
            except ValueError:
                height = 720
            if HAS_FFMPEG:
                opts["format"] = (
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"best[height<={height}]")
                opts["merge_output_format"] = "mp4"
            else:
                opts["format"] = (
                    f"best[height<={height}][ext=mp4]/"
                    f"best[height<={height}]/best")

        if HAS_FFMPEG:
            opts["writethumbnail"] = True
            opts["convert_thumbnails"] = "jpg"
            existing_pp = opts.get("postprocessors", [])
            existing_pp.append({"key": "FFmpegMetadata"})
            existing_pp.append({"key": "EmbedThumbnail",
                                "already_have_thumbnail": False})
            opts["postprocessors"] = existing_pp

    def _configure_audio_opts(self, opts, fmt):
        if fmt == "abest":
            opts["format"] = "bestaudio/best"
            if HAS_FFMPEG:
                opts["writethumbnail"] = True
                opts["convert_thumbnails"] = "jpg"
                opts["postprocessors"] = [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "m4a",
                     "preferredquality": "0"},
                    {"key": "FFmpegMetadata"},
                    {"key": "EmbedThumbnail",
                     "already_have_thumbnail": False},
                ]
        elif fmt in ("a320", "a192", "a128"):
            if not HAS_FFMPEG:
                raise RuntimeError("FFmpeg required for MP3.")
            bitrate = fmt[1:]
            opts["format"] = "bestaudio/best"
            opts["writethumbnail"] = True
            opts["convert_thumbnails"] = "jpg"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                 "preferredquality": bitrate},
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail",
                 "already_have_thumbnail": False},
            ]
        elif fmt == "flac":
            if not HAS_FFMPEG:
                raise RuntimeError("FFmpeg required for FLAC.")
            opts["format"] = "bestaudio/best"
            opts["writethumbnail"] = True
            opts["convert_thumbnails"] = "jpg"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "flac",
                 "preferredquality": "0"},
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail",
                 "already_have_thumbnail": False},
            ]
        elif fmt == "wav":
            if not HAS_FFMPEG:
                raise RuntimeError("FFmpeg required for WAV.")
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "wav"},
            ]

    def _progress_or_info_with_id(self, task_id, d):
        if d.get("status") == "downloading":
            info = d.get("info_dict") or {}
            title = info.get("title")
            task = self.active_tasks.get(task_id)
            if task and title and task.title != title:
                task.title = title
                self.root.after(0, self._update_task_title, task_id, title)

            if task and not task.thumb_loaded:
                thumb_url = info.get("thumbnail")
                if not thumb_url:
                    thumbs = info.get("thumbnails") or []
                    if thumbs:
                        sorted_t = sorted(thumbs, key=lambda x: x.get("width") or 0)
                        thumb_url = sorted_t[-1].get("url")
                if thumb_url:
                    self._apply_thumbnail(task_id, thumb_url)

        self._progress_hook(task_id, d)

    # ============ Обновления UI ============
    def _update_task_title(self, task_id, title):
        task = self.active_tasks.get(task_id)
        if not task or not task.title_lbl:
            return
        try:
            if task.title_lbl.winfo_exists():
                mode_icon = "🎵" if task.mode == "audio" else "🎬"
                task.title_lbl.config(
                    text=f"{mode_icon}  {self._shorten(title, 60)}")
        except Exception:
            pass

    def _update_task_progress(self, task_id, percent):
        task = self.active_tasks.get(task_id)
        if not task:
            return
        task.target_percent = percent
        task._locked_status = False

    def _update_task_status_i18n(self, task_id, key, percent=None):
        task = self.active_tasks.get(task_id)
        if not task:
            return
        try:
            if percent is not None:
                task.target_percent = percent
            task._locked_status = True
            task._status_key = key
            task._status_color = self.T["fg_dim"]
            if task.status_lbl and task.status_lbl.winfo_exists():
                task.status_lbl.config(text=self._t(key),
                                        fg=self.T["fg_dim"])
        except Exception:
            pass

    def _task_error(self, task_id, error):
        task = self.active_tasks.get(task_id)
        log_event(f"Задача {task_id} ошибка: {error}")
        self._last_error_time = time.time()
        if task:
            try:
                task._locked_status = True
                task._status_key = None
                task._status_color = None
                if task.status_lbl and task.status_lbl.winfo_exists():
                    task.status_lbl.config(
                        text=f"❌ {error[:80]}", fg=self.T["red"])
                if task.progress_canvas and task.progress_canvas.winfo_exists():
                    task.progress_canvas.itemconfig(
                        task.progress_rect, fill=self.T["red"])
            except Exception:
                pass
        self._update_tray_status()
        self.root.after(5000, lambda: self._finalize_task(task_id, success=False))
        self.root.after(6000, self._update_tray_status)

    def _task_finished(self, task_id):
        task = self.active_tasks.get(task_id)
        log_event(f"Задача {task_id} завершена успешно")
        if task:
            try:
                task.target_percent = 100
                task.display_percent = 100
                task._locked_status = True
                task._status_key = None
                task._status_color = None
                if task.status_lbl and task.status_lbl.winfo_exists():
                    task.status_lbl.config(text="✅", fg=self.T["green"])
                if task.progress_canvas and task.progress_canvas.winfo_exists():
                    w = task.progress_canvas.winfo_width()
                    if w > 1:
                        task.progress_canvas.coords(
                            task.progress_rect, 0, 0, w, 5)
            except Exception:
                pass
        self.root.after(2500, lambda: self._finalize_task(task_id, success=True))

    def _finalize_task(self, task_id, success=True):
        task = self.active_tasks.get(task_id)
        if not task:
            return
        entry = {
            "title": task.title,
            "url": task.url,
            "folder": task.folder,
            "filename": task.filename,
            "format": task.fmt,
            "mode": task.mode,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "success": success,
        }
        self.history.insert(0, entry)
        self.history = self.history[:30]
        self._persist_settings()

        self._remove_task_row(task)
        self.active_tasks.pop(task_id, None)
        self._update_active_header()
        self._render_completed()
        self._update_tray_status()

        if success:
            try:
                self.status.config(text="✅", fg=self.T["green"])
            except Exception:
                pass
        else:
            try:
                self.status.config(text="❌", fg=self.T["red"])
            except Exception:
                pass

    # ============ Завершённые ============
    def _render_completed(self):
        T = self.T
        for wdg in self._completed_widgets:
            try:
                wdg.destroy()
            except Exception:
                pass
        self._completed_widgets = []

        if not self.history:
            try:
                self.completed_header.pack_forget()
                self.completed_area.pack_forget()
            except Exception:
                pass
            return

        try:
            if not self.completed_header.winfo_ismapped():
                self.completed_header.pack(fill="x", padx=18,
                                           before=self.status)
            if not self.completed_area.winfo_ismapped():
                self.completed_area.pack(fill="x", padx=18, pady=(4, 6),
                                          before=self.status)
        except Exception:
            pass

        entries = self.history[:MAX_COMPLETED_VISIBLE]
        total = len(self.history)
        if total > MAX_COMPLETED_VISIBLE:
            self.completed_count_lbl.config(
                text=f"{len(entries)} / {total}")
        else:
            self.completed_count_lbl.config(text=f"{total}")

        for entry in entries:
            w = self._build_completed_row(entry)
            self._completed_widgets.append(w)

    def _build_completed_row(self, entry):
        T = self.T
        row = tk.Frame(self.completed_area, bg=T["bg_dark"],
                       highlightthickness=1,
                       highlightbackground=T["entry_border"])
        row.pack(fill="x", pady=2)
        self._completed_widgets.append(row)

        fname = entry.get("filename", "") or ""
        file_exists = bool(fname) and os.path.exists(fname)
        folder = entry.get("folder", "") or ""
        folder_exists = bool(folder) and os.path.isdir(folder)

        if not entry.get("success", True):
            status_icon = "❌"; icon_color = T["red"]
        elif file_exists:
            status_icon = "✅"; icon_color = T["green"]
        else:
            status_icon = "🚫"; icon_color = T["orange"]

        mode_icon = "🎵" if entry.get("mode") == "audio" else "🎬"

        left = tk.Frame(row, bg=T["bg_dark"])
        left.pack(side="left", padx=(10, 6), pady=6)

        tk.Label(left, text=status_icon, bg=T["bg_dark"], fg=icon_color,
                 font=("Segoe UI", 12)).pack(side="left", padx=(0, 6))
        tk.Label(left, text=mode_icon, bg=T["bg_dark"], fg=T["fg"],
                 font=("Segoe UI", 11)).pack(side="left")

        info = tk.Frame(row, bg=T["bg_dark"])
        info.pack(side="left", fill="x", expand=True, pady=6, padx=(0, 6))

        title = entry.get("title", "?")
        tk.Label(info, text=title, bg=T["bg_dark"], fg=T["fg"],
                 font=("Segoe UI", 10, "bold"),
                 anchor="w", justify="left",
                 wraplength=520).pack(anchor="w", fill="x")

        time_str = entry.get("time", "")
        fmt_str = entry.get("format", "")
        sub = f"{time_str}  •  {fmt_str}"
        sub_color = T["fg_dim"]

        tk.Label(info, text=sub, bg=T["bg_dark"], fg=sub_color,
                 font=("Segoe UI", 8), anchor="w").pack(anchor="w")

        btns = tk.Frame(row, bg=T["bg_dark"])
        btns.pack(side="right", padx=(0, 8))

        if file_exists:
            open_btn = tk.Label(btns, text="▶", bg=T["bg_dark"], fg=T["blue"],
                                font=("Segoe UI", 12), cursor="hand2", padx=6)
            open_btn.pack(side="left")
            open_btn.bind("<Button-1>", lambda e, f=fname: self._open_file(f))
            open_btn.bind("<Enter>", lambda e: open_btn.config(fg=T["blue_hov"]))
            open_btn.bind("<Leave>", lambda e: open_btn.config(fg=T["blue"]))

        if file_exists or folder_exists:
            folder_btn = tk.Label(btns, text="📁", bg=T["bg_dark"],
                                  fg=T["fg_dim"], font=("Segoe UI", 11),
                                  cursor="hand2", padx=6)
            folder_btn.pack(side="left")
            folder_btn.bind(
                "<Button-1>",
                lambda e, f=fname, d=folder: self._reveal_in_folder(f, d))
            folder_btn.bind("<Enter>", lambda e: folder_btn.config(fg=T["fg"]))
            folder_btn.bind("<Leave>",
                            lambda e: folder_btn.config(fg=T["fg_dim"]))

        del_btn = tk.Label(btns, text="🗑", bg=T["bg_dark"],
                           fg=T["fg_dim"], font=("Segoe UI", 11),
                           cursor="hand2", padx=6)
        del_btn.pack(side="left")
        del_btn.bind("<Button-1>",
                     lambda e, en=entry: self._delete_completed_entry(en))
        del_btn.bind("<Enter>", lambda e: del_btn.config(fg=T["red"]))
        del_btn.bind("<Leave>",
                     lambda e: del_btn.config(fg=T["fg_dim"]))

        return row

    def _delete_completed_entry(self, entry):
        fname = entry.get("filename", "") or ""
        has_file = bool(fname) and os.path.exists(fname)

        def remove_only():
            try:
                self.history.remove(entry)
            except ValueError:
                pass
            self._persist_settings()
            self._render_completed()

        def remove_with_file():
            if fname and os.path.exists(fname):
                try:
                    os.remove(fname)
                    log_event(f"Удалён файл: {fname}")
                except Exception as e:
                    log_event(f"Не удалось удалить {fname}: {e}")
            remove_only()

        if has_file:
            base = os.path.basename(fname)
            self._show_confirm_dialog(
                'Удалить запись?',
                f"{base}",
                remove_only, remove_with_file, self._t('Удалить с диска'))
        else:
            self._show_confirm_dialog(
                'Удалить запись из истории?',
                'Файл отсутствует.',
                remove_only)

    def _clear_all_completed(self):
        if not self.history:
            return

        def do_clear():
            self.history = []
            self._persist_settings()
            self._render_completed()

        self._show_confirm_dialog(
            'Очистить всю историю?',
            'Все записи будут удалены.',
            do_clear)

    # ============ Диалоги ============
    def _show_confirm_dialog(self, title_key, message, on_yes,
                              on_yes2=None, yes2_label=None):
        if self._confirm_dlg is not None:
            try:
                if self._confirm_dlg.winfo_exists():
                    self._confirm_dlg.lift()
                    self._confirm_dlg.attributes("-topmost", True)
                    return
            except Exception:
                pass
            self._confirm_dlg = None

        title = self._t(title_key) if title_key in UI_TR else title_key
        if message in UI_TR:
            message = self._t(message)

        T = self.T
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=T["orange"])
        self._confirm_dlg = dlg

        inner = tk.Frame(dlg, bg=T["bg"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        top = tk.Frame(inner, bg=T["bg"])
        top.pack(fill="x", padx=22, pady=(20, 10))
        tk.Label(top, text="❓", bg=T["bg"], fg=T["orange"],
                 font=("Segoe UI", 20)).pack(side="left", padx=(0, 12))
        tk.Label(top, text=title, bg=T["bg"], fg=T["fg"],
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        tk.Label(inner, text=message, bg=T["bg"], fg=T["fg_dim"],
                 justify="left", font=("Segoe UI", 10),
                 wraplength=460).pack(padx=22, pady=(0, 18), anchor="w")

        def close_dlg():
            self._confirm_dlg = None
            try:
                dlg.destroy()
            except Exception:
                pass

        def do_yes():
            close_dlg()
            try: on_yes()
            except Exception: pass

        def do_yes2():
            close_dlg()
            try: on_yes2()
            except Exception: pass

        btn_row = tk.Frame(inner, bg=T["bg"])
        btn_row.pack(pady=(0, 20))

        tk.Button(btn_row, text=self._t('Отмена'),
                  bg=T["preset_bg"], fg=T["fg"],
                  activebackground=T["preset_hover"],
                  activeforeground=T["fg"],
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  bd=0, padx=22, pady=8, cursor="hand2",
                  command=close_dlg).pack(side="left", padx=5)

        if on_yes2 is not None:
            tk.Button(btn_row, text=self._t('Только из истории'),
                      bg=T["preset_bg"], fg=T["fg"],
                      activebackground=T["preset_hover"],
                      activeforeground=T["fg"],
                      font=("Segoe UI", 10, "bold"), relief="flat",
                      bd=0, padx=16, pady=8, cursor="hand2",
                      command=do_yes).pack(side="left", padx=5)
            tk.Button(btn_row, text=yes2_label or self._t('Удалить и файл'),
                      bg=T["btn_cancel"], fg=T["white"],
                      activebackground=T["btn_cancel_hov"],
                      activeforeground=T["white"],
                      font=("Segoe UI", 10, "bold"), relief="flat",
                      bd=0, padx=16, pady=8, cursor="hand2",
                      command=do_yes2).pack(side="left", padx=5)
        else:
            tk.Button(btn_row, text=self._t('Да'),
                      bg=T["btn_cancel"], fg=T["white"],
                      activebackground=T["btn_cancel_hov"],
                      activeforeground=T["white"],
                      font=("Segoe UI", 10, "bold"), relief="flat",
                      bd=0, padx=26, pady=8, cursor="hand2",
                      command=do_yes).pack(side="left", padx=5)

        self._center_dialog(dlg)
        self.root.after(30, lambda d=dlg: self._center_dialog(d))

        def _drag_start(e):
            dlg._dx = e.x_root - dlg.winfo_x()
            dlg._dy = e.y_root - dlg.winfo_y()
        def _drag_move(e):
            dlg.geometry(f"+{e.x_root - dlg._dx}+{e.y_root - dlg._dy}")
        top.bind("<Button-1>", _drag_start)
        top.bind("<B1-Motion>", _drag_move)

        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.bind("<Escape>", lambda e: close_dlg())

    def _show_warning_dialog(self, title_key, message):
        if self._warning_dlg is not None:
            try:
                if self._warning_dlg.winfo_exists():
                    self._warning_dlg.lift()
                    self._warning_dlg.attributes("-topmost", True)
                    return
            except Exception:
                pass
            self._warning_dlg = None

        title = self._t(title_key) if title_key in UI_TR else title_key
        # message может содержать \n и русские фрагменты — переводим по ключу
        if message in UI_TR:
            message = self._t(message)
        else:
            # разбираем на строки, каждую пытаемся перевести
            lines = message.split("\n")
            translated_lines = [self._t(l) if l in UI_TR else l for l in lines]
            message = "\n".join(translated_lines)

        T = self.T
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=T["orange"])
        self._warning_dlg = dlg

        inner = tk.Frame(dlg, bg=T["bg"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        top = tk.Frame(inner, bg=T["bg"])
        top.pack(fill="x", padx=22, pady=(20, 10))
        tk.Label(top, text="⚠", bg=T["bg"], fg=T["orange"],
                 font=("Segoe UI", 22)).pack(side="left", padx=(0, 12))
        tk.Label(top, text=title, bg=T["bg"], fg=T["fg"],
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        tk.Label(inner, text=message, bg=T["bg"], fg=T["fg_dim"],
                 justify="left", font=("Segoe UI", 10),
                 wraplength=440).pack(padx=22, pady=(0, 18), anchor="w")

        def close_dlg():
            self._warning_dlg = None
            try:
                dlg.destroy()
            except Exception:
                pass

        ok = tk.Button(inner, text=self._t('Понятно'),
                       bg=T["orange"], fg="#1a1a1a",
                       activebackground=T["orange"],
                       activeforeground="#1a1a1a",
                       font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                       padx=26, pady=8, cursor="hand2",
                       command=close_dlg)
        ok.pack(pady=(0, 20))

        self._center_dialog(dlg)
        self.root.after(30, lambda d=dlg: self._center_dialog(d))

        def _drag_start(e):
            dlg._dx = e.x_root - dlg.winfo_x()
            dlg._dy = e.y_root - dlg.winfo_y()
        def _drag_move(e):
            dlg.geometry(f"+{e.x_root - dlg._dx}+{e.y_root - dlg._dy}")
        top.bind("<Button-1>", _drag_start)
        top.bind("<B1-Motion>", _drag_move)

        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.bind("<Escape>", lambda e: close_dlg())
        dlg.bind("<Return>", lambda e: close_dlg())
        ok.focus_set()

    # ============ История ============
    def _open_history_window(self):
        T = self.T
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=T["blue"])

        inner = tk.Frame(dlg, bg=T["bg"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        top = tk.Frame(inner, bg=T["bg"])
        top.pack(fill="x", padx=22, pady=(18, 8))
        tk.Label(top, text="📜", bg=T["bg"], fg=T["blue"],
                 font=("Segoe UI", 18)).pack(side="left", padx=(0, 10))
        tk.Label(top, text=self._t('История'), bg=T["bg"], fg=T["fg"],
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        list_wrap = tk.Frame(inner, bg=T["entry_border"])
        list_wrap.pack(fill="both", expand=True, padx=22, pady=(0, 10))

        scroll = tk.Scrollbar(list_wrap, orient="vertical")
        scroll.pack(side="right", fill="y")

        list_canvas = tk.Canvas(list_wrap, bg=T["bg_dark"],
                                highlightthickness=0, bd=0,
                                width=680, height=420,
                                yscrollcommand=scroll.set)
        list_canvas.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        scroll.config(command=list_canvas.yview)

        inner_list = tk.Frame(list_canvas, bg=T["bg_dark"])
        list_canvas.create_window((0, 0), window=inner_list, anchor="nw")

        def on_config(e):
            list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        inner_list.bind("<Configure>", on_config)

        if not self.history:
            tk.Label(inner_list, text=self._t('(пусто)'), bg=T["bg_dark"],
                     fg=T["fg_dim"], font=("Segoe UI", 10)).pack(pady=30)
        else:
            for entry in self.history:
                self._add_history_row(inner_list, entry)

        def close_dlg():
            try:
                dlg.destroy()
            except Exception:
                pass

        btn_row = tk.Frame(inner, bg=T["bg"])
        btn_row.pack(pady=(0, 18))

        def _clear_confirmed():
            self.history = []
            self._persist_settings()
            close_dlg()
            self._render_completed()
            self.root.after(50, self._open_history_window)

        def _clear_clicked():
            self._show_confirm_dialog(
                'Очистить историю?',
                'Все записи о загрузках будут удалены.',
                _clear_confirmed)

        tk.Button(btn_row, text=self._t('Очистить'),
                  bg=T["btn_cancel"], fg=T["white"],
                  activebackground=T["btn_cancel_hov"],
                  activeforeground=T["white"],
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=8, cursor="hand2",
                  command=_clear_clicked).pack(side="left", padx=5)
        tk.Button(btn_row, text=self._t('Закрыть'),
                  bg=T["btn_start"], fg=T["white"],
                  activebackground=T["btn_start_hov"],
                  activeforeground=T["white"],
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=8, cursor="hand2",
                  command=close_dlg).pack(side="left", padx=5)

        self._center_dialog(dlg)
        self.root.after(30, lambda d=dlg: self._center_dialog(d))

        def _drag_start(e):
            dlg._dx = e.x_root - dlg.winfo_x()
            dlg._dy = e.y_root - dlg.winfo_y()
        def _drag_move(e):
            dlg.geometry(f"+{e.x_root - dlg._dx}+{e.y_root - dlg._dy}")
        top.bind("<Button-1>", _drag_start)
        top.bind("<B1-Motion>", _drag_move)

        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.bind("<Escape>", lambda e: close_dlg())

    def _add_history_row(self, parent, entry):
        T = self.T
        row = tk.Frame(parent, bg=T["bg_dark"])
        row.pack(fill="x", padx=6, pady=3)

        fname = entry.get("filename", "") or ""
        file_exists = bool(fname) and os.path.exists(fname)
        folder = entry.get("folder", "") or ""
        folder_exists = bool(folder) and os.path.isdir(folder)

        if not entry.get("success", True):
            status_icon = "❌"; icon_color = T["red"]
        elif file_exists:
            status_icon = "✅"; icon_color = T["green"]
        else:
            status_icon = "🚫"; icon_color = T["orange"]

        mode_icon = "🎵" if entry.get("mode") == "audio" else "🎬"

        tk.Label(row, text=status_icon, bg=T["bg_dark"], fg=icon_color,
                 font=("Segoe UI", 12)).pack(side="left",
                                             padx=(6, 4), pady=8)
        tk.Label(row, text=mode_icon, bg=T["bg_dark"], fg=T["fg"],
                 font=("Segoe UI", 11)).pack(side="left",
                                             padx=(0, 8), pady=8)

        info = tk.Frame(row, bg=T["bg_dark"])
        info.pack(side="left", fill="x", expand=True, pady=6)

        title = entry.get("title", "?")
        tk.Label(info, text=title, bg=T["bg_dark"], fg=T["fg"],
                 font=("Segoe UI", 10, "bold"),
                 anchor="w", justify="left",
                 wraplength=480).pack(anchor="w", fill="x")

        time_str = entry.get("time", "")
        fmt_str = entry.get("format", "")
        sub = f"{time_str}  •  {fmt_str}"
        sub_color = T["fg_dim"]
        tk.Label(info, text=sub, bg=T["bg_dark"], fg=sub_color,
                 font=("Segoe UI", 8), anchor="w").pack(anchor="w")

        btns = tk.Frame(row, bg=T["bg_dark"])
        btns.pack(side="right", padx=6)

        if file_exists:
            open_btn = tk.Label(btns, text="▶", bg=T["bg_dark"], fg=T["blue"],
                                font=("Segoe UI", 12), cursor="hand2", padx=6)
            open_btn.pack(side="left")
            open_btn.bind("<Button-1>", lambda e, f=fname: self._open_file(f))
            open_btn.bind("<Enter>", lambda e: open_btn.config(fg=T["blue_hov"]))
            open_btn.bind("<Leave>", lambda e: open_btn.config(fg=T["blue"]))

        if file_exists or folder_exists:
            folder_btn = tk.Label(btns, text="📁", bg=T["bg_dark"],
                                  fg=T["fg_dim"], font=("Segoe UI", 11),
                                  cursor="hand2", padx=6)
            folder_btn.pack(side="left")
            folder_btn.bind(
                "<Button-1>",
                lambda e, f=fname, d=folder: self._reveal_in_folder(f, d))
            folder_btn.bind("<Enter>", lambda e: folder_btn.config(fg=T["fg"]))
            folder_btn.bind("<Leave>",
                            lambda e: folder_btn.config(fg=T["fg_dim"]))

        del_btn = tk.Label(btns, text="🗑", bg=T["bg_dark"],
                           fg=T["fg_dim"], font=("Segoe UI", 11),
                           cursor="hand2", padx=6)
        del_btn.pack(side="left")
        del_btn.bind("<Button-1>",
                     lambda e, en=entry: self._delete_history_entry_from_window(en, row))
        del_btn.bind("<Enter>", lambda e: del_btn.config(fg=T["red"]))
        del_btn.bind("<Leave>",
                     lambda e: del_btn.config(fg=T["fg_dim"]))

    def _delete_history_entry_from_window(self, entry, row_widget):
        fname = entry.get("filename", "") or ""
        has_file = bool(fname) and os.path.exists(fname)

        def remove_only():
            try:
                self.history.remove(entry)
            except ValueError:
                pass
            self._persist_settings()
            self._render_completed()
            try:
                row_widget.destroy()
            except Exception:
                pass

        def remove_with_file():
            if fname and os.path.exists(fname):
                try:
                    os.remove(fname)
                    log_event(f"Удалён файл: {fname}")
                except Exception as e:
                    log_event(f"Не удалось удалить {fname}: {e}")
            remove_only()

        if has_file:
            base = os.path.basename(fname)
            self._show_confirm_dialog(
                'Удалить запись?',
                f"{base}",
                remove_only, remove_with_file, self._t('Удалить с диска'))
        else:
            self._show_confirm_dialog(
                'Удалить запись из истории?',
                'Файл отсутствует.',
                remove_only)

    # ============ Открытие файла / папки ============
    def _open_file(self, path):
        try:
            os.startfile(path)
        except Exception:
            pass

    def _reveal_in_folder(self, filepath, folderpath):
        target_file = ""
        if filepath and os.path.exists(filepath):
            target_file = filepath
        target_dir = ""
        if folderpath and os.path.isdir(folderpath):
            target_dir = folderpath
        elif target_file:
            target_dir = os.path.dirname(target_file)
        try:
            if os.name == "nt":
                if target_file:
                    subprocess.Popen(['explorer', '/select,', target_file])
                elif target_dir:
                    subprocess.Popen(['explorer', target_dir])
            else:
                p = target_file or target_dir
                if p:
                    subprocess.Popen(["xdg-open", p])
        except Exception as e:
            log_event(f"Не удалось открыть папку: {e}")

    # ============ Лог ============
    def _open_log_window(self):
        if self._log_dlg is not None:
            try:
                if self._log_dlg.winfo_exists():
                    self._log_dlg.lift()
                    self._log_dlg.attributes("-topmost", True)
                    self._refresh_log_text()
                    return
            except Exception:
                pass
            self._log_dlg = None

        T = self.T
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=T["green"])
        self._log_dlg = dlg

        inner = tk.Frame(dlg, bg=T["bg"])
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        top = tk.Frame(inner, bg=T["bg"])
        top.pack(fill="x", padx=22, pady=(18, 8))
        tk.Label(top, text="📋", bg=T["bg"], fg=T["green"],
                 font=("Segoe UI", 18)).pack(side="left", padx=(0, 10))
        tk.Label(top, text=self._t('Журнал'), bg=T["bg"], fg=T["fg"],
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        self._log_size_lbl = tk.Label(inner, text="", bg=T["bg"],
                                      fg=T["fg_dim"], font=("Segoe UI", 9))
        self._log_size_lbl.pack(anchor="w", padx=22, pady=(0, 6))

        text_wrap = tk.Frame(inner, bg=T["entry_border"])
        text_wrap.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        self._log_text = tk.Text(
            text_wrap, height=16, width=72,
            bg=T["entry_bg"], fg=T["fg"], insertbackground=T["fg"],
            font=("Consolas", 9), relief="flat", bd=0, wrap="word")
        self._log_text.pack(padx=1, pady=1, fill="both", expand=True)

        btn_row = tk.Frame(inner, bg=T["bg"])
        btn_row.pack(pady=(0, 18))

        def close_dlg():
            self._log_dlg = None
            try:
                dlg.destroy()
            except Exception:
                pass

        tk.Button(btn_row, text=self._t('Обновить'),
                  bg=T["preset_bg"], fg=T["fg"],
                  activebackground=T["preset_hover"],
                  activeforeground=T["fg"],
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=8, cursor="hand2",
                  command=self._refresh_log_text).pack(side="left", padx=5)
        tk.Button(btn_row, text=self._t('Очистить'),
                  bg=T["btn_cancel"], fg=T["white"],
                  activebackground=T["btn_cancel_hov"],
                  activeforeground=T["white"],
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=8, cursor="hand2",
                  command=self._clear_log).pack(side="left", padx=5)
        tk.Button(btn_row, text=self._t('Закрыть'),
                  bg=T["btn_start"], fg=T["white"],
                  activebackground=T["btn_start_hov"],
                  activeforeground=T["white"],
                  font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
                  padx=18, pady=8, cursor="hand2",
                  command=close_dlg).pack(side="left", padx=5)

        self._center_dialog(dlg)
        self.root.after(30, lambda d=dlg: self._center_dialog(d))

        def _drag_start(e):
            dlg._dx = e.x_root - dlg.winfo_x()
            dlg._dy = e.y_root - dlg.winfo_y()
        def _drag_move(e):
            dlg.geometry(f"+{e.x_root - dlg._dx}+{e.y_root - dlg._dy}")
        top.bind("<Button-1>", _drag_start)
        top.bind("<B1-Motion>", _drag_move)

        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.bind("<Escape>", lambda e: close_dlg())
        self._refresh_log_text()

    def _refresh_log_text(self):
        try:
            if not self._log_text.winfo_exists():
                return
            n = len(_LOG_BUFFER)
            self._log_size_lbl.config(text=f"{n} / 500")
            self._log_text.config(state="normal")
            self._log_text.delete("1.0", "end")
            self._log_text.insert("end", get_log_text())
            self._log_text.see("end")
            self._log_text.config(state="disabled")
        except Exception:
            pass

    def _clear_log(self):
        try:
            clear_log_memory()
            log_event("=== Журнал очищен вручную ===")
            self._refresh_log_text()
        except Exception:
            pass

    # ============ Закрытие / трей ============
    def close_app(self):
        if self.active_tasks:
            n = len(self.active_tasks)
            if not messagebox.askyesno(
                    self._t('Скачиватель'), f"{n}"):
                return
        self._really_quit()

    def _really_quit(self):
        log_event("=== Приложение закрыто ===")
        self._persist_settings()
        self.stop_flag = True
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            pass

    def _poll_signal(self):
        try:
            if os.path.exists(SIGNAL_FILE):
                try:
                    os.remove(SIGNAL_FILE)
                except Exception:
                    pass
                self._restore_main()
        except Exception:
            pass
        try:
            self.root.after(500, self._poll_signal)
        except Exception:
            pass

    # ============ Иконка окна ============
    def _apply_icon(self):
        if not TRAY_AVAILABLE:
            return
        try:
            img = self._make_icon_image(state="idle")
            ico_path = os.path.join(tempfile.gettempdir(),
                                    "video_downloader_icon.ico")
            try:
                img.save(ico_path, format="ICO",
                         sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
                self.root.iconbitmap(default=ico_path)
            except Exception:
                pass
            photo = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, photo)
            self._icon_photo = photo
        except Exception:
            pass

    # ============ Трей ============
    def _build_tray_menu(self):
        autorun_menu = pystray.Menu(
            pystray.MenuItem(
                self._t('Через реестр'),
                self._tray_set_registry,
                checked=lambda item: self._current_autorun_method() == "registry"),
            pystray.MenuItem(
                self._t('Через папку Startup'),
                self._tray_set_startup,
                checked=lambda item: self._current_autorun_method() == "startup"),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                self._t('Отключить автозагрузку'),
                self._tray_disable_autorun,
                enabled=lambda item: self._current_autorun_method() != "none"),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                self._t('Запускать свёрнутым в трей'),
                self._toggle_start_minimized,
                checked=lambda item: self.settings.get("start_minimized", False)),
        )

        return pystray.Menu(
            pystray.MenuItem(self._t('Открыть окно'), self._tray_open,
                             default=True),
            pystray.MenuItem(self._t('Сменить режим'), self._tray_switch_mode),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._t('Автозапуск с Windows'), autorun_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._t('Выход'), self._tray_quit),
        )

    def _rebuild_tray_menu(self):
        if not TRAY_AVAILABLE or not self.tray_icon:
            return
        try:
            self.tray_icon.menu = self._build_tray_menu()
            self.tray_icon.title = self._t('Скачиватель')
            self.tray_icon.update_menu()
        except Exception:
            pass

    def _setup_tray(self):
        if not TRAY_AVAILABLE:
            return

        def _run_tray():
            try:
                menu = self._build_tray_menu()
                tray_img = self._make_icon_image(state="idle")
                icon = pystray.Icon(
                    "video_downloader", tray_img,
                    self._t('Скачиватель'), menu)
                self.tray_icon = icon
                icon.run()
            except Exception:
                pass

        threading.Thread(target=_run_tray, daemon=True, name="tray").start()

    def _tray_open(self, icon=None, item=None):
        self.root.after(0, self._restore_main)

    def _tray_switch_mode(self, icon=None, item=None):
        self.root.after(0, self._show_mode_select)

    def _tray_quit(self, icon=None, item=None):
        self.root.after(0, self.close_app)

    def _restore_main(self):
        self.root.deiconify()
        try:
            self.root.overrideredirect(True)
        except Exception:
            pass
        self.root.after(100, self._force_window_focus)
        if self.current_mode is not None:
            self.root.after(200, self._refocus_entry)

    def hide_to_tray(self):
        if TRAY_AVAILABLE and self.tray_icon is not None:
            self.root.withdraw()
            try:
                self.tray_icon.notify(
                    self._t('Приложение свёрнуто в трей.'),
                    self._t('Скачиватель'))
            except Exception:
                pass
        else:
            self.root.iconify()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if not acquire_single_instance():
        signal_existing_instance()
        time.sleep(0.15)
        sys.exit(0)

    App().run()