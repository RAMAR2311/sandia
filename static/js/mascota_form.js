/* Formulario de mascota: búsqueda de tutor, razas por especie y edad aproximada. */
(function () {
  'use strict';

  var formulario = document.getElementById('form-mascota');
  if (!formulario) { return; }

  var urlRazas = formulario.dataset.urlRazas;
  var urlTutores = formulario.dataset.urlTutores;
  var razaActual = parseInt(formulario.dataset.razaActual || '0', 10);

  // --- Tutor: búsqueda con resultados en vivo --------------------------------
  var campoTutorId = document.getElementById('tutor_id');
  var bloqueSeleccionado = document.getElementById('tutor-seleccionado');
  var bloqueBuscador = document.getElementById('buscador-tutor');
  var entradaBusqueda = document.getElementById('buscar-tutor');
  var listaResultados = document.getElementById('resultados-tutor');
  var botonCambiar = document.getElementById('cambiar-tutor');
  var temporizador = null;

  function seleccionarTutor(tutor) {
    campoTutorId.value = tutor.id;
    bloqueSeleccionado.querySelector('.avatar-usuario').textContent = (tutor.nombre || '?').charAt(0).toUpperCase();
    bloqueSeleccionado.querySelector('[data-campo="nombre"]').textContent = tutor.nombre;
    bloqueSeleccionado.querySelector('[data-campo="detalle"]').textContent = [tutor.telefono, tutor.documento].filter(Boolean).join(' · ');
    bloqueSeleccionado.classList.remove('d-none');
    bloqueBuscador.classList.add('d-none');
    listaResultados.classList.add('d-none');
    listaResultados.innerHTML = '';
    var campoNombre = document.getElementById('nombre');
    if (campoNombre && !campoNombre.value) { campoNombre.focus(); }
  }

  function mostrarResultados(tutores) {
    listaResultados.innerHTML = '';
    if (!tutores.length) {
      var vacio = document.createElement('div');
      vacio.className = 'list-group-item text-secondary';
      vacio.textContent = 'Sin coincidencias.';
      listaResultados.appendChild(vacio);
    }
    tutores.forEach(function (tutor) {
      var boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'list-group-item list-group-item-action py-2';
      var mascotas = (tutor.mascotas || []).map(function (m) { return m.emoji + ' ' + m.nombre; }).join(', ');
      boton.innerHTML = '<div class="fw-bold"></div><div class="small text-secondary"></div>';
      boton.querySelector('.fw-bold').textContent = tutor.nombre;
      boton.querySelector('.small').textContent = [tutor.telefono, tutor.documento, mascotas].filter(Boolean).join(' · ');
      boton.addEventListener('click', function () { seleccionarTutor(tutor); });
      listaResultados.appendChild(boton);
    });
    listaResultados.classList.remove('d-none');
  }

  entradaBusqueda.addEventListener('input', function () {
    var texto = entradaBusqueda.value.trim();
    window.clearTimeout(temporizador);
    if (texto.length < 2) { listaResultados.classList.add('d-none'); return; }
    temporizador = window.setTimeout(function () {
      VetCare.fetchJson(urlTutores + '?q=' + encodeURIComponent(texto))
        .then(mostrarResultados)
        .catch(function () { listaResultados.classList.add('d-none'); });
    }, 250);
  });

  botonCambiar.addEventListener('click', function () {
    campoTutorId.value = '';
    bloqueSeleccionado.classList.add('d-none');
    bloqueBuscador.classList.remove('d-none');
    entradaBusqueda.focus();
  });

  // --- Raza según especie -----------------------------------------------------
  var selectEspecie = document.getElementById('especie');
  var selectRaza = document.getElementById('raza_id');

  function cargarRazas(mantener) {
    VetCare.fetchJson(urlRazas + '?especie=' + encodeURIComponent(selectEspecie.value))
      .then(function (razas) {
        selectRaza.innerHTML = '';
        var opcionVacia = new Option('Sin especificar', '0');
        selectRaza.appendChild(opcionVacia);
        razas.forEach(function (raza) {
          var opcion = new Option(raza.nombre, String(raza.id));
          if (mantener && raza.id === razaActual) { opcion.selected = true; }
          selectRaza.appendChild(opcion);
        });
      })
      .catch(function () { /* se conservan las opciones renderizadas por el servidor */ });
  }

  selectEspecie.addEventListener('change', function () { cargarRazas(false); });

  // --- Edad exacta o aproximada ----------------------------------------------
  var interruptor = document.getElementById('conoce_fecha');
  var bloqueFecha = document.getElementById('bloque-fecha');
  var bloqueEdad = document.getElementById('bloque-edad');

  function alternarEdad() {
    bloqueFecha.classList.toggle('d-none', !interruptor.checked);
    bloqueEdad.classList.toggle('d-none', interruptor.checked);
  }
  interruptor.addEventListener('change', alternarEdad);
  alternarEdad();
})();
