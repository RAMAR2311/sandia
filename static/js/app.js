/* VetCare · utilidades base del frontend (JavaScript vanilla, sin build). */
(function () {
  'use strict';

  var metaToken = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = metaToken ? metaToken.getAttribute('content') : '';

  /**
   * Petición JSON con el token CSRF en el header X-CSRFToken.
   * Uso: VetCare.fetchJson('/api/ruta', { method: 'POST', body: { a: 1 } })
   */
  function fetchJson(url, opciones) {
    opciones = opciones || {};
    var cabeceras = Object.assign(
      { Accept: 'application/json', 'X-CSRFToken': csrfToken },
      opciones.headers || {}
    );
    var cuerpo = opciones.body;
    if (cuerpo !== undefined && cuerpo !== null && typeof cuerpo !== 'string' && !(cuerpo instanceof FormData)) {
      cabeceras['Content-Type'] = 'application/json';
      cuerpo = JSON.stringify(cuerpo);
    }
    return fetch(url, Object.assign({ credentials: 'same-origin' }, opciones, { headers: cabeceras, body: cuerpo }))
      .then(function (respuesta) {
        return respuesta.json().catch(function () { return null; }).then(function (datos) {
          if (!respuesta.ok) {
            var error = new Error((datos && datos.error) || ('Error ' + respuesta.status));
            error.status = respuesta.status;
            error.datos = datos;
            throw error;
          }
          return datos;
        });
      });
  }

  /** Formato de pesos colombianos en el navegador: 45000 -> "$45.000". */
  function formatoCop(valor) {
    var entero = Math.round(Number(valor) || 0);
    var signo = entero < 0 ? '-' : '';
    return signo + '$' + Math.abs(entero).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  window.VetCare = { csrfToken: csrfToken, fetchJson: fetchJson, formatoCop: formatoCop };

  document.addEventListener('DOMContentLoaded', function () {
    // Confirmación en formularios sensibles: <form data-confirmar="¿Seguro?">
    document.addEventListener('submit', function (evento) {
      var formulario = evento.target;
      if (formulario.matches('form[data-confirmar]') && !window.confirm(formulario.dataset.confirmar)) {
        evento.preventDefault();
      }
    });

    // Evita doble envío: deshabilita el botón al enviar.
    document.addEventListener('submit', function (evento) {
      var boton = evento.target.querySelector('button[type="submit"], input[type="submit"]');
      if (boton && !evento.defaultPrevented) {
        window.setTimeout(function () { boton.disabled = true; }, 0);
        window.setTimeout(function () { boton.disabled = false; }, 4000);
      }
    });

    // Las alertas informativas se cierran solas; las de error permanecen.
    document.querySelectorAll('.alert[data-autocierre]').forEach(function (alerta) {
      window.setTimeout(function () {
        if (window.bootstrap && bootstrap.Alert) { bootstrap.Alert.getOrCreateInstance(alerta).close(); }
      }, 6000);
    });

    if (window.bootstrap && bootstrap.Tooltip) {
      document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) { new bootstrap.Tooltip(el); });
    }
  });
})();
