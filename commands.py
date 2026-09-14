"""Comandos CLI para copias de seguridad de la base de datos PostgreSQL de VetCare."""

import os
import subprocess
from datetime import datetime
from pathlib import Path

import click
from flask import current_app
from flask.cli import AppGroup

backup_cli = AppGroup("backup", help="Comandos de resguardo y restauración de la base de datos.")


@backup_cli.command("dump")
@click.option("--directorio", default="backups", help="Directorio donde guardar la copia.")
def backup_dump(directorio):
    """Crea una copia de seguridad (dump) de la base de datos en formato SQL/Dump."""
    url_db = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not url_db or "postgresql" not in url_db:
        click.echo("Error: La base de datos configurada no es PostgreSQL o la URL es inválida.")
        return

    ruta_dir = Path(directorio)
    ruta_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo_salida = ruta_dir / f"vetcare_backup_{timestamp}.sql"

    # Comando pg_dump
    cmd = f'pg_dump "{url_db}" -f "{archivo_salida}"'
    click.echo(f"Generando respaldo en {archivo_salida}...")

    try:
        resultado = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if resultado.returncode == 0:
            click.echo(f"¡Respaldo completado con éxito! Archivo: {archivo_salida}")
        else:
            click.echo(f"Error al ejecutar pg_dump: {resultado.stderr}")
    except Exception as exc:
        click.echo(f"Excepción al ejecutar respaldo: {exc}")


@backup_cli.command("restore")
@click.argument("archivo")
def backup_restore(archivo):
    """Restaura la base de datos a partir de un archivo .sql de respaldo."""
    url_db = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not url_db or "postgresql" not in url_db:
        click.echo("Error: La base de datos configurada no es PostgreSQL.")
        return

    ruta_archivo = Path(archivo)
    if not ruta_archivo.exists():
        click.echo(f"Error: El archivo {archivo} no existe.")
        return

    cmd = f'psql "{url_db}" -f "{ruta_archivo}"'
    click.echo(f"Restaurando base de datos desde {ruta_archivo}...")

    try:
        resultado = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if resultado.returncode == 0:
            click.echo("¡Restauración completada exitosamente!")
        else:
            click.echo(f"Error al restaurar: {resultado.stderr}")
    except Exception as exc:
        click.echo(f"Excepción al restaurar base de datos: {exc}")
