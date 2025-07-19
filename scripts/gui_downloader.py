"""Minimalistic downloader using ``yt_dlp`` with optional GUI.

The script provides two modes of operation:

* **GUI mode** (default) based on Tkinter where users can manage a queue of
  URLs, select a download folder and configure hotkeys.
* **Headless mode** activated by ``--headless``. In this mode the program runs
  purely in the console which is useful for environments without a display
  server. Progress information is printed to stdout.

Settings are stored in ``config.ini`` inside the ``system`` folder and events
are logged to ``script.log``.
"""

from typing import List, Dict, Callable
import os
import sys
import configparser
import threading
import logging
import time
import subprocess

import yt_dlp
import pyperclip
import keyboard
try:
    import pystray
    from PIL import Image
except Exception:  # When display server is missing
    pystray = None  # type: ignore
    Image = None  # type: ignore
if os.name == 'nt':
    try:
        import win32con
        import win32api
        import win32gui
    except Exception:
        win32con = win32api = win32gui = None  # type: ignore
else:
    win32con = win32api = win32gui = None  # type: ignore

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
from cairosvg import svg2png


def get_root_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(folder) if os.path.basename(folder) == 'scripts' else folder

ROOT_DIR = get_root_dir()
SYSTEM_DIR = os.path.join(ROOT_DIR, 'system')
ICO_DIR = os.path.join(ROOT_DIR, 'ico')
CONFIG_FILE = os.path.join(SYSTEM_DIR, 'config.ini')
LOG_FILE = os.path.join(SYSTEM_DIR, 'script.log')


# Ensure the system directory exists for logs and config
os.makedirs(SYSTEM_DIR, exist_ok=True)

ICON_DEFAULT = os.path.join(ICO_DIR, 'ico.ico')
ICON_ACTIVE = os.path.join(ICO_DIR, 'act.ico')
ICON_DOWNLOAD = os.path.join(ICO_DIR, 'dw.ico')
ICONS_DIR = os.path.join(ICO_DIR, 'program_icons')
FONTS_DIR = os.path.join(ROOT_DIR, 'assets', 'fonts', 'static')
FONT_FAMILY = 'Roboto'

BG_COLOR = '#2b2b2b'
FG_COLOR = '#f0f0f0'
TEXT_COLOR = '#dddddd'
PROGRESS_EMPTY = '#555555'


def _shade(color: str, factor: float) -> str:
    """Return color darkened by ``factor`` (0-1)."""
    color = color.lstrip('#')
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f'#{r:02x}{g:02x}{b:02x}'


class HotkeyManager:
    """Cross-platform hotkey registration with fallback to ``keyboard``."""

    def __init__(self) -> None:
        self.ids: dict[int, Callable] = {}
        self._counter = 1
        self._loop_thread: threading.Thread | None = None

    def _parse_win(self, combo: str) -> tuple[int, int] | None:
        if not win32con:
            return None
        mods = 0
        key = None
        for part in combo.lower().split('+'):
            if part == 'ctrl':
                mods |= win32con.MOD_CONTROL
            elif part == 'alt':
                mods |= win32con.MOD_ALT
            elif part == 'shift':
                mods |= win32con.MOD_SHIFT
            elif part == 'win':
                mods |= win32con.MOD_WIN
            else:
                key = part
        if key is None:
            return None
        vk = getattr(win32con, f'VK_{key.upper()}', None)
        if vk is None:
            if len(key) == 1:
                vk = ord(key.upper())
            else:
                return None
        return mods, vk

    def _run_loop(self) -> None:
        if not win32gui:
            return
        while True:
            msg = win32gui.GetMessage(None, 0, 0)
            if not msg:
                break
            if msg[1][1] == win32con.WM_HOTKEY:
                hot_id = msg[1][2]
                cb = self.ids.get(hot_id)
                if cb:
                    cb()
            win32gui.TranslateMessage(msg[1])
            win32gui.DispatchMessage(msg[1])

    def register(self, combo: str, callback: Callable) -> None:
        if os.name == 'nt' and win32api:
            parsed = self._parse_win(combo)
            if parsed:
                mods, vk = parsed
                hot_id = self._counter
                self._counter += 1
                try:
                    if win32api.RegisterHotKey(None, hot_id, mods, vk):
                        self.ids[hot_id] = callback
                        if not self._loop_thread:
                            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
                            self._loop_thread.start()
                        return
                except Exception as e:
                    logging.error('Win32 hotkey failed: %s', e)
        keyboard.add_hotkey(combo, callback, suppress=True, trigger_on_release=True)

    def unregister_all(self) -> None:
        if os.name == 'nt' and win32api:
            for hot_id in list(self.ids):
                try:
                    win32api.UnregisterHotKey(None, hot_id)
                except Exception:
                    pass
            self.ids.clear()
        keyboard.unhook_all_hotkeys()


