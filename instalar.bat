@echo off
cd /d "%~dp0"
echo Creando entorno virtual...
py -3.12 -m venv .venv
if errorlevel 1 (
  echo No se pudo crear el entorno. Verifique que Python 3.12 este instalado.
  pause
  exit /b 1
)
echo Instalando librerias...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Hubo un error al instalar. Revise los mensajes de arriba.
  pause
  exit /b 1
)
echo.
echo Listo. Ahora abra el programa con abrir.bat
pause
