@echo off
echo ===================================================
echo Iniciando Servicio de PostgreSQL 17...
echo ===================================================
"C:\Users\jhond\pgsql\bin\pg_ctl.exe" status -D "C:\Program Files\PostgreSQL\17\data" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo.
    echo PostgreSQL ya se encuentra en ejecucion y listo para recibir conexiones.
) else (
    "C:\Users\jhond\pgsql\bin\pg_ctl.exe" -D "C:\Program Files\PostgreSQL\17\data" -l "C:\Users\jhond\pgsql\logfile.log" start
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo PostgreSQL se ha iniciado correctamente.
    ) else (
        echo.
        echo Hubo un error al iniciar PostgreSQL. Consulta el archivo C:\Users\jhond\pgsql\logfile.log
    )
)
echo ===================================================
pause
