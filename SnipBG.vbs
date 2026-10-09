' Launches SnipBG with no console window. Pin this (or a shortcut to it) to your taskbar.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run ".venv\Scripts\pythonw.exe app.py", 0, False
