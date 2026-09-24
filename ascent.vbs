Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = dir
pythonExe = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonExe) Then
  pythonExe = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\pythonw.exe")
End If
shell.Run """" & pythonExe & """ """ & dir & "\app.py""", 0, False
