@echo off
set CSC_PATH=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe

if not exist "%CSC_PATH%" (
    echo "CSC.exe not found at %CSC_PATH%. Trying 32-bit..."
    set CSC_PATH=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe
)

if not exist "%CSC_PATH%" (
    echo "Error: csc.exe not found. Please ensure .NET Framework is installed."
    pause
    exit /b 1
)

echo Found csc.exe at %CSC_PATH%
echo Compiling SC2Overlay.cs...

"%CSC_PATH%" /target:winexe /out:SC2Overlay.exe /r:System.Web.Extensions.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll SC2Overlay.cs

if %errorlevel% neq 0 (
    echo Compilation failed!
    exit /b 1
)

echo Compilation successful! SC2Overlay.exe created.
echo You can now run SC2Overlay.exe
pause
