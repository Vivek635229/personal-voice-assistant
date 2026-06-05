# Personal Assistant — Command Center

Professional README for the Personal Assistant project. This file explains how to set up a Python virtual environment, install dependencies, run the app, and troubleshoot the most common issues on Windows.

## Project Summary

A small desktop personal assistant with a polished Tkinter GUI, voice input, text-to-speech, and news/weather/reminder features. The main program entry is `Task1.py`.

## Features

- GUI for typed and voice commands
- Text-to-speech responses (pyttsx3)
- Speech recognition (speech_recognition)
- News fetching (RSS and topic search) with optional images
- Weather lookup using Open-Meteo
- Reminders and basic calculator

## Prerequisites

- Windows (instructions are Windows-focused)
- Python 3.8+ installed and on `PATH`
- A microphone if you want voice input

Optional (recommended): create a dedicated virtual environment for this project.

## Recommended Dependencies

The project uses these Python packages (not exhaustive):

- `pyttsx3`
- `SpeechRecognition`
- `sounddevice`
- `requests`
- `Pillow` (optional, for inline news images)

If you maintain a `requirements.txt`, install with `pip install -r requirements.txt` (see Setup).

## Setup (Windows)

Open PowerShell (recommended) and run these commands from the project root (`d:\Qskill Internship`):

1. Create and activate a virtual environment

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Or using cmd.exe:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

2. Upgrade pip and install core dependencies

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install pyttsx3 SpeechRecognition requests sounddevice
# Optional for images and better RSS thumbnail support:
pip install pillow
```

Notes:

- `sounddevice` may need system libraries (PortAudio). If you encounter build errors, ensure Visual C++ Build Tools are installed or use prebuilt binaries where available. `pipwin` can sometimes help: `pip install pipwin` then `pipwin install sounddevice`.
- If you plan to use microphone with `SpeechRecognition`, you may need `pyaudio`; install via `pipwin install pyaudio` on Windows if required.

3. (Optional) Freeze current environment to `requirements.txt`

```powershell
pip freeze > requirements.txt
```

## Running the App

After activating the venv and installing dependencies:

```powershell
python Task1.py
```

The GUI opens. Try example commands from the Quick Commands panel (right side), or speak the wake word if you have a microphone configured.

## News & Images

- The assistant fetches news via RSS feeds. Some feeds include images; install `Pillow` to render images inline in the conversation pane.
- If images don't appear, try installing `Pillow` and ensure the network allows outbound requests to RSS/image URLs.

## Common Issues & Troubleshooting

- Microphone not working: check Windows microphone privacy settings, ensure the app has permission, and test with other apps. If `sounddevice` fails to install, install PortAudio or use `pipwin`.
- SpeechRecognition errors: the library uses external recognizers (the default in the code uses Google Web Speech via the internet). Ensure network access.
- TTS (pyttsx3) voices: voice availability depends on your system. If audio doesn't play, verify system audio devices and test `pyttsx3` in a small script.
- RSS returns same headlines for every query: some feeds don't support search queries. The assistant falls back to world/regional feeds; for more accurate results we can add more sources or fetch `og:image`/meta tags from article pages (requires additional network calls).

## Development Notes

- Main script: `Task1.py` (GUI + assistant logic).
- The assistant exposes UI hooks so the GUI can append logs and structured news items with images.
- If you modify the code, keep changes small and run the app to verify behavior.

## Contributing

- Fork the repo, create a feature branch, and open a pull request with a clear description.
- Add tests for new behaviors where reasonable.

## License

- Add a license file appropriate to your project (e.g., `MIT`, `Apache-2.0`) and reference it here.

## Contact

- For help or to request features, open an issue on the GitHub repository.
