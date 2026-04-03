import os
import winshell
from win32com.client import Dispatch

def create_startup_shortcut():
    # Путь к папке автозагрузки
    startup_path = winshell.startup()
    # Find the main.py correctly relative to project
    proj_dir = os.path.dirname(os.path.abspath(__file__))
    vbs_path = os.path.join(proj_dir, "run_whisper.vbs")
    # Имя ярлыка
    shortcut_name = "voysix.lnk"
    
    shortcut_path = os.path.join(startup_path, shortcut_name)
    
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = vbs_path
    shortcut.WorkingDirectory = proj_dir
    shortcut.IconLocation = "python.exe"
    shortcut.save()
    
    print(f"Ярлык успешно создан в: {shortcut_path}")
    print("Теперь скрипт будет запускаться автоматически при входе в систему.")

if __name__ == "__main__":
    create_startup_shortcut()