hotkey_manager = HotkeyManager()


def resource_path(*parts: str) -> str:
    """Resolve resource path for bundled executables."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = ROOT_DIR
    return os.path.join(base, *parts)


def load_svg_icon(name: str, size: int = 20) -> tk.PhotoImage:
    """Convert an SVG icon to ``PhotoImage``."""
    path = resource_path(ICONS_DIR, name)
    try:
        with open(path, 'rb') as f:
            data = f.read()
        png = svg2png(bytestring=data, output_width=size, output_height=size)
        return tk.PhotoImage(data=png)
    except Exception:
        return tk.PhotoImage()

DEFAULT_CONFIG = {
    'download_path': os.path.join(ROOT_DIR, 'Downloads'),
    'add_hotkey': 'ctrl+space',
    'download_hotkey': 'ctrl+shift+space'
}

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def load_config() -> Dict[str, str]:
    """Return configuration dictionary merging defaults with ``config.ini``.

    If the file is missing or broken the default configuration is returned and
    the error is logged.
    """
    parser = configparser.ConfigParser()
    if parser.read(CONFIG_FILE, encoding='utf-8'):
        try:
            data = dict(parser.items('hotkeys'))
            cfg = {**DEFAULT_CONFIG, **data}
            return cfg
        except Exception as e:
            logging.error('Failed to parse config: %s', e)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict[str, str]) -> None:
    """Write configuration dictionary to ``config.ini``."""
    parser = configparser.ConfigParser()
    parser['hotkeys'] = {
        'add_hotkey': cfg.get('add_hotkey', DEFAULT_CONFIG['add_hotkey']),
        'download_hotkey': cfg.get('download_hotkey', DEFAULT_CONFIG['download_hotkey'])
    }
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            parser.write(f)
    except Exception as e:
        logging.error('Failed to save config: %s', e)


def ensure_download_dir(path: str) -> None:
    """Create download directory if it does not exist."""
    os.makedirs(path, exist_ok=True)


def download_url(url: str, folder: str, progress_callback: Callable | None = None) -> None:
    """Download a single URL to *folder* using ``yt_dlp``.

    ``progress_callback`` is passed directly to the yt_dlp progress hook.
    Any exception from ``yt_dlp`` is logged and re-raised.
    """
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': True,
        'progress_hooks': [progress_callback] if progress_callback else None,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logging.error('Download error: %s', e)
        raise


def run_headless() -> None:
    """Run downloader in console-only mode.

    Hotkeys configured in ``config.ini`` remain functional. Progress for each
    download is printed to stdout. Use ``Ctrl+C`` to exit.
    """

    cfg = load_config()
    ensure_download_dir(cfg['download_path'])
    links: List[str] = []

    def read_clipboard() -> None:
        url = pyperclip.paste().strip()
        if url:
            links.append(url)
            print(f"Added: {url}")
            logging.info('Added URL: %s', url)
        else:
            print('Clipboard empty')

    def add_from_clipboard() -> None:
        try:
            pyperclip.copy('')
            keyboard.press_and_release('ctrl+c')
            threading.Timer(0.2, read_clipboard).start()
        except Exception as e:
            logging.error('Clipboard error: %s', e)

    def progress_hook(d) -> None:
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            percent = d['downloaded_bytes'] / total * 100
            print(f"\r{percent:5.1f}%", end='', flush=True)
        elif d['status'] == 'finished':
            print()

    def start_downloads() -> None:
        if not links:
            print('Queue is empty')
            return
        while links:
            url = links.pop(0)
            print(f'Downloading {url}')
            try:
                download_url(url, cfg['download_path'], progress_hook)
            except Exception:
                print(f'Failed to download {url}')

    try:
        hotkey_manager.register(cfg['add_hotkey'], add_from_clipboard)
        hotkey_manager.register(cfg['download_hotkey'], start_downloads)
    except Exception as e:
        logging.error('Failed to register hotkeys: %s', e)

    print('Headless mode active. Press Ctrl+C to exit.')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nExiting...')
    finally:
        try:
            hotkey_manager.unregister_all()
        except Exception:
            pass


class TrayController:
    """Manage system tray icon and menu."""

    def __init__(self, app: 'App') -> None:
        self.app = app
        if pystray and Image:
            self.icon = pystray.Icon(
                'YTDownloader',
                Image.open(resource_path('ico', 'ico.ico')),
                'YT Downloader',
                pystray.Menu(
                    pystray.MenuItem('Показать окно', self.show_app),
                    pystray.MenuItem('Скачать', self.on_download),
                    pystray.MenuItem('Открыть папку', self.open_folder),
                    pystray.MenuItem('Выход', self.on_exit),
                ),
            )
        else:
            self.icon = None

    def run(self) -> None:
        if self.icon:
            threading.Thread(target=self.icon.run, daemon=True).start()

    def flash(self, path: str, duration: float = 0.3) -> None:
        if not self.icon:
            return
        try:
            img = Image.open(resource_path(path))
        except Exception:
            return

        current = self.icon.icon
        self.icon.icon = img

        def restore() -> None:
            try:
                self.icon.icon = current
            except Exception:
                pass

        threading.Timer(duration, restore).start()

    def set_icon(self, path: str) -> None:
        if not self.icon:
            return
        try:
            self.icon.icon = Image.open(resource_path(path))
        except Exception:
            pass

    def show_app(self, icon, item) -> None:
        self.app.show_window()

    def on_download(self, icon, item) -> None:
        self.app.start_downloads()

    def open_folder(self, icon, item) -> None:
        folder = self.app.path_var.get()
        try:
            if sys.platform.startswith('win'):
                os.startfile(folder)
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            logging.error('Failed to open folder: %s', e)

    def on_exit(self, icon, item) -> None:
        if self.icon:
            self.icon.stop()
        self.app.safe_exit()

class App(tk.Tk):
    """Graphical interface for managing the download queue."""

    def __init__(self) -> None:
        super().__init__()
        self.title('YT Downloader')
        self.resizable(False, False)
        self.configure(bg=BG_COLOR)

        default_font = tkfont.nametofont('TkDefaultFont')
        default_font.configure(family=FONT_FAMILY)
        self.option_add('*Font', default_font)

        self.folder_icon = load_svg_icon('folder-solid.svg')
        self.add_icon = load_svg_icon('plus-solid.svg')
        self.trash_icon = load_svg_icon('trash-can-solid.svg')

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background=BG_COLOR)
        style.configure('TLabel', background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure('TButton', background=FG_COLOR, foreground=BG_COLOR)
        style.map('TButton', background=[('active', FG_COLOR)])

        self.cfg = load_config()
        ensure_download_dir(self.cfg['download_path'])

        self.links: List[str] = []
        self.tray = TrayController(self)
        self.tray.run()

        self.create_widgets()
        self.register_hotkeys()
        self.protocol('WM_DELETE_WINDOW', self.hide_window)

    def show_window(self) -> None:
        self.deiconify()

    def hide_window(self) -> None:
        self.withdraw()

    def safe_exit(self) -> None:
        try:
            hotkey_manager.unregister_all()
        except Exception:
            pass
        self.destroy()

    def create_widgets(self) -> None:
        """Build all widgets for the interface."""
        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')
        entry_opts = {
            'bd': 1,
            'relief': 'flat',
            'highlightthickness': 1,
            'highlightbackground': 'white',
            'highlightcolor': 'white',
            'bg': '#1a1a1a',
            'fg': 'white',
            'insertbackground': 'white',
        }

        def make_button(master, text, icon, color, cmd):
            btn = tk.Button(master, text=' ' + text, image=icon, compound='left',
                            command=cmd, bg=color, fg='white', activeforeground='white',
                            activebackground=_shade(color, 0.9), bd=0, relief='flat',
                            padx=10, pady=5)
            btn.bind('<Enter>', lambda e, b=btn, c=color: b.configure(bg=_shade(c, 0.9)))
            btn.bind('<Leave>', lambda e, b=btn, c=color: b.configure(bg=c))
            return btn

        # Path selection
        path_label = ttk.Label(frm, text='Путь:')
        path_label.grid(row=0, column=0, sticky='w')

        self.path_var = tk.StringVar(value=self.cfg['download_path'])
        path_entry = tk.Entry(frm, textvariable=self.path_var, width=40, **entry_opts)
        path_entry.grid(row=0, column=1, sticky='we')

        path_btn = make_button(frm, 'Выбрать', self.folder_icon, '#1E88E5', self.choose_path)
        path_btn.grid(row=0, column=2, padx=5)

        # Hotkeys
        ttk.Label(frm, text='Горячая клавиша добавления:').grid(row=1, column=0, sticky='w')
        self.add_hotkey_var = tk.StringVar(value=self.cfg['add_hotkey'])
        tk.Entry(frm, textvariable=self.add_hotkey_var, width=20, **entry_opts).grid(row=1, column=1, sticky='w')

        ttk.Label(frm, text='Горячая клавиша скачивания:').grid(row=2, column=0, sticky='w')
        self.download_hotkey_var = tk.StringVar(value=self.cfg['download_hotkey'])
        tk.Entry(frm, textvariable=self.download_hotkey_var, width=20, **entry_opts).grid(row=2, column=1, sticky='w')

        reserve_btn = make_button(frm, 'Применить', self.add_icon, '#388E3C', self.apply_settings)
        reserve_btn.grid(row=1, column=2, rowspan=2, padx=5)

        # Manual link entry
        ttk.Label(frm, text='Ссылка:').grid(row=3, column=0, sticky='w')
        self.link_var = tk.StringVar()
        tk.Entry(frm, textvariable=self.link_var, width=40, **entry_opts).grid(row=3, column=1, sticky='we')
        make_button(frm, 'Добавить', self.add_icon, '#388E3C', self.add_from_entry).grid(row=3, column=2, padx=5)

        # Queue list
        self.listbox = tk.Listbox(frm, width=60, height=10, bg=BG_COLOR, fg=TEXT_COLOR, highlightbackground=FG_COLOR, selectbackground=FG_COLOR, selectforeground=BG_COLOR)
        self.listbox.grid(row=4, column=0, columnspan=3, pady=5)
        add_btn = make_button(frm, 'Добавить из буфера', self.add_icon, '#388E3C', self.add_from_clipboard)
        add_btn.grid(row=5, column=0, sticky='we', pady=2)
        remove_btn = make_button(frm, 'Удалить выбранное', self.trash_icon, '#D32F2F', self.remove_selected)
        remove_btn.grid(row=5, column=1, sticky='we', pady=2)
        clear_btn = make_button(frm, 'Очистить список', self.trash_icon, '#616161', self.clear_list)
        clear_btn.grid(row=5, column=2, sticky='we', pady=2)
        start_btn = make_button(frm, 'Скачать', self.folder_icon, '#1E88E5', self.start_downloads)
        start_btn.grid(row=6, column=0, columnspan=3, sticky='we', pady=(10,2))

        self.progress_canvas = tk.Canvas(frm, width=120, height=30, bg=BG_COLOR, highlightthickness=0)
        self.progress_canvas.grid(row=7, column=0, columnspan=3, pady=2)
        self.progress_dots = []
        for i in range(4):
            x = 15 + i * 30
            self.progress_dots.append(
                self.progress_canvas.create_oval(
                    x-10, 10, x+10, 30,
                    outline=FG_COLOR, fill=PROGRESS_EMPTY
                )
            )

    def _update_progress(self, percent: float) -> None:
        filled = int(percent // 25)
        for i, dot in enumerate(self.progress_dots):
            color = FG_COLOR if i < filled else PROGRESS_EMPTY
            self.progress_canvas.itemconfig(dot, fill=color)
        self.update_idletasks()

    def choose_path(self) -> None:
        """Show folder selection dialog and update path variable."""
        new_path = filedialog.askdirectory(initialdir=self.path_var.get())
        if new_path:
            self.path_var.set(new_path)

    def apply_settings(self) -> None:
        """Save settings and re-register hotkeys."""
        try:
            hotkey_manager.unregister_all()
        except Exception:
            pass

        self.cfg['download_path'] = self.path_var.get()
        self.cfg['add_hotkey'] = self.add_hotkey_var.get() or DEFAULT_CONFIG['add_hotkey']
        self.cfg['download_hotkey'] = self.download_hotkey_var.get() or DEFAULT_CONFIG['download_hotkey']
        ensure_download_dir(self.cfg['download_path'])
        save_config(self.cfg)
        self.register_hotkeys()
        messagebox.showinfo('Hotkeys', 'Settings applied')

    def register_hotkeys(self) -> None:
        """Register global hotkeys for adding links and starting downloads."""
        try:
            hotkey_manager.register(self.cfg['add_hotkey'], self.add_from_clipboard)
            hotkey_manager.register(self.cfg['download_hotkey'], self.start_downloads)
        except Exception as e:
            logging.error('Failed to register hotkeys: %s', e)

    def add_from_clipboard(self) -> None:
        """Grab URL from clipboard and add it to the queue."""
        try:
            pyperclip.copy('')
            keyboard.press_and_release('ctrl+c')
            threading.Timer(0.2, self._read_clipboard).start()
            self.tray.flash('ico/act.ico')
        except Exception as e:
            logging.error('Clipboard error: %s', e)

    def add_from_entry(self) -> None:
        """Add URL from entry field to the queue."""
        url = self.link_var.get().strip()
        if not url:
            return
        self.links.append(url)
        self.listbox.insert(tk.END, url)
        self.link_var.set('')
        logging.info('Added URL manually: %s', url)

    def _read_clipboard(self) -> None:
        """Read clipboard contents and append to the listbox."""
        url = pyperclip.paste().strip()
        if url:
            self.links.append(url)
            self.listbox.insert(tk.END, url)
            logging.info('Added URL: %s', url)
        else:
            logging.info('Clipboard empty')

    def remove_selected(self) -> None:
        """Remove selected items from the queue."""
        sel = list(self.listbox.curselection())
        for i in reversed(sel):
            self.listbox.delete(i)
            del self.links[i]

    def clear_list(self) -> None:
        """Remove all URLs from the queue."""
        self.listbox.delete(0, tk.END)
        self.links.clear()

    def start_downloads(self) -> None:
        """Start background thread to download all queued URLs."""
        if not self.links:
            return
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self) -> None:
        """Worker thread that iterates over the queue and downloads each URL."""
        folder = self.path_var.get()
        self.tray.set_icon('ico/dw.ico')
        for idx, url in enumerate(list(self.links)):
            self._update_progress(0)
            try:
                download_url(url, folder, self._progress_hook)
            except Exception:
                messagebox.showerror('Error', f'Failed to download {url}')
            self.listbox.delete(0)
            self.links.pop(0)
        self._update_progress(0)
        self.tray.set_icon('ico/ico.ico')
        messagebox.showinfo('Done', 'All downloads finished')

    def _progress_hook(self, d):
        """Update progress bar using ``yt_dlp`` progress hooks."""
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            percent = d['downloaded_bytes'] / total * 100
            self._update_progress(percent)


if __name__ == '__main__':
    headless = '--headless' in sys.argv
    try:
        if headless:
            run_headless()
        else:
            app = App()
            app.mainloop()
    finally:
        try:
            hotkey_manager.unregister_all()
        except Exception:
            pass
