# 🍉 Manual Integral del Sistema Sandía · Medicina & Spa Veterinario

Bienvenido al **Manual de Usuario y Operación de Sandía**, el sistema integral de gestión clínica, estética y comercial diseñado específicamente para clínicas veterinarias y centros de bienestar animal.

---

## 📑 Tabla de Contenido
1. [Introducción y Arquitectura del Sistema](#1-introducción-y-arquitectura-del-sistema)
2. [Roles de Usuario y Permisos](#2-roles-de-usuario-y-permisos)
3. [Punto de Partida: Acceso y Navegación](#3-punto-de-partida-acceso-y-navegación)
4. [Módulo de Pacientes & Tutores](#4-módulo-de-pacientes--tutores)
5. [Módulo de Ficha Clínica & Historias Médicas](#5-módulo-de-ficha-clínica--historias-médicas)
   - 5.1 [Cronología y Línea de Tiempo General](#51-cronología-y-línea-de-tiempo-general)
   - 5.2 [Consultas Médicas (Método SOAP)](#52-consultas-médicas-método-soap)
   - 5.3 [Fórmulas Médicas (Rx) y Recetario Oficial](#53-fórmulas-médicas-rx-y-recetario-oficial)
   - 5.4 [Controles y Evoluciones Clínicas](#54-controles-y-evoluciones-clínicas)
   - 5.5 [Ayudas Diagnósticas & Exámenes (Visor Tablet/Web)](#55-ayudas-diagnósticas--exámenes-visor-tabletweb)
   - 5.6 [Plan de Vacunación y Desparasitación](#56-plan-de-vacunación-y-desparasitación)
   - 5.7 [Hospitalización y Cirugías](#57-hospitalización-y-cirugías)
   - 5.8 [Consentimientos Informados Digitales](#58-consentimientos-informados-digitales)
   - 5.9 [Certificados de Salud Animal](#59-certificados-de-salud-animal)
   - 5.10 [Notas y Novedades Rápidas](#510-notas-y-novedades-rápidas)
6. [Módulo de Spa & Peluquería Canina/Felina](#6-módulo-de-spa--peluquería-caninafelina)
7. [Módulo de Agenda Médica & Turnos](#7-módulo-de-agenda-médica--turnos)
8. [Módulo de Punto de Venta (POS) & Control de Caja](#8-módulo-de-punto-de-venta-pos--control-de-caja)
9. [Módulo de Inventario, Lotes y Proveedores](#9-módulo-de-inventario-lotes-y-proveedores)
10. [Módulo de Reportes Financieros y Métricas](#10-módulo-de-reportes-financieros-y-métricas)
11. [Configuración General & Datos Clínicos](#11-configuración-general--datos-clínicos)
12. [Preguntas Frecuentes y Solución de Problemas](#12-preguntas-frecuentes-y-solución-de-problemas)

---

## 1. Introducción y Arquitectura del Sistema

**Sandía** unifica en una sola plataforma:
- **Gestión Médica:** Historial clínico riguroso bajo metodología SOAP, certificados legales con verificación pública, consentimientos digitales y recetas con firma profesional.
- **Spa & Estética:** Control de citas, fotografías de ingreso/salida, cargos adicionales y notificaciones automáticas por WhatsApp para retiro del paciente.
- **Caja & Punto de Venta (POS):** Facturación rápida con descuento automático de inventario por lotes, turnos de caja con arqueo y múltiples medios de pago (Efectivo, Nequi, Daviplata, Bancolombia, Tarjetas y Mixto).
- **Control de Inventario:** Kardex valorizado, alertas de stock mínimo y trazabilidad de fechas de vencimiento.

---

## 2. Roles de Usuario y Permisos

El sistema implementa control de acceso basado en roles (RBAC) para garantizar la seguridad clínica y financiera:

| Rol | Descripción y Funciones Principales | Acceso a Finanzas / Config |
| :--- | :--- | :---: |
| **Administrador (`admin`)** | Control absoluto: configuración de la clínica, creación y edición de usuarios, edición de precios base, aprobación de descuentos en POS, cierre y arqueo de turnos, reportes financieros globales y auditoría. | Total |
| **Médico Veterinario (`veterinario`)** | Emisión de consultas SOAP, formulación médica (Rx), registro de cirugías, hospitalizaciones, certificados de salud, consentimientos informados y expedición de recetas oficiales. | Solo clínico |
| **Auxiliar (`auxiliar`)** | Recepción de pacientes, gestión de agenda médica y spa, cobro en punto de venta (POS), apertura de turno de cobro y registro de notas básicas. | Restringido |

---

## 3. Punto de Partida: Acceso y Navegación

### 3.1 Inicio de Sesión
1. Ingresa a la URL del sistema (Local: `http://127.0.0.1:5000` o dominio en producción).
2. Escribe tu correo electrónico institucional y contraseña asignada.
3. Haz clic en **Ingresar**.

> **Credenciales predeterminadas para entorno local:**
> - **Administrador:** `admin@sandia.com` / `Sandia2026*`
> - **Veterinaria:** `veterinario@sandia.com` / `Sandia2026*`

### 3.2 Menú Principal Superior
- **🐾 Pacientes:** Directorio de mascotas y tutores.
- **📅 Agenda:** Calendario de citas médicas y de spa.
- **🩺 Historias:** Listado directo de consultas e historial clínico.
- **🛁 Spa & Peluquería:** Tablero de turnos de estética, fotos de ingreso y avisos por WhatsApp.
- **💳 POS / Caja:** Terminal de ventas, turnos de cobro y arqueo.
- **📦 Inventario:** Catálogo de productos, stock, lotes y proveedores.
- **📊 Reportes:** Métricas financieras y balance de caja.

---

## 4. Módulo de Pacientes & Tutores

### 4.1 Registrar un Nuevo Tutor y Paciente
1. Ve al menú **Pacientes** y haz clic en **`+ Nuevo Paciente`**.
2. **Datos del Tutor:**
   - Nombre completo, número de documento de identidad (C.C. / C.E. / NIT).
   - Teléfono celular y número de WhatsApp (fundamental con indicativo para mensajería automática).
   - Dirección y correo electrónico.
3. **Datos de la Mascota:**
   - Nombre, especie (Canina, Felina, etc.), raza (con autocompletado inteligente).
   - Sexo, fecha de nacimiento (o edad aproximada calculada automáticamente).
   - Color, microchip, estado reproductivo (Castrado / Entero).
   - Alergias y condiciones preexistentes.
4. Haz clic en **Guardar Paciente**.

---

## 5. Módulo de Ficha Clínica & Historias Médicas

La **Ficha Médica** (`/historias/mascota/<id>`) es el corazón asistencial del paciente. Contiene un panel lateral con información biológica, accesos directos y una barra de acciones médicas.

### 5.1 Cronología y Línea de Tiempo General
En la pestaña **General**, el sistema presenta una línea de tiempo unificada e interactiva con todo lo acontecido con el paciente ordenado cronológicamente:
- Cada tarjeta indica fecha, profesional responsable, tipo de evento y badge de color.
- Permite cambiar la fecha de cualquier registro retrospectivo si hubo un error en la digitación.
- Incluye botones directos para **WhatsApp**, **PDF**, **Editar** y **Eliminar** (según permisos).

### 5.2 Consultas Médicas (Método SOAP)
Para abrir una nueva consulta, haz clic en **`+ Nueva Consulta SOAP`**:

- **S · Subjetivo:** Anamnesis, motivo de la visita referido por el tutor y dieta actual.
- **O · Objetivo:** Constantes fisiológicas (Peso, Temperatura, FC, FR, Mucosas, TLLC) y evaluación física sistemática.
- **A · Avalúo:** Diagnóstico presuntivo, diagnósticos diferenciales y diagnóstico definitivo.
- **P · Plan:** Plan diagnóstico, plan terapéutico y posología inicial.

- **Firma digital:** Si el veterinario tiene su firma configurada en el perfil, aparecerá automáticamente sellada en el documento final.
- **Exportación:** Cada consulta genera un informe médico oficial descargable en PDF o compartible vía WhatsApp.

### 5.3 Fórmulas Médicas (Rx) y Recetario Oficial
Puedes prescribir de dos formas:
1. **Directamente en la Consulta SOAP:** Rellenando el campo *Fórmula Médica (Rx)*.
2. **Mediante el botón directo `+ Agregar Fórmula`:** Ubicado en la barra lateral izquierda y en la barra superior de la cronología.

#### Pasos para emitir una Fórmula Rápida:
1. Haz clic en **`+ Agregar Fórmula`**.
2. Escribe el **Motivo / Diagnóstico** (ej. *Tratamiento Dermatitis Alérgica*).
3. Selecciona el **Veterinario Responsable**.
4. Usa los **Botones de Prescripción Rápida (Snippets)** para insertar estructuras comunes:
   - `+ Antibiótico oral`
   - `+ Antiinflamatorio / Analgésico`
   - `+ Protector gástrico`
   - `+ Tratamiento ótico`
   - `+ Baño dérmico`
5. Ajusta la concentración, dosis, frecuencia y días de tratamiento.
6. (Opcional) Agrega recomendaciones de cuidado en casa (ej. uso de collar isabelino).
7. Haz clic en **Guardar Fórmula en Historial**.

> **Edición y Envío:** En la tarjeta de la fórmula en el historial tendrás los botones:
> - **Fórmula PDF:** Descarga el recetario membretado oficial de Sandía con logo, datos legales y firma profesional.
> - **WhatsApp:** Envía la receta con un solo clic al tutor de la mascota.
> - **Editar (Lápiz):** Corrige dosis o indicaciones sin necesidad de editar toda la consulta clínica.

### 5.4 Controles y Evoluciones Clínicas
- Registra el seguimiento a tratamientos previos.
- Permite evaluar mejorías, reprogramar la fecha del próximo control y generar enlaces automáticos para **Google Calendar** y **Apple Calendar (.ics)**.

### 5.5 Ayudas Diagnósticas & Exámenes (Visor Tablet/Web)
- Registra exámenes de **Laboratorio Clínico, Rayos X, Ecografías y Cardiología**.
- **Visualizador responsivo:** En pantallas de escritorio y tablets, los PDFs y radiografías se previsualizan de forma integrada.
- Para tablets que bloquean iframes nativos, se incluye un botón destacado **`Ver / Abrir PDF`** para visualización a pantalla completa sin errores.

### 5.6 Plan de Vacunación y Desparasitación
- Control de biológicos aplicados: nombre de la vacuna, laboratorio, número de lote y fecha de vencimiento.
- Semáforo de estado de vacunas: **Al día**, **Próxima a vencer** o **Vencida**.
- Generación con 1 clic del **Carnet de Vacunación Digital (PDF)**.

### 5.7 Hospitalización y Cirugías
- Control de ingreso a jaulas hospitalarias, monitorización de signos vitales periódicos, balance hídrico y protocolo de alta médica.
- Registro quirúrgico: tipo de procedimiento, protocolo anestésico, cirujano, ayudante y notas postquirúrgicas.

### 5.8 Consentimientos Informados Digitales
- Permite generar autorizaciones para cirugías, sedaciones, eutanasia o procedimientos especiales.
- El tutor puede firmar en pantalla táctil (celular o tablet) o mediante enlace público seguro.

### 5.9 Certificados de Salud Animal
- Emisión de certificados de salud para viajes nacionales e internacionales o fines legales.
- Consecutivo único y código de verificación pública para autoridades sanitarias.

### 5.10 Notas y Novedades Rápidas
- Registra anotaciones que no constituyen una consulta formal (ej. *"Tutor canceló control por llamada telefónica"*, *"Se reporta vómito en horas de la mañana"*).

---

## 6. Módulo de Spa & Peluquería Canina/Felina

El módulo de estética veterinaria permite un seguimiento minucioso del servicio para garantizar la satisfacción del cliente:

### 6.1 Flujo Operativo del Spa
1. **Agendamiento:** Se programa el turno indicando la mascota, el estilista asignado y el servicio base (ej. *Corte de Raza & Spa Completo*).
2. **Ingreso:**
   - Se toma o carga la **Foto de Ingreso** desde la cámara del celular o tablet.
   - Se anotan observaciones de pelaje, nudos o lesiones en la piel.
3. **Cargos Adicionales y Edición de Precios:**
   - Si la mascota requiere desenredo extra, corte de uñas especial o baño medicado, se pueden agregar cargos adicionales.
   - **Edición en un clic:** Puedes editar directamente el precio del **Servicio Base** o el **Total Estimado a Cobrar** con el botón de lápiz integrado.
4. **Finalización & Salida:**
   - Se sube la **Foto de Salida** con el resultado final.
   - Se hace clic en **`Aviso al Tutor por WhatsApp`**: el sistema abre WhatsApp con un mensaje automático indicando que la mascota ya está lista y hermosa para su recogida, junto con el valor a cancelar.
5. **Cobro:** Botón directo **`Facturar Servicio en el POS`** para liquidar el servicio en caja en 3 segundos.

---

## 7. Módulo de Agenda Médica & Turnos

- Vista de calendario interactivo para planificar el flujo de trabajo de la clínica y el spa.
- **Búsqueda con Scroll de Pacientes:** Al crear una cita médica o de spa, el selector de pacientes permite escribir para filtrar y cuenta con **barra de desplazamiento (scroll)** y navegación por flechas (`↑` / `↓` / `Enter`) para encontrar cómodamente a cualquier paciente entre cientos de registros.

---

## 8. Módulo de Punto de Venta (POS) & Control de Caja

### 8.1 Turno de Cobro (Apertura y Cierre)
- **Apertura de Turno:** Al iniciar la jornada, se abre el turno ingresando la **Base Inicial en Efectivo**.
- **Edición de Base:** Si hubo una equivocación al digitar el dinero de base, el sistema permite corregir el monto de la base inicial haciendo clic en el lápiz junto a **Base Inicial (Efectivo)** sin necesidad de cerrar el turno.
- **Arqueo y Cierre:** El sistema totaliza automáticamente las ventas discriminadas por cada canal: Efectivo, Nequi, Daviplata, Bancolombia y Tarjetas.

### 8.2 Terminal de Venta (POS)
1. Selecciona o busca al cliente/tutor.
2. Agrega los productos del catálogo o servicios médicos/spa.
3. El sistema valida automáticamente las existencias en inventario.
4. **Forma de Pago:**
   - Selecciona el método: **Efectivo**, **Nequi**, **Daviplata**, **Bancolombia**, **Tarjetas (Débito/Crédito)** o **Pago Dividido / Mixto** (ej. parte en Efectivo y parte en Bancolombia).
5. Haz clic en **Completar Venta & Facturar**.
6. Se genera el ticket de venta imprimible o exportable.

---

## 9. Módulo de Inventario, Lotes y Proveedores

- **Catálogo de Productos:** Medicamentos, alimentos, biológicos, accesorios y servicios.
- **Trazabilidad por Lotes:** Permite registrar fecha de vencimiento y lote de fabricación para medicamentos y vacunas.
- **Kardex Automático:** Cada venta en el POS descuenta las unidades correspondientes del inventario mediante el principio PEPS (Primero en Entrar, Primero en Salir).
- **Alertas de Reposición:** Alerta amarilla para productos por debajo del stock mínimo y alerta roja para productos agotados o próximos a caducar.

---

## 10. Módulo de Reportes Financieros y Métricas

Ubicado en el menú **Reportes**, ofrece análisis en tiempo real:
- **Balance Diario y Mensual:** Ingresos brutos, devoluciones y ventas netas.
- **Desglose por Medios de Pago:** Total recaudado por Efectivo, Nequi, Daviplata, Bancolombia y Tarjetas.
- **Servicios vs. Productos:** Identifica qué área genera mayor rentabilidad (Clínica, Farmacia, Spa o Pet Shop).
- **Exportación:** Generación de reportes tabulares en Excel/CSV y PDF.

---

## 11. Configuración General & Datos Clínicos

En el panel de **Administración > Configuración**:
- **Datos de la Empresa:** Nombre de la clínica, NIT, teléfono fijo, celular, WhatsApp comercial y dirección física.
- **Perfil Médico Principal:** Nombre del director médico, tarjeta profesional (T.P.), diplomados/especialidades y carga de la firma digital escaneada para los recetarios y certificados.

---

## 12. Preguntas Frecuentes y Solución de Problemas

- **¿Qué hago si me equivoqué en la dosis de una fórmula médica ya guardada?**  
  Ve a la ficha de la mascota, busca la fórmula en la cronología general y presiona el botón de **Editar (Lápiz)** en la cabecera de la tarjeta. Modifica la dosis y guarda. Tanto el PDF como el enlace de WhatsApp se actualizarán de inmediato.

- **¿Cómo cobro una cuenta con dos medios de pago diferentes?**  
  En el POS, selecciona la opción **Pago Mixto / Dividido**. El sistema te permitirá ingresar cuánto dinero entrega el cliente en Efectivo y cuánto abona a través de Bancolombia, Nequi o Tarjeta.

- **¿Por qué un producto no aparece en el POS?**  
  Verifica en el módulo de Inventario que el producto esté marcado como **Activo** y cuente con existencias registradas mayores a cero.

- **¿Cómo visualizo los exámenes en una Tablet o iPad?**  
  En la tarjeta del examen en la ficha médica, encontrarás el botón rojo **`Ver / Abrir PDF`**, el cual abrirá el documento en pantalla completa aprovechando el visor nativo de tu tablet.

---

*Manual elaborado para el equipo asistencial y administrativo de Sandía · Medicina & Spa Veterinario.*  
*Versión del Sistema: 2026.11 · Todos los derechos reservados.*

