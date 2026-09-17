Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\eullon.silva\.gemini\antigravity\scratch\voice_notes_app"
WshShell.Run "pythonw.exe main.py", 0, False
Set WshShell = Nothing
