"""
Weather Forecast Application
A modern Tkinter GUI app using the OpenWeatherMap API.
"""

import io
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = "dd70759a264ca77ffcda238d9873bf82"  # <-- Replace with your OpenWeatherMap API key
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
ICON_URL = "https://openweathermap.org/img/wn/{icon}@2x.png"
HISTORY_FILE = "search_history.json"
MAX_HISTORY = 10

# Optional Pillow for icon rendering
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
THEMES = {
    "light": {
        "bg": "#f4f6fb", "fg": "#1a1a2e", "card": "#ffffff",
        "accent": "#4f6df5", "muted": "#6b7280", "entry_bg": "#ffffff",
        "btn_fg": "#ffffff", "border": "#e5e7eb",
    },
    "dark": {
        "bg": "#0f172a", "fg": "#f1f5f9", "card": "#1e293b",
        "accent": "#6366f1", "muted": "#94a3b8", "entry_bg": "#1e293b",
        "btn_fg": "#ffffff", "border": "#334155",
    },
}


class WeatherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Weather Forecast")
        self.root.geometry("520x680")
        self.root.minsize(480, 640)

        self.theme_name = "light"
        self.history = self.load_history()
        self.current_icon_image = None
        self.loading = False
        self._spinner_after = None

        self.build_ui()
        self.apply_theme()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build_ui(self):
        # Top bar
        self.top_frame = tk.Frame(self.root)
        self.top_frame.pack(fill="x", padx=20, pady=(20, 10))

        self.title_label = tk.Label(self.top_frame, text="🌤  Weather",
                                    font=("Segoe UI", 20, "bold"))
        self.title_label.pack(side="left")

        self.theme_btn = tk.Button(self.top_frame, text="🌙", width=3,
                                   font=("Segoe UI", 12), relief="flat",
                                   command=self.toggle_theme, cursor="hand2")
        self.theme_btn.pack(side="right")

        # Search row
        self.search_frame = tk.Frame(self.root)
        self.search_frame.pack(fill="x", padx=20, pady=10)

        self.city_var = tk.StringVar()
        self.city_entry = tk.Entry(self.search_frame, textvariable=self.city_var,
                                   font=("Segoe UI", 12), relief="flat", bd=0)
        self.city_entry.pack(side="left", fill="x", expand=True,
                             ipady=10, ipadx=10)
        self.city_entry.bind("<Return>", lambda e: self.search_weather())

        self.search_btn = tk.Button(self.search_frame, text="Search",
                                    font=("Segoe UI", 11, "bold"),
                                    relief="flat", cursor="hand2", bd=0,
                                    padx=18, pady=8,
                                    command=self.search_weather)
        self.search_btn.pack(side="left", padx=(8, 0))

        self.refresh_btn = tk.Button(self.search_frame, text="⟳",
                                     font=("Segoe UI", 13, "bold"),
                                     relief="flat", cursor="hand2", bd=0,
                                     padx=12, pady=6,
                                     command=self.refresh)
        self.refresh_btn.pack(side="left", padx=(6, 0))

        # Status / loading
        self.status_label = tk.Label(self.root, text="",
                                     font=("Segoe UI", 10))
        self.status_label.pack(pady=(0, 4))

        # Weather card
        self.card = tk.Frame(self.root, bd=0, highlightthickness=1)
        self.card.pack(fill="x", padx=20, pady=10)

        self.icon_label = tk.Label(self.card)
        self.icon_label.pack(pady=(20, 0))

        self.city_label = tk.Label(self.card, text="—",
                                   font=("Segoe UI", 18, "bold"))
        self.city_label.pack(pady=(6, 0))

        self.temp_label = tk.Label(self.card, text="--°C",
                                   font=("Segoe UI", 44, "bold"))
        self.temp_label.pack(pady=(4, 0))

        self.cond_label = tk.Label(self.card, text="",
                                   font=("Segoe UI", 12))
        self.cond_label.pack(pady=(0, 16))

        # Details grid
        self.details_frame = tk.Frame(self.card)
        self.details_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.detail_vars = {
            "Feels Like": tk.StringVar(value="--"),
            "Humidity":   tk.StringVar(value="--"),
            "Wind":       tk.StringVar(value="--"),
            "Pressure":   tk.StringVar(value="--"),
        }
        self.detail_widgets = []
        for i, (label, var) in enumerate(self.detail_vars.items()):
            cell = tk.Frame(self.details_frame)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            self.details_frame.grid_columnconfigure(i % 2, weight=1)

            t = tk.Label(cell, text=label, font=("Segoe UI", 9))
            t.pack(anchor="w")
            v = tk.Label(cell, textvariable=var, font=("Segoe UI", 13, "bold"))
            v.pack(anchor="w")
            self.detail_widgets.append((cell, t, v))

        # History section
        self.history_header = tk.Label(self.root, text="Recent Searches",
                                       font=("Segoe UI", 11, "bold"))
        self.history_header.pack(anchor="w", padx=22, pady=(10, 4))

        self.history_frame = tk.Frame(self.root)
        self.history_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.history_list = tk.Listbox(self.history_frame, font=("Segoe UI", 10),
                                       relief="flat", bd=0, activestyle="none",
                                       highlightthickness=1)
        self.history_list.pack(fill="both", expand=True)
        self.history_list.bind("<Double-Button-1>", self.on_history_click)
        self.refresh_history_view()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def apply_theme(self):
        t = THEMES[self.theme_name]
        self.root.configure(bg=t["bg"])

        for widget in [self.top_frame, self.search_frame,
                       self.details_frame, self.history_frame]:
            widget.configure(bg=t["bg"])

        self.title_label.configure(bg=t["bg"], fg=t["fg"])
        self.status_label.configure(bg=t["bg"], fg=t["muted"])
        self.history_header.configure(bg=t["bg"], fg=t["fg"])

        self.theme_btn.configure(bg=t["card"], fg=t["fg"],
                                 activebackground=t["card"],
                                 text="☀" if self.theme_name == "dark" else "🌙")

        self.city_entry.configure(bg=t["entry_bg"], fg=t["fg"],
                                  insertbackground=t["fg"],
                                  highlightthickness=1,
                                  highlightbackground=t["border"],
                                  highlightcolor=t["accent"])
        self.search_btn.configure(bg=t["accent"], fg=t["btn_fg"],
                                  activebackground=t["accent"],
                                  activeforeground=t["btn_fg"])
        self.refresh_btn.configure(bg=t["card"], fg=t["fg"],
                                   activebackground=t["card"])

        self.card.configure(bg=t["card"], highlightbackground=t["border"],
                            highlightcolor=t["border"])
        for w in (self.icon_label, self.city_label, self.temp_label, self.cond_label):
            w.configure(bg=t["card"], fg=t["fg"])
        self.cond_label.configure(fg=t["muted"])

        for cell, lbl, val in self.detail_widgets:
            cell.configure(bg=t["card"])
            lbl.configure(bg=t["card"], fg=t["muted"])
            val.configure(bg=t["card"], fg=t["fg"])

        self.history_list.configure(bg=t["card"], fg=t["fg"],
                                    selectbackground=t["accent"],
                                    selectforeground=t["btn_fg"],
                                    highlightbackground=t["border"])

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.apply_theme()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def load_history(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def add_history(self, city):
        city = city.strip().title()
        if not city:
            return
        if city in self.history:
            self.history.remove(city)
        self.history.insert(0, city)
        self.history = self.history[:MAX_HISTORY]
        self.save_history()
        self.refresh_history_view()

    def refresh_history_view(self):
        self.history_list.delete(0, tk.END)
        if not self.history:
            self.history_list.insert(tk.END, "  No recent searches")
        else:
            for c in self.history:
                self.history_list.insert(tk.END, f"  {c}")

    def on_history_click(self, _event):
        sel = self.history_list.curselection()
        if not sel or not self.history:
            return
        city = self.history_list.get(sel[0]).strip()
        if city and city != "No recent searches":
            self.city_var.set(city)
            self.search_weather()

    # ------------------------------------------------------------------
    # Loading animation
    # ------------------------------------------------------------------
    def start_loading(self, msg="Loading"):
        self.loading = True
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx = 0
        self._spinner_msg = msg
        self._tick_spinner()

    def _tick_spinner(self):
        if not self.loading:
            return
        frame = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
        self.status_label.configure(text=f"{frame}  {self._spinner_msg}...")
        self._spinner_idx += 1
        self._spinner_after = self.root.after(90, self._tick_spinner)

    def stop_loading(self, msg=""):
        self.loading = False
        if self._spinner_after:
            self.root.after_cancel(self._spinner_after)
            self._spinner_after = None
        self.status_label.configure(text=msg)

    # ------------------------------------------------------------------
    # Network / search
    # ------------------------------------------------------------------
    def search_weather(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showwarning("Input required", "Please enter a city name.")
            return
        if API_KEY == "YOUR_API_KEY_HERE" or not API_KEY:
            messagebox.showerror(
                "API key missing",
                "Please set your OpenWeatherMap API key in main.py (API_KEY).")
            return

        self.start_loading(f"Fetching weather for {city}")
        threading.Thread(target=self._fetch_weather, args=(city,), daemon=True).start()

    def refresh(self):
        city = self.city_label.cget("text")
        if city and city != "—":
            self.city_var.set(city)
            self.search_weather()
        elif self.history:
            self.city_var.set(self.history[0])
            self.search_weather()
        else:
            messagebox.showinfo("Refresh", "Search a city first.")

    def _fetch_weather(self, city):
        try:
            url = f"{BASE_URL}?q={quote(city)}&appid={API_KEY}&units=metric"
            req = Request(url, headers={"User-Agent": "WeatherApp/1.0"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            icon_bytes = None
            icon_code = data.get("weather", [{}])[0].get("icon")
            if icon_code and PIL_AVAILABLE:
                try:
                    with urlopen(ICON_URL.format(icon=icon_code), timeout=10) as r:
                        icon_bytes = r.read()
                except Exception:
                    icon_bytes = None
            self.root.after(0, self._update_ui, data, icon_bytes)
        except HTTPError as e:
            msg = "City not found." if e.code == 404 else f"HTTP error: {e.code}"
            self.root.after(0, self._show_error, msg)
        except URLError:
            self.root.after(0, self._show_error,
                            "Network error. Check your internet connection.")
        except Exception as e:
            self.root.after(0, self._show_error, f"Unexpected error: {e}")

    def _update_ui(self, data, icon_bytes):
        self.stop_loading("")
        try:
            name = f"{data['name']}, {data.get('sys', {}).get('country', '')}".strip(", ")
            main = data["main"]
            weather = data["weather"][0]
            wind = data.get("wind", {})

            self.city_label.configure(text=name)
            self.temp_label.configure(text=f"{round(main['temp'])}°C")
            self.cond_label.configure(text=weather["description"].title())
            self.detail_vars["Feels Like"].set(f"{round(main['feels_like'])}°C")
            self.detail_vars["Humidity"].set(f"{main['humidity']}%")
            self.detail_vars["Wind"].set(f"{wind.get('speed', 0)} m/s")
            self.detail_vars["Pressure"].set(f"{main['pressure']} hPa")

            if icon_bytes and PIL_AVAILABLE:
                img = Image.open(io.BytesIO(icon_bytes))
                self.current_icon_image = ImageTk.PhotoImage(img)
                self.icon_label.configure(image=self.current_icon_image, text="")
            else:
                emoji = self._emoji_for(weather.get("main", ""))
                self.icon_label.configure(image="", text=emoji,
                                          font=("Segoe UI Emoji", 56))
                self.apply_theme()

            self.add_history(data["name"])
        except KeyError:
            self._show_error("Unexpected response from server.")

    def _show_error(self, msg):
        self.stop_loading("")
        messagebox.showerror("Error", msg)

    @staticmethod
    def _emoji_for(main):
        return {
            "Clear": "☀️", "Clouds": "☁️", "Rain": "🌧️", "Drizzle": "🌦️",
            "Thunderstorm": "⛈️", "Snow": "❄️", "Mist": "🌫️", "Fog": "🌫️",
            "Haze": "🌫️", "Smoke": "🌫️",
        }.get(main, "🌤️")


def main():
    root = tk.Tk()
    WeatherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
