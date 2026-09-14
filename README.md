# VetCare · Sandía

Sistema web de gestión para la clínica veterinaria **Sandía** (Medicina y Spa
Veterinario): historia clínica, spa de mascotas, punto de venta, inventario con
lotes y administración financiera.

Stack: Python 3.12+ · Flask 3 · Flask-SQLAlchemy + Alembic · PostgreSQL 16+ ·
Jinja2 + Bootstrap 5 + JavaScript vanilla (sin build step).

## Puesta en marcha local

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env           # y completa SECRET_KEY y DATABASE_URL
flask db upgrade                 # crea las tablas y siembra la configuración
flask crear-admin                # primer administrador (interactivo)
flask run --debug                # http://localhost:5000
```

`SECRET_KEY` se genera con `python -c "import secrets; print(secrets.token_hex(32))"`.
La aplicación **no arranca** si falta `SECRET_KEY` o `DATABASE_URL`, y solo
acepta PostgreSQL.

## Pruebas

Define `TEST_DATABASE_URL` en `.env` apuntando a una base distinta (por ejemplo
`vetcare_test`) y ejecuta:

```bash
pytest
```

Las pruebas corren las migraciones reales de Alembic sobre la base de prueba.

## Estructura

```
app.py            fábrica create_app(), configuración, blueprints, errores, CLI
wsgi.py           entrada de Gunicorn
models.py         modelos SQLAlchemy
forms.py          formularios Flask-WTF
decorators.py     control de acceso por rol
utils.py          obtener_hora_bogota(), formato COP, enlaces WhatsApp
routes/           un blueprint por módulo
templates/        una carpeta por módulo + base.html
static/           css, js, img, fonts, vendor (Bootstrap local), uploads
migrations/       Alembic
tests/            pytest
```

## Reglas de ingeniería (resumen)

- Toda ruta que hace `commit()` va en `try/except` con `db.session.rollback()`.
- Nunca `db.create_all()` fuera de pruebas: cada cambio de modelo lleva migración.
- Dinero en `Decimal` (`Numeric(12, 2)`); fechas con `utils.obtener_hora_bogota()`.
- CSRF siempre activo; las APIs JSON envían el token en `X-CSRFToken`.
- Precio de costo solo visible para `admin`, filtrado en el backend.
