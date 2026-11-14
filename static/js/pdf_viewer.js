/**
 * Sandia Universal PDF Viewer
 * Renderizador de PDFs 100% responsive para:
 * - Teléfonos móviles (iOS Safari, Android Chrome, navegadores web)
 * - Tablets (iPadOS, Android Tablets)
 * - Aplicación PWA instalada (Standalone Web App)
 * - Computadores de escritorio / Laptops
 *
 * Desarrollado con Mozilla PDF.js nativo sobre HTML5 Canvas y aceleración gráfica.
 */
(function (global) {
  'use strict';

  var pdfjs = global.pdfjsLib || global['pdfjs-dist/build/pdf'];

  if (pdfjs && pdfjs.GlobalWorkerOptions) {
    pdfjs.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.js';
  }

  function debounce(fn, delay) {
    var timer = null;
    return function () {
      var context = this;
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(context, args);
      }, delay);
    };
  }

  function crearIcono(biClass) {
    var i = document.createElement('i');
    i.className = 'bi ' + biClass;
    return i;
  }

  /**
   * Instancia del Visor PDF
   */
  function SandiaViewerInstance(container, source, options) {
    this.container = typeof container === 'string' ? document.getElementById(container) : container;
    this.source = source;
    this.options = options || {};
    this.pdfDoc = null;
    this.numPages = 0;
    this.currentPage = 1;
    this.baseScale = 1.0;
    this.zoomLevel = 1.0; // Multiplicador relativo: 1.0 = fit-width (100%)
    this.renderTasks = {};
    this.pagesData = [];
    this.isRendering = false;
    this.destroyed = false;

    if (!this.container) {
      console.error('[SandiaPdfViewer] Contenedor no encontrado:', container);
      return;
    }

    this.init();
  }

  SandiaViewerInstance.prototype.init = function () {
    var self = this;
    var opts = this.options;

    // Estructura DOM principal
    this.container.innerHTML = '';
    this.container.classList.add('sandia-pdf-container');
    if (opts.height) {
      this.container.style.height = opts.height;
    }

    // 1. Barra de Herramientas
    var showToolbar = opts.showToolbar !== false;
    if (showToolbar) {
      this.toolbarEl = document.createElement('div');
      this.toolbarEl.className = 'sandia-pdf-toolbar';

      // Grupo Izquierdo: Paginación
      var groupPag = document.createElement('div');
      groupPag.className = 'sandia-pdf-toolbar-group';

      this.btnPrev = document.createElement('button');
      this.btnPrev.type = 'button';
      this.btnPrev.className = 'btn-pdf-control';
      this.btnPrev.title = 'Página anterior';
      this.btnPrev.appendChild(crearIcono('bi-chevron-left'));
      this.btnPrev.disabled = true;

      this.pageText = document.createElement('span');
      this.pageText.className = 'sandia-pdf-page-indicator';
      this.pageText.textContent = 'Pág. 1 / ...';

      this.btnNext = document.createElement('button');
      this.btnNext.type = 'button';
      this.btnNext.className = 'btn-pdf-control';
      this.btnNext.title = 'Página siguiente';
      this.btnNext.appendChild(crearIcono('bi-chevron-right'));
      this.btnNext.disabled = true;

      groupPag.appendChild(this.btnPrev);
      groupPag.appendChild(this.pageText);
      groupPag.appendChild(this.btnNext);
      this.toolbarEl.appendChild(groupPag);

      // Grupo Central: Zoom
      var groupZoom = document.createElement('div');
      groupZoom.className = 'sandia-pdf-toolbar-group';

      this.btnZoomOut = document.createElement('button');
      this.btnZoomOut.type = 'button';
      this.btnZoomOut.className = 'btn-pdf-control';
      this.btnZoomOut.title = 'Reducir zoom';
      this.btnZoomOut.appendChild(crearIcono('bi-dash-lg'));

      this.zoomText = document.createElement('span');
      this.zoomText.className = 'sandia-pdf-zoom-indicator';
      this.zoomText.textContent = '100%';

      this.btnZoomIn = document.createElement('button');
      this.btnZoomIn.type = 'button';
      this.btnZoomIn.className = 'btn-pdf-control';
      this.btnZoomIn.title = 'Aumentar zoom';
      this.btnZoomIn.appendChild(crearIcono('bi-plus-lg'));

      this.btnFit = document.createElement('button');
      this.btnFit.type = 'button';
      this.btnFit.className = 'btn-pdf-control';
      this.btnFit.title = 'Ajustar al ancho de pantalla';
      this.btnFit.appendChild(crearIcono('bi-arrows-expand'));

      groupZoom.appendChild(this.btnZoomOut);
      groupZoom.appendChild(this.zoomText);
      groupZoom.appendChild(this.btnZoomIn);
      groupZoom.appendChild(this.btnFit);
      this.toolbarEl.appendChild(groupZoom);

      // Grupo Derecho: Acciones (Descargar, Pestaña nueva, Pantalla completa)
      var groupActions = document.createElement('div');
      groupActions.className = 'sandia-pdf-toolbar-group';

      // Pantalla Completa
      this.btnFullscreen = document.createElement('button');
      this.btnFullscreen.type = 'button';
      this.btnFullscreen.className = 'btn-pdf-control';
      this.btnFullscreen.title = 'Pantalla completa';
      this.btnFullscreen.appendChild(crearIcono('bi-fullscreen'));
      groupActions.appendChild(this.btnFullscreen);

      // Pestaña Nueva (si hay URL de origen)
      var fileUrl = typeof this.source === 'string' ? this.source : (opts.downloadUrl || null);
      if (fileUrl) {
        this.btnNewTab = document.createElement('a');
        this.btnNewTab.href = fileUrl;
        this.btnNewTab.target = '_blank';
        this.btnNewTab.rel = 'noopener';
        this.btnNewTab.className = 'btn-pdf-control';
        this.btnNewTab.title = 'Abrir PDF en pestaña nueva';
        this.btnNewTab.appendChild(crearIcono('bi-box-arrow-up-right'));
        groupActions.appendChild(this.btnNewTab);

        this.btnDownload = document.createElement('a');
        this.btnDownload.href = fileUrl;
        this.btnDownload.download = opts.filename || 'documento.pdf';
        this.btnDownload.className = 'btn-pdf-control';
        this.btnDownload.title = 'Descargar archivo PDF';
        this.btnDownload.appendChild(crearIcono('bi-download'));
        groupActions.appendChild(this.btnDownload);
      }

      this.toolbarEl.appendChild(groupActions);
      this.container.appendChild(this.toolbarEl);

      // Eventos barra de herramientas
      this.btnPrev.addEventListener('click', function () {
        self.scrollToPage(self.currentPage - 1);
      });
      this.btnNext.addEventListener('click', function () {
        self.scrollToPage(self.currentPage + 1);
      });
      this.btnZoomIn.addEventListener('click', function () {
        self.setZoom(self.zoomLevel + 0.25);
      });
      this.btnZoomOut.addEventListener('click', function () {
        self.setZoom(self.zoomLevel - 0.25);
      });
      this.btnFit.addEventListener('click', function () {
        self.setZoom(1.0);
      });
      this.btnFullscreen.addEventListener('click', function () {
        self.toggleFullscreen();
      });
    }

    // 2. Viewport con scroll táctil
    this.viewportEl = document.createElement('div');
    this.viewportEl.className = 'sandia-pdf-viewport';

    // Loading State Inicial
    this.loadingEl = document.createElement('div');
    this.loadingEl.className = 'sandia-pdf-loading';
    this.loadingEl.innerHTML =
      '<div class="spinner-border spinner-border-sm text-danger mb-2" role="status"></div>' +
      '<span class="small text-white-50">Cargando documento PDF...</span>';
    this.viewportEl.appendChild(this.loadingEl);

    // Contenedor de páginas
    this.pagesContainer = document.createElement('div');
    this.pagesContainer.className = 'sandia-pdf-pages';
    this.viewportEl.appendChild(this.pagesContainer);

    this.container.appendChild(this.viewportEl);

    // Scroll listener para actualizar número de página activa
    this.viewportEl.addEventListener('scroll', debounce(function () {
      self.updateCurrentPageFromScroll();
    }, 100));

    // Resize listener responsivo (p. ej. rotación de tablet / celular vertical a horizontal)
    this.resizeHandler = debounce(function () {
      if (self.destroyed || !self.pdfDoc) return;
      if (Math.abs(self.zoomLevel - 1.0) < 0.05) {
        self.calculateBaseScale().then(function () {
          self.renderAllPages();
        });
      }
    }, 250);
    window.addEventListener('resize', this.resizeHandler);

    // Cargar Documento
    this.loadDocument();
  };

  SandiaViewerInstance.prototype.loadDocument = function () {
    var self = this;
    if (!pdfjs) {
      this.showError('No se encontró el motor Mozilla PDF.js.');
      return;
    }

    var loadPromise;
    if (typeof this.source === 'string') {
      loadPromise = pdfjs.getDocument(this.source).promise;
    } else if (this.source instanceof ArrayBuffer || this.source instanceof Uint8Array) {
      loadPromise = pdfjs.getDocument({ data: this.source }).promise;
    } else if (this.source instanceof Blob || (global.File && this.source instanceof File)) {
      var reader = new FileReader();
      var promiseFileReader = new Promise(function (resolve, reject) {
        reader.onload = function (e) {
          resolve(new Uint8Array(e.target.result));
        };
        reader.onerror = reject;
      });
      reader.readAsArrayBuffer(this.source);
      loadPromise = promiseFileReader.then(function (typedArray) {
        return pdfjs.getDocument({ data: typedArray }).promise;
      });
    } else {
      this.showError('Formato de origen no reconocido.');
      return;
    }

    loadPromise
      .then(function (doc) {
        if (self.destroyed) return;
        self.pdfDoc = doc;
        self.numPages = doc.numPages;
        if (self.loadingEl && self.loadingEl.parentNode) {
          self.loadingEl.parentNode.removeChild(self.loadingEl);
        }
        return self.calculateBaseScale().then(function () {
          self.setupPagesDom();
          self.renderAllPages();
          self.updatePaginationControls();
          if (typeof self.options.onLoaded === 'function') {
            self.options.onLoaded(self);
          }
        });
      })
      .catch(function (err) {
        console.error('[SandiaPdfViewer] Error cargando PDF:', err);
        self.showError('No se pudo visualizar el PDF directamente en este dispositivo.', err);
        if (typeof self.options.onError === 'function') {
          self.options.onError(err);
        }
      });
  };

  SandiaViewerInstance.prototype.calculateBaseScale = function () {
    var self = this;
    return this.pdfDoc.getPage(1).then(function (firstPage) {
      var unscaledViewport = firstPage.getViewport({ scale: 1.0 });
      var availWidth = self.viewportEl.clientWidth || self.container.clientWidth || 360;
      var targetWidth = Math.max(availWidth - 28, 200);
      var scale = targetWidth / unscaledViewport.width;
      self.baseScale = Math.min(Math.max(scale, 0.35), 2.5);
    });
  };

  SandiaViewerInstance.prototype.setupPagesDom = function () {
    this.pagesContainer.innerHTML = '';
    this.pagesData = [];

    for (var i = 1; i <= this.numPages; i++) {
      var wrapper = document.createElement('div');
      wrapper.className = 'sandia-pdf-page-wrapper';
      wrapper.dataset.pageNumber = i;

      var canvas = document.createElement('canvas');
      canvas.className = 'sandia-pdf-page-canvas';
      wrapper.appendChild(canvas);

      if (this.numPages > 1) {
        var badge = document.createElement('span');
        badge.className = 'sandia-pdf-page-number';
        badge.textContent = 'Pág. ' + i + ' / ' + this.numPages;
        wrapper.appendChild(badge);
      }

      this.pagesContainer.appendChild(wrapper);

      this.pagesData.push({
        pageNumber: i,
        wrapper: wrapper,
        canvas: canvas,
        rendered: false,
      });
    }
  };

  SandiaViewerInstance.prototype.renderAllPages = function () {
    var self = this;
    var effectiveScale = this.baseScale * this.zoomLevel;
    var dpr = window.devicePixelRatio || 1;

    this.pagesData.forEach(function (pageItem) {
      var pageNum = pageItem.pageNumber;
      var canvas = pageItem.canvas;
      var wrapper = pageItem.wrapper;

      if (self.renderTasks[pageNum]) {
        try {
          self.renderTasks[pageNum].cancel();
        } catch (e) {}
        self.renderTasks[pageNum] = null;
      }

      self.pdfDoc.getPage(pageNum).then(function (page) {
        if (self.destroyed) return;

        var viewport = page.getViewport({ scale: effectiveScale });

        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);

        canvas.style.width = Math.floor(viewport.width) + 'px';
        canvas.style.height = Math.floor(viewport.height) + 'px';

        wrapper.style.width = Math.floor(viewport.width) + 'px';
        wrapper.style.height = Math.floor(viewport.height) + 'px';

        var ctx = canvas.getContext('2d', { alpha: false });
        var transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null;

        var renderTask = page.render({
          canvasContext: ctx,
          viewport: viewport,
          transform: transform,
        });

        self.renderTasks[pageNum] = renderTask;

        renderTask.promise
          .then(function () {
            pageItem.rendered = true;
            self.renderTasks[pageNum] = null;
          })
          .catch(function (err) {
            if (err && err.name === 'RenderingCancelledException') {
              return;
            }
            console.warn('[SandiaPdfViewer] Advertencia renderizando página ' + pageNum, err);
          });
      });
    });
  };

  SandiaViewerInstance.prototype.setZoom = function (newZoom) {
    var clamped = Math.min(Math.max(newZoom, 0.4), 3.0);
    this.zoomLevel = clamped;
    if (this.zoomText) {
      this.zoomText.textContent = Math.round(this.zoomLevel * 100) + '%';
    }
    this.renderAllPages();
  };

  SandiaViewerInstance.prototype.scrollToPage = function (pageNum) {
    if (pageNum < 1 || pageNum > this.numPages) return;
    var target = this.pagesData[pageNum - 1];
    if (target && target.wrapper) {
      target.wrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
      this.currentPage = pageNum;
      this.updatePaginationControls();
    }
  };

  SandiaViewerInstance.prototype.updateCurrentPageFromScroll = function () {
    if (!this.pagesData || this.pagesData.length === 0) return;
    var viewportRect = this.viewportEl.getBoundingClientRect();
    var viewportMid = viewportRect.top + viewportRect.height / 3;

    var bestPage = 1;
    var minDiff = Infinity;

    for (var i = 0; i < this.pagesData.length; i++) {
      var rect = this.pagesData[i].wrapper.getBoundingClientRect();
      var diff = Math.abs(rect.top - viewportMid);
      if (diff < minDiff) {
        minDiff = diff;
        bestPage = i + 1;
      }
    }

    if (this.currentPage !== bestPage) {
      this.currentPage = bestPage;
      this.updatePaginationControls();
    }
  };

  SandiaViewerInstance.prototype.updatePaginationControls = function () {
    if (this.pageText) {
      this.pageText.textContent = 'Pág. ' + this.currentPage + ' / ' + this.numPages;
    }
    if (this.btnPrev) {
      this.btnPrev.disabled = this.currentPage <= 1;
    }
    if (this.btnNext) {
      this.btnNext.disabled = this.currentPage >= this.numPages;
    }
  };

  SandiaViewerInstance.prototype.toggleFullscreen = function () {
    var elem = this.container;
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      if (elem.requestFullscreen) {
        elem.requestFullscreen();
      } else if (elem.webkitRequestFullscreen) {
        elem.webkitRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  };

  SandiaViewerInstance.prototype.showError = function (msg, err) {
    if (this.destroyed) return;
    this.pagesContainer.innerHTML = '';
    var fileUrl = typeof this.source === 'string' ? this.source : (this.options.downloadUrl || null);

    var errorBox = document.createElement('div');
    errorBox.className = 'sandia-pdf-error p-4 text-center';
    errorBox.innerHTML =
      '<i class="bi bi-file-earmark-pdf text-danger fs-1 mb-2 d-block"></i>' +
      '<h6 class="text-white fw-bold mb-1">Previsualización de Documento</h6>' +
      '<p class="small text-white-50 mb-3">' + (msg || 'No se pudo cargar el documento.') + '</p>' +
      (fileUrl
        ? '<a href="' + fileUrl + '" target="_blank" class="btn btn-sm btn-danger rounded-pill px-4 fw-bold shadow-sm">' +
          '<i class="bi bi-download me-1"></i> Abrir o Descargar PDF</a>'
        : '');

    this.viewportEl.innerHTML = '';
    this.viewportEl.appendChild(errorBox);
  };

  SandiaViewerInstance.prototype.destroy = function () {
    this.destroyed = true;
    window.removeEventListener('resize', this.resizeHandler);
    for (var k in this.renderTasks) {
      if (this.renderTasks[k]) {
        try {
          this.renderTasks[k].cancel();
        } catch (e) {}
      }
    }
    this.renderTasks = {};
    if (this.pdfDoc) {
      try {
        this.pdfDoc.destroy();
      } catch (e) {}
      this.pdfDoc = null;
    }
    this.container.innerHTML = '';
  };

  // =========================================================================
  // API Pública y Global Modal
  // =========================================================================

  var SandiaPdfViewer = {
    instances: new Map(),

    /**
     * Renderiza un visor en el contenedor especificado.
     * @param {string|HTMLElement} container - Selector o elemento DOM.
     * @param {string|File|Blob|ArrayBuffer} source - Archivo o URL.
     * @param {object} options - Opciones de visualización.
     */
    render: function (container, source, options) {
      var elem = typeof container === 'string' ? document.getElementById(container) : container;
      if (!elem) {
        console.warn('[SandiaPdfViewer] Elemento no encontrado:', container);
        return null;
      }

      if (SandiaPdfViewer.instances.has(elem)) {
        try {
          SandiaPdfViewer.instances.get(elem).destroy();
        } catch (e) {}
        SandiaPdfViewer.instances.delete(elem);
      }

      var instance = new SandiaViewerInstance(elem, source, options);
      SandiaPdfViewer.instances.set(elem, instance);
      return instance;
    },

    /**
     * Abre el modal global responsivo de previsualización de documentos.
     * @param {string} url - URL del PDF.
     * @param {string} title - Título del documento.
     * @param {string} downloadUrl - URL de descarga directa opcional.
     */
    openModal: function (url, title, downloadUrl) {
      var modalId = 'modalGlobalPdfViewer';
      var modalEl = document.getElementById(modalId);

      if (!modalEl) {
        modalEl = document.createElement('div');
        modalEl.id = modalId;
        modalEl.className = 'modal fade';
        modalEl.tabIndex = -1;
        modalEl.setAttribute('aria-hidden', 'true');
        modalEl.innerHTML =
          '<div class="modal-dialog modal-xl modal-dialog-centered modal-fullscreen-sm-down">' +
            '<div class="modal-content border-0 shadow-lg rounded-4 overflow-hidden bg-dark text-white">' +
              '<div class="modal-header bg-dark border-secondary py-2.5 px-3 d-flex align-items-center justify-content-between">' +
                '<div class="d-flex align-items-center gap-2 min-w-0 me-2">' +
                  '<i class="bi bi-file-earmark-pdf-fill text-danger fs-5"></i>' +
                  '<span class="fw-bold modal-title-pdf text-truncate small" id="globalPdfModalTitle">Documento PDF</span>' +
                '</div>' +
                '<div class="d-flex align-items-center gap-2">' +
                  '<a id="globalPdfModalDownload" href="#" download class="btn btn-xs btn-outline-light rounded-pill px-2.5 py-1" title="Descargar PDF">' +
                    '<i class="bi bi-download me-1"></i>Descargar' +
                  '</a>' +
                  '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Cerrar"></button>' +
                '</div>' +
              '</div>' +
              '<div class="modal-body p-0 bg-dark" style="height: 75vh; min-height: 480px;">' +
                '<div id="globalPdfViewerContainer" style="width: 100%; height: 100%;"></div>' +
              '</div>' +
            '</div>' +
          '</div>';
        document.body.appendChild(modalEl);

        modalEl.addEventListener('hidden.bs.modal', function () {
          var container = document.getElementById('globalPdfViewerContainer');
          if (container && SandiaPdfViewer.instances.has(container)) {
            SandiaPdfViewer.instances.get(container).destroy();
            SandiaPdfViewer.instances.delete(container);
          }
        });
      }

      var titleEl = document.getElementById('globalPdfModalTitle');
      if (titleEl) {
        titleEl.textContent = title || 'Documento PDF';
      }

      var downloadEl = document.getElementById('globalPdfModalDownload');
      if (downloadEl) {
        var finalDownloadUrl = downloadUrl || url;
        downloadEl.href = finalDownloadUrl;
      }

      var containerEl = document.getElementById('globalPdfViewerContainer');
      var bsModal = global.bootstrap ? global.bootstrap.Modal.getOrCreateInstance(modalEl) : null;
      if (bsModal) {
        bsModal.show();
      }

      setTimeout(function () {
        SandiaPdfViewer.render(containerEl, url, {
          height: '100%',
          title: title,
          downloadUrl: downloadUrl || url,
          showToolbar: true,
        });
      }, 150);
    },

    /**
     * Auto-inicializa todos los contenedores con clase .sandia-pdf-embed
     */
    autoInit: function () {
      document.querySelectorAll('.sandia-pdf-embed').forEach(function (el) {
        var url = el.getAttribute('data-pdf-url');
        if (!url) return;
        var height = el.getAttribute('data-height') || '480px';
        var title = el.getAttribute('data-title') || '';
        SandiaPdfViewer.render(el, url, {
          height: height,
          title: title,
          downloadUrl: url,
        });
      });
    },
  };

  document.addEventListener('DOMContentLoaded', function () {
    SandiaPdfViewer.autoInit();

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-pdf-preview], .btn-preview-pdf');
      if (btn) {
        var url = btn.getAttribute('data-pdf-url') || btn.getAttribute('href');
        if (url && url !== '#') {
          e.preventDefault();
          var title = btn.getAttribute('data-pdf-title') || btn.getAttribute('title') || 'Previsualización de Documento';
          var download = btn.getAttribute('data-pdf-download') || url;
          SandiaPdfViewer.openModal(url, title, download);
        }
      }
    });
  });

  global.SandiaPdfViewer = SandiaPdfViewer;
})(window);
