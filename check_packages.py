import sys
import subprocess
import importlib.util

required_packages = {
    'yt_dlp': 'yt_dlp',
    'pyperclip': 'pyperclip',
    'requests': 'requests',
    'bs4': 'beautifulsoup4',
    'pystray': 'pystray',
    'keyboard': 'keyboard',
    'PIL': 'pillow',
    'win32api': 'pywin32',
}

installed_new = False

for module, package in required_packages.items():
    if package == 'pywin32' and not sys.platform.startswith('win'):
        continue
    if importlib.util.find_spec(module) is None:
        print(f"Installing {package}...")
        subprocess.check_call([
            sys.executable,
            '-m',
            'pip',
            'install',
            '--quiet',
            '--disable-pip-version-check',
            package,
        ])
        installed_new = True

if installed_new:
    print("All packages installed.")
else:
    print("All packages already present.")
