param(
    [string]$IconPath = ""
)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5.1 reads a UTF-8 script without a BOM using the active
# ANSI code page.  Build this default path from Unicode code points so the
# project file remains portable UTF-8 and the Japanese icon path cannot garble.
if ([string]::IsNullOrWhiteSpace($IconPath)) {
    $artworkDirectory = "D:\" + [char]0x4F5C + [char]0x54C1 + "\JPBL"
    $iconFileName = "JPBL" + [char]0x30ED + [char]0x30B4 + [char]0x767D + [char]0x67A0 + [char]0x3042 + [char]0x308A + ".png"
    $IconPath = Join-Path -Path $artworkDirectory -ChildPath $iconFileName
}

if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
    throw "Icon file was not found: $IconPath"
}

& .\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "JPBL PowerPro Importer" `
    --icon $IconPath `
    --add-data "config\batter_screen_regions.json;config" `
    --add-data "config\pitcher_screen_regions.json;config" `
    --add-data "runtime;runtime" `
    --collect-all paddleocr `
    --collect-all paddlex `
    --collect-all paddle `
    --collect-all bidi `
    --collect-all cv2 `
    --collect-all pypdfium2 `
    --collect-all qfluentwidgets `
    --copy-metadata python-bidi `
    --copy-metadata opencv-contrib-python `
    --copy-metadata pypdfium2 `
    main.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

Write-Host "Build complete: dist\JPBL PowerPro Importer\JPBL PowerPro Importer.exe"
