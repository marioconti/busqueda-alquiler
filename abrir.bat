@echo off
REM ============================================================================
REM  ESTE ES EL UNICO ARCHIVO QUE HACE FALTA. Doble click y listo.
REM
REM  Mira si los datos son de hoy:
REM     - si ya se busco hoy  -> abre la pagina directo (no molesta al portal)
REM     - si no                -> busca primero, y despues abre la pagina
REM
REM  Ademas la busqueda corre sola todas las mananas a las 9 (tarea de Windows
REM  "BusquedaAlquiler-Diaria"), asi que lo normal es que abra directo.
REM
REM  Si queres forzar una busqueda aunque ya se haya hecho hoy: actualizar.bat
REM
REM  ESTA VENTANA NEGRA ES EL SERVIDOR. Mientras este abierta, lo que marques en
REM  la pagina se guarda solo en el disco. Si la cerras, se apaga.
REM  Hace falta porque un index.html abierto con doble click no tiene permiso
REM  para escribir archivos: el navegador no lo deja, por seguridad.
REM ============================================================================
title Busqueda de alquiler
cd /d "%~dp0"

echo.
echo   BUSQUEDA DE ALQUILER
echo   --------------------

python scripts\estado.py --hay-que-buscar
if errorlevel 2 goto :buscar
if errorlevel 1 goto :abrir

:buscar
echo.
echo   Los datos no son de hoy. Buscando lo nuevo en el portal.
echo   Tarda entre 5 y 15 minutos. NO cierres esta ventana.
echo.
python scripts\main.py
echo.
echo   --------------------

:abrir
echo.
echo   Abriendo la pagina...
echo.
echo   DEJA ESTA VENTANA ABIERTA mientras la uses.
echo   Cerrala (o Ctrl+C) cuando termines.
echo.

title Busqueda de alquiler - servidor (cerra esta ventana para apagarlo)
python scripts\servidor.py

if errorlevel 1 (
  echo.
  echo   No se pudo iniciar.
  echo   Revisa que Python este instalado y accesible desde la consola:
  echo      python --version
  echo.
  pause
)
