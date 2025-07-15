import subprocess
import sys
import os


def main() -> None:
    """Run package check and build the executable."""
    # Run dependency check
    result = subprocess.run([sys.executable, 'check_packages.py'])
    if result.returncode != 0:
        input('Ошибки при проверке зависимостей. Нажмите Enter для выхода...')
        return

    sep = ';' if os.name == 'nt' else ':'
    cmd = [
        'pyinstaller',
        '--onefile',
        '--windowed',
        '--icon=ico.ico',
        f'--add-data=ico.ico{sep}.',
        f'--add-data=act.ico{sep}.',
        f'--add-data=dw.ico{sep}.',
        f'--add-data=info.txt{sep}.',
        'main_windows_strict.py',
    ]
    build = subprocess.run(cmd)
    if build.returncode == 0:
        input('Сборка завершена успешно. Нажмите Enter для выхода...')
    else:
        input('Ошибка сборки. Нажмите Enter для выхода...')


if __name__ == '__main__':
    main()