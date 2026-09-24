Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = dir
pythonExe = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonExe) Then
  pythonExe = "pythonw.exe"  ' falls back to pythonw on PATH
End If
shell.Run """" & pythonExe & """ """ & dir & "\app.py""", 0, False
