import os
import sys
import atexit
import time
import json
import logging
from urllib.parse import urlparse
from typing import Optional

import yt_dlp
import requests
from bs4 import BeautifulSoup
import keyboard
import pystray
import pyperclip
import threading

from PIL import Image
import subprocess


def get_base_folder() -> str:
    """Returns the folder where persistent files should be stored."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name: str) -> str:
    """Resolve resource path for bundled executables."""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, name)  # type: ignore[attr-defined]
    return os.path.join(get_base_folder(), name)


# === Пути и файлы ===
BASE_FOLDER = get_base_folder()
DOWNLOAD_LIST = os.path.join(BASE_FOLDER, 'download-list.txt')
CONFIG_FILE = os.path.join(BASE_FOLDER, 'config.json')
LOG_FILE = os.path.join(BASE_FOLDER, 'script.log')
INFO_FILE = resource_path('info.txt')

# Эти переменные инициализируются после загрузки конфигурации
DOWNLOADS_FOLDER = os.path.join(BASE_FOLDER, 'Downloads')
VIDEOS_FOLDER = os.path.join(DOWNLOADS_FOLDER, 'Videos')
PLAYLIST_FOLDER = os.path.join(VIDEOS_FOLDER, 'Playlist Videos')
PICTURES_FOLDER = os.path.join(DOWNLOADS_FOLDER, 'Pictures')

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# Флаг, указывающий выполняется ли сейчас скачивание
downloading = threading.Event()

# Изображения для разных состояний значка
ICON_DEFAULT = None
ICON_ACTIVE = None
ICON_DOWNLOADING = None

def flash_tray_icon(icon: pystray.Icon, image: Image.Image, duration: float = 0.3) -> None:
    """Temporarily change the tray icon."""
    if not icon or not image:
        return
    current = icon.icon
    try:
        icon.icon = image
    except Exception:
        return

    def restore() -> None:
        try:
            icon.icon = current
        except Exception:
            pass

    threading.Timer(duration, restore).start()


DEFAULT_CONFIG = {
    'add_hotkey': 'ctrl+space',
    'download_hotkey': 'ctrl+shift+space',
}


def ensure_directories() -> None:
    """Создаёт директории для загрузок."""
    os.makedirs(VIDEOS_FOLDER, exist_ok=True)
    os.makedirs(PLAYLIST_FOLDER, exist_ok=True)
    os.makedirs(PICTURES_FOLDER, exist_ok=True)

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            logging.error('Ошибка загрузки конфигурации: %s', e)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error('Ошибка сохранения конфигурации: %s', e)


def ensure_single_instance() -> None:
    """Предотвращает запуск нескольких экземпляров скрипта."""
    if sys.platform.startswith('win'):
        import msvcrt
        lock_path = os.path.join(BASE_FOLDER, 'script.lock')
        lock_file = open(lock_path, 'w')
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            logging.info('Попытка запуска второго экземпляра.')
            print('Скрипт уже запущен.')
            sys.exit(0)

        def release_lock() -> None:
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                lock_file.close()
                os.remove(lock_path)
            except Exception:
                pass
            logging.info('Lock file released.')

        atexit.register(release_lock)


def download_video(url, folder):
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logging.error('Ошибка при скачивании YouTube-содержимого: %s', e)
        print(f"Ошибка при скачивании YouTube-содержимого: {e}")


def download_playlist(url, folder):
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': False,
        'no_warnings': True,
        'yes_playlist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logging.error('Ошибка при скачивании плейлиста: %s', e)
        print(f"Ошибка при скачивании плейлиста: {e}")


def download_pinterest_image(url, folder):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            img_url = img_tag['src']
            print(f"Скачиваем изображение: {img_url}")
            img_data = requests.get(img_url).content
            filename = os.path.join(folder, os.path.basename(img_url.split("?")[0]))
            with open(filename, 'wb') as f:
                f.write(img_data)
            print(f"Изображение сохранено как: {filename}")
        else:
            print("Не удалось найти изображение на странице Pinterest.")
    except Exception as e:
        logging.error('Ошибка при скачивании изображения с Pinterest: %s', e)
        print(f"Ошибка при скачивании изображения с Pinterest: {e}")


def handle_url(url: str) -> None:
    """Определяет тип ссылки и запускает скачивание."""
    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()

    if "youtube.com/playlist" in url:
        logging.info('Скачиваем плейлист: %s', url)
        print(f"Это плейлист YouTube. Скачиваем всё в: {PLAYLIST_FOLDER}")
        download_playlist(url, PLAYLIST_FOLDER)

    elif "youtube.com" in hostname or "youtu.be" in hostname:
        logging.info('Скачиваем видео: %s', url)
        print(f"Это видео YouTube. Скачиваем в: {VIDEOS_FOLDER}")
        download_video(url, VIDEOS_FOLDER)

    elif "pinterest.com" in hostname:
        logging.info('Скачиваем изображение Pinterest: %s', url)
        print("Это Pinterest ссылка. Пытаемся скачать...")
        download_pinterest_image(url, PICTURES_FOLDER)

    else:
        logging.warning('Неизвестная ссылка: %s', url)
        print("Сайт не поддерживается этим скриптом.")


def download_all(icon: Optional[pystray.Icon] = None) -> None:
    """Скачивает все ссылки из файла download-list.txt в отдельном потоке."""
    if downloading.is_set():
        print("Скачивание уже выполняется.")
        return

    # —————— Смена иконки на dw.ico ——————
    if icon is not None:
        try:
            icon.icon = Image.open(resource_path('dw.ico'))
        except Exception:
            pass

    def worker() -> None:
        try:
            if not os.path.exists(DOWNLOAD_LIST):
                print("Файл download-list.txt не найден.")
                return

            with open(DOWNLOAD_LIST, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]

            if not urls:
                print("Список ссылок пуст.")
                return

            for url in urls:
                handle_url(url)

            open(DOWNLOAD_LIST, 'w', encoding='utf-8').close()
            print("Скачивание завершено!")
            if icon is not None:
                try:
                    icon.notify('Complete', 'Скачивание завершено')
                except Exception:
                    pass

        finally:
            downloading.clear()
            # —————— Возврат иконки ico.ico ——————
            if icon is not None:
                try:
                    icon.icon = Image.open(resource_path('ico.ico'))
                except Exception:
                    pass

    downloading.set()
    threading.Thread(target=worker, daemon=True).start()



def add_link_from_clipboard() -> None:
    """Copy the current selection and append it to download-list.txt."""
    # Clear clipboard and send Ctrl+C to copy the highlighted text. Waiting
    # a short moment ensures the clipboard is updated before reading it.
    pyperclip.copy('')
    keyboard.press_and_release('ctrl+c')
    time.sleep(0.2)
    url = pyperclip.paste().strip()
    if not url:
        print("Не удалось скопировать ссылку. Возможно, она не выделена.")
        return

    existing = []
    if os.path.exists(DOWNLOAD_LIST):
        with open(DOWNLOAD_LIST, 'r', encoding='utf-8') as f:
            existing = [line.strip() for line in f if line.strip()]

    if url in existing:
        logging.info('Дубликат ссылки: %s', url)
        print('Ссылка уже присутствует в списке.')
        return

    with open(DOWNLOAD_LIST, 'a', encoding='utf-8') as f:
        f.write(url + '\n')
    print(f"Добавлено в список: {url}")


def main() -> None:
    """Запускает горячие клавиши и значок в трее."""
    ensure_single_instance()
    config = load_config()
    ensure_directories()
    if not os.path.exists(DOWNLOAD_LIST):
        open(DOWNLOAD_LIST, 'a', encoding='utf-8').close()

    add_hotkey = config.get('add_hotkey', DEFAULT_CONFIG['add_hotkey'])
    download_hotkey = config.get('download_hotkey', DEFAULT_CONFIG['download_hotkey'])

    # Функция-обёртка для добавления ссылки + смена иконки act.ico
    def on_add(icon: pystray.Icon):
        try:
            icon.icon = Image.open(resource_path('act.ico'))
        except Exception:
            pass

        add_link_from_clipboard()

        try:
            icon.icon = Image.open(resource_path('ico.ico'))
        except Exception:
            pass

    # Меняем горячую клавишу
    def change_hotkey(icon, item):
        icon.notify('Настройка', 'Нажмите новое сочетание и Enter')
        keyboard.unhook_all_hotkeys()
        try:
            new_key = keyboard.read_hotkey()
            if new_key:
                config['add_hotkey'] = new_key
                save_config(config)
                icon.notify('Готово', f'Новая клавиша: {new_key}')
        except Exception as e:
            logging.error('Ошибка смены горячей клавиши: %s', e)
        finally:
            # Восстанавливаем привязки
            keyboard.add_hotkey(config['add_hotkey'], lambda: on_add(icon))
            keyboard.add_hotkey(config['download_hotkey'], lambda: download_all(icon))

    # Меню «Скачать»
    def on_download(icon, item):
        download_all(icon)

    # Выход
    def on_exit(icon, item):
        icon.stop()

    # Открыть список загрузок
    def open_list(icon, item):
        try:
            if sys.platform.startswith('win'):
                os.startfile(DOWNLOAD_LIST)
            else:
                subprocess.Popen(['xdg-open', DOWNLOAD_LIST])
        except Exception as e:
            logging.error('Не удалось открыть файл со списком: %s', e)

    # Открыть папку загрузок
    def open_folder(icon, item):
        try:
            if sys.platform.startswith('win'):
                os.startfile(DOWNLOADS_FOLDER)
            else:
                subprocess.Popen(['xdg-open', DOWNLOADS_FOLDER])
        except Exception as e:
            logging.error('Не удалось открыть папку загрузок: %s', e)

    # Информация
    def show_info(icon, item):
        try:
            if os.path.exists(INFO_FILE):
                if sys.platform.startswith('win'):
                    os.startfile(INFO_FILE)
                else:
                    subprocess.Popen(['xdg-open', INFO_FILE])
            else:
                icon.notify('Информация', 'Файл info.txt не найден')
        except Exception as e:
            logging.error('Не удалось открыть info.txt: %s', e)

    # Составляем меню
    menu = pystray.Menu(
        pystray.MenuItem('Скачать', on_download),
        pystray.MenuItem('Список загрузок', open_list),
        pystray.MenuItem('Открыть папку для загрузки', open_folder),
        pystray.MenuItem('Горячие клавиши', change_hotkey),
        pystray.MenuItem('Инфо', show_info),
        pystray.MenuItem('Выход', on_exit),
    )

    # Иконка в трее
    icon_path = resource_path('ico.ico')
    image = Image.open(icon_path) if os.path.exists(icon_path) else None
    tray_icon = pystray.Icon('YTDownloader', image, 'YT Downloader', menu)

    # Привязка горячих клавиш
    keyboard.add_hotkey(add_hotkey, lambda: on_add(tray_icon))
    keyboard.add_hotkey(download_hotkey, lambda: download_all(tray_icon))

    print(f"Значок размещён в трее. Горячие клавиши {add_hotkey} и {download_hotkey} активны.")
    tray_icon.run()
    keyboard.unhook_all_hotkeys()
    print('Скрипт завершён.')

if __name__ == '__main__':
    main()