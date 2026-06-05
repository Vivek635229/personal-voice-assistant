import datetime
import difflib
import ast
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import random
import pyttsx3
import requests
import urllib.parse
import io
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False
import sounddevice as sd
import speech_recognition as sr


class PersonalAssistant:
    def __init__(self, name="Assistant", wake_word="hey assistant"):
        self.name = name
        self.wake_word = wake_word
        self.ui_log_callback = None
        self.ui_status_callback = None
        # store last news results as list of dicts: {title, link, description}
        self.last_news = []
        
        # Initialize Text-to-Speech
        self.engine = pyttsx3.init()
        voices = self.engine.getProperty("voices")
        self.engine.setProperty("voice", voices[0].id)
        self.engine.setProperty("rate", 165)
        self.engine.setProperty("volume", 1.0)
        
        # Initialize Speech Recognition
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True

    def speak(self, text: str):
        """Outputs audio to the user and prints it to the console."""
        print(f"\n{self.name}: {text}")
        if self.ui_log_callback:
            self.ui_log_callback(f"{self.name}: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def announce_completion(self):
        completion_lines = [
            "Task completed.",
            "Done. What would you like next?",
            "Completed successfully.",
            "That task is finished.",
        ]
        self.speak(random.choice(completion_lines))

    def set_ui_hooks(self, log_callback=None, status_callback=None):
        self.ui_log_callback = log_callback
        self.ui_status_callback = status_callback
        # structured news callback: receives dict {title, link, image}
        self.ui_news_callback = None

    def set_ui_news_hook(self, news_callback=None):
        """Optional hook for structured news items. Called with dict {title, link, image} (image may be a URL)."""
        self.ui_news_callback = news_callback

    def _normalize_command(self, command: str) -> str:
        return re.sub(r"\s+", " ", command.strip().lower())

    def _command_matches(self, command: str, phrases) -> bool:
        normalized_command = self._normalize_command(command)
        return any(phrase in normalized_command for phrase in phrases)

    def _closest_keyword(self, command: str, keywords, cutoff: float = 0.78):
        words = re.findall(r"[a-z]+", command.lower())
        if not words:
            return ""

        match = difflib.get_close_matches(words[0], keywords, n=1, cutoff=cutoff)
        if match:
            return match[0]
        return ""

    def _safe_calculate(self, expression: str):
        operators = {
            ast.Add: lambda left, right: left + right,
            ast.Sub: lambda left, right: left - right,
            ast.Mult: lambda left, right: left * right,
            ast.Div: lambda left, right: left / right,
            ast.FloorDiv: lambda left, right: left // right,
            ast.Mod: lambda left, right: left % right,
            ast.Pow: lambda left, right: left ** right,
            ast.USub: lambda value: -value,
            ast.UAdd: lambda value: value,
        }

        def evaluate(node):
            if isinstance(node, ast.Expression):
                return evaluate(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in operators:
                return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
                return operators[type(node.op)](evaluate(node.operand))
            raise ValueError("Unsupported expression")

        tree = ast.parse(expression, mode="eval")
        return evaluate(tree)

    def _extract_calculation(self, command: str) -> str:
        command = self._normalize_command(command)
        command = command.replace("what is", "")
        command = command.replace("calculate", "")
        command = command.replace("compute", "")
        command = command.replace("please", "")
        command = command.replace("divided by", "/")
        command = command.replace("times", "*")
        command = command.replace("plus", "+")
        command = command.replace("minus", "-")
        command = command.replace("over", "/")
        command = command.replace("x", "*")
        command = command.replace("=", " ")

        allowed = re.findall(r"[0-9\+\-\*/\.%() ]+", command)
        expression = "".join(allowed).strip()
        return expression

    def _open_windows_resource(self, target: str):
        paths = {
            "settings": "ms-settings:",
            "calculator": "calc.exe",
            "notepad": "notepad.exe",
            "paint": "mspaint.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "task manager": "taskmgr.exe",
            "control panel": "control.exe",
            "browser": "https://www.google.com",
            "chrome": "https://www.google.com",
            "edge": "https://www.google.com",
            "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
            "documents": os.path.join(os.path.expanduser("~"), "Documents"),
        }

        target = target.strip().lower()
        if target in {"browser", "chrome", "edge"}:
            webbrowser.open(paths[target])
            return True

        if target in {"downloads", "documents"}:
            os.startfile(paths[target])
            return True

        if target in paths:
            os.startfile(paths[target])
            return True

        return False

    def _help_message(self):
        self.speak(
            "I can open Settings, Calculator, Notepad, File Explorer, Task Manager, Control Panel, Paint, Downloads, and Documents. "
            "I can also tell the time, check weather, read news, set reminders, and solve basic calculations."
        )

    def _extract_weather_city(self, command: str) -> str:
        match = re.search(r"(?:check\s+)?weather(?:\s+(?:in|for))?\s+(.+)$", command)
        if match:
            return match.group(1).strip()
        return "New York"

    def _read_typed_command(self, prompt: str) -> str:
        try:
            command = input(prompt).strip().lower()
            if command:
                print(f"You typed: '{command}'")
            return command
        except EOFError:
            return ""

    def _listen_with_sounddevice(self, duration: float, show_prompt: bool = True) -> str:
        sample_rate = 16000

        try:
            if duration <= 0:
                return ""

            if show_prompt:
                print("\n[Listening...]")
            recording = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
            )
            sd.wait()

            audio_data = sr.AudioData(recording.tobytes(), sample_rate, 2)
            command = self.recognizer.recognize_google(audio_data).lower()
            print(f"You said: '{command}'")
            return command
        except sr.UnknownValueError:
            print("[Unrecognized Audio]")
            return ""
        except sr.RequestError:
            self.speak("My speech recognition service is currently down.")
            return ""
        except Exception:
            return ""

    def listen(self, timeout=5, phrase_time_limit=8, show_prompt=True) -> str:
        """Listens to the microphone and returns the transcribed text."""
        try:
            recorded_command = self._listen_with_sounddevice(float(phrase_time_limit or timeout or 5), show_prompt=show_prompt)
            if recorded_command:
                return recorded_command

            if show_prompt:
                print("\n[Microphone unavailable. Type your response instead.]")
                return self._read_typed_command("You: ")

            return self._read_typed_command("Wake word: ")
        except (sd.PortAudioError, OSError, ValueError):
            if show_prompt:
                print("\n[Microphone unavailable. Type your response instead.]")
                return self._read_typed_command("You: ")
            return self._read_typed_command("Wake word: ")

    # ---------------------------------------------------------
    # CORE SKILLS
    # ---------------------------------------------------------

    def get_time(self):
        now = datetime.datetime.now().strftime("%I:%M %p")
        self.speak(f"It is currently {now}.")

    def open_settings(self):
        if self._open_windows_resource("settings"):
            self.speak("Opening Settings.")
        else:
            self.speak("I couldn't open Settings on this device.")

    def open_calculator(self):
        if self._open_windows_resource("calculator"):
            self.speak("Opening Calculator.")
        else:
            self.speak("I couldn't open Calculator on this device.")

    def open_named_app(self, command: str):
        normalized = self._normalize_command(command)
        app_aliases = {
            "notepad": ["notepad", "text editor"],
            "paint": ["paint", "mspaint"],
            "task manager": ["task manager", "taskmgr"],
            "control panel": ["control panel"],
            "file explorer": ["file explorer", "explorer", "files"],
            "downloads": ["downloads", "download folder"],
            "documents": ["documents", "document folder"],
            "browser": ["browser", "web browser", "chrome", "edge"],
        }

        for app_name, aliases in app_aliases.items():
            if any(alias in normalized for alias in aliases):
                if self._open_windows_resource(app_name):
                    self.speak(f"Opening {app_name.title()}.")
                else:
                    self.speak(f"I couldn't open {app_name.title()} on this device.")
                return True

        return False

    def calculate(self, command: str):
        expression = self._extract_calculation(command)
        if not expression:
            self.speak("Tell me a calculation like 12 plus 5 or calculate 7 times 8.")
            return

        expression = expression.replace("x", "*")
        expression = expression.replace("times", "*")
        expression = expression.replace("plus", "+")
        expression = expression.replace("minus", "-")
        expression = expression.replace("divided by", "/")
        expression = expression.replace("over", "/")

        try:
            result = self._safe_calculate(expression)
            self.speak(f"The answer is {result}.")
        except Exception:
            self.speak("I couldn't solve that calculation.")

    def get_weather(self, command: str):
        command = self._normalize_command(command)
        city = self._extract_weather_city(command)

        if city == "New York" and self._command_matches(command, ["check weather", "what is the weather", "weather"]):
            city = "New York"

        self.speak(f"Checking the weather for {city}.")
        try:
            # Free Geocoding API
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&format=json"
            geo_res = requests.get(geo_url).json()

            if "results" not in geo_res:
                self.speak(f"I couldn't find a location named {city}.")
                return

            lat = geo_res["results"][0]["latitude"]
            lon = geo_res["results"][0]["longitude"]

            # Free Weather API
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            weather_res = requests.get(weather_url).json()
            temp = weather_res["current_weather"]["temperature"]

            self.speak(f"It is currently {temp} degrees Celsius in {city}.")
        except Exception:
            self.speak("I am having trouble reaching the weather service.")

    def get_news(self):
        # Deprecated: simple call no longer used. Keep compatibility wrapper.
        return self.get_news_for_query("")

    def _extract_news_topic(self, command: str) -> str:
        command = self._normalize_command(command)
        # Try explicit patterns first: "news about india", "show news on hindustan"
        match = re.search(r"(?:news|headlines|read news|show news)(?:\s+(?:about|on|from|in))?\s+(.+)$", command)
        if match:
            topic = match.group(1).strip()
            if topic and topic not in ("latest", "top", "top stories", "the news"):
                return topic

        # fallback: remove common verbs and return remaining words as topic
        cleaned = re.sub(r"\b(read|show|give|tell|me|the|latest|top|headlines|news|about|on|in|from)\b", "", command)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            return cleaned

        return ""

    def get_news_for_query(self, query: str):
        """Fetch news for a given query. If query is empty, fetch top headlines."""
        topic = query.strip()
        sources = []
        if topic:
            self.speak(f"Searching news for {topic}.")
            q = urllib.parse.quote_plus(topic)
            sources.append(f"https://news.google.com/rss/search?q={q}")
            # regional / world fallbacks
            sources.append("https://feeds.bbci.co.uk/news/world/rss.xml")
            sources.append("https://feeds.bbci.co.uk/news/world/asia/rss.xml")
        else:
            self.speak("Fetching the latest headlines.")
            sources.append("http://feeds.bbci.co.uk/news/rss.xml")
            sources.append("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en")

        collected = []
        for src in sources:
            try:
                resp = requests.get(src, timeout=8)
                root = ET.fromstring(resp.content)
                items = root.findall('.//item')
                for item in items:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    # description may be in <description> or <summary>
                    desc_elem = item.find('description') or item.find('summary')
                    if title_elem is None or not title_elem.text:
                        continue
                    title = title_elem.text.strip()
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                    # try to find an image URL inside known tags
                    image_url = ""
                    for child in list(item):
                        tag = child.tag.lower()
                        if 'thumbnail' in tag or 'content' in tag or 'enclosure' in tag or 'image' in tag:
                            # common attributes carrying urls
                            image_url = child.attrib.get('url') or child.attrib.get('href') or child.attrib.get('src') or image_url
                            if image_url:
                                break
                    collected.append((title, link, desc, image_url))
                if collected:
                    break
            except Exception:
                continue

        if not collected:
            if topic:
                self.speak(f"I couldn't find news for {topic}. Please try a different topic.")
            else:
                self.speak("I couldn't retrieve headlines right now.")
            return

        # Limit to top 5 and compute simple relevance percentage when topic provided
        # store structured news results and display numbered list
        self.last_news = []
        results = collected[:10]
        lines = []
        for idx, (title, link, desc, image_url) in enumerate(results[:5], start=1):
            if topic:
                ratio = difflib.SequenceMatcher(None, topic.lower(), title.lower()).ratio()
                pct = int(round(ratio * 100))
                line = f"{idx}. {title} ({pct}% match)"
            else:
                line = f"{idx}. {title}"
            lines.append(line)
            # store structured item
            self.last_news.append({"title": title, "link": link, "description": desc, "image": image_url})
            # log each headline to UI with link when available
            if self.ui_log_callback:
                display = f"News: {line}"
                if link:
                    display += f" — {link}"
                self.ui_log_callback(display)
            # send structured news item to UI for image rendering (background thread -> UI thread)
            if hasattr(self, 'ui_news_callback') and self.ui_news_callback:
                try:
                    self.ui_news_callback({"title": title, "link": link, "image": image_url})
                except Exception:
                    pass

        # Speak a concise summary and give follow-up instructions
        if topic:
            self.speak(f"Found {len(lines)} stories for {topic}. I listed the top {len(lines)} in the conversation. Say 'more about 1' to open the first story or say the headline fragment.")
        else:
            self.speak(f"Here are the top stories. I listed the top {len(lines)} in the conversation. Say 'more about 1' to open the first story.")

    def show_news_detail(self, identifier: str) -> bool:
        """Show details for a news item. Identifier may be a number (1-based) or a text fragment of the title."""
        if not self.last_news:
            self.speak("I don't have any recent headlines. Ask me for news first.")
            return False

        ident = identifier.strip().lower()
        # numeric selection
        if re.fullmatch(r"\d+", ident):
            idx = int(ident) - 1
            if 0 <= idx < len(self.last_news):
                item = self.last_news[idx]
                title = item.get("title")
                link = item.get("link")
                desc = item.get("description")
                if link:
                    self.speak(f"Opening article: {title}")
                    try:
                        webbrowser.open(link)
                    except Exception:
                        self.speak("I couldn't open the article in your browser.")
                else:
                    # speak description or title
                    if desc:
                        self.speak(desc)
                    else:
                        self.speak(title)
                return True
            else:
                self.speak("That article number is out of range.")
                return False

        # text fragment: find best matching title
        best_idx = -1
        best_ratio = 0.0
        for i, item in enumerate(self.last_news):
            title = item.get("title", "")
            ratio = difflib.SequenceMatcher(None, ident, title.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i

        if best_idx >= 0 and best_ratio > 0.35:
            item = self.last_news[best_idx]
            title = item.get("title")
            link = item.get("link")
            desc = item.get("description")
            if link:
                self.speak(f"Opening article: {title}")
                try:
                    webbrowser.open(link)
                except Exception:
                    self.speak("I couldn't open the article in your browser.")
            else:
                if desc:
                    self.speak(desc)
                else:
                    self.speak(title)
            return True

        self.speak("I couldn't match that to any recent headline. Try saying the article number or a distinct headline phrase.")
        return False

    def set_reminder(self, command: str):
        # Regex to capture task and time (e.g., "remind me to check emails in 5 minutes")
        match = re.search(r"remind me to (.+?) in (\d+)\s*(second|minute|hour)", command)
        
        if not match:
            self.speak("I didn't catch the time. Try saying: remind me to stretch in 10 minutes.")
            return

        task, duration_str, unit = match.groups()
        duration = int(duration_str)

        # Convert to seconds
        multiplier = {"second": 1, "minute": 60, "hour": 3600}
        delay = duration * multiplier[unit]

        self.speak(f"Got it. I will remind you to {task} in {duration} {unit}s.")

        # Run reminder in a background thread so the assistant can keep listening
        def alert():
            time.sleep(delay)
            # Create a new TTS engine instance for the thread
            alert_engine = pyttsx3.init()
            print(f"\n[REMINDER] {task.upper()}")
            alert_engine.say(f"Reminder alert! You asked me to remind you to {task}.")
            alert_engine.runAndWait()

        threading.Thread(target=alert, daemon=True).start()

    # ---------------------------------------------------------
    # ROUTER & MAIN LOOP
    # ---------------------------------------------------------

    def process_command(self, command: str) -> bool:
        """Routes the command to the correct function. Returns False to exit."""
        if not command:
            return True

        command = self._normalize_command(command)
        fuzzy_keyword = self._closest_keyword(command, ["weather", "settings", "setting", "remind", "news", "time"])
        handled = False

        if any(word in command for word in ["stop", "exit", "quit", "goodbye"]):
            self.speak("Goodbye!")
            return False

        if self._command_matches(command, ["what can you do", "help me", "help", "show commands"]):
            self._help_message()
            handled = True

        elif self._command_matches(command, ["open settings", "open setting", "open the settings", "open windows settings"]):
            self.open_settings()
            handled = True
        elif self._command_matches(command, ["open calculator", "start calculator", "launch calculator", "calculator"]):
            self.open_calculator()
            handled = True
        elif self._command_matches(command, ["open notepad", "open paint", "open task manager", "open control panel", "open file explorer", "open browser", "open downloads", "open documents"]):
            if not self.open_named_app(command):
                self.speak("I couldn't open that app on this device.")
            handled = True
        elif "time" in command or fuzzy_keyword == "time":
            self.get_time()
            handled = True
        elif "weather" in command or self._command_matches(command, ["check weather", "what's the weather", "what is the weather", "weather in", "weather for"]) or fuzzy_keyword == "weather":
            self.get_weather(command)
            handled = True
        elif "news" in command or fuzzy_keyword == "news":
            topic = self._extract_news_topic(command)
            self.get_news_for_query(topic)
            handled = True
        # Follow-up news interactions: "more about 1", "more about watchdog", or short topics like "asia"
        elif re.match(r"(?:more about|details about|open|read|more on)\s+(.+)$", command):
            q = re.match(r"(?:more about|details about|open|read|more on)\s+(.+)$", command).group(1).strip()
            if self.show_news_detail(q):
                handled = True
        elif re.fullmatch(r"\d+", command.strip()):
            if self.show_news_detail(command.strip()):
                handled = True
        elif 0 < len(command.split()) <= 3 and not any(w in {"open", "start", "launch", "what", "who", "when", "where", "why", "how", "the", "a", "an"} for w in command.split()):
            # Treat short free text as a news topic search
            self.get_news_for_query(command)
            handled = True
        elif "remind" in command or fuzzy_keyword == "remind":
            self.set_reminder(command)
            handled = True
        elif any(symbol in command for symbol in ["+", "-", "*", "/", "times", "plus", "minus", "divided by", "compute", "calculate", "what is"]):
            self.calculate(command)
            handled = True
        else:
            if self._command_matches(command, ["open", "settings", "setting"]):
                self.open_settings()
                handled = True
            else:
                if self.open_named_app(command):
                    handled = True
                else:
                    self.speak("I don't know how to do that yet.")

        if handled:
            self.announce_completion()

        return True

    def run(self):
        """The main execution loop with Wake Word detection."""
        self.speak(f"Online. Say '{self.wake_word}' to wake me up.")
        
        while True:
            # Standby mode: Listen silently for the wake word
            trigger = self.listen(timeout=None, phrase_time_limit=3, show_prompt=False)
            trigger = self._normalize_command(trigger) if trigger else ""

            if trigger and self._looks_like_direct_command(trigger):
                should_continue = self.process_command(trigger)
                if not should_continue:
                    break
                continue
            
            if trigger and self.wake_word in trigger:
                self.speak("Yes? How can I help?")
                
                # Active mode: Listen for the actual command
                command = self.listen(timeout=5, phrase_time_limit=8, show_prompt=True)
                
                if command:
                    should_continue = self.process_command(command)
                    if not should_continue:
                        break
                else:
                    self.speak("I didn't hear anything. Going back to sleep.")

    def _looks_like_direct_command(self, command: str) -> bool:
        return any(
            keyword in command
            for keyword in (
                "time",
                "weather",
                "news",
                "remind",
                "calculator",
                "notepad",
                "paint",
                "explorer",
                "browser",
                "task",
                "control",
                "check",
                "open",
                "open setting",
                "open settings",
            )
        )

    def launch_gui(self):
        ui = AssistantUI(self)
        ui.run()


class AssistantUI:
    def __init__(self, assistant: PersonalAssistant):
        self.assistant = assistant
        self.root = tk.Tk()
        self.root.title("Personal Assistant Command Center")
        self.root.geometry("920x640")
        self.root.minsize(820, 560)
        self.root.configure(bg="#07111f")

        self.assistant.set_ui_hooks(self._append_log_threadsafe, self._set_status_threadsafe)
        # provide a structured news hook so assistant can send images/links
        self.assistant.set_ui_news_hook(self._append_news_item_threadsafe)

        # keep references to PhotoImage objects to avoid GC
        self._image_refs = []

        self._build_styles()
        self._build_layout()

    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#07111f")
        style.configure("Header.TFrame", background="#0c1a2d")
        style.configure("Card.TFrame", background="#0c1a2d")
        style.configure("Title.TLabel", background="#0c1a2d", foreground="#f8fafc", font=("Segoe UI", 24, "bold"))
        style.configure("Subtitle.TLabel", background="#0c1a2d", foreground="#9fb2c9", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#0c1a2d", foreground="#dbeafe", font=("Segoe UI", 11, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8), background="#1f6feb")
        style.map("Accent.TButton", background=[("active", "#2d8cff")], foreground=[("active", "white")])

    def _build_layout(self):
        container = ttk.Frame(self.root, style="Root.TFrame", padding=18)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="Header.TFrame", padding=20)
        header.pack(fill="x")

        top_row = ttk.Frame(header, style="Header.TFrame")
        top_row.pack(fill="x")

        ttk.Label(top_row, text="Personal Assistant", style="Title.TLabel").pack(side="left", anchor="w")
        badge = tk.Label(
            top_row,
            text="LIVE",
            bg="#0f766e",
            fg="#ecfeff",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        badge.pack(side="right")

        ttk.Label(
            header,
            text="A polished command center for typing, voice input, and instant spoken feedback.",
            style="Subtitle.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))

        accent_bar = tk.Frame(header, bg="#1f6feb", height=4)
        accent_bar.pack(fill="x", pady=(14, 0))

        body = ttk.Frame(container, style="Root.TFrame")
        body.pack(fill="both", expand=True, pady=(16, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left_card = ttk.Frame(body, style="Card.TFrame", padding=16)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right_card = ttk.Frame(body, style="Card.TFrame", padding=16)
        right_card.grid(row=0, column=1, sticky="nsew")

        ttk.Label(left_card, text="Conversation", style="Section.TLabel").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(
            left_card,
            height=18,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            relief="flat",
            padx=12,
            pady=12,
        )
        self.log.pack(fill="both", expand=True, pady=(12, 0))
        self.log.configure(state="disabled")

        input_bar = ttk.Frame(left_card, style="Card.TFrame")
        input_bar.pack(fill="x", pady=(14, 0))

        self.command_var = tk.StringVar()
        self.command_entry = ttk.Entry(input_bar, textvariable=self.command_var, font=("Segoe UI", 11))
        self.command_entry.pack(side="left", fill="x", expand=True)
        self.command_entry.bind("<Return>", self._on_send)

        ttk.Button(input_bar, text="Send", style="Accent.TButton", command=self._on_send).pack(side="left", padx=(10, 0))

        controls = ttk.Frame(left_card, style="Card.TFrame")
        controls.pack(fill="x", pady=(10, 0))

        ttk.Button(controls, text="Voice Input", style="Accent.TButton", command=self._listen_once).pack(side="left")
        ttk.Button(controls, text="Clear", style="Accent.TButton", command=self._clear_log).pack(side="left", padx=10)
        ttk.Button(controls, text="Exit", style="Accent.TButton", command=self.root.destroy).pack(side="left")

        ttk.Label(right_card, text="Quick Commands", style="Section.TLabel").pack(anchor="w")
        info_card = tk.Frame(right_card, bg="#10233d", highlightthickness=1, highlightbackground="#1f6feb")
        info_card.pack(fill="x", pady=(12, 14))
        tk.Label(
            info_card,
            text="Tip: press Enter to send instantly.\nUse voice input for a hands-free experience.",
            justify="left",
            anchor="w",
            bg="#10233d",
            fg="#dbeafe",
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
        ).pack(fill="x")

        quick_text = (
            "• open calculator\n"
            "• open settings\n"
            "• what time is it\n"
            "• check weather in London\n"
            "• read news\n"
            "• remind me to stretch in 10 minutes\n"
            "• calculate 7 times 8"
        )
        quick_label = tk.Label(
            right_card,
            text=quick_text,
            justify="left",
            anchor="nw",
            bg="#0c1a2d",
            fg="#cbd5e1",
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
        )
        quick_label.pack(fill="x", pady=(12, 16))

        self.status_var = tk.StringVar(value="Ready. Type a command or use voice input.")
        status = tk.Label(
            right_card,
            textvariable=self.status_var,
            justify="left",
            anchor="nw",
            bg="#0b1220",
            fg="#7dd3fc",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=12,
            wraplength=260,
        )
        status.pack(fill="x")

        self._append_log("Personal Assistant: Online. Use the box below to send a command.")
        self.command_entry.focus_set()

    def _append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _append_log_threadsafe(self, text: str):
        self.root.after(0, lambda: self._append_log(text))

    def _append_news_item_threadsafe(self, item: dict):
        """Schedule appending a structured news item to the conversation pane.
        Item format: {title, link, image}
        """
        self.root.after(0, lambda: self._append_news_item(item))

    def _append_news_item(self, item: dict):
        """Append a news item with optional image. Runs on the main thread."""
        title = item.get("title", "")
        link = item.get("link", "")
        image_url = item.get("image") or item.get("img") or ""

        self.log.configure(state="normal")
        try:
            if image_url and HAS_PIL:
                try:
                    resp = requests.get(image_url, timeout=6)
                    img_data = resp.content
                    image = Image.open(io.BytesIO(img_data))
                    # resize to fit UI nicely
                    max_w, max_h = 360, 200
                    image.thumbnail((max_w, max_h), Image.ANTIALIAS)
                    photo = ImageTk.PhotoImage(image)
                    self._image_refs.append(photo)
                    self.log.image_create("end", image=photo)
                    self.log.insert("end", "\n")
                except Exception:
                    # ignore image errors and continue with text
                    pass

            # insert title and link
            if title:
                self.log.insert("end", f"{title}\n")
            if link:
                self.log.insert("end", f"{link}\n\n")
            else:
                self.log.insert("end", "\n")
        finally:
            self.log.see("end")
            self.log.configure(state="disabled")

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_status_threadsafe(self, text: str):
        self.root.after(0, lambda: self._set_status(text))

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._set_status("Conversation cleared.")

    def _on_send(self, event=None):
        command = self.command_var.get().strip()
        if not command:
            messagebox.showinfo("Assistant", "Type a command first.")
            return
        self.command_var.set("")
        self._append_log(f"You: {command}")
        self._set_status("Processing command...")
        threading.Thread(target=self._process_command, args=(command,), daemon=True).start()

    def _listen_once(self):
        self._set_status("Listening for one voice command...")
        threading.Thread(target=self._listen_and_process, daemon=True).start()

    def _listen_and_process(self):
        command = self.assistant.listen(timeout=5, phrase_time_limit=8, show_prompt=True)
        if not command:
            self.root.after(0, lambda: self._set_status("No voice input captured."))
            return
        self.root.after(0, lambda: self._append_log(f"You (voice): {command}"))
        self._process_command(command)

    def _process_command(self, command: str):
        should_continue = self.assistant.process_command(command)
        if should_continue:
            self.root.after(0, lambda: self._set_status("Task completed."))
        else:
            self.root.after(0, lambda: self._set_status("Assistant closed."))
            self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    # You can change the wake word here
    assistant = PersonalAssistant(name="Personal Assistant", wake_word="hey assistant")
    assistant.launch_gui()