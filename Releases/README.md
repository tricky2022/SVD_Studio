# Releases

`build-exe.bat` builds the desktop and command-line programs. Run it from a
checkout with the `.venv` described in the project README.

```bat
build-exe.bat
```

Output:

```text
Releases/SVDStudio.exe
Releases/svdstudio-cli.exe
```

The build uses the checked-in application icon and includes the Qt UI files
and themes. Run `Releases\svdstudio-cli.exe --help` for command-line commands.
