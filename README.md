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
---

## ⚠️ Windows SmartScreen / Defender warning (first launch)

This app is **not digitally signed**. That's why on first launch Windows may show:

- **SmartScreen:** *"Windows protected your PC"* (blue dialog)
- **Defender:** *"This app has been blocked for your protection"*

This is a **false positive**. It happens because Windows doesn't recognize the publisher — not because the app contains a virus. All source code is available in this repository, so you can inspect it and even build the `.exe` yourself.

### ✅ How to run it anyway

**For SmartScreen (blue dialog):**

1. Click **More info**.
2. Click **Run anyway**.

**Alternative — unblock the file permanently:**

1. Right-click the downloaded `.exe` file → **Properties**.
2. At the bottom of the **General** tab, check **Unblock**.
3. Click **Apply** → **OK**.

**If Windows Defender blocks it entirely:**

1. Open **Windows Security** → **Virus & threat protection**.
2. Scroll down to **Virus & threat protection settings** → **Manage settings**.
3. Under **Exclusions**, click **Add or remove exclusions**.
4. Click **Add an exclusion** → **File** → select the `.exe` file.
5. Run the app again.

> 💡 **Safety tip:** You can also upload the `.exe` to [VirusTotal](https://www.virustotal.com/) to verify it before running.

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
