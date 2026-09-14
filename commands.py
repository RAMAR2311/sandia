"""Comandos CLI para copias de seguridad de la base de datos PostgreSQL de VetCare.

Usa ``pg_dump``/``psql`` con argumentos en lista (nunca ``shell=True``) y pasa la
contraseña por la variable de entorno ``PGPASSWORD``, nunca en la línea de
comandos: así no queda visible en el listado de procesos (``ps aux``) ni abre
la puerta a inyección de comandos a través de la URL o el nombre de archivo.
"""

import gzip
import os
import shutil
import subprocess
from pathlib import Path

import click
from flask import current_app
from flask.cli import AppGroup
from sqlalchemy.engine import make_url

from utils import obtener_hora_bogota

backup_cli = AppGroup("backup", help="Comandos de resguardo y restauración de la base de datos.")

DIAS_ROTACION_PREDETERMINADOS = 30
PREFIJO_ARCHIVO = "vetcare_backup_"


def _datos_conexion():
    """Extrae host/puerto/usuario/clave/nombre de la BD desde SQLALCHEMY_DATABASE_URI.

    Lanza ``click.ClickException`` si la URL no es PostgreSQL (la app entera
    exige PostgreSQL; este comando nunca debe ejecutarse contra otra base).
    """
    url_cruda = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not url_cruda or "postgresql" not in url_cruda:
        raise click.ClickException("La base de datos configurada no es PostgreSQL o la URL es inválida.")
    url = make_url(url_cruda)
    return {
        "host": url.host or "localhost",
        "port": str(url.port or 5432),
        "usuario": url.username or "postgres",
        "clave": url.password or "",
        "base": url.database,
    }


def _herramienta_disponible(nombre: str) -> bool:
    return shutil.which(nombre) is not None


def _rotar_backups(directorio: Path, dias: int) -> int:
    """Borra copias de más de ``dias`` días. Devuelve cuántas se eliminaron."""
    limite = obtener_hora_bogota().timestamp() - dias * 86400
    eliminados = 0
    for archivo in directorio.glob(f"{PREFIJO_ARCHIVO}*.sql.gz"):
        try:
            if archivo.stat().st_mtime < limite:
                archivo.unlink()
                eliminados += 1
        except OSError as exc:
            click.echo(f"Aviso: no se pudo evaluar/borrar {archivo.name}: {exc}")
    return eliminados


@backup_cli.command("dump")
@click.option("--directorio", default="backups", help="Directorio donde guardar la copia.")
@click.option(
    "--dias-rotacion",
    default=DIAS_ROTACION_PREDETERMINADOS,
    show_default=True,
    help="Copias más antiguas que este número de días se eliminan tras el respaldo.",
)
def backup_dump(directorio, dias_rotacion):
    """Crea una copia de seguridad comprimida (.sql.gz) de la base de datos."""
    if not _herramienta_disponible("pg_dump"):
        raise click.ClickException("No se encontró 'pg_dump' en el PATH del sistema.")

    conexion = _datos_conexion()
    ruta_dir = Path(directorio)
    ruta_dir.mkdir(parents=True, exist_ok=True)

    timestamp = obtener_hora_bogota().strftime("%Y%m%d_%H%M%S")
    archivo_salida = ruta_dir / f"{PREFIJO_ARCHIVO}{timestamp}.sql.gz"

    comando = [
        "pg_dump",
        "-h", conexion["host"],
        "-p", conexion["port"],
        "-U", conexion["usuario"],
        "-d", conexion["base"],
        "--no-password",
    ]
    entorno = {**os.environ, "PGPASSWORD": conexion["clave"]}

    click.echo(f"Generando respaldo comprimido en {archivo_salida}...")
    # stderr NO se captura como PIPE: si nadie la drena mientras escribimos el
    # stdout descomprimido, y pg_dump llena ese buffer, el proceso se bloquea
    # (interbloqueo clásico de subprocess). Se deja heredado: los avisos de
    # pg_dump se ven en la consola en vivo.
    try:
        proceso = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=None, env=entorno)
        with gzip.open(archivo_salida, "wb") as destino:
            shutil.copyfileobj(proceso.stdout, destino)
        proceso.wait()
    except OSError as exc:
        archivo_salida.unlink(missing_ok=True)
        raise click.ClickException(f"No se pudo ejecutar pg_dump: {exc}") from exc

    if proceso.returncode != 0:
        archivo_salida.unlink(missing_ok=True)
        raise click.ClickException("pg_dump terminó con error; revisa el mensaje mostrado arriba.")

    tamano_kb = archivo_salida.stat().st_size / 1024
    click.echo(f"¡Respaldo completado! {archivo_salida} ({tamano_kb:.1f} KB)")

    eliminados = _rotar_backups(ruta_dir, dias_rotacion)
    if eliminados:
        click.echo(f"Rotación: se eliminaron {eliminados} copia(s) de más de {dias_rotacion} días.")


