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
- Dark / light theme
- Autostart with Windows

---

## ✅ Requirements
- Windows 10 or 11
- Internet connection
- **Python 3.11 or newer** — required even if you use the `.exe` version
- **FFmpeg** — mandatory for MP3 / FLAC / WAV and best-quality mode

---

## 🚀 Installation

### Step 1 — Install / update Python (always, one command)

Open **CMD** (`Win + R` → `cmd` → Enter):

```cmd
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements & winget upgrade --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
```

This command **installs Python if missing** and **updates it if already present**.

Then **close and reopen CMD** and verify:

```cmd
py -3 --version
```

### Step 2 — Update pip, setuptools, wheel (always, one command)

```cmd
py -3 -m pip install --upgrade pip setuptools wheel
```

### Step 3 — Install FFmpeg (pick one way)

**Option A — via winget (recommended):**

```cmd
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements & winget upgrade --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
```

Then **close and reopen CMD** and verify:

```cmd
ffmpeg -version
```

**Option B — offline bundle (no install, no admin rights):**

1. Download `ffmpeg.exe` and `ffprobe.exe` from the [**FFmpeg bundle release**](../../releases/tag/ffmpeg-bundle).
2. Put **both files next to** `VideoDownloader.exe`.
3. The app will detect them automatically.

**Without FFmpeg:** MP3 / FLAC / WAV and "best quality" mode will not work.

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
Then double-click the `.bat`. The ready `.exe` will appear in `dist\`.

---

## ▶️ Usage
1. Pick mode: **Video** or **Music**.
2. Paste a URL (or press **📋** to paste from clipboard and download immediately).
3. Choose format / quality.
4. Choose the save folder.
5. Press **Download**.
6. Watch the progress bar. When done — the entry appears in **Completed**.

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

**If Defender blocks your `.bat` build:**

PyInstaller "packs" Python code into a single `.exe`, which sometimes looks suspicious to Defender. Just add the project folder to Windows Security exclusions:

1. Open **Windows Security** → **Virus & threat protection** → **Manage settings**.
2. Under **Exclusions**, click **Add or remove exclusions** → **Add an exclusion** → **Folder**.
3. Select the folder containing your `.pyw` file and `.bat` script.
4. Run the `.bat` again.

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
| `FFmpeg not found` | Install FFmpeg (Step 3). If winget fails — download the offline bundle and put both files next to the app |
| MP3 / FLAC / WAV fail | Without FFmpeg these formats are impossible |
| `'py' is not recognized` | Reinstall Python with PrependPath: `winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --override "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1"` then reopen CMD |
| `pip` not found | Use `py -3 -m pip ...` instead of `pip ...` |
| `winget` not found | Update "App Installer" from Microsoft Store |
| Download fails on YouTube | Update `yt-dlp`: `py -3 -m pip install --upgrade yt-dlp` |

---

## 🔗 More apps by the same author

- ⏻ [Shutdown Timer](https://github.com/SKRRIXZZ/shutdown-timer) — PC shutdown / restart / sleep / hibernate timer
- 🌐 [Mini Translator](https://github.com/SKRRIXZZ/mini-translator) — clipboard translator with a global hotkey
- ⬇ [Video & Music Downloader](https://github.com/SKRRIXZZ/video-music-downloader) — GUI downloader based on yt-dlp

---

## 📜 License
MIT
