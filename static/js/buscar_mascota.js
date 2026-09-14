/* Buscador de mascota reutilizable: agenda, hospitalización, cirugías, laboratorio.
   Requiere en el HTML: input hidden #mascota_id, bloque #mascota-seleccionada
   (con [data-campo=nombre] y [data-campo=detalle] y botón #cambiar-mascota),
   bloque #buscador-mascota con input #buscar-mascota y lista #resultados-mascota. */
(function () {
  'use strict';

  var campoId = document.getElementById('mascota_id');
  if (!campoId) { return; }

  var bloqueSeleccionada = document.getElementById('mascota-seleccionada');
  var bloqueBuscador = document.getElementById('buscador-mascota');
  var entrada = document.getElementById('buscar-mascota');
  var resultados = document.getElementById('resultados-mascota');
  var botonCambiar = document.getElementById('cambiar-mascota');
  var temporizador = null;

  function seleccionar(mascota) {
    campoId.value = mascota.id;
    bloqueSeleccionada.querySelector('[data-campo="nombre"]').textContent = mascota.emoji + ' ' + mascota.nombre;
    bloqueSeleccionada.querySelector('[data-campo="detalle"]').textContent =
      [mascota.especie_etiqueta, mascota.tutor.nombre].filter(Boolean).join(' · ');
    bloqueSeleccionada.classList.remove('d-none');
    bloqueBuscador.classList.add('d-none');
    resultados.classList.add('d-none');
    resultados.innerHTML = '';
  }

  function mostrar(lista) {
    resultados.innerHTML = '';
    if (!lista.length) {
      var vacio = document.createElement('div');
      vacio.className = 'list-group-item text-secondary';
      vacio.textContent = 'Sin coincidencias.';
      resultados.appendChild(vacio);
    }
    lista.forEach(function (m) {
      var boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'list-group-item list-group-item-action py-2';
      boton.innerHTML = '<div class="fw-bold"></div><div class="small text-secondary"></div>';
      boton.querySelector('.fw-bold').textContent = m.emoji + ' ' + m.nombre;
      boton.querySelector('.small').textContent = [m.especie_etiqueta, m.tutor.nombre].filter(Boolean).join(' · ');
      boton.addEventListener('click', function () { seleccionar(m); });
      resultados.appendChild(boton);
    });
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
      }, 250);
    });
  }

  if (botonCambiar) {
    botonCambiar.addEventListener('click', function () {
      campoId.value = '';
      bloqueSeleccionada.classList.add('d-none');
      bloqueBuscador.classList.remove('d-none');
      if (entrada) { entrada.focus(); }
    });
  }
})();
