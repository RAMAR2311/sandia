/* Buscador de mascota reutilizable: agenda, hospitalización, cirugías, laboratorio.
   Requiere en el HTML: input hidden #mascota_id, bloque #mascota-seleccionada
   (con [data-campo=nombre], [data-campo=detalle], [data-campo=emoji], [data-campo=tutor] y botón #cambiar-mascota),
   bloque #buscador-mascota con input #buscar-mascota y lista #resultados-mascota. */
(function () {
  'use strict';

  var campoId = document.getElementById('mascota_id');
  if (!campoId) { return; }

  var campoTutorId = document.getElementById('tutor_id');
  var bloqueSeleccionada = document.getElementById('mascota-seleccionada');
  var bloqueBuscador = document.getElementById('buscador-mascota');
  var entrada = document.getElementById('buscar-mascota');
  var resultados = document.getElementById('resultados-mascota');
  var botonCambiar = document.getElementById('cambiar-mascota');
  var temporizador = null;
  var indiceActivo = -1;
  var listaActual = [];

  if (resultados) {
    resultados.classList.remove('overflow-hidden');
    resultados.style.maxHeight = '320px';
    resultados.style.overflowY = 'auto';
    resultados.style.overscrollBehavior = 'contain';
  }

  function seleccionar(mascota) {
    campoId.value = mascota.id;
    if (campoTutorId && mascota.tutor) {
      campoTutorId.value = mascota.tutor.id;
    }
    var elNombre = bloqueSeleccionada.querySelector('[data-campo="nombre"]');
    var elDetalle = bloqueSeleccionada.querySelector('[data-campo="detalle"]');
    var elEmoji = bloqueSeleccionada.querySelector('[data-campo="emoji"]');
    var elTutor = bloqueSeleccionada.querySelector('[data-campo="tutor"]');

    if (elNombre) { elNombre.textContent = mascota.nombre; }
    if (elEmoji) { elEmoji.textContent = mascota.emoji || '🐾'; }
    if (elDetalle) {
      var detalles = [mascota.especie_etiqueta, mascota.raza].filter(Boolean).join(' · ');
      elDetalle.textContent = detalles || mascota.especie_etiqueta;
    }
    if (elTutor && mascota.tutor) {
      elTutor.textContent = 'Tutor: ' + mascota.tutor.nombre + (mascota.tutor.telefono ? ' · Tel: ' + mascota.tutor.telefono : '');
    }

    bloqueSeleccionada.classList.remove('d-none');
    bloqueBuscador.classList.add('d-none');
    resultados.classList.add('d-none');
    resultados.innerHTML = '';
    indiceActivo = -1;
    listaActual = [];
  }

  function actualizarFocoTeclado() {
    if (!resultados) return;
    var items = resultados.querySelectorAll('.item-resultado-mascota');
    items.forEach(function (item, idx) {
      if (idx === indiceActivo) {
        item.classList.add('active', 'bg-danger-subtle', 'text-dark', 'border-danger-subtle');
        item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else {
        item.classList.remove('active', 'bg-danger-subtle', 'text-dark', 'border-danger-subtle');
      }
    });
  }

  function mostrar(lista) {
    resultados.innerHTML = '';
    listaActual = lista || [];
    indiceActivo = -1;

    if (!listaActual.length) {
      var vacio = document.createElement('div');
      vacio.className = 'list-group-item text-secondary py-3 text-center bg-white';
      vacio.innerHTML = '<i class="bi bi-search me-1"></i> No se encontraron mascotas con ese nombre o tutor.';
      resultados.appendChild(vacio);
    } else {
      var cabecera = document.createElement('div');
      cabecera.className = 'list-group-item py-1 px-3 bg-light text-secondary d-flex justify-content-between align-items-center sticky-top border-bottom';
      cabecera.style.fontSize = '0.75rem';
      cabecera.style.zIndex = '2';
      cabecera.innerHTML =
        '<span><i class="bi bi-list-ul me-1"></i><strong>' + listaActual.length + '</strong> paciente' + (listaActual.length === 1 ? '' : 's') + ' encontrado' + (listaActual.length === 1 ? '' : 's') + '</span>' +
        (listaActual.length > 3 ? '<span class="text-danger fw-semibold"><i class="bi bi-arrows-vertical me-1"></i>Desplázate para ver todos</span>' : '');
      resultados.appendChild(cabecera);

      listaActual.forEach(function (m, idx) {
        var boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'list-group-item list-group-item-action p-2 p-sm-3 d-flex align-items-center gap-3 border-bottom item-resultado-mascota';
        boton.setAttribute('data-idx', idx);

        var avatarHtml = '<div class="avatar-sandia-circulo fs-4 d-flex align-items-center justify-content-center bg-light rounded-circle shadow-sm flex-shrink-0" style="width:42px; height:42px;">' + (m.emoji || '🐾') + '</div>';
        var tutorTexto = m.tutor ? ('Tutor: ' + m.tutor.nombre + (m.tutor.telefono ? ' · ' + m.tutor.telefono : '')) : '';
        var infoHtml = '<div class="flex-grow-1 text-start min-w-0">' +
          '<div class="d-flex align-items-center gap-2 flex-wrap">' +
            '<span class="fw-bold text-dark fs-6">' + m.nombre + '</span>' +
            '<span class="badge bg-danger-subtle text-danger border border-danger-subtle rounded-pill py-1 px-2" style="font-size: 0.75rem;">' + m.especie_etiqueta + '</span>' +
            (m.raza ? '<span class="text-secondary small">· ' + m.raza + '</span>' : '') +
          '</div>' +
          '<div class="small text-secondary mt-1"><i class="bi bi-person me-1"></i>' + tutorTexto + '</div>' +
        '</div>' +
        '<div class="text-end flex-shrink-0"><span class="btn btn-sm btn-outline-danger rounded-pill px-3">Elegir</span></div>';

        boton.innerHTML = avatarHtml + infoHtml;
        boton.addEventListener('click', function () { seleccionar(m); });
        resultados.appendChild(boton);
      });
    }
    resultados.classList.remove('d-none');
  }

  function consultarMascotas(texto) {
    var url = '/api/mascotas/buscar?limite=100&todas=1&q=' + encodeURIComponent(texto || '');
    fetch(url)
      .then(function (r) { return r.json(); })
      .then(mostrar)
      .catch(function () { resultados.classList.add('d-none'); });
  }

  if (entrada) {
    entrada.addEventListener('input', function () {
      var texto = entrada.value.trim();
      window.clearTimeout(temporizador);
      temporizador = window.setTimeout(function () {
        consultarMascotas(texto);
      }, 180);
    });

    entrada.addEventListener('focus', function () {
      if (resultados.classList.contains('d-none') || !listaActual.length) {
        consultarMascotas(entrada.value.trim());
      }
    });

    entrada.addEventListener('keydown', function (ev) {
      if (resultados.classList.contains('d-none') || !listaActual.length) return;
      if (ev.key === 'ArrowDown') {
        ev.preventDefault();
        indiceActivo = (indiceActivo + 1) % listaActual.length;
        actualizarFocoTeclado();
      } else if (ev.key === 'ArrowUp') {
        ev.preventDefault();
        indiceActivo = (indiceActivo - 1 + listaActual.length) % listaActual.length;
        actualizarFocoTeclado();
      } else if (ev.key === 'Enter' && indiceActivo >= 0 && listaActual[indiceActivo]) {
        ev.preventDefault();
        seleccionar(listaActual[indiceActivo]);
      }
    });

    // Si el formulario abre sin paciente preseleccionado, cargar lista inicial para poder hacer scroll de inmediato
    if (!campoId.value) {
      consultarMascotas(entrada.value.trim());
    }
  }

  if (botonCambiar) {
    botonCambiar.addEventListener('click', function () {
      campoId.value = '';
      if (campoTutorId) { campoTutorId.value = ''; }
      bloqueSeleccionada.classList.add('d-none');
      bloqueBuscador.classList.remove('d-none');
      if (entrada) {
        entrada.value = '';
        entrada.focus();
        consultarMascotas('');
      }
    });
  }
})();
