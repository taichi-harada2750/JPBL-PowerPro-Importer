$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath "assets\icon.ico" -PathType Leaf)) {
    throw "Icon file was not found: assets\icon.ico"
}

& .\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "JPBL PowerPro Importer" `
    --icon "assets\icon.ico" `
    --version-file "version_info.txt" `
    --add-data "assets\icon.ico;assets" `
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
