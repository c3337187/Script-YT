
"""Minimalistic downloader using ``yt_dlp`` with optional GUI.

The script provides two modes of operation:

* **GUI mode** (default) based on Tkinter where users can manage a queue of
  URLs, select a download folder and configure hotkeys.
* **Headless mode** activated by ``--headless``. In this mode the program runs
  purely in the console which is useful for environments without a display
  server. Progress information is printed to stdout.

It stores settings in ``config.json`` next to the script and logs events to
``script.log``.
"""

from typing import List, Dict, Callable

import os
import sys
import json
import threading
import logging
import time
from typing import List, Dict


import yt_dlp
import pyperclip
import keyboard

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


BASE_FOLDER = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_FOLDER, 'config.json')
LOG_FILE = os.path.join(BASE_FOLDER, 'script.log')

DEFAULT_CONFIG = {
    'download_path': os.path.join(BASE_FOLDER, 'Downloads'),
    'add_hotkey': 'ctrl+space',
    'download_hotkey': 'ctrl+shift+space'
}

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def load_config() -> Dict[str, str]:

    """Return configuration dictionary merging defaults with ``config.json``.

    If the file is missing or broken the default configuration is returned and
    the error is logged.
    """

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cfg = {**DEFAULT_CONFIG, **data}
                return cfg
        except Exception as e:
            logging.error('Failed to load config: %s', e)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict[str, str]) -> None:

    """Write configuration dictionary to ``config.json``."""

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
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

    Hotkeys configured in ``config.json`` remain functional. Progress for each
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
        keyboard.add_hotkey(cfg['add_hotkey'], add_from_clipboard)
        keyboard.add_hotkey(cfg['download_hotkey'], start_downloads)
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
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass


class App(tk.Tk):
    """Graphical interface for managing the download queue."""


    def __init__(self) -> None:
        super().__init__()
        self.title('YT Downloader')
        self.resizable(False, False)

        self.cfg = load_config()
        ensure_download_dir(self.cfg['download_path'])

        self.links: List[str] = []
        self.create_widgets()
        self.register_hotkeys()

    def create_widgets(self) -> None:

        """Build all widgets for the interface."""
        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')

        # Path selection
        path_label = ttk.Label(frm, text='Path:')
        path_label.grid(row=0, column=0, sticky='w')

        self.path_var = tk.StringVar(value=self.cfg['download_path'])
        path_entry = ttk.Entry(frm, textvariable=self.path_var, width=40)
        path_entry.grid(row=0, column=1, sticky='we')

        path_btn = ttk.Button(frm, text='Select', command=self.choose_path)
        path_btn.grid(row=0, column=2, padx=5)

        # Hotkeys
        ttk.Label(frm, text='Add hotkey:').grid(row=1, column=0, sticky='w')
        self.add_hotkey_var = tk.StringVar(value=self.cfg['add_hotkey'])
        ttk.Entry(frm, textvariable=self.add_hotkey_var, width=20).grid(row=1, column=1, sticky='w')

        ttk.Label(frm, text='Download hotkey:').grid(row=2, column=0, sticky='w')
        self.download_hotkey_var = tk.StringVar(value=self.cfg['download_hotkey'])
        ttk.Entry(frm, textvariable=self.download_hotkey_var, width=20).grid(row=2, column=1, sticky='w')

        reserve_btn = ttk.Button(frm, text='Apply', command=self.apply_settings)
        reserve_btn.grid(row=1, column=2, rowspan=2, padx=5)

        # Queue list
        self.listbox = tk.Listbox(frm, width=60, height=10)
        self.listbox.grid(row=3, column=0, columnspan=3, pady=5)

        add_btn = ttk.Button(frm, text='Add from clipboard', command=self.add_from_clipboard)
        add_btn.grid(row=4, column=0, sticky='we', pady=2)

        remove_btn = ttk.Button(frm, text='Remove selected', command=self.remove_selected)
        remove_btn.grid(row=4, column=1, sticky='we', pady=2)

        clear_btn = ttk.Button(frm, text='Clear list', command=self.clear_list)
        clear_btn.grid(row=4, column=2, sticky='we', pady=2)

        start_btn = ttk.Button(frm, text='Start download', command=self.start_downloads)
        start_btn.grid(row=5, column=0, columnspan=3, sticky='we', pady=(10,2))

        self.progress = ttk.Progressbar(frm, length=400)
        self.progress.grid(row=6, column=0, columnspan=3, pady=2)

    def choose_path(self) -> None:
        """Show folder selection dialog and update path variable."""

        new_path = filedialog.askdirectory(initialdir=self.path_var.get())
        if new_path:
            self.path_var.set(new_path)

    def apply_settings(self) -> None:

        """Save settings and re-register hotkeys."""
        try:
            keyboard.unhook_all_hotkeys()
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
            keyboard.add_hotkey(self.cfg['add_hotkey'], self.add_from_clipboard)
            keyboard.add_hotkey(self.cfg['download_hotkey'], self.start_downloads)
        except Exception as e:
            logging.error('Failed to register hotkeys: %s', e)

    def add_from_clipboard(self) -> None:

        """Grab URL from clipboard and add it to the queue."""

        try:
            pyperclip.copy('')
            keyboard.press_and_release('ctrl+c')
            threading.Timer(0.2, self._read_clipboard).start()
        except Exception as e:
            logging.error('Clipboard error: %s', e)

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
        for idx, url in enumerate(list(self.links)):
            self.progress['value'] = 0
            try:
                download_url(url, folder, self._progress_hook)
            except Exception:
                messagebox.showerror('Error', f'Failed to download {url}')
            self.listbox.delete(0)
            self.links.pop(0)
        self.progress['value'] = 0
        messagebox.showinfo('Done', 'All downloads finished')

    def _progress_hook(self, d):

        """Update progress bar using ``yt_dlp`` progress hooks."""
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            percent = d['downloaded_bytes'] / total * 100
            self.progress['value'] = percent
            self.update_idletasks()


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
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

