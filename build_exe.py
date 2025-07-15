import os
import subprocess
import sys


def main() -> None:
    """Check dependencies, compile sources and build the executable."""
    if subprocess.run([sys.executable, 'check_packages.py']).returncode != 0:
        input('Ошибки при проверке зависимостей. Нажмите Enter для выхода...')
        return

    # Abort if syntax errors are found
    if subprocess.run([sys.executable, '-m', 'py_compile', 'gui_downloader.py']).returncode != 0:
        input('Ошибки при компиляции. Нажмите Enter для выхода...')
        return

    sep = ';' if os.name == 'nt' else ':'
    cmd = [
        'pyinstaller',
        '--noconfirm',
        '--onefile',
        '--windowed',
        '--icon=ico.ico',
        f'--add-data=ico.ico{sep}.',
        f'--add-data=act.ico{sep}.',
        f'--add-data=dw.ico{sep}.',
        f'--add-data=config.json{sep}.',
        'gui_downloader.py',
    ]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        input('Сборка завершена успешно. Нажмите Enter для выхода...')
    else:
        input('Ошибка сборки. Нажмите Enter для выхода...')


if __name__ == '__main__':
    main()
