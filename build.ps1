# Сборка QuickAssist.exe (папка dist\QuickAssist). Запускать из корня проекта в PowerShell:
#   .\.venv\Scripts\Activate.ps1
#   pip install -r requirements-dev.txt
#   .\build.ps1
$ErrorActionPreference = "Stop"

$args = @(
  "--noconfirm", "--clean", "--windowed",
  "--name", "QuickAssist",
  "--collect-submodules", "keyring.backends",
  "--hidden-import", "keyring.backends.Windows",
  "--collect-submodules", "anthropic"
)

# Windows OCR включается в сборку, только если пакеты установлены.
python -c "import winrt.windows.media.ocr" 2>$null
if ($LASTEXITCODE -eq 0) {
  Write-Host "Windows OCR найден — добавляю в сборку"
  $args += @("--collect-submodules", "winrt")
} else {
  Write-Host "Windows OCR не установлен — сборка без него (OCR через ИИ останется доступен)"
}

python -m PyInstaller @args run.pyw
Write-Host "Готово: dist\QuickAssist\QuickAssist.exe"
