# ⬇ Video Downloader

Multi-language video & music downloader based on `yt-dlp`, with a nice GUI, thumbnails, live progress, download history, and tray support.

**English** | [Русский](README.ru.md)

---

## ✨ Features
- Two modes: **Video** and **Music**
- Quality picker: 1080p / 720p / 480p / 360p
- Audio formats: M4A, MP3, FLAC, WAV
- Best-quality mode with merging via FFmpeg
- Auto thumbnail embedding (MP4 / MKV / MP3)
- Live progress bar, speed, ETA
- History (last 30 downloads)
- Playlist support in music mode
- 20 interface languages
- Autostart with Windows

---

## ✅ Requirements
- Windows 10 or 11
- Internet connection
- **Python 3.11 or newer** — required even if you use the `.exe` version
- **FFmpeg** — mandatory for MP3 / FLAC / WAV and best quality

---

## 🚀 Installation

### Step 1 — Install / update Python (always, one command)

Open **CMD** (`Win + R` → `cmd` → Enter):

```cmd
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements & winget upgrade --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
```

**Close and reopen CMD** and verify:

```cmd
py -3 --version
```

### Step 2 — Update pip, setuptools, wheel (always, one command)

```cmd
py -3 -m pip install --upgrade pip setuptools wheel
```

### Step 3 — Install / update FFmpeg (always, one command)

```cmd
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements & winget upgrade --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
```

**Close and reopen CMD**, verify:

```cmd
ffmpeg -version
```

If not recognized — drop `ffmpeg.exe` next to the app.

---

## 📥 Installing the app

### 🟢 A. If you have the `.exe` file
Double-click `VideoDownloader.exe`. Done.

### 🟡 B. If you have the `.pyw` file
```cmd
py -3 -m pip install --upgrade yt-dlp Pillow pystray
pythonw video_downloader_multilang.pyw
```

### 🔴 C. If you have a `.bat` that builds `.exe`
```cmd
py -3 -m pip install --upgrade pyinstaller yt-dlp Pillow pystray
```
Then double-click the `.bat`. The `.exe` appears in `dist\`.

---

## ▶️ Usage
1. Pick mode: **Video** or **Music**.
2. Paste a URL (or press **📋** to paste from clipboard and download immediately).
3. Choose format / quality.
4. Choose the save folder.
5. Press **Download**.
6. Watch the progress bar. When done — the entry appears in **Completed**.

---

## ⚠️ Предупреждение Windows SmartScreen / Defender (при первом запуске)

Приложение **не имеет цифровой подписи**. Поэтому при первом запуске Windows может показать:

- **SmartScreen:** *«Windows защитила ваш компьютер»* (синее окно)
- **Defender:** *«Это приложение было заблокировано для вашей защиты»*

Это **ложное срабатывание**. Оно возникает потому, что Windows не знает издателя, а не потому что в приложении есть вирус. Весь исходный код открыт в этом репозитории — ты можешь его проверить и даже собрать `.exe` сам.

### ✅ Как всё равно запустить

**Для SmartScreen (синее окно):**

1. Нажми **Подробнее**.
2. Нажми **Выполнить в любом случае**.

**Альтернатива — разблокировать файл навсегда:**

1. Правый клик по скачанному `.exe` → **Свойства**.
2. Внизу вкладки **Общие** поставь галочку **Разблокировать**.
3. Нажми **Применить** → **ОК**.

**Если Windows Defender блокирует полностью:**

1. Открой **Безопасность Windows** → **Защита от вирусов и угроз**.
2. Прокрути вниз до **Параметры защиты от вирусов и угроз** → **Управление настройками**.
3. В разделе **Исключения** нажми **Добавить или удалить исключения**.
4. Нажми **Добавить исключение** → **Файл** → выбери `.exe`.
5. Запусти приложение снова.

**Если Defender блокирует `.bat`-сборку:**

PyInstaller «упаковывает» Python-код в один `.exe`, и это иногда выглядит подозрительно для Defender. Просто добавь папку с проектом в исключения Безопасности Windows:

1. Открой **Безопасность Windows** → **Защита от вирусов и угроз** → **Управление настройками**.
2. В разделе **Исключения** нажми **Добавить или удалить исключения** → **Добавить исключение** → **Папка**.
3. Выбери папку, где лежат твой `.pyw` файл и `.bat`-скрипт.
4. Запусти `.bat` заново.

> 💡 **Совет по безопасности:** можешь загрузить `.exe` на [VirusTotal](https://www.virustotal.com/), чтобы проверить его перед запуском.

---

## 🔄 Keeping yt-dlp fresh
YouTube changes frequently. Update yt-dlp regularly:

```cmd
py -3 -m pip install --upgrade yt-dlp
```

Once a month is enough, unless something stops working — then update right away.

---

## 🛠 Troubleshooting

| Problem | Solution |
|---|---|
| `yt-dlp not installed` inside the `.exe` | The `.exe` was built without `yt-dlp`. Install via pip and rebuild |
| `FFmpeg not found` | Install FFmpeg (Step 3). If winget fails — drop `ffmpeg.exe` next to the app |
| MP3 / FLAC / WAV fail | Without FFmpeg these formats are impossible |
| `'py' is not recognized` | Reinstall Python with PrependPath (see weather README) |
| `pip` not found | Use `py -3 -m pip ...` |

---

## 📜 License
MIT
