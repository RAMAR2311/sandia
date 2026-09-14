/* Curva de peso: gráfica de líneas en SVG sin dependencias. */
(function () {
  'use strict';

  var contenedor = document.getElementById('grafica-peso');
  if (!contenedor) { return; }

  var puntos;
  try { puntos = JSON.parse(contenedor.dataset.puntos || '[]'); } catch (e) { puntos = []; }

  if (!puntos.length) {
    contenedor.innerHTML = '<div class="grafica-peso__vacia">Registra el primer peso para ver la curva.</div>';
    return;
  }

  var ANCHO = 640, ALTO = 240;
  var margen = { arriba: 24, derecha: 20, abajo: 40, izquierda: 48 };
  var anchoUtil = ANCHO - margen.izquierda - margen.derecha;
  var altoUtil = ALTO - margen.arriba - margen.abajo;
  var SVG = 'http://www.w3.org/2000/svg';

  function elemento(nombre, atributos, texto) {
    var el = document.createElementNS(SVG, nombre);
    Object.keys(atributos || {}).forEach(function (clave) { el.setAttribute(clave, atributos[clave]); });
    if (texto !== undefined) { el.textContent = texto; }
    return el;
  }

  function fechaLocal(iso) {
    var partes = iso.split('-');
    return new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]));
  }

  function etiquetaFecha(fecha) {
    var dia = String(fecha.getDate()).padStart(2, '0');
    var mes = String(fecha.getMonth() + 1).padStart(2, '0');
    return dia + '/' + mes + '/' + String(fecha.getFullYear()).slice(2);
  }

  function formatoKg(valor) {
    return (Math.round(valor * 100) / 100).toString().replace('.', ',') + ' kg';
  }

  var datos = puntos.map(function (p) { return { fecha: fechaLocal(p.fecha), peso: Number(p.peso) }; });
  var tiempos = datos.map(function (d) { return d.fecha.getTime(); });
  var pesos = datos.map(function (d) { return d.peso; });
  var tMin = Math.min.apply(null, tiempos), tMax = Math.max.apply(null, tiempos);
  var pMin = Math.min.apply(null, pesos), pMax = Math.max.apply(null, pesos);
  if (tMax === tMin) { tMin -= 86400000; tMax += 86400000; }
  var holgura = Math.max((pMax - pMin) * 0.2, pMax * 0.1, 0.5);
  pMin = Math.max(0, pMin - holgura);
  pMax = pMax + holgura;

  function x(t) { return margen.izquierda + ((t - tMin) / (tMax - tMin)) * anchoUtil; }
  function y(p) { return margen.arriba + altoUtil - ((p - pMin) / (pMax - pMin)) * altoUtil; }

  var svg = elemento('svg', { viewBox: '0 0 ' + ANCHO + ' ' + ALTO, role: 'img', 'aria-label': 'Curva de peso' });

  // Rejilla y eje Y (4 divisiones)
  for (var i = 0; i <= 4; i++) {
    var valor = pMin + ((pMax - pMin) * i) / 4;
    var yy = y(valor);
    svg.appendChild(elemento('line', { x1: margen.izquierda, x2: ANCHO - margen.derecha, y1: yy, y2: yy, class: 'grafica-peso__rejilla' }));
    svg.appendChild(elemento('text', { x: margen.izquierda - 8, y: yy + 4, 'text-anchor': 'end', class: 'grafica-peso__eje' }, formatoKg(valor).replace(' kg', '')));
  }
  svg.appendChild(elemento('text', { x: margen.izquierda - 8, y: 12, 'text-anchor': 'end', class: 'grafica-peso__eje' }, 'kg'));

  // Eje X: primera, última y hasta 3 fechas intermedias sin solaparse
  var cantidadEtiquetas = Math.min(datos.length, 5);
  for (var j = 0; j < cantidadEtiquetas; j++) {
    var indice = Math.round((j * (datos.length - 1)) / Math.max(cantidadEtiquetas - 1, 1));
    var d = datos[indice];
    svg.appendChild(elemento('text', { x: x(d.fecha.getTime()), y: ALTO - 14, 'text-anchor': 'middle', class: 'grafica-peso__eje' }, etiquetaFecha(d.fecha)));
  }

  // Área y línea
  var ruta = datos.map(function (d, k) { return (k === 0 ? 'M' : 'L') + x(d.fecha.getTime()).toFixed(1) + ' ' + y(d.peso).toFixed(1); }).join(' ');
  if (datos.length > 1) {
    var area = ruta + ' L' + x(datos[datos.length - 1].fecha.getTime()).toFixed(1) + ' ' + (margen.arriba + altoUtil) +
      ' L' + x(datos[0].fecha.getTime()).toFixed(1) + ' ' + (margen.arriba + altoUtil) + ' Z';
    svg.appendChild(elemento('path', { d: area, class: 'grafica-peso__area' }));
    svg.appendChild(elemento('path', { d: ruta, class: 'grafica-peso__linea' }));
  }

  // Puntos con su valor
  datos.forEach(function (d, k) {
    var cx = x(d.fecha.getTime()), cy = y(d.peso);
    var grupo = elemento('g');
    grupo.appendChild(elemento('circle', { cx: cx, cy: cy, r: 5, class: 'grafica-peso__punto' }));
    var titulo = elemento('title', {}, etiquetaFecha(d.fecha) + ': ' + formatoKg(d.peso));
    grupo.appendChild(titulo);
    if (datos.length <= 8 || k === datos.length - 1 || k === 0) {
      var anclaje = k === datos.length - 1 && datos.length > 1 ? 'end' : (k === 0 && datos.length > 1 ? 'start' : 'middle');
      grupo.appendChild(elemento('text', { x: cx, y: cy - 10, 'text-anchor': anclaje, class: 'grafica-peso__valor' }, formatoKg(d.peso)));
    }
    svg.appendChild(grupo);
  });

  contenedor.innerHTML = '';
  contenedor.appendChild(svg);
})();
