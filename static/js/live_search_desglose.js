/**
 * Sandia VetCare - Buscador Universal en Vivo con Desglose Flotante
 * Permite buscar pacientes y tutores en tiempo real desde cualquier página,
 * mostrando todas las coincidencias de toda la base de datos sin importar la paginación.
 */
(function() {
  'use strict';

  function initLiveSearch() {
    // Buscar inputs de búsqueda candidatos en la página
    const searchInputs = document.querySelectorAll(
      'input#q, input#inputBuscador, input[type="search"], .live-search-input, form[role="search"] input[type="text"]'
    );

    searchInputs.forEach(input => {
      if (input.dataset.liveSearchActive || input.id === 'buscar-mascota' || input.id === 'buscar-tutor') {
        // Ignorar si ya está inicializado o si es un selector embebido de modal específico
        return;
      }
      input.dataset.liveSearchActive = 'true';
      setupLiveDropdown(input);
    });
  }

  function setupLiveDropdown(input) {
    let timer = null;
    let currentQuery = '';
    const isTutoresPage = window.location.pathname.includes('/tutores');

    // Crear contenedor flotante del desglose
    const wrapper = document.createElement('div');
    wrapper.className = 'desglose-search-wrapper position-relative w-100';
    
    // Insertar wrapper alrededor del input o como hermano
    const parent = input.parentElement;
    const isInputGroup = parent.classList.contains('input-group');
    const targetParent = isInputGroup ? parent.parentElement : parent;

    const dropdown = document.createElement('div');
    dropdown.className = 'desglose-busqueda-flotante shadow-lg d-none';
    dropdown.setAttribute('role', 'listbox');

    if (isInputGroup) {
      parent.insertAdjacentElement('afterend', dropdown);
    } else {
      input.insertAdjacentElement('afterend', dropdown);
    }

    // Función para resaltar coincidencias
    function highlight(text, query) {
      if (!text || !query) return text || '';
      const esc = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const reg = new RegExp(`(${esc})`, 'gi');
      return text.replace(reg, '<mark class="desglose-highlight">$1</mark>');
    }

    // Renderizar lista de mascotas
    function renderMascotas(items, query) {
      if (!items || items.length === 0) {
        dropdown.innerHTML = `
          <div class="desglose-header">
            <span class="small fw-bold text-muted"><i class="bi bi-search me-1"></i>Búsqueda en todo el sistema</span>
            <span class="badge bg-secondary-subtle text-secondary rounded-pill">0 resultados</span>
          </div>
          <div class="p-3 text-center text-muted small">
            <i class="bi bi-emoji-neutral fs-4 d-block mb-1 text-secondary"></i>
            No se encontraron pacientes con "<strong>${escapeHtml(query)}</strong>" en ninguna página.
          </div>
          <div class="desglose-footer">
            <small class="text-muted"><i class="bi bi-info-circle me-1"></i>Presiona <strong>Enter</strong> o <strong>Buscar</strong> para filtrar.</small>
          </div>
        `;
        dropdown.classList.remove('d-none');
        return;
      }

      let html = `
        <div class="desglose-header d-flex justify-content-between align-items-center">
          <span class="small fw-bold text-dark">
            <i class="bi bi-stars text-danger me-1"></i>Desglose en vivo de Pacientes
          </span>
          <span class="badge bg-danger-subtle text-danger border border-danger-subtle rounded-pill px-2.5 py-1 fw-bold">
            ${items.length} ${items.length === 1 ? 'coincidencia' : 'coincidencias'} en total
          </span>
        </div>
        <div class="desglose-list">
      `;

      items.forEach(m => {
        const nombreHL = highlight(m.nombre, query);
        const tutorNombre = m.tutor ? m.tutor.nombre : 'Sin tutor';
        const tutorHL = highlight(tutorNombre, query);
        const emoji = m.emoji || '🐾';
        const raza = m.raza ? ` · ${m.raza}` : '';
        const tel = m.tutor && m.tutor.telefono ? ` · 📞 ${m.tutor.telefono}` : '';
        const urlFicha = m.url_ficha || `/historias/mascota/${m.id}`;
        const urlDetalle = m.url_detalle || `/mascotas/${m.id}`;
        const urlConsulta = m.url_consulta_nueva || `/historias/mascota/${m.id}/consulta/nueva`;

        html += `
          <div class="desglose-item p-2 p-md-2.5 d-flex align-items-center justify-content-between gap-2 border-bottom" data-url="${urlFicha}">
            <div class="d-flex align-items-center gap-2.5 min-w-0 flex-grow-1">
              <div class="desglose-avatar flex-shrink-0">
                ${m.foto_mini ? `<img src="${m.foto_mini}" alt="${m.nombre}" class="rounded-circle object-fit-cover" style="width:38px;height:38px;">` : `<div class="avatar-emoji">${emoji}</div>`}
              </div>
              <div class="min-w-0 flex-grow-1">
                <div class="d-flex align-items-center gap-1.5 flex-wrap">
                  <span class="fw-bold text-dark fs-6 lh-sm">${nombreHL}</span>
                  <span class="badge bg-light text-dark border rounded-pill small" style="font-size: 0.7rem;">${m.especie_etiqueta || m.especie}${raza}</span>
                  ${m.activo === false ? '<span class="badge bg-secondary rounded-pill" style="font-size:0.65rem;">Inactivo</span>' : ''}
                </div>
                <div class="text-muted small text-truncate" style="font-size: 0.78rem;">
                  <i class="bi bi-person me-0.5"></i>Tutor: <strong>${tutorHL}</strong>${tel}
                </div>
              </div>
            </div>
            <div class="d-flex align-items-center gap-1 flex-shrink-0">
              <a href="${urlFicha}" class="btn btn-sm btn-outline-success rounded-pill px-2.5 py-0.5 fw-bold" style="font-size: 0.75rem;" title="Ver Ficha Médica">
                <i class="bi bi-clipboard2-pulse me-1"></i>Ficha
              </a>
              <a href="${urlConsulta}" class="btn btn-sm btn-outline-primary rounded-pill px-2.5 py-0.5 fw-bold d-none d-sm-inline-flex" style="font-size: 0.75rem;" title="Nueva Consulta">
                <i class="bi bi-plus-lg me-1"></i>Consulta
              </a>
              <a href="${urlDetalle}" class="btn btn-sm btn-light rounded-circle p-1 text-secondary" style="width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center;" title="Ver perfil de mascota">
                <i class="bi bi-chevron-right"></i>
              </a>
            </div>
          </div>
        `;
      });

      html += `
        </div>
        <div class="desglose-footer d-flex justify-content-between align-items-center">
          <small class="text-muted"><i class="bi bi-keyboard me-1"></i>Presiona <strong>Enter</strong> para ver la lista completa</small>
          <span class="small text-danger fw-bold cursor-pointer" onclick="this.closest('.desglose-busqueda-flotante').classList.add('d-none')">Cerrar ✕</span>
        </div>
      `;

      dropdown.innerHTML = html;

      // Evento de clic en filas
      dropdown.querySelectorAll('.desglose-item').forEach(item => {
        item.addEventListener('click', function(e) {
          if (e.target.closest('a') || e.target.closest('button')) return;
          const url = this.getAttribute('data-url');
          if (url) window.location.href = url;
        });
      });

      dropdown.classList.remove('d-none');
    }

    // Renderizar tutores si estamos en módulo de tutores
    function renderTutores(items, query) {
      if (!items || items.length === 0) {
        dropdown.innerHTML = `
          <div class="desglose-header">
            <span class="small fw-bold text-muted"><i class="bi bi-search me-1"></i>Búsqueda de Tutores</span>
            <span class="badge bg-secondary-subtle text-secondary rounded-pill">0 resultados</span>
          </div>
          <div class="p-3 text-center text-muted small">
            No se encontraron tutores con "<strong>${escapeHtml(query)}</strong>" en ninguna página.
          </div>
        `;
        dropdown.classList.remove('d-none');
        return;
      }

      let html = `
        <div class="desglose-header d-flex justify-content-between align-items-center">
          <span class="small fw-bold text-dark"><i class="bi bi-people-fill text-primary me-1"></i>Desglose en vivo de Tutores</span>
          <span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill px-2.5 py-1 fw-bold">${items.length} tutores</span>
        </div>
        <div class="desglose-list">
      `;

      items.forEach(t => {
        const nombreHL = highlight(t.nombre, query);
        const doc = t.documento ? ` · Doc: ${t.documento}` : '';
        const tel = t.telefono ? ` · 📞 ${t.telefono}` : '';
        const mascotasStr = (t.mascotas || []).map(m => `${m.emoji || '🐾'} ${m.nombre}`).join(', ');

        html += `
          <div class="desglose-item p-2 p-md-2.5 d-flex align-items-center justify-content-between gap-2 border-bottom" data-url="${t.url}">
            <div class="min-w-0 flex-grow-1">
              <div class="fw-bold text-dark fs-6 lh-sm">${nombreHL}</div>
              <div class="text-muted small" style="font-size: 0.78rem;">
                ${tel}${doc}
              </div>
              ${mascotasStr ? `<div class="small text-secondary mt-0.5" style="font-size: 0.75rem;"><strong>Mascotas:</strong> ${mascotasStr}</div>` : ''}
            </div>
            <a href="${t.url}" class="btn btn-sm btn-outline-primary rounded-pill px-2.5 py-0.5 fw-bold flex-shrink-0" style="font-size: 0.75rem;">
              Ver Tutor →
            </a>
          </div>
        `;
      });

      html += `</div>`;
      dropdown.innerHTML = html;

      dropdown.querySelectorAll('.desglose-item').forEach(item => {
        item.addEventListener('click', function(e) {
          if (e.target.closest('a')) return;
          const url = this.getAttribute('data-url');
          if (url) window.location.href = url;
        });
      });

      dropdown.classList.remove('d-none');
    }

    function doSearch() {
      const q = input.value.trim();
      currentQuery = q;
      if (q.length < 1) {
        dropdown.classList.add('d-none');
        dropdown.innerHTML = '';
        return;
      }

      const endpoint = isTutoresPage ? `/api/tutores/buscar?q=${encodeURIComponent(q)}&limite=20` : `/api/mascotas/buscar?q=${encodeURIComponent(q)}&limite=20`;

      fetch(endpoint)
        .then(res => res.json())
        .then(data => {
          if (input.value.trim() !== currentQuery) return; // Evitar carrera
          if (isTutoresPage) {
            renderTutores(data, q);
          } else {
            renderMascotas(data, q);
          }
        })
        .catch(err => {
          console.warn('Error en búsqueda en vivo:', err);
        });
    }

    input.addEventListener('input', function() {
      clearTimeout(timer);
      timer = setTimeout(doSearch, 150);
    });

    input.addEventListener('focus', function() {
      if (input.value.trim().length >= 1 && dropdown.innerHTML.trim().length > 0) {
        dropdown.classList.remove('d-none');
      }
    });

    // Cerrar al hacer clic afuera
    document.addEventListener('click', function(e) {
      if (!dropdown.contains(e.target) && e.target !== input) {
        dropdown.classList.add('d-none');
      }
    });

    // Tecla Escape cierra
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        dropdown.classList.add('d-none');
      }
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Inicializar al cargar DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLiveSearch);
  } else {
    initLiveSearch();
  }
})();