@backup_cli.command("restore")
@click.argument("archivo", type=click.Path(exists=True, dir_okay=False))
@click.option("--si", is_flag=True, help="Omite la confirmación interactiva (úsalo solo en scripts controlados).")
def backup_restore(archivo, si):
    """Restaura la base de datos a partir de un archivo .sql o .sql.gz de respaldo."""
    if not _herramienta_disponible("psql"):
        raise click.ClickException("No se encontró 'psql' en el PATH del sistema.")

    ruta_archivo = Path(archivo).resolve()
    if ruta_archivo.suffix not in (".sql", ".gz") or (
        ruta_archivo.suffix == ".gz" and ruta_archivo.stem[-4:] != ".sql"
    ):
        raise click.ClickException("El archivo debe tener extensión .sql o .sql.gz")

    conexion = _datos_conexion()
    if not si:
        click.confirm(
            f"Esto SOBRESCRIBE la base '{conexion['base']}' en {conexion['host']} con el contenido de "
            f"{ruta_archivo.name}. ¿Continuar?",
            abort=True,
        )

    comando = [
        "psql",
        "-h", conexion["host"],
        "-p", conexion["port"],
        "-U", conexion["usuario"],
        "-d", conexion["base"],
        "--no-password",
        "-v", "ON_ERROR_STOP=1",
    ]
    entorno = {**os.environ, "PGPASSWORD": conexion["clave"]}

    click.echo(f"Restaurando base de datos desde {ruta_archivo}...")
    # No se puede pasar un GzipFile como stdin= de subprocess: éste usa el
    # descriptor de archivo del sistema operativo (los bytes SIN descomprimir),
    # no la lectura descomprimida en espacio de usuario. Hay que volcar la
    # descompresión manualmente al stdin (tubería) del proceso hijo.
    # stdout/stderr heredados (no PIPE): si escribimos a stdin manualmente y a la
    # vez dejamos su salida sin drenar en un buffer, psql puede bloquearse
    # esperando que alguien la lea (interbloqueo). Así, el progreso y los
    # errores de psql se ven en vivo en la consola.
    try:
        proceso = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=None, stderr=None, env=entorno)
    except OSError as exc:
        raise click.ClickException(f"No se pudo ejecutar psql: {exc}") from exc

    try:
        abridor = gzip.open if ruta_archivo.suffix == ".gz" else open
        with abridor(ruta_archivo, "rb") as origen:
            shutil.copyfileobj(origen, proceso.stdin)
    except BrokenPipeError:
        pass  # psql ya cerró la tubería por un error; el mensaje ya se vio en consola
    finally:
        proceso.stdin.close()

    proceso.wait()
    if proceso.returncode != 0:
        raise click.ClickException("Error al restaurar; revisa el mensaje de psql mostrado arriba.")
    click.echo("¡Restauración completada exitosamente!")
