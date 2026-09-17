Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Eullon\Projeto Eullon\voice-tasks-app"
WshShell.Run "pythonw.exe main.py", 0, False
Set WshShell = Nothing
