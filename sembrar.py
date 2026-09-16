"""Script para sembrar datos de prueba completos y realistas en todos los módulos de VetCare.

Cubre:
1. Usuarios y roles (admin, veterinario, auxiliar, groomer, cajero, recepcion)
2. Razas (caninos y felinos)
3. Tutores y Mascotas con historial de pesos
4. Proveedores, Productos, Variantes, Lotes FEFO y Movimientos de Stock
5. Servicios de Spa y Citas de Spa (hoy y recientes)
6. Turnos de Caja, Ventas con factura correlativa, pagos y Aprobaciones de precio
7. Historias Clínicas SOAP completas, Enmiendas, Vacunación y Desparasitación
8. Agenda Médica General (Citas médicas)
9. Hospitalizaciones con evoluciones horarias y Cirugías con protocolo
10. Exámenes de Laboratorio con resultados interpretados
11. Gastos de operación clínica
12. Cartera de Tutores a crédito y Facturas por pagar a Proveedores
"""

import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app import create_app
from models import (
    AbonoCuentaTutor,
    AprobacionPrecio,
    Cirugia,
    Cita,
    CitaSpa,
    ConfiguracionSistema,
    ConsultaMedica,
    CuentaTutor,
    DesparasitacionMascota,
    DetalleVenta,
    EnmiendaConsulta,
    EvolucionHospitalaria,
    ExamenLaboratorio,
    FacturaProveedor,
    Gasto,
    Hospitalizacion,
    Lote,
    Mascota,
    MovimientoStock,
    PagoProveedor,
    PagoVenta,
    Producto,
    Proveedor,
    Raza,
    RegistroPeso,
    ServicioSpa,
    TurnoCaja,
    Tutor,
    Usuario,
    VacunaMascota,
    VarianteProducto,
    Venta,
    db,
)
from utils import ZONA_BOGOTA, hoy_bogota, obtener_hora_bogota


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def sembrar():
    app = create_app()
    with app.app_context():
        print("[*] Iniciando siembra de datos de prueba en VetCare...")
        ahora = obtener_hora_bogota()
        hoy = hoy_bogota()

        # -------------------------------------------------------------------
        # 1. Usuarios con todos los roles
        # -------------------------------------------------------------------
        print("  -> Creando usuarios para todos los roles...")
        usuarios_data = [
            ("Administrador Principal", "admin@sandia.com", "admin", "3105550001", None, None, None),
            ("Dra. Daniela Pulido", "veterinario@sandia.com", "veterinario", "3105550002", "53214", "Médica veterinaria", "Dpl. Dermatología de pequeñas especies"),
            ("Andrés Castro", "auxiliar@sandia.com", "auxiliar", "3105550003", None, None, None),
            ("Valentina Ríos", "groomer@sandia.com", "groomer", "3105550004", None, None, None),
            ("Mateo Gómez", "cajero@sandia.com", "cajero", "3105550005", None, None, None),
            ("Sofía Herrera", "recepcion@sandia.com", "recepcion", "3105550006", None, None, None),
        ]
        usuarios_dict = {}
        for nombre, email, rol, tel, tp, titulo, esp in usuarios_data:
            u = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one_or_none()
            if not u:
                u = Usuario(
                    nombre=nombre,
                    email=email,
                    rol=rol,
                    telefono=tel,
                    tarjeta_profesional=tp,
                    titulo_profesional=titulo,
                    especialidad=esp,
                    activo=True,
                )
                u.establecer_password("Sandia2026*")
                db.session.add(u)
                db.session.flush()
            else:
                if rol == "veterinario":
                    u.nombre = nombre
                    u.tarjeta_profesional = tp
                    u.titulo_profesional = titulo
                    u.especialidad = esp
                    db.session.flush()
            usuarios_dict[rol] = u

        admin = usuarios_dict["admin"]
        vet = usuarios_dict["veterinario"]
        aux = usuarios_dict["auxiliar"]
        groomer = usuarios_dict["groomer"]
        cajero = usuarios_dict["cajero"]
        recep = usuarios_dict["recepcion"]

        # -------------------------------------------------------------------
        # 2. Razas
        # -------------------------------------------------------------------
        print("  -> Verificando y creando catálogo de razas...")
        razas_data = [
            ("canino", "Golden Retriever"),
            ("canino", "Bulldog Francés"),
            ("canino", "Beagle"),
            ("canino", "Schnauzer"),
            ("canino", "Pomerania"),
            ("canino", "Poodle"),
            ("canino", "Pastor Alemán"),
            ("canino", "Criollo Canino"),
            ("canino", "Labrador Retriever"),
            ("canino", "Chihuahua"),
            ("felino", "Siamés"),
            ("felino", "Persa"),
            ("felino", "Maine Coon"),
            ("felino", "Bengala"),
            ("felino", "Criollo Felino"),
        ]
        razas_dict = {}
        for especie, nombre in razas_data:
            r = db.session.execute(db.select(Raza).filter_by(especie=especie, nombre=nombre)).scalar_one_or_none()
            if not r:
                r = Raza(especie=especie, nombre=nombre, activo=True)
                db.session.add(r)
                db.session.flush()
            razas_dict[(especie, nombre)] = r

        # -------------------------------------------------------------------
        # 3. Tutores
        # -------------------------------------------------------------------
        print("  -> Creando tutores colombianos...")
        tutores_data = [
            ("Carlos Alberto Restrepo", "CC", "79845123", "3105551122", "carlos.restrepo@correo.com", "Calle 72 # 11-45", "Bogotá"),
            ("María Paula Gómez", "CC", "52412987", "3154443322", "mpaula.gomez@correo.com", "Carrera 15 # 104-20", "Bogotá"),
            ("Jorge Enrique Martínez", "CC", "80123456", "3208889900", "jorge.martinez@correo.com", "Calle 140 # 19-30", "Bogotá"),
            ("Andrea Carolina Silva", "CC", "1018456789", "3112224455", "andrea.silva@correo.com", "Calle 45 # 22-10", "Bogotá"),
            ("Juan David Rodríguez", "CC", "1020789123", "3187776655", "juand.rodriguez@correo.com", "Carrera 91 # 145-60", "Bogotá"),
            ("Diana Marcela Ortiz", "CC", "53012345", "3123334455", "diana.ortiz@correo.com", "Avenida Esperanza # 68-12", "Bogotá"),
        ]
        tutores_objs = []
        for nom, tipo_doc, num_doc, tel, email, dir_, ciudad in tutores_data:
            t = db.session.execute(db.select(Tutor).filter_by(numero_documento=num_doc)).scalar_one_or_none()
            if not t:
                t = Tutor(
                    nombre_completo=nom,
                    tipo_documento=tipo_doc,
                    numero_documento=num_doc,
                    telefono=tel,
                    whatsapp=tel,
                    email=email,
                    direccion=dir_,
                    barrio="Urbano",
                    activo=True,
                )
                db.session.add(t)
                db.session.flush()
            tutores_objs.append(t)

        # -------------------------------------------------------------------
        # 4. Mascotas con Pesos Históricos
        # -------------------------------------------------------------------
        print("  -> Creando mascotas y curvas de peso...")
        mascotas_data = [
            (tutores_objs[0], "Lucas", "canino", razas_dict[("canino", "Golden Retriever")], "macho", hoy - timedelta(days=365 * 3), "Dorado", "grande", True, "Alergia a picadura de pulgas", "981098102345671", [Decimal("26.00"), Decimal("27.30"), Decimal("28.50")]),
            (tutores_objs[1], "Mia", "felino", razas_dict[("felino", "Siamés")], "hembra", hoy - timedelta(days=365 * 2), "Foca point", "pequeno", True, None, "981098102345672", [Decimal("3.20"), Decimal("3.50"), Decimal("3.80")]),
            (tutores_objs[2], "Max", "canino", razas_dict[("canino", "Bulldog Francés")], "macho", hoy - timedelta(days=500), "Fawn / Leonado", "mediano", False, "Sensible a cambios de concentrado", "981098102345673", [Decimal("11.50"), Decimal("12.00"), Decimal("12.40")]),
            (tutores_objs[3], "Luna", "felino", razas_dict[("felino", "Criollo Felino")], "hembra", hoy - timedelta(days=400), "Carey", "pequeno", True, None, "981098102345674", [Decimal("3.80"), Decimal("4.00"), Decimal("4.20")]),
            (tutores_objs[4], "Toby", "canino", razas_dict[("canino", "Beagle")], "macho", hoy - timedelta(days=365 * 4), "Tricolor", "mediano", True, None, "981098102345675", [Decimal("14.20"), Decimal("14.80"), Decimal("15.10")]),
            (tutores_objs[5], "Simba", "felino", razas_dict[("felino", "Persa")], "macho", hoy - timedelta(days=365 * 1), "Blanco", "pequeno", False, None, "981098102345676", [Decimal("4.10"), Decimal("4.30"), Decimal("4.50")]),
            (tutores_objs[0], "Rocky", "canino", razas_dict[("canino", "Schnauzer")], "macho", hoy - timedelta(days=365 * 5), "Sal y pimienta", "pequeno", True, None, "981098102345677", [Decimal("7.20"), Decimal("7.50"), Decimal("7.80")]),
            (tutores_objs[1], "Nala", "canino", razas_dict[("canino", "Criollo Canino")], "hembra", hoy - timedelta(days=600), "Caramelo", "mediano", True, None, "981098102345678", [Decimal("17.50"), Decimal("18.00"), Decimal("18.20")]),
        ]
        mascotas_objs = []
        for tutor, nom, esp, raza, sexo, f_nac, color, tam, est, alerg, chip, pesos in mascotas_data:
            m = db.session.execute(db.select(Mascota).filter_by(nombre=nom, tutor_id=tutor.id)).scalar_one_or_none()
            if not m:
                m = Mascota(
                    tutor_id=tutor.id,
                    nombre=nom,
                    especie=esp,
                    raza_id=raza.id if raza else None,
                    sexo=sexo,
                    fecha_nacimiento=f_nac,
                    color=color,
                    tamano=tam,
                    esterilizado=est,
                    alergias=alerg,
                    microchip=chip,
                    activo=True,
                    fallecido=False,
                    creado_por_id=admin.id,
                )
                db.session.add(m)
                db.session.flush()
                # Registrar curva de pesos histórica
                dias_offset = [60, 30, 0]
                for p_val, d_off in zip(pesos, dias_offset):
                    fecha_p = ahora - timedelta(days=d_off)
                    rp = RegistroPeso(
                        mascota_id=m.id,
                        peso_kg=p_val,
                        fecha=fecha_p,
                        registrado_por_id=vet.id,
                    )
                    db.session.add(rp)
            mascotas_objs.append(m)

        lucas, mia, max_m, luna, toby, simba, rocky, nala = mascotas_objs

        # -------------------------------------------------------------------
        # 5. Proveedores
        # -------------------------------------------------------------------
        print("  -> Creando proveedores...")
        proveedores_data = [
            ("Laboratorios Zoetis Colombia SAS", "860001234-1", "6013334455", "contacto@zoetis.com.co", "Bogotá"),
            ("Distribuidora Andina de Mascotas SAS", "900555666-2", "6017778899", "ventas@andina.com.co", "Bogotá"),
            ("Purina PetCare Colombia", "800111222-3", "6014445566", "pedidos@purina.com.co", "Bogotá"),
            ("Virbac Colombia Ltda", "830098765-4", "6015556677", "servicio@virbac.co", "Bogotá"),
        ]
        prov_objs = []
        for nom, nit, tel, email, ciu in proveedores_data:
            p = db.session.execute(db.select(Proveedor).filter_by(nombre=nom)).scalar_one_or_none()
            if not p:
                p = Proveedor(nombre=nom, nit=nit, telefono=tel, email=email, ciudad=ciu, activo=True)
                db.session.add(p)
                db.session.flush()
            prov_objs.append(p)

        zoetis_prov, andina_prov, purina_prov, virbac_prov = prov_objs

        # -------------------------------------------------------------------
        # 6. Inventario: Productos, Variantes, Lotes y Kardex
        # -------------------------------------------------------------------
        print("  -> Sembrando productos, lotes FEFO y stock...")
        prods_data = [
            ("MED-001", "Amoxicilina + Ác. Clavulánico 250mg", "medicamento", "producto", "caja", Decimal("22000.00"), Decimal("30000.00"), Decimal("35000.00"), Decimal("24.00"), Decimal("5.00"), zoetis_prov.id, "AMOX-26A", hoy + timedelta(days=365)),
            ("MED-002", "Meloxicam Gotas 10ml", "medicamento", "producto", "frasco", Decimal("18000.00"), Decimal("24000.00"), Decimal("28000.00"), Decimal("15.00"), Decimal("4.00"), virbac_prov.id, "MELOX-04", hoy + timedelta(days=240)),
            ("VAC-001", "Vacuna Canina Séxtuple Nobivac", "medicamento", "producto", "dosis", Decimal("25000.00"), Decimal("35000.00"), Decimal("42000.00"), Decimal("30.00"), Decimal("6.00"), zoetis_prov.id, "NOBI-77", hoy + timedelta(days=180)),
            ("VAC-002", "Vacuna Antirrábica Defensor 3", "medicamento", "producto", "dosis", Decimal("15000.00"), Decimal("22000.00"), Decimal("26000.00"), Decimal("40.00"), Decimal("8.00"), zoetis_prov.id, "DEF-99", hoy + timedelta(days=270)),
            ("VAC-003", "Vacuna Triple Felina Felocell", "medicamento", "producto", "dosis", Decimal("28000.00"), Decimal("38000.00"), Decimal("45000.00"), Decimal("20.00"), Decimal("5.00"), zoetis_prov.id, "FELO-12", hoy + timedelta(days=210)),
            ("ALM-001", "Pro Plan Puppy Razas Medianas 15kg", "alimento", "producto", "bulto", Decimal("190000.00"), Decimal("235000.00"), Decimal("260000.00"), Decimal("8.00"), Decimal("3.00"), purina_prov.id, "PP-889", hoy + timedelta(days=300)),
            ("ALM-002", "Royal Canin Urinary S/O Feline 2kg", "alimento", "producto", "unidad", Decimal("75000.00"), Decimal("95000.00"), Decimal("110000.00"), Decimal("2.00"), Decimal("5.00"), andina_prov.id, "RC-402", hoy + timedelta(days=120)),  # Stock crítico
            ("HIG-001", "Shampoo Antiséptico Clorhexidina 250ml", "higiene", "producto", "frasco", Decimal("16000.00"), Decimal("22000.00"), Decimal("26000.00"), Decimal("18.00"), Decimal("5.00"), virbac_prov.id, "CLOR-10", hoy + timedelta(days=400)),
            ("ACC-001", "Collar Antipulgas Seresto Perros Grandes", "accesorio", "producto", "unidad", Decimal("110000.00"), Decimal("145000.00"), Decimal("165000.00"), Decimal("1.00"), Decimal("4.00"), andina_prov.id, "SER-01", hoy + timedelta(days=500)),  # Stock crítico
            ("MED-003", "Suero Hartman 500ml Inyectable", "medicamento", "producto", "frasco", Decimal("8000.00"), Decimal("12000.00"), Decimal("15000.00"), Decimal("12.00"), Decimal("4.00"), andina_prov.id, "HART-09", hoy + timedelta(days=9)),  # ¡Lote próximo a vencer en 9 días!
            ("SRV-001", "Consulta Médica General", "servicio", "servicio", "unidad", Decimal("0.00"), Decimal("40000.00"), Decimal("45000.00"), Decimal("0.00"), Decimal("0.00"), None, None, None),
            ("SRV-002", "Profilaxis Dental Canina", "servicio", "servicio", "unidad", Decimal("20000.00"), Decimal("120000.00"), Decimal("140000.00"), Decimal("0.00"), Decimal("0.00"), None, None, None),
        ]
        productos_dict = {}
        for sku, nom, cat, tipo, un, costo, p_min, p_sug, stock, s_min, prov_id, num_lote, f_venc in prods_data:
            prod = db.session.execute(db.select(Producto).filter_by(sku=sku)).scalar_one_or_none()
            if not prod:
                prod = Producto(
                    sku=sku,
                    nombre=nom,
                    categoria=cat,
                    tipo=tipo,
                    unidad_medida=un,
                    precio_costo=costo,
                    precio_minimo=p_min,
                    precio_sugerido=p_sug,
                    cantidad_stock=stock,
                    stock_minimo=s_min,
                    proveedor_id=prov_id,
                    activo=True,
                )
                db.session.add(prod)
                db.session.flush()

                # Crear lote si aplica
                if num_lote and f_venc:
                    lote = Lote(
                        producto_id=prod.id,
                        numero_lote=num_lote,
                        fecha_vencimiento=f_venc,
                        cantidad_inicial=stock,
                        cantidad_disponible=stock,
                        proveedor_id=prov_id,
                        creado_por_id=admin.id,
                    )
                    db.session.add(lote)
                    db.session.flush()

                # Registrar movimiento inicial
                if stock > 0:
                    mov = MovimientoStock(
                        producto_id=prod.id,
                        tipo_movimiento="inicial",
                        cantidad=stock,
                        stock_anterior=Decimal("0.00"),
                        stock_nuevo=stock,
                        usuario_id=admin.id,
                        motivo="Carga inicial de inventario",
                    )
                    db.session.add(mov)

            productos_dict[sku] = prod

        # Producto con Variantes: Nexgard Spectra
        prod_nex = db.session.execute(db.select(Producto).filter_by(sku="PAR-001")).scalar_one_or_none()
        if not prod_nex:
            prod_nex = Producto(
                sku="PAR-001",
                nombre="Nexgard Spectra Antiparasitario",
                categoria="medicamento",
                tipo="producto",
                unidad_medida="tableta",
                precio_costo=Decimal("28000.00"),
                precio_minimo=Decimal("38000.00"),
                precio_sugerido=Decimal("45000.00"),
                cantidad_stock=Decimal("25.00"),
                stock_minimo=Decimal("5.00"),
                proveedor_id=zoetis_prov.id,
                activo=True,
            )
            db.session.add(prod_nex)
            db.session.flush()

            variantes_data = [
                ("Perros 2 a 3.5 kg", "PAR-001-XS", Decimal("28000.00"), Decimal("38000.00"), Decimal("45000.00"), Decimal("8.00")),
                ("Perros 3.6 a 7.5 kg", "PAR-001-S", Decimal("32000.00"), Decimal("42000.00"), Decimal("49000.00"), Decimal("10.00")),
                ("Perros 7.6 a 15 kg", "PAR-001-M", Decimal("36000.00"), Decimal("46000.00"), Decimal("54000.00"), Decimal("7.00")),
            ]
            for v_nom, v_sku, v_costo, v_min, v_sug, v_stock in variantes_data:
                var = VarianteProducto(
                    producto_id=prod_nex.id,
                    nombre_variante=v_nom,
                    sku=v_sku,
                    precio_costo=v_costo,
                    precio_minimo=v_min,
                    precio_sugerido=v_sug,
                    cantidad_stock=v_stock,
                    activo=True,
                )
                db.session.add(var)

        # -------------------------------------------------------------------
        # 7. Servicios de Spa y Citas de Spa
        # -------------------------------------------------------------------
        print("  -> Configurando Spa & Grooming...")
        spa_servicios_data = [
            ("Baño Básico & Secado", "Baño relajante con shampoo nutritivo, secado suave y cepillado", 45, Decimal("35000.00")),
            ("Baño Medicado Hipoalergénico", "Tratamiento dermatológico con shampoo antiséptico y humectante", 60, Decimal("55000.00")),
            ("Corte de Raza & Spa Completo", "Corte especializado según estándar de la raza, arreglo higiénico y perfume", 90, Decimal("70000.00")),
            ("Deslanado Profundo & Cepillado", "Retiro de subpelo muerto y nudos para razas de pelo denso", 60, Decimal("50000.00")),
            ("Limpieza de Oídos y Corte de Uñas", "Aseo auricular profiláctico y corte/limado de uñas", 30, Decimal("25000.00")),
        ]
        spa_srv_objs = []
        for s_nom, s_desc, s_dur, s_prec in spa_servicios_data:
            srv = db.session.execute(db.select(ServicioSpa).filter_by(nombre=s_nom)).scalar_one_or_none()
            if not srv:
                srv = ServicioSpa(
                    nombre=s_nom,
                    descripcion=s_desc,
                    duracion_minutos=s_dur,
                    precio_sugerido=s_prec,
                    activo=True,
                )
                db.session.add(srv)
                db.session.flush()
            spa_srv_objs.append(srv)

        # Citas de Spa para hoy y recientes
        citas_spa_data = [
            (lucas, tutores_objs[0], spa_srv_objs[2], groomer.id, ahora.replace(hour=9, minute=0), "en_proceso", "Corte estándar Golden, desenredar patas traseras"),
            (max_m, tutores_objs[2], spa_srv_objs[1], groomer.id, ahora.replace(hour=11, minute=30), "listo_recogida", "Baño con clorhexidina por recomendación médica"),
            (mia, tutores_objs[1], spa_srv_objs[3], groomer.id, ahora.replace(hour=14, minute=0), "programada", "Tratar con suavidad, sensible al ruido del soplador"),
            (toby, tutores_objs[4], spa_srv_objs[0], groomer.id, ahora - timedelta(days=1, hours=2), "entregado", "Baño impecable, tutor satisfecho"),
        ]
        for masc, tut, srv, gr_id, f_hora, est, obs in citas_spa_data:
            c_spa = db.session.execute(db.select(CitaSpa).filter_by(mascota_id=masc.id, fecha_hora=f_hora)).scalar_one_or_none()
            if not c_spa:
                c_spa = CitaSpa(
                    mascota_id=masc.id,
                    tutor_id=tut.id,
                    servicio_spa_id=srv.id,
                    groomer_id=gr_id,
                    fecha_hora=f_hora,
                    duracion_minutos=srv.duracion_minutos,
                    estado=est,
                    notas_ingreso=obs,
                    creado_por_id=recep.id,
                )
                db.session.add(c_spa)

        # -------------------------------------------------------------------
        # 8. Caja & Punto de Venta (POS)
        # -------------------------------------------------------------------
        print("  -> Creando turnos de caja, ventas y solicitudes de precio...")
        # Turno de ayer cerrado
        turno_ayer = db.session.execute(db.select(TurnoCaja).filter_by(usuario_id=cajero.id, estado="cerrada")).scalar_one_or_none()
        if not turno_ayer:
            turno_ayer = TurnoCaja(
                usuario_id=cajero.id,
                monto_apertura=Decimal("50000.00"),
                monto_cierre_esperado=Decimal("280000.00"),
                monto_cierre_real=Decimal("280000.00"),
                diferencia=Decimal("0.00"),
                estado="cerrada",
                fecha_apertura=ahora - timedelta(days=1, hours=8),
                fecha_cierre=ahora - timedelta(days=1),
                notas_apertura="Apertura con base en efectivo normal",
                notas_cierre="Cierre perfecto sin novedades",
            )
            db.session.add(turno_ayer)
            db.session.flush()

        # Turno de hoy ABIERTO
        turno_hoy = db.session.execute(db.select(TurnoCaja).filter_by(usuario_id=admin.id, estado="abierta")).scalar_one_or_none()
        if not turno_hoy:
            turno_hoy = TurnoCaja(
                usuario_id=admin.id,
                monto_apertura=Decimal("100000.00"),
                estado="abierta",
                fecha_apertura=ahora.replace(hour=8, minute=0),
                notas_apertura="Apertura turno matutino principal",
            )
            db.session.add(turno_hoy)
            db.session.flush()

        # Ventas de hoy
        hoy_str = hoy.strftime("%Y%m%d")
        f1_num = f"VET-{hoy_str}-0001"
        v1 = db.session.execute(db.select(Venta).filter_by(numero_factura=f1_num)).scalar_one_or_none()
        if not v1:
            p_proplan = productos_dict["ALM-001"]
            p_melo = productos_dict["MED-002"]
            total_v1 = p_proplan.precio_sugerido + p_melo.precio_sugerido
            v1 = Venta(
                numero_factura=f1_num,
                turno_caja_id=turno_hoy.id,
                tutor_id=tutores_objs[0].id,
                mascota_id=lucas.id,
                usuario_id=admin.id,
                subtotal=total_v1,
                descuento_monto=Decimal("0.00"),
                impuesto_monto=Decimal("0.00"),
                total=total_v1,
                estado="completada",
                fecha_venta=ahora.replace(hour=9, minute=45),
            )
            db.session.add(v1)
            db.session.flush()

            d1 = DetalleVenta(
                venta_id=v1.id,
                producto_id=p_proplan.id,
                descripcion=p_proplan.nombre,
                cantidad=Decimal("1.00"),
                precio_unitario=p_proplan.precio_sugerido,
                subtotal=p_proplan.precio_sugerido,
                total_linea=p_proplan.precio_sugerido,
            )
            d2 = DetalleVenta(
                venta_id=v1.id,
                producto_id=p_melo.id,
                descripcion=p_melo.nombre,
                cantidad=Decimal("1.00"),
                precio_unitario=p_melo.precio_sugerido,
                subtotal=p_melo.precio_sugerido,
                total_linea=p_melo.precio_sugerido,
            )
            pago1 = PagoVenta(venta_id=v1.id, metodo_pago="tarjeta_debito", monto=total_v1)
            db.session.add_all([d1, d2, pago1])

        # Venta 2: Consulta Médica
        f2_num = f"VET-{hoy_str}-0002"
        v2 = db.session.execute(db.select(Venta).filter_by(numero_factura=f2_num)).scalar_one_or_none()
        if not v2:
            p_srv = productos_dict["SRV-001"]
            total_v2 = p_srv.precio_sugerido
            v2 = Venta(
                numero_factura=f2_num,
                turno_caja_id=turno_hoy.id,
                tutor_id=tutores_objs[1].id,
                mascota_id=mia.id,
                usuario_id=admin.id,
                subtotal=total_v2,
                descuento_monto=Decimal("0.00"),
                impuesto_monto=Decimal("0.00"),
                total=total_v2,
                estado="completada",
                fecha_venta=ahora.replace(hour=10, minute=15),
            )
            db.session.add(v2)
            db.session.flush()
            d_srv = DetalleVenta(
                venta_id=v2.id,
                producto_id=p_srv.id,
                descripcion=p_srv.nombre,
                cantidad=Decimal("1.00"),
                precio_unitario=total_v2,
                subtotal=total_v2,
                total_linea=total_v2,
            )
            pago2 = PagoVenta(venta_id=v2.id, metodo_pago="efectivo", monto=total_v2)
            db.session.add_all([d_srv, pago2])

        # Aprobaciones de precio
        aprob_exist = db.session.execute(db.select(AprobacionPrecio)).scalars().first()
        if not aprob_exist:
            # 1. Aprobada
            p_proplan = productos_dict["ALM-001"]
            ap1 = AprobacionPrecio(
                solicitante_id=cajero.id,
                admin_id=admin.id,
                producto_id=p_proplan.id,
                descripcion=f"Descuento especial {p_proplan.nombre}",
                precio_original=p_proplan.precio_minimo,
                precio_solicitado=Decimal("230000.00"),
                precio_aprobado=Decimal("230000.00"),
                estado="aprobado",
                motivo="Cliente frecuente de más de 3 años",
                fecha_solicitud=ahora - timedelta(hours=3),
                fecha_resolucion=ahora - timedelta(hours=2, minutes=50),
            )
            # 2. Pendiente
            p_seresto = productos_dict["ACC-001"]
            ap2 = AprobacionPrecio(
                solicitante_id=cajero.id,
                producto_id=p_seresto.id,
                descripcion=f"Solicitud descuento {p_seresto.nombre}",
                precio_original=p_seresto.precio_minimo,
                precio_solicitado=Decimal("138000.00"),
                estado="pendiente",
                motivo="Cliente lleva 2 unidades y solicita precio por mayor",
                fecha_solicitud=ahora - timedelta(minutes=25),
            )
            db.session.add_all([ap1, ap2])

        # -------------------------------------------------------------------
        # 9. Historias Clínicas SOAP, Enmiendas, Vacunas y Desparasitaciones
        # -------------------------------------------------------------------
        print("  -> Creando historias clínicas SOAP y carnets de vacunación...")
        c_med1 = db.session.execute(db.select(ConsultaMedica).filter_by(mascota_id=lucas.id)).scalar_one_or_none()
        if not c_med1:
            c_med1 = ConsultaMedica(
                mascota_id=lucas.id,
                tutor_id=tutores_objs[0].id,
                veterinario_id=vet.id,
                fecha_hora=ahora - timedelta(days=2),
                motivo_consulta="Claudicación de miembro anterior derecho tras salto en parque",
                anamnesis="El tutor refiere que hace 24 horas el paciente resbaló jugando con pelota y desde entonces apoya con dificultad la extremidad.",
                peso_kg=Decimal("28.50"),
                temperatura_c=Decimal("38.6"),
                frecuencia_cardiaca=96,
                frecuencia_respiratoria=22,
                tllc_segundos=2,
                mucosas="rosadas_humedas",
                condicion_corporal="3_ideal",
                examen_sistemas="A la palpación manifiesta dolor moderado en articulación carpal derecha. Sin crepitación ni aumento severo de volumen.",
                diagnostico="Esguince carpal grado I por trauma contuso leve.",
                plan_tratamiento="1. Reposo absoluto por 5 días sin saltos ni ejercicio vigoroso.\n2. Meloxicam gotas: 0.1 mg/kg cada 24 horas por 4 días.\n3. Aplicación de frío local por 10 minutos 2 veces al día.",
                receta_medica="Meloxicam gotas 10ml - Administrar 28 gotas vía oral cada 24 horas con alimento durante 4 días.",
                observaciones="Citar a control en 7 días si persiste la cojera.",
                creado_por_id=vet.id,
            )
            db.session.add(c_med1)
            db.session.flush()

        c_med2 = db.session.execute(db.select(ConsultaMedica).filter_by(mascota_id=max_m.id)).scalar_one_or_none()
        if not c_med2:
            c_med2 = ConsultaMedica(
                mascota_id=max_m.id,
                tutor_id=tutores_objs[2].id,
                veterinario_id=vet.id,
                fecha_hora=ahora - timedelta(days=5),
                motivo_consulta="Prurito intenso en patas y abdomen, lamido constante",
                anamnesis="Tutor indica rascado frecuente desde hace 1 semana, zona ventral eritematosa.",
                peso_kg=Decimal("12.40"),
                temperatura_c=Decimal("38.8"),
                frecuencia_cardiaca=112,
                frecuencia_respiratoria=26,
                tllc_segundos=2,
                mucosas="rosadas",
                condicion_corporal="4_sobrepeso_leve",
                examen_sistemas="Eritema interdigital en 4 miembros y región inguinal. Sin pústulas visibles.",
                diagnostico="Dermatitis atópica / alérgica podal con sobrecrecimiento probable de levaduras.",
                plan_tratamiento="1. Baños medicados 2 veces por semana con shampoo de Clorhexidina.\n2. Limpieza de pliegues faciales y patas a diario.\n3. Solicitar raspado y citología cutánea.",
                creado_por_id=vet.id,
            )
            db.session.add(c_med2)
            db.session.flush()

            # Enmienda clínica legal
            enmienda = EnmiendaConsulta(
                consulta_id=c_med2.id,
                autor_id=vet.id,
                fecha=ahora - timedelta(days=4),
                texto="Adición de recomendación nutricional solicitada por tutor: Se recomienda iniciar transición gradual a concentrado hipoalergénico Royal Canin Hypoallergenic durante 10 días para descartar componente alimentario.",
            )
            db.session.add(enmienda)

        # Vacunas (1 por vencer en 3 días para ver alerta, 1 vencida, 1 al día)
        vacunas_seed = [
            (lucas, tutores_objs[0], "Séxtuple Canina Nobivac DHPPi+L", "Nobivac", "NOB-2025", hoy - timedelta(days=362), hoy + timedelta(days=3), "Próximo refuerzo anual programado"),
            (rocky, tutores_objs[0], "Antirrábica Defensor 3", "Zoetis", "DEF-881", hoy - timedelta(days=370), hoy - timedelta(days=5), "Vacuna vencida - contactar al tutor"),
            (mia, tutores_objs[1], "Triple Felina Felocell", "Zoetis", "FEL-901", hoy - timedelta(days=90), hoy + timedelta(days=275), "Al día con su esquema"),
        ]
        for masc, tut, nom_v, lab, lt, f_ap, f_pr, obs in vacunas_seed:
            v_exist = db.session.execute(db.select(VacunaMascota).filter_by(mascota_id=masc.id, nombre_vacuna=nom_v)).scalar_one_or_none()
            if not v_exist:
                vm = VacunaMascota(
                    mascota_id=masc.id,
                    tutor_id=tut.id,
                    veterinario_id=vet.id,
                    nombre_vacuna=nom_v,
                    laboratorio=lab,
                    lote=lt,
                    dosis="1.0 mL",
                    fecha_aplicacion=f_ap,
                    fecha_proxima=f_pr,
                    observaciones=obs,
                    creado_por_id=vet.id,
                )
                db.session.add(vm)

        # Desparasitaciones
        desparasitaciones_seed = [
            (lucas, tutores_objs[0], "Drontal Plus 35kg", "interna", "1 tableta", Decimal("28.50"), hoy - timedelta(days=45), hoy + timedelta(days=45)),
            (max_m, tutores_objs[2], "Simparica Trio 10-20kg", "mixta", "1 tableta masticable", Decimal("12.40"), hoy - timedelta(days=20), hoy + timedelta(days=10)),
            (simba, tutores_objs[5], "Total Feline Gotas", "interna", "0.5 mL", Decimal("4.50"), hoy - timedelta(days=60), hoy + timedelta(days=30)),
        ]
        for masc, tut, prod_n, t_tipo, dos, peso, f_ap, f_pr in desparasitaciones_seed:
            d_exist = db.session.execute(db.select(DesparasitacionMascota).filter_by(mascota_id=masc.id, producto=prod_n)).scalar_one_or_none()
            if not d_exist:
                dm = DesparasitacionMascota(
                    mascota_id=masc.id,
                    tutor_id=tut.id,
                    veterinario_id=vet.id,
                    producto=prod_n,
                    tipo=t_tipo,
                    dosis=dos,
                    peso_kg=peso,
                    fecha_aplicacion=f_ap,
                    fecha_proxima=f_pr,
                    creado_por_id=vet.id,
                )
                db.session.add(dm)

        # -------------------------------------------------------------------
        # 10. Agenda Médica General (Citas)
        # -------------------------------------------------------------------
        print("  -> Creando citas en la agenda médica general...")
        citas_agenda_seed = [
            (toby, tutores_objs[4], vet.id, "consulta", ahora.replace(hour=10, minute=30), 30, "confirmada", "Control por otitis externa derecha"),
            (simba, tutores_objs[5], vet.id, "vacunacion", ahora.replace(hour=11, minute=45), 20, "programada", "Refuerzo anual triple felina"),
            (nala, tutores_objs[1], vet.id, "control", ahora + timedelta(days=1, hours=2), 30, "programada", "Revisión herida quirúrgica"),
            (lucas, tutores_objs[0], vet.id, "consulta", ahora + timedelta(days=2), 30, "programada", "Chequeo de rutina carpal"),
        ]
        for masc, tut, prof_id, tipo_c, f_h, dur, est, mot in citas_agenda_seed:
            c_exist = db.session.execute(db.select(Cita).filter_by(mascota_id=masc.id, fecha_hora=f_h)).scalar_one_or_none()
            if not c_exist:
                c = Cita(
                    mascota_id=masc.id,
                    tutor_id=tut.id,
                    profesional_id=prof_id,
                    tipo=tipo_c,
                    fecha_hora=f_h,
                    duracion_minutos=dur,
                    estado=est,
                    motivo=mot,
                    creado_por_id=recep.id,
                )
                db.session.add(c)

        # -------------------------------------------------------------------
        # 11. Hospitalización & Cirugías
        # -------------------------------------------------------------------
        print("  -> Registrando hospitalización y cirugía...")
        hosp_activa = db.session.execute(db.select(Hospitalizacion).filter_by(mascota_id=rocky.id, estado="activa")).scalar_one_or_none()
        if not hosp_activa:
            hosp_activa = Hospitalizacion(
                mascota_id=rocky.id,
                tutor_id=tutores_objs[0].id,
                veterinario_responsable_id=vet.id,
                fecha_ingreso=ahora - timedelta(hours=14),
                motivo="Gastroenteritis aguda severa con vómito persistente y deshidratación 6%",
                diagnostico="Gastroenteritis aguda / sospecha de indiscreción alimentaria",
                jaula="Jaula Canina 01",
                estado="activa",
                costo_dia=Decimal("65000.00"),
                creado_por_id=vet.id,
            )
            db.session.add(hosp_activa)
            db.session.flush()

            # Evoluciones
            ev1 = EvolucionHospitalaria(
                hospitalizacion_id=hosp_activa.id,
                usuario_id=vet.id,
                fecha_hora=ahora - timedelta(hours=8),
                constantes="T: 38.9°C, FC: 110 lpm, FR: 24 rpm, Mucosas pálidas secas, TLLC 3s.",
                tratamiento_aplicado="Canalización de vía venosa periférica. Hartman a 20 ml/h + Metoclopramida 0.3 mg/kg.",
                alimentacion="Ayuno estricto de sólidos y líquidos.",
                eliminaciones="1 micción espontánea en jaula. No ha presentado vómito tras antiemético.",
                observaciones="Paciente deprimido pero alerta a estímulos.",
            )
            ev2 = EvolucionHospitalaria(
                hospitalizacion_id=hosp_activa.id,
                usuario_id=aux.id,
                fecha_hora=ahora - timedelta(hours=2),
                constantes="T: 38.5°C, FC: 98 lpm, FR: 20 rpm, Mucosas rosadas, TLLC 2s.",
                tratamiento_aplicado="Continuación de fluidoterapia. Ranitidina 2 mg/kg IV lenta.",
                alimentacion="Se ofrece 10ml de agua tibia con electrolitos, tolerada con éxito.",
                eliminaciones="Sin novedades.",
                observaciones="Mucho más activo, mueve la cola al acercarse.",
            )
            db.session.add_all([ev1, ev2])

        # Cirugía
        cir_exist = db.session.execute(db.select(Cirugia).filter_by(mascota_id=luna.id)).scalar_one_or_none()
        if not cir_exist:
            cirugia = Cirugia(
                mascota_id=luna.id,
                tutor_id=tutores_objs[3].id,
                veterinario_id=vet.id,
                tipo_procedimiento="Ovariohisterectomía (OVH) Electiva",
                fecha=ahora - timedelta(days=10),
                consentimiento_firmado=True,
                notas_prequirurgicas="Paciente con 8 horas de ayuno. Exámenes prequirúrgicos dentro de rangos normales.",
                protocolo_anestesico="Premedicación: Xilacina + Tramadol. Inducción: Propofol. Mantenimiento: Isoflurano + O2.",
                notas_postquirurgicas="Procedimiento sin complicaciones. Incisión por línea media de 3 cm. Sutura intradérmica con Vicryl 3-0. Recuperación anestésica rápida y suave.",
                creado_por_id=vet.id,
            )
            db.session.add(cirugia)

        # -------------------------------------------------------------------
        # 12. Exámenes de Laboratorio
        # -------------------------------------------------------------------
        print("  -> Registrando exámenes de laboratorio...")
        lab_seed = [
            (rocky, c_med1.id if c_med1 else None, vet.id, "Hemograma Completo + Plaquetas", ahora - timedelta(hours=12), "Laboratorio Veterinario VetLab", "Leucocitosis reactiva leve (17.500/uL) con neutrofilia. Plaquetas normales (280.000). Hematocrito 48% sugerente de hemoconcentración por deshidratación.", "con_resultado"),
            (max_m, c_med2.id if c_med2 else None, vet.id, "Citología y Raspado Cutáneo", ahora - timedelta(days=4), "Laboratorio Dermatológico Vet", "Presencia moderada de levaduras compatibles morfológicamente con Malassezia pachydermatis. Negativo para ácaros Demodex y Sarcoptes.", "con_resultado"),
            (lucas, c_med1.id if c_med1 else None, vet.id, "Perfil Bioquímico Hepático (ALT, FA, Bilirrubinas)", ahora - timedelta(hours=4), "Laboratorio Central Andino", None, "en_proceso"),
        ]
        for masc, c_id, sol_id, tipo_ex, f_toma, lab_ext, interp, est in lab_seed:
            ex_exist = db.session.execute(db.select(ExamenLaboratorio).filter_by(mascota_id=masc.id, tipo_examen=tipo_ex)).scalar_one_or_none()
            if not ex_exist:
                ex = ExamenLaboratorio(
                    mascota_id=masc.id,
                    consulta_id=c_id,
                    solicitado_por_id=sol_id,
                    tipo_examen=tipo_ex,
                    fecha_toma=f_toma,
                    laboratorio_externo=lab_ext,
                    interpretacion=interp,
                    estado=est,
                )
                db.session.add(ex)

        # -------------------------------------------------------------------
        # 13. Gastos de la Clínica
        # -------------------------------------------------------------------
        print("  -> Registrando gastos operativos...")
        gastos_seed = [
            (admin.id, "diario", "servicios_publicos", "Pago servicio energía eléctrica Enel Colombia", Decimal("285000.00"), hoy - timedelta(days=3)),
            (admin.id, "diario", "insumos", "Compra guantes de nitrilo, jeringas y gasas estériles", Decimal("145000.00"), hoy - timedelta(days=6)),
            (admin.id, "diario", "mantenimiento", "Detergentes y desinfectante hospitalario Virkon", Decimal("68000.00"), hoy - timedelta(days=8)),
            (admin.id, "diario", "otro", "Hojas membretadas y bolsas para medicamentos", Decimal("42000.00"), hoy - timedelta(days=12)),
        ]
        for u_id, t_g, cat, desc, monto, f_g in gastos_seed:
            g_exist = db.session.execute(db.select(Gasto).filter_by(descripcion=desc)).scalar_one_or_none()
            if not g_exist:
                g = Gasto(
                    usuario_id=u_id,
                    tipo_gasto=t_g,
                    categoria=cat,
                    descripcion=desc,
                    monto=monto,
                    fecha_gasto=f_g,
                )
                db.session.add(g)

        # -------------------------------------------------------------------
        # 14. Cartera de Tutores y Facturas a Proveedores
        # -------------------------------------------------------------------
        print("  -> Creando cartera de crédito y cuentas por pagar...")
        # Factura proveedor Zoetis a crédito
        fac_prov = db.session.execute(db.select(FacturaProveedor).filter_by(numero_factura="FAC-ZOETIS-8812")).scalar_one_or_none()
        if not fac_prov:
            fac_prov = FacturaProveedor(
                proveedor_id=zoetis_prov.id,
                creado_por_id=admin.id,
                numero_factura="FAC-ZOETIS-8812",
                fecha_factura=hoy - timedelta(days=15),
                fecha_vencimiento=hoy + timedelta(days=15),
                monto_total=Decimal("1450000.00"),
                estado="pendiente",
                notas="Pedido mensual de vacunas y antiparasitarios Zoetis",
            )
            db.session.add(fac_prov)
            db.session.flush()

            abono_prov = PagoProveedor(
                factura_id=fac_prov.id,
                usuario_id=admin.id,
                monto=Decimal("800000.00"),
                metodo_pago="transferencia",
                fecha_pago=ahora - timedelta(days=5),
                notas="Primer abono vía Bancolombia",
            )
            db.session.add(abono_prov)

        # Cuenta de tutor a crédito
        cta_tutor = db.session.execute(db.select(CuentaTutor).filter_by(tutor_id=tutores_objs[2].id)).scalar_one_or_none()
        if not cta_tutor:
            cta_tutor = CuentaTutor(
                tutor_id=tutores_objs[2].id,
                creado_por_id=admin.id,
                descripcion="Tratamiento médico dermatológico y medicamentos a crédito",
                monto_total=Decimal("320000.00"),
                estado="pendiente",
                fecha_factura=hoy - timedelta(days=7),
                fecha_vencimiento=hoy + timedelta(days=8),
            )
            db.session.add(cta_tutor)
            db.session.flush()

            abono_tut = AbonoCuentaTutor(
                cuenta_id=cta_tutor.id,
                usuario_id=cajero.id,
                monto=Decimal("150000.00"),
                metodo_pago="efectivo",
                fecha_pago=ahora - timedelta(days=2),
                notas="Abono en efectivo en recepción",
            )
            db.session.add(abono_tut)

        # Commit final
        db.session.commit()
        print("\n[OK] ¡Siembra de datos de prueba finalizada exitosamente!")
        print("---------------------------------------------------------------")
        print("Credenciales de acceso para pruebas (todos con clave: Sandia2026*):")
        for nom, email, rol, *_ in usuarios_data:
            print(f"  - {rol.upper():12}: {email:26} ({nom})")
        print("---------------------------------------------------------------")


if __name__ == "__main__":
    sembrar()
