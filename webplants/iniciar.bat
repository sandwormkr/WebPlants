@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WebPlants

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Criando ambiente Python...
    %PY% -m venv .venv || (echo Python nao encontrado. Instale o Python 3.11+ em python.org & pause & exit /b 1)
    echo [2/3] Instalando dependencias - pode demorar alguns minutos na primeira vez...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo Arquivo .env criado. Abra-o no Bloco de Notas, preencha e rode este arquivo de novo.
    notepad ".env"
    pause
    exit /b 0
)

echo [3/3] Iniciando WebPlants... (feche esta janela para parar)
".venv\Scripts\python.exe" app.py
pause
