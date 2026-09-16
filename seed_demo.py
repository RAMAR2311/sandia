"""Script de siembra (seed) de datos de demostración para Sandía - VetCare.

Crea usuarios por rol, datos de la clínica, razas, clientes (tutores),
mascotas con peso e historial, productos con stock y variantes, servicios de
SPA, citas de agenda, citas de spa, consultas médicas SOAP, vacunas por
vencer (para activar recordatorios), hospitalizaciones activas, cirugías,
exámenes de laboratorio, gastos operativos y turnos de caja con ventas.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from app import create_app, db
from models import (
    Usuario, ConfiguracionSistema, Raza, Tutor, Mascota, RegistroPeso,
    Proveedor, Producto, VarianteProducto, Lote, MovimientoStock,
    ServicioSpa, CitaSpa, ConsultaMedica, VacunaMascota, DesparasitacionMascota,
    Cita, Hospitalizacion, EvolucionHospitalaria, Cirugia, ExamenLaboratorio,
    Gasto, FacturaProveedor, PagoProveedor, CuentaTutor, AbonoCuentaTutor,
    TurnoCaja, Venta, DetalleVenta, PagoVenta
)
from utils import hoy_bogota, obtener_hora_bogota

app = create_app()

with app.app_context():
    print("Iniciando carga de datos de ejemplo...")

    # 1. Configuración de la Clínica
    configs = {
        "clinica_nombre": "Sandía",
        "clinica_subtitulo": "Medicina y Spa Veterinario",
        "clinica_nit": "901.554.892-1",
        "clinica_direccion": "Cra. 15 # 104-32, Usaquén",
        "clinica_ciudad": "Bogotá D.C.",
        "clinica_telefono": "3124567890",
        "clinica_whatsapp": "573124567890",
        "clinica_email": "contacto@sandiavet.com",
        "descontar_stock_ventas": "true"
    }
    for clave, valor in configs.items():
        cfg = db.session.execute(db.select(ConfiguracionSistema).filter_by(clave=clave)).scalar_one_or_none()
        if cfg:
            cfg.valor = valor
        else:
            db.session.add(ConfiguracionSistema(clave=clave, valor=valor, tipo="str", grupo="clinica"))

    db.session.commit()
    print("[1/12] Configuración de la clínica actualizada.")

    # 2. Usuarios por rol
    usuarios_data = [
        ("Dr. Jhon Administrador", "admin@sandiavet.com", "Admin123456*", "admin", "3101112233", None, None, None),
        ("Dra. Daniela Pulido", "veterinaria@sandiavet.com", "Vet123456*", "veterinario", "3152223344", "53214", "Médica veterinaria", "Dpl. Dermatología de pequeñas especies"),
        ("Carlos Andrés Gómez", "cajero@sandiavet.com", "Caja123456*", "cajero", "3203334455", None, None, None),
        ("Andrea Restrepo", "spa@sandiavet.com", "Spa123456*", "groomer", "3004445566", None, None, None),
    ]

    usuarios = {}
    for nombre, email, pwd, rol, tel, tp, titulo, esp in usuarios_data:
        u = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one_or_none()
        if not u:
            u = Usuario(
                nombre=nombre,
                email=email,
                rol=rol,
                activo=True,
                telefono=tel,
                tarjeta_profesional=tp,
                titulo_profesional=titulo,
                especialidad=esp,
            )
            u.establecer_password(pwd)
            db.session.add(u)
            db.session.flush()
        else:
            if rol == "veterinario":
                u.nombre = nombre
                u.tarjeta_profesional = tp
                u.titulo_profesional = titulo
                u.especialidad = esp
                db.session.flush()
        usuarios[rol] = u

    db.session.commit()
    print("[2/12] Usuarios creados (admin, veterinario, cajero, groomer).")

    # 3. Razas
    razas_data = [
        ("canino", "Golden Retriever"),
        ("canino", "Bulldog Francés"),
        ("canino", "Pastor Alemán"),
        ("canino", "Poodle"),
        ("canino", "Schnauzer"),
        ("canino", "Criollo / Mestizo"),
        ("canino", "Beagle"),
        ("canino", "Labrador Retriever"),
        ("felino", "Siamés"),
        ("felino", "Persa"),
        ("felino", "Maine Coon"),
        ("felino", "Bengalí"),
        ("felino", "Criollo / Mestizo Felino"),
    ]
    razas = {}
    for esp, nom in razas_data:
        r = db.session.execute(db.select(Raza).filter_by(especie=esp, nombre=nom)).scalar_one_or_none()
        if not r:
            r = Raza(especie=esp, nombre=nom, activo=True)
            db.session.add(r)
            db.session.flush()
        razas[nom] = r
    db.session.commit()
    print("[3/12] Catálogo de razas poblado.")

    # 4. Tutores (Clientes)
    admin_id = usuarios["admin"].id
    tutores_data = [
        ("CC", "1018456789", "Andrés Felipe Martínez", "3105551234", "573105551234", "andres.martinez@gmail.com", "Calle 116 # 19-24", "Santa Bárbara"),
        ("CC", "1020478965", "Valentina Ríos Castro", "3158884321", "573158884321", "valen.rios@hotmail.com", "Cra. 7 # 127-10", "Bella Suiza"),
        ("CC", "79845123", "Carlos Eduardo Ospina", "3209998765", "573209998765", "carlos.ospina@yahoo.com", "Calle 140 # 11-45", "Cedritos"),
        ("CC", "1032897456", "Mariana Gómez Botero", "3004445566", "573004445566", "mariana.gomez@gmail.com", "Calle 100 # 8A-55", "Chicó"),
        ("CC", "98765432", "Jorge Iván Ramírez", "3123337788", "573123337788", "jorge.ramirez@outlook.com", "Cra. 19 # 134-20", "Contador"),
        ("CC", "1015674321", "Sofía Herrera Peláez", "3182221199", "573182221199", "sofia.herrera@gmail.com", "Calle 106 # 14-30", "San Patricio"),
    ]
    tutores = []
    for td, nd, nc, tel, wa, em, dir_t, bar in tutores_data:
        t = db.session.execute(db.select(Tutor).filter_by(numero_documento=nd)).scalar_one_or_none()
        if not t:
            t = Tutor(
                tipo_documento=td, numero_documento=nd, nombre_completo=nc,
                telefono=tel, whatsapp=wa, email=em, direccion=dir_t, barrio=bar,
                acepta_recordatorios=True, activo=True, creado_por_id=admin_id
            )
            db.session.add(t)
            db.session.flush()
        tutores.append(t)
    db.session.commit()
    print("[4/12] Tutores / clientes creados.")

    # 5. Mascotas
    hoy = hoy_bogota()
    mascotas_data = [
        (tutores[0], "Max", "canino", razas["Golden Retriever"].id, "macho", hoy - timedelta(days=365*3), "Dorado", "Mancha blanca en pecho", "981098102345671", True, "grande"),
        (tutores[1], "Luna", "canino", razas["Bulldog Francés"].id, "hembra", hoy - timedelta(days=365*2), "Vaquita (blanco y negro)", "Orejas de murciélago erguidas", "981098102345672", True, "pequeno"),
        (tutores[2], "Milo", "felino", razas["Siamés"].id, "macho", hoy - timedelta(days=365*1 + 180), "Seal point", "Ojos azules intensos", "981098102345673", True, "pequeno"),
        (tutores[3], "Toby", "canino", razas["Criollo / Mestizo"].id, "macho", hoy - timedelta(days=365*4), "Caramelo", "Cola enroscada", "981098102345674", True, "mediano"),
        (tutores[4], "Nala", "felino", razas["Persa"].id, "hembra", hoy - timedelta(days=365*2 + 60), "Blanco puro", "Pelo largo y denso", "981098102345675", False, "pequeno"),
        (tutores[5], "Rocky", "canino", razas["Pastor Alemán"].id, "macho", hoy - timedelta(days=365*5), "Negro y fuego", "Cicatriz leve pata delantera izq", "981098102345676", True, "grande"),
    ]
    mascotas = []
    for tut, nom, esp, r_id, sex, fn, col, sen, chip, est, tam in mascotas_data:
        m = db.session.execute(db.select(Mascota).filter_by(tutor_id=tut.id, nombre=nom)).scalar_one_or_none()
        if not m:
            m = Mascota(
                tutor_id=tut.id, nombre=nom, especie=esp, raza_id=r_id, sexo=sex,
                fecha_nacimiento=fn, color=col, senas_particulares=sen,
                microchip=chip, esterilizado=est, tamano=tam, activo=True, creado_por_id=admin_id
            )
            db.session.add(m)
            db.session.flush()
        mascotas.append(m)
    db.session.commit()
    print("[5/12] Mascotas creadas.")

    # 6. Historial de pesos
    pesos_base = [32.0, 11.2, 4.3, 18.5, 3.8, 35.0]
    for i, m in enumerate(mascotas):
        p_base = pesos_base[i]
        for meses_atras in [6, 4, 2, 0]:
            f_peso = hoy - timedelta(days=meses_atras * 30)
            p_val = Decimal(str(round(p_base - (meses_atras * 0.15), 2)))
            db.session.add(RegistroPeso(mascota_id=m.id, peso_kg=p_val, fecha=f_peso, registrado_por_id=usuarios["veterinario"].id))
    db.session.commit()
    print("[6/12] Historial de pesos registrado.")

    # 7. Proveedores y Productos
    prov_zoetis = Proveedor(nit="860.001.234-1", nombre="Zoetis Colombia S.A.S.", contacto="Juan Pablo Pérez", telefono="3102345678", email="pedidos@zoetis.com", direccion="Zona Franca Bogotá")
    prov_distri = Proveedor(nit="900.543.210-9", nombre="Distribuidora Mascotas & Salud", contacto="Laura Restrepo", telefono="3204567890", email="ventas@mascotasysalud.com", direccion="Calle 80 # 68-12")
    db.session.add_all([prov_zoetis, prov_distri])
    db.session.flush()

    productos_data = [
        ("NEX-1530", "770123456001", "NexGard Spectra 15.1 - 30 kg", "Antiparasitario masticable mensual para pulgas, garrapatas y parásitos internos", "medicamento", "producto", "caja", Decimal("48000"), Decimal("65000"), Decimal("78000"), Decimal("35"), Decimal("5"), True, prov_zoetis.id),
        ("BRAV-1020", "770123456002", "Bravecto Perros 10 - 20 kg", "Comprimido masticable protección 12 semanas contra pulgas y garrapatas", "medicamento", "producto", "caja", Decimal("92000"), Decimal("125000"), Decimal("145000"), Decimal("22"), Decimal("4"), True, prov_distri.id),
        ("ROY-MINI-3K", "770123456003", "Royal Canin Mini Adult 3 kg", "Nutrición a medida para perros adultos de raza pequeña de 10 meses a 8 años", "alimento", "producto", "bulto", Decimal("85000"), Decimal("110000"), Decimal("128000"), Decimal("16"), Decimal("3"), False, prov_distri.id),
        ("HIL-PUP-2K", "770123456004", "Hill's Science Diet Puppy 2 kg", "Alimento seco para cachorros en crecimiento con DHA de aceite de pescado", "alimento", "producto", "bulto", Decimal("72000"), Decimal("95000"), Decimal("112000"), Decimal("12"), Decimal("3"), False, prov_distri.id),
        ("NOBI-PUP-DP", "770123456005", "Vacuna Nobivac Puppy DP", "Inmunización activa contra Distemper canino y Parvovirus", "medicamento", "producto", "dosis", Decimal("22000"), Decimal("38000"), Decimal("48000"), Decimal("18"), Decimal("5"), True, prov_zoetis.id),
        ("FELOCELL-4", "770123456006", "Vacuna Felocell 4 Felina", "Vacuna viral felina contra Rinotraqueítis, Calicivirus, Panleucopenia y Clamidia", "medicamento", "producto", "dosis", Decimal("25000"), Decimal("42000"), Decimal("52000"), Decimal("14"), Decimal("4"), True, prov_zoetis.id),
        ("MELOX-10ML", "770123456007", "Meloxicam Gotas 10 ml (Meloxivet)", "Antiinflamatorio no esteroideo y analgésico de uso veterinario", "medicamento", "producto", "frasco", Decimal("18000"), Decimal("28000"), Decimal("35000"), Decimal("20"), Decimal("5"), True, prov_zoetis.id),
        ("SHAMP-CLOR-250", "770123456008", "Shampoo Clorhexidina 3% 250 ml", "Shampoo dermatológico antiséptico para caninos y felinos", "higiene", "producto", "frasco", Decimal("24000"), Decimal("36000"), Decimal("44000"), Decimal("25"), Decimal("4"), False, prov_distri.id),
        ("CEFAL-500MG", "770123456009", "Cefalexina 500 mg x 10 tab", "Antibiótico bactericida de amplio espectro para infecciones dérmicas y de tejidos blandos", "medicamento", "producto", "blister", Decimal("14000"), Decimal("22000"), Decimal("29000"), Decimal("4"), Decimal("6"), True, prov_distri.id),  # Stock bajo intencional para alerta
    ]
    productos = []
    for sku, cb, nom, desc, cat, tip, um, pc, pm, ps, cs, sm, cl, p_id in productos_data:
        p = db.session.execute(db.select(Producto).filter_by(sku=sku)).scalar_one_or_none()
        if not p:
            p = Producto(
                sku=sku, codigo_barras=cb, nombre=nom, descripcion=desc,
                categoria=cat, tipo=tip, unidad_medida=um, precio_costo=pc,
                precio_minimo=pm, precio_sugerido=ps, cantidad_stock=cs, stock_minimo=sm,
                controla_lote=cl, proveedor_id=p_id, activo=True, creado_por_id=admin_id
            )
            db.session.add(p)
            db.session.flush()
            if cl:
                lote_venc = hoy + timedelta(days=180 if "DP" not in sku else 25)
                db.session.add(Lote(
                    producto_id=p.id, numero_lote=f"LOT-{sku}-2026", fecha_vencimiento=lote_venc,
                    cantidad_inicial=cs, cantidad_disponible=cs, proveedor_id=p_id, creado_por_id=admin_id
                ))
        productos.append(p)
    db.session.commit()
    print("[7/12] Proveedores, catálogo de productos y lotes creados con alertas de stock.")

    # 8. Servicios de SPA
    spa_servicios_data = [
        ("Baño & Peluquería Canina Raza Grande", "Incluye baño cosmético o medicado, corte higiénico o de raza, secado térmico, deslanado, limpieza de oídos y corte de uñas.", 90, Decimal("75000"), "canino", "grande"),
        ("Baño & Peluquería Canina Raza Pequeña", "Baño relajante, secado rápido, corte de pelo estético, arreglo de almohadillas y perfume hipoalergénico.", 60, Decimal("45000"), "canino", "pequeno"),
        ("Spa Felino Anti-Estrés", "Baño en seco o húmedo con feromonas felinas (Feliway), cepillado profundo, limpieza ótica y corte de uñas.", 60, Decimal("55000"), "felino", "pequeno"),
        ("Profilaxis Dental Ultrasonido", "Limpieza y destartraje profundo sin dolor bajo supervisión veterinaria con pulido de esmalte.", 60, Decimal("120000"), "canino", "mediano"),
        ("Corte de Uñas & Limpieza Ótica", "Servicio exprés higiénico preventivo.", 20, Decimal("20000"), None, None),
    ]
    servicios_spa = []
    for nom, desc, dur, ps, esp, tam in spa_servicios_data:
        s = db.session.execute(db.select(ServicioSpa).filter_by(nombre=nom)).scalar_one_or_none()
        if not s:
            s = ServicioSpa(nombre=nom, descripcion=desc, duracion_minutos=dur, precio_sugerido=ps, especie=esp, tamano_mascota=tam, activo=True)
            db.session.add(s)
            db.session.flush()
        servicios_spa.append(s)
    db.session.commit()
    print("[8/12] Catálogo de SPA y Grooming configurado.")

    # 9. Consultas Médicas SOAP
    vet_id = usuarios["veterinario"].id
    # Consulta 1: Max (Golden Retriever)
    c1 = ConsultaMedica(
        mascota_id=mascotas[0].id, tutor_id=tutores[0].id, veterinario_id=vet_id,
        fecha_hora=obtener_hora_bogota() - timedelta(days=12),
        motivo_consulta="Chequeo preventivo semestral y control de peso",
        anamnesis="El tutor refiere apetito normal, defecaciones normales, actividad física vigorosa de 1 hora diaria. Sin vómitos ni diarreas.",
        peso_kg=Decimal("32.0"), temperatura_c=Decimal("38.4"), frecuencia_cardiaca=92, frecuencia_respiratoria=22,
        tllc_segundos=1, mucosas="rosadas_humedas", condicion_corporal="3_ideal",
        examen_sistemas="Ganglios submandibulares y poplíteos normales. Auscultación cardiorrespiratoria sin soplos ni estertores. Palpación abdominal no dolorosa. Articulaciones coxofemorales sin dolor a la hiperextensión.",
        diagnostico="Paciente canino en óptimo estado de salud general. Condición corporal ideal.",
        plan_tratamiento="1. Continuar con plan nutricional actual.\n2. Administrar NexGard Spectra para prevención antiparasitaria.\n3. Próxima vacunación anual programada.",
        receta_medica="NexGard Spectra 15-30kg: 1 tableta vía oral mensual.",
        creado_por_id=vet_id
    )
    # Consulta 2: Luna (Bulldog Francés)
    c2 = ConsultaMedica(
        mascota_id=mascotas[1].id, tutor_id=tutores[1].id, veterinario_id=vet_id,
        fecha_hora=obtener_hora_bogota() - timedelta(days=3),
        motivo_consulta="Episodios de prurito ótico y sacudidas frecuentes de cabeza",
        anamnesis="Presenta rascado intenso de oreja derecha desde hace 4 días con secreción parduzca moderada y olor característico.",
        peso_kg=Decimal("11.2"), temperatura_c=Decimal("38.7"), frecuencia_cardiaca=110, frecuencia_respiratoria=28,
        tllc_segundos=2, mucosas="rosadas", condicion_corporal="3_ideal",
        examen_sistemas="Otoscopia revela eritema de canal auditivo externo derecho con exudado ceruminoso bilateral. Membranas timpánicas íntegras. Citología ótica compatible con Malassezia pachydermatis.",
        diagnostico="Otitis externa ceruminosa / micótica por Malassezia bilateral, predominantemente derecha.",
        plan_tratamiento="1. Limpieza con solución ótica secante.\n2. Gotas óticas antibacterianas/antifúngicas cada 12 horas por 10 días.\n3. Control en 10 días.",
        receta_medica="Otovet / Posatex gotas: 4 gotas en cada oído cada 12 horas previa limpieza por 10 días.",
        creado_por_id=vet_id
    )
    db.session.add_all([c1, c2])
    db.session.commit()
    print("[9/12] Historias clínicas SOAP completas registradas.")

    # 10. Vacunas y Desparasitaciones (Incluyendo alertas de vencimiento)
    # Vacuna próxima a vencer en 7 días para Max (¡aparece en el Dashboard con botón de WhatsApp!)
    v1 = VacunaMascota(
        mascota_id=mascotas[0].id, tutor_id=tutores[0].id, veterinario_id=vet_id,
        nombre_vacuna="Rabia Canina (Rabisin)", lote="LOT-RAB-2025", laboratorio="Boehringer Ingelheim",
        dosis="1 ml SC", fecha_aplicacion=hoy - timedelta(days=358), fecha_proxima=hoy + timedelta(days=7),
        observaciones="Refuerzo anual programado. Alerta activa para notificación por WhatsApp.",
        creado_por_id=vet_id
    )
    # Vacuna para Luna vencida hace 2 días (¡alerta roja en Dashboard!)
    v2 = VacunaMascota(
        mascota_id=mascotas[1].id, tutor_id=tutores[1].id, veterinario_id=vet_id,
        nombre_vacuna="Hexavalente Canina (Nobivac DHPPi+L)", lote="LOT-HEX-998", laboratorio="MSD Animal Health",
        dosis="1 ml SC", fecha_aplicacion=hoy - timedelta(days=367), fecha_proxima=hoy - timedelta(days=2),
        observaciones="Dosis vencida. Tutor contactable por WhatsApp para agendar turno.",
        creado_por_id=vet_id
    )
    # Vacuna al día para Milo (Siamés)
    v3 = VacunaMascota(
        mascota_id=mascotas[2].id, tutor_id=tutores[2].id, veterinario_id=vet_id,
        nombre_vacuna="Triple Felina + Leucemia", lote="LOT-FEL-402", laboratorio="Zoetis",
        dosis="1 ml SC", fecha_aplicacion=hoy - timedelta(days=60), fecha_proxima=hoy + timedelta(days=305),
        observaciones="Vacunación al día, excelente tolerancia.",
        creado_por_id=vet_id
    )
    db.session.add_all([v1, v2, v3])

    # Desparasitaciones
    d1 = DesparasitacionMascota(
        mascota_id=mascotas[0].id, tutor_id=tutores[0].id, veterinario_id=vet_id,
        producto="NexGard Spectra", tipo="ambos", dosis="1 tableta masticable", peso_kg=Decimal("32.0"),
        fecha_aplicacion=hoy - timedelta(days=20), fecha_proxima=hoy + timedelta(days=10),
        observaciones="Protección interna y externa activa.", creado_por_id=vet_id
    )
    db.session.add(d1)
    db.session.commit()
    print("[10/12] Vacunas y desparasitaciones con alertas preventivas cargadas.")

    # 11. Agenda de Citas, Hospitalización, Cirugía y SPA
    # Citas médicas generales
    ahora_bog = obtener_hora_bogota()
    cita_hoy_1 = Cita(
        mascota_id=mascotas[0].id, tutor_id=tutores[0].id, profesional_id=vet_id,
        tipo="vacunacion", fecha_hora=ahora_bog.replace(hour=10, minute=0, second=0), duracion_minutos=30,
        estado="confirmada", motivo="Aplicación de vacuna antirrábica y chequeo",
        notas="El tutor solicitó confirmación por WhatsApp temprano.", recordatorio_enviado=True, creado_por_id=admin_id
    )
    cita_hoy_2 = Cita(
        mascota_id=mascotas[1].id, tutor_id=tutores[1].id, profesional_id=vet_id,
        tipo="control", fecha_hora=ahora_bog.replace(hour=11, minute=30, second=0), duracion_minutos=30,
        estado="programada", motivo="Control de evolución de otitis externa",
        notas="Revisar citología de control.", recordatorio_enviado=False, creado_por_id=admin_id
    )
    cita_manana = Cita(
        mascota_id=mascotas[3].id, tutor_id=tutores[3].id, profesional_id=vet_id,
        tipo="consulta", fecha_hora=(ahora_bog + timedelta(days=1)).replace(hour=15, minute=0, second=0), duracion_minutos=45,
        estado="programada", motivo="Revisión general y desparasitación", recordatorio_enviado=False, creado_por_id=admin_id
    )
    db.session.add_all([cita_hoy_1, cita_hoy_2, cita_manana])

    # Cita SPA
    spa_cita_hoy = CitaSpa(
        mascota_id=mascotas[0].id, tutor_id=tutores[0].id, groomer_id=usuarios["groomer"].id,
        servicio_spa_id=servicios_spa[0].id, fecha_hora=ahora_bog.replace(hour=14, minute=0, second=0), duracion_minutos=90,
        estado="en_proceso", notas_ingreso="Tutor pide corte no muy pegado y perfume cítrico. Mascota muy dócil.",
        notificado_whatsapp=False, creado_por_id=admin_id
    )
    db.session.add(spa_cita_hoy)

    # Hospitalización activa: Rocky (Pastor Alemán)
    hosp = Hospitalizacion(
        mascota_id=mascotas[5].id, tutor_id=tutores[5].id, veterinario_responsable_id=vet_id,
        fecha_ingreso=ahora_bog - timedelta(hours=18), motivo="Gastroenteritis hemorrágica aguda y deshidratación moderada (7%)",
        diagnostico="Gastroenteritis aguda probablemente infecciosa en tratamiento de soporte hidroelectrolítico",
        jaula="Jaula 02 - Cuidados Intensivos", estado="activa", costo_dia=Decimal("110000"),
        creado_por_id=vet_id
    )
    db.session.add(hosp)
    db.session.flush()

    # Evolución hospitalaria
    evo = EvolucionHospitalaria(
        hospitalizacion_id=hosp.id, usuario_id=vet_id, fecha_hora=ahora_bog - timedelta(hours=4),
        constantes="T: 38.3 °C | FC: 88 lpm | FR: 20 rpm | Mucosas: rosadas húmedas | TLLC: 1 seg",
        tratamiento_aplicado="Lactato de Ringer 120 ml/h IV + Ranitidina 2mg/kg + Ondansetrón 0.2mg/kg IV",
        observaciones="Paciente alerta, tolera fluidoterapia sin vómitos en las últimas 8 horas. No ha presentado nuevas deposiciones líquidas.",
        alimentacion="Dieta blanda gastrointestinal en pequeñas porciones", eliminaciones="Micción positiva, sin heces recientes"
    )
    db.session.add(evo)

    # Cirugía programada
    cirugia = Cirugia(
        mascota_id=mascotas[1].id, tutor_id=tutores[1].id, veterinario_id=vet_id,
        tipo_procedimiento="Ovariohisterectomía profiláctica (Esterilización)",
        fecha=ahora_bog + timedelta(days=3), consentimiento_firmado=True,
        notas_prequirurgicas="Ayuno de 8 horas de sólidos y 4 de líquidos. Exámenes prequirúrgicos normales (hemograma y perfil bioquímico en rango).",
        protocolo_anestesico="Premedicación: Acepromacina + Tramadol. Inducción: Propofol. Mantenimiento: Isoflurano.",
        creado_por_id=vet_id
    )
    db.session.add(cirugia)

    # Examen de Laboratorio
    lab = ExamenLaboratorio(
        mascota_id=mascotas[5].id, consulta_id=c1.id, solicitado_por_id=vet_id,
        tipo_examen="Hemograma Automatizado + Bioquímica Sanguínea (Creatinina, ALT, FA)",
        fecha_toma=ahora_bog - timedelta(days=1), laboratorio_externo="Laboratorio Clínico Veterinario VetLab",
        interpretacion="Leucocitos levemente elevados (16.500) con neutrofilia moderada compatible con proceso inflamatorio agudo. Función renal y hepática en rangos normales.",
        estado="con_resultado"
    )
    db.session.add(lab)

    # Gastos Operativos
    g1 = Gasto(usuario_id=admin_id, tipo_gasto="indirecto", categoria="arriendo", descripcion="Canon de arrendamiento sede principal Usaquén", monto=Decimal("3800000"), fecha_gasto=hoy - timedelta(days=5))
    g2 = Gasto(usuario_id=admin_id, tipo_gasto="indirecto", categoria="servicios_publicos", descripcion="Factura Enel Codensa energía eléctrica y Acueducto", monto=Decimal("495000"), fecha_gasto=hoy - timedelta(days=4))
    g3 = Gasto(usuario_id=admin_id, tipo_gasto="diario", categoria="insumos", descripcion="Compra de gasas, jeringas 3ml, catéteres y alcohol antiséptico", monto=Decimal("185000"), fecha_gasto=hoy - timedelta(days=1))
    db.session.add_all([g1, g2, g3])
    db.session.commit()
    print("[11/12] Agenda, hospitalización, cirugías, laboratorio y gastos registrados.")

    # 12. Turno de Caja Abierto y Ventas POS
    cajero_id = usuarios["cajero"].id
    turno = TurnoCaja(
        usuario_id=cajero_id, monto_apertura=Decimal("200000"),
        estado="abierto", fecha_apertura=ahora_bog.replace(hour=8, minute=0, second=0),
        notas_apertura="Apertura turno de mañana con base en billetes y monedas fraccionarias de $200.000."
    )
    db.session.add(turno)
    db.session.flush()

    # Venta 1: Productos POS (NexGard + Royal Canin)
    p_nexgard = productos[0]
    p_royal = productos[2]
    v1_sub = p_nexgard.precio_sugerido + p_royal.precio_sugerido
    v1 = Venta(
        numero_factura="FAC-0001", turno_caja_id=turno.id, tutor_id=tutores[0].id, mascota_id=mascotas[0].id,
        usuario_id=cajero_id, subtotal=v1_sub, descuento_monto=Decimal("0"), impuesto_monto=Decimal("0"),
        total=v1_sub, estado="completada", fecha_venta=ahora_bog.replace(hour=9, minute=15, second=0)
    )
    db.session.add(v1)
    db.session.flush()

    db.session.add(DetalleVenta(
        venta_id=v1.id, producto_id=p_nexgard.id, descripcion=p_nexgard.nombre,
        tipo_item="producto", cantidad=Decimal("1"), precio_unitario=p_nexgard.precio_sugerido,
        subtotal=p_nexgard.precio_sugerido, descuento=Decimal("0"), total_linea=p_nexgard.precio_sugerido
    ))
    db.session.add(DetalleVenta(
        venta_id=v1.id, producto_id=p_royal.id, descripcion=p_royal.nombre,
        tipo_item="producto", cantidad=Decimal("1"), precio_unitario=p_royal.precio_sugerido,
        subtotal=p_royal.precio_sugerido, descuento=Decimal("0"), total_linea=p_royal.precio_sugerido
    ))
    db.session.add(PagoVenta(
        venta_id=v1.id, metodo_pago="tarjeta_debito", monto=v1_sub,
        referencia_transaccion="RED-BAN-884920", fecha_pago=v1.fecha_venta
    ))

    # Venta 2: Servicio SPA en efectivo
    s_spa = servicios_spa[1]
    v2 = Venta(
        numero_factura="FAC-0002", turno_caja_id=turno.id, tutor_id=tutores[1].id, mascota_id=mascotas[1].id,
        usuario_id=cajero_id, subtotal=s_spa.precio_sugerido, descuento_monto=Decimal("0"), impuesto_monto=Decimal("0"),
        total=s_spa.precio_sugerido, estado="completada", fecha_venta=ahora_bog.replace(hour=10, minute=40, second=0)
    )
    db.session.add(v2)
    db.session.flush()
    db.session.add(DetalleVenta(
        venta_id=v2.id, producto_id=None, descripcion=s_spa.nombre,
        tipo_item="servicio", cantidad=Decimal("1"), precio_unitario=s_spa.precio_sugerido,
        subtotal=s_spa.precio_sugerido, descuento=Decimal("0"), total_linea=s_spa.precio_sugerido
    ))
    db.session.add(PagoVenta(
        venta_id=v2.id, metodo_pago="efectivo", monto=s_spa.precio_sugerido,
        referencia_transaccion="EFECTIVO-CAJA", fecha_pago=v2.fecha_venta
    ))

    # Venta 3: Nequi
    p_shampoo = productos[7]
    v3 = Venta(
        numero_factura="FAC-0003", turno_caja_id=turno.id, tutor_id=tutores[2].id, mascota_id=mascotas[2].id,
        usuario_id=cajero_id, subtotal=p_shampoo.precio_sugerido, descuento_monto=Decimal("0"), impuesto_monto=Decimal("0"),
        total=p_shampoo.precio_sugerido, estado="completada", fecha_venta=ahora_bog.replace(hour=11, minute=20, second=0)
    )
    db.session.add(v3)
    db.session.flush()
    db.session.add(DetalleVenta(
        venta_id=v3.id, producto_id=p_shampoo.id, descripcion=p_shampoo.nombre,
        tipo_item="producto", cantidad=Decimal("1"), precio_unitario=p_shampoo.precio_sugerido,
        subtotal=p_shampoo.precio_sugerido, descuento=Decimal("0"), total_linea=p_shampoo.precio_sugerido
    ))
    db.session.add(PagoVenta(
        venta_id=v3.id, metodo_pago="nequi", monto=p_shampoo.precio_sugerido,
        referencia_transaccion="NEQ-M18492048", fecha_pago=v3.fecha_venta
    ))

    db.session.commit()
    print("[12/12] Turno de caja y ventas POS completadas con diferentes métodos de pago.")

    print("\n=================================================================")
    print("¡CARGA DE DATOS DE DEMOSTRACIÓN EXITOSA!")
    print("=================================================================")
    print("Credenciales de acceso creadas:")
    print(" 1. Administrador:")
    print("    - Correo:     admin@sandiavet.com")
    print("    - Contraseña: Admin123456*")
    print(" 2. Médica Veterinaria:")
    print("    - Correo:     veterinaria@sandiavet.com")
    print("    - Contraseña: Vet123456*")
    print(" 3. Cajero / Facturación:")
    print("    - Correo:     cajero@sandiavet.com")
    print("    - Contraseña: Caja123456*")
    print(" 4. Spa & Grooming:")
    print("    - Correo:     spa@sandiavet.com")
    print("    - Contraseña: Spa123456*")
    print("=================================================================")
