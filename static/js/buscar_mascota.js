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
  }

  function mostrar(lista) {
    resultados.innerHTML = '';
    if (!lista.length) {
      var vacio = document.createElement('div');
      vacio.className = 'list-group-item text-secondary py-3 text-center bg-white';
      vacio.innerHTML = '<i class="bi bi-search me-1"></i> No se encontraron mascotas con ese nombre o tutor.';
      resultados.appendChild(vacio);
    } else {
      lista.forEach(function (m) {
        var boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'list-group-item list-group-item-action p-2 p-sm-3 d-flex align-items-center gap-3 border-bottom';
        
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

  if (entrada) {
    entrada.addEventListener('input', function () {
      var texto = entrada.value.trim();
      window.clearTimeout(temporizador);
      if (texto.length < 2) { resultados.classList.add('d-none'); return; }
      temporizador = window.setTimeout(function () {
        fetch('/api/mascotas/buscar?q=' + encodeURIComponent(texto))
          .then(function (r) { return r.json(); })
          .then(mostrar)
          .catch(function () { resultados.classList.add('d-none'); });
      }, 200);
    });
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
      }
    });
  }
})();
