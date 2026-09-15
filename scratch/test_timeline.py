from app import create_app
from models import Mascota, db
from routes.mascotas import construir_linea_tiempo

app = create_app()
with app.app_context():
    mascotas = db.session.execute(db.select(Mascota).limit(5)).scalars().all()
    for m in mascotas:
        evs = construir_linea_tiempo(m)
        print(f"Mascota {m.id} ({m.nombre}): {len(evs)} eventos encontrados")
        for e in evs[:3]:
            print(f"  - [{e['categoria']}] {e['fecha']}: {e['titulo']}")
