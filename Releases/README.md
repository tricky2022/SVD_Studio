# Releases

`build-exe.bat` builds a one-file Windows executable with the application icon:

```bat
build-exe.bat
```

Output:

```text
Releases/SVDStudio.exe
```

Requirements are installed automatically (`pyinstaller`, `pillow`).
The bundle includes Qt UI files, QSS themes and icons, and hides the console
(`console=False`) so the app runs as a normal desktop program.
