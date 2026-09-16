"""Pruebas para la configuración del médico principal, especialidad y firma digital."""

import io
from PIL import Image
from models import ConfiguracionSistema, Usuario, db
from utils import guardar_firma_digital, eliminar_firma_digital


def test_configuracion_inicial_medico():
    """Verifica que los valores por defecto del médico principal estén inicializados."""
    datos = ConfiguracionSistema.datos_clinica()
    assert datos["doctora_nombre"] == "Dra. Daniela Pulido"
    assert datos["doctora_tp"] == "53214"
    assert datos["doctora_titulo"] == "Médica veterinaria"
    assert datos["doctora_especialidad"] == "Dpl. Dermatología de pequeñas especies"


def test_guardar_y_eliminar_firma_digital(tmp_path, monkeypatch):
    """Verifica el procesamiento, guardado y eliminación de firmas digitales."""
    import base64
    sample_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    
    # Probar que procesa base64 data URI
    nombre_archivo = guardar_firma_digital(sample_b64)
    assert nombre_archivo.startswith("firma_")
    assert nombre_archivo.endswith(".png")

    # Probar eliminación
    eliminar_firma_digital(nombre_archivo)
