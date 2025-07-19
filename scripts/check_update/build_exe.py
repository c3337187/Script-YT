import os
import sys
import subprocess
import importlib.util

REQUIRED = {
    'yt_dlp': 'yt_dlp',
    'pyperclip': 'pyperclip',
    'requests': 'requests',
    'bs4': 'beautifulsoup4',
    'pystray': 'pystray',
    'keyboard': 'keyboard',
    'PIL': 'pillow',
    'win32api': 'pywin32',
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
os.chdir(ROOT_DIR)


def check_packages() -> bool:
    """Install missing dependencies."""
    installed_new = False
    for module, package in REQUIRED.items():
        if package == 'pywin32' and not sys.platform.startswith('win'):
            continue
        if importlib.util.find_spec(module) is None:
            print(f"Installing {package}...")
            try:
                subprocess.check_call([
                    sys.executable,
                    '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                    package,
                ])
                installed_new = True
            except subprocess.CalledProcessError:
                return False
    if installed_new:
        print('All packages installed.')
    else:
        print('All packages already present.')
    return True


def compile_sources(paths: list[str]) -> bool:
    for p in paths:
        if subprocess.run([sys.executable, '-m', 'py_compile', p]).returncode != 0:
            return False
    return True


def build_executable(script: str) -> bool:
    sep = ';' if os.name == 'nt' else ':'
    cmd = [
        'pyinstaller',
        '--noconfirm',
        '--onefile',
        '--windowed',
        f'--icon=ico/ico.ico',
        f'--add-data=ico{sep}ico',
        f'--add-data=system{sep}system',
        script,
    ]
    return subprocess.run(cmd).returncode == 0


def main() -> None:
    if not check_packages():
        input('Dependency check failed. Press Enter to exit...')
        return
    scripts = ['scripts/gui_downloader.py', 'scripts/main_windows_strict.py']
    if not compile_sources(scripts):
        input('Compilation failed. Press Enter to exit...')
        return
    for sc in scripts:
        if not build_executable(sc):
            input(f'Build failed for {sc}. Press Enter to exit...')
            return
    input('Build completed successfully. Press Enter to exit...')


if __name__ == '__main__':
    main()
