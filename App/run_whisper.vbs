Set WinScriptHost = CreateObject("WScript.Shell")
' Запускаем скрипт через pythonw.exe (без консоли) из вашего venv
' Используем абсолютный путь к папке проекта (настраивается при установке или вручную)
WinScriptHost.Run "d:\Project\voysix\venv\Scripts\pythonw.exe d:\Project\voysix\App\main.py", 0
Set WinScriptHost = Nothing
