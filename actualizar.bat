@echo off
REM ============================================================================
REM  FORZAR UNA BUSQUEDA AHORA, aunque ya se haya buscado hoy.
REM
REM  PARA EL USO NORMAL NO HACE FALTA: alcanza con abrir.bat, que busca solo si
REM  los datos no son de hoy. Este archivo es para cuando querés mirar de nuevo
REM  el portal en el mismo dia (por ejemplo a la tarde, despues de la corrida
REM  automatica de la manana).
REM
REM  Igual hay un techo de 2 busquedas por dia: pasado eso la corrida saltea la
REM  red sola y reprocesa lo que ya bajo. No se puede insistirle al portal.
REM
REM  La busqueda tarda entre 5 y 15 minutos y va contando lo que encuentra.
REM  Es normal que aparezcan lineas con "!": son avisos del propio sistema
REM  (paginas que no toma, barrios que saltea). Las que empiezan con "!!" son
REM  las que importan.
REM ============================================================================
title Busqueda de alquiler - actualizando
cd /d "%~dp0"

echo.
echo   BUSQUEDA DE ALQUILER
echo   --------------------
echo   Buscando lo nuevo en el portal. Esto tarda unos minutos.
echo   NO cierres esta ventana.
echo.

python scripts\main.py

if errorlevel 1 (
  echo.
  echo   La busqueda fallo. La pagina se abre igual, con los datos de la ultima vez.
  echo.
  pause
)

echo.
echo   --------------------
echo   Listo. Abriendo la pagina...
echo.

title Busqueda de alquiler - servidor (cerra esta ventana para apagarlo)
python scripts\servidor.py

if errorlevel 1 (
  echo.
  echo   No se pudo abrir la pagina.
  echo   Revisa que Python este instalado: python --version
  echo.
  pause
)
