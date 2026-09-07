@echo off
REM ============================================================================
REM  LA CORRIDA DE LA MANANA, sin ventanas y sin navegador.
REM
REM  Esto NO se toca a mano: lo ejecuta el Programador de tareas de Windows
REM  (tarea "BusquedaAlquiler-Diaria"). Para correr la busqueda vos mismo esta
REM  actualizar.bat, que ademas abre la pagina.
REM
REM  La salida queda en data/logs/<fecha>.txt, y el resumen legible en
REM  corridas/<fecha>.md como siempre.
REM
REM  Para ver, cambiar o sacar la tarea:  taskschd.msc  (Programador de tareas)
REM  Para sacarla desde la consola:       schtasks /delete /tn BusquedaAlquiler-Diaria /f
REM ============================================================================
cd /d "%~dp0.."
if not exist "data\logs" mkdir "data\logs"

REM Un solo archivo, sobrescrito en cada corrida, y sin fecha en el nombre: %date% se
REM escribe distinto segun el idioma de Windows (aca salia "21-08-Fri") y armar la fecha
REM en un .bat es una fuente de bugs para nada. El historico ya vive en corridas/<fecha>.md,
REM que lo escribe la propia corrida. Esto es solo la salida cruda de la ultima.
"C:\Users\mario\AppData\Local\Programs\Python\Python312\python.exe" scripts\main.py > "data\logs\ultima-corrida.txt" 2>&1
