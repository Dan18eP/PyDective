/**
 * PyDective PDF Viewer Controller (PDF.js Integration)
 * Proporciona:
 * 1. Renderizado interactivo del PDF real con PDF.js.
 * 2. Buscador exacto estilo Chrome (Ctrl+F, N de M, navegación anterior/siguiente, resaltado dual).
 * 3. Visual Grounding bidireccional (resaltado con Bounding Boxes animados para citas y hallazgos).
 */

class PydectivePdfViewer {
    constructor(options = {}) {
        this.pdfHash = options.pdfHash || '';
        this.containerId = options.containerId || 'pdf-viewer-pages-container';
        this.container = document.getElementById(this.containerId);
        this.searchInput = document.getElementById(options.searchInputId || 'pdf-search-input');
        this.searchCounter = document.getElementById(options.searchCounterId || 'pdf-search-counter');
        this.searchPrevBtn = document.getElementById(options.searchPrevId || 'pdf-search-prev');
        this.searchNextBtn = document.getElementById(options.searchNextId || 'pdf-search-next');
        this.searchCloseBtn = document.getElementById(options.searchCloseId || 'pdf-search-close');
        
        // Toolbar controls
        this.pageCurrentSpan = document.getElementById('pdf-page-current');
        this.pageTotalSpan = document.getElementById('pdf-page-total');
        this.btnPrevPage = document.getElementById('pdf-btn-prev');
        this.btnNextPage = document.getElementById('pdf-btn-next');
        this.btnZoomIn = document.getElementById('pdf-btn-zoom-in');
        this.btnZoomOut = document.getElementById('pdf-btn-zoom-out');
        this.btnFitWidth = document.getElementById('pdf-btn-fit-width');
        this.zoomLevelSpan = document.getElementById('pdf-zoom-level');

        this.pdfDoc = null;
        this.totalPages = 0;
        this.currentPage = 1;
        this.scale = 1.45;
        this.pageRenders = {}; // pageNum -> { canvas, overlay, viewport, pageObj }
        this.matches = [];
        this.currentMatchIndex = -1;
        this.groundingBox = null;
        this.searchDebounceTimer = null;

        this.init();
    }

    async init() {
        if (!this.pdfHash || !this.container) return;

        // Configurar PDF.js worker
        if (window.pdfjsLib) {
            pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        }

        this.bindEvents();
        await this.loadDocument();
    }

    bindEvents() {
        // Buscador Chrome-like
        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => {
                clearTimeout(this.searchDebounceTimer);
                this.searchDebounceTimer = setTimeout(() => this.executeSearch(this.searchInput.value), 250);
            });

            this.searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    if (e.shiftKey) {
                        this.prevMatch();
                    } else {
                        this.nextMatch();
                    }
                } else if (e.key === 'Escape') {
                    this.clearSearch();
                }
            });
        }

        if (this.searchPrevBtn) this.searchPrevBtn.addEventListener('click', () => this.prevMatch());
        if (this.searchNextBtn) this.searchNextBtn.addEventListener('click', () => this.nextMatch());
        if (this.searchCloseBtn) this.searchCloseBtn.addEventListener('click', () => this.clearSearch());

        // Atajo global Ctrl+F o Cmd+F para enfocar buscador
        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
                const searchBar = document.getElementById('pdf-finder-toolbar');
                if (searchBar && this.searchInput) {
                    e.preventDefault();
                    searchBar.classList.remove('hidden');
                    this.searchInput.focus();
                    this.searchInput.select();
                }
            }
        });

        // Controles de navegación y zoom
        if (this.btnPrevPage) this.btnPrevPage.addEventListener('click', () => this.goToPage(this.currentPage - 1));
        if (this.btnNextPage) this.btnNextPage.addEventListener('click', () => this.goToPage(this.currentPage + 1));
        if (this.btnZoomIn) this.btnZoomIn.addEventListener('click', () => this.changeZoom(0.15));
        if (this.btnZoomOut) this.btnZoomOut.addEventListener('click', () => this.changeZoom(-0.15));
        if (this.btnFitWidth) this.btnFitWidth.addEventListener('click', () => this.fitWidth());

        // Actualizar número de página visible según scroll
        if (this.container) {
            this.container.addEventListener('scroll', () => this.updateCurrentPageOnScroll());
        }
    }

    async loadDocument() {
        const url = `/documentos/${this.pdfHash}/raw`;
        this.container.innerHTML = `
            <div class="pdf-loading-state">
                <div class="loading-spinner"></div>
                <p>Cargando visor documental de alta fidelidad...</p>
            </div>
        `;

        try {
            const loadingTask = pdfjsLib.getDocument({
                url: url,
                cMapUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/cmaps/',
                cMapPacked: true,
            });

            this.pdfDoc = await loadingTask.promise;
            this.totalPages = this.pdfDoc.numPages;
            if (this.pageTotalSpan) this.pageTotalSpan.innerText = this.totalPages;
            
            this.container.innerHTML = '';
            await this.renderAllPages();
            this.updateCurrentPageUI(1);

            // Ajustar al ancho del contenedor para máxima legibilidad
            setTimeout(() => {
                this.fitWidth();
            }, 100);
        } catch (err) {
            console.error('[PyDective Viewer] Error cargando PDF:', err);
            this.container.innerHTML = `
                <div class="pdf-error-state">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ff4d4f" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <p>No se pudo cargar el archivo PDF original para visualización.</p>
                </div>
            `;
        }
    }

    async renderAllPages() {
        for (let p = 1; p <= this.totalPages; p++) {
            const pageCard = document.createElement('div');
            pageCard.className = 'pdf-page-card';
            pageCard.id = `pdf-page-card-${p}`;
            pageCard.dataset.pageNum = p;

            const pageHeader = document.createElement('div');
            pageHeader.className = 'pdf-page-num-pill';
            pageHeader.innerText = `Página ${p}`;

            const canvasWrapper = document.createElement('div');
            canvasWrapper.className = 'pdf-canvas-wrapper';
            canvasWrapper.id = `pdf-canvas-wrapper-${p}`;

            const canvas = document.createElement('canvas');
            canvas.className = 'pdf-canvas';
            canvas.id = `pdf-canvas-${p}`;

            const overlay = document.createElement('div');
            overlay.className = 'pdf-highlight-overlay';
            overlay.id = `pdf-overlay-${p}`;

            canvasWrapper.appendChild(canvas);
            canvasWrapper.appendChild(overlay);
            pageCard.appendChild(pageHeader);
            pageCard.appendChild(canvasWrapper);
            this.container.appendChild(pageCard);

            await this.renderPageCanvas(p, canvas, overlay);
        }
    }

    async renderPageCanvas(pageNum, canvas, overlay) {
        try {
            const page = await this.pdfDoc.getPage(pageNum);
            const viewport = page.getViewport({ scale: this.scale });

            const outputScale = window.devicePixelRatio || 1;
            canvas.width = Math.floor(viewport.width * outputScale);
            canvas.height = Math.floor(viewport.height * outputScale);
            canvas.style.width = Math.floor(viewport.width) + 'px';
            canvas.style.height = Math.floor(viewport.height) + 'px';

            overlay.style.width = Math.floor(viewport.width) + 'px';
            overlay.style.height = Math.floor(viewport.height) + 'px';

            const ctx = canvas.getContext('2d');
            ctx.scale(outputScale, outputScale);

            const renderContext = {
                canvasContext: ctx,
                viewport: viewport
            };

            await page.render(renderContext).promise;

            this.pageRenders[pageNum] = {
                canvas,
                overlay,
                viewport,
                pageWidthPts: page.view[2] - page.view[0],
                pageHeightPts: page.view[3] - page.view[1]
            };
        } catch (e) {
            console.warn(`[PyDective Viewer] Error renderizando página ${pageNum}:`, e);
        }
    }

    async executeSearch(query) {
        const cleanQuery = (query || '').trim();
        if (!cleanQuery) {
            this.clearSearch();
            return;
        }

        try {
            const resp = await fetch(`/documentos/${this.pdfHash}/search?q=${encodeURIComponent(cleanQuery)}`);
            const data = await resp.json();

            this.matches = data.coincidencias || [];
            this.currentMatchIndex = this.matches.length > 0 ? 0 : -1;
            this.updateSearchCounterUI();
            this.renderAllSearchHighlights();

            if (this.matches.length > 0) {
                this.focusCurrentMatch();
            }
        } catch (err) {
            console.error('[PyDective Viewer] Error en búsqueda exacta:', err);
        }
    }

    updateSearchCounterUI() {
        if (!this.searchCounter) return;
        if (this.matches.length === 0) {
            this.searchCounter.innerText = '0 de 0';
            this.searchCounter.classList.add('no-matches');
        } else {
            this.searchCounter.innerText = `${this.currentMatchIndex + 1} de ${this.matches.length}`;
            this.searchCounter.classList.remove('no-matches');
        }
    }

    renderAllSearchHighlights() {
        // Limpiar overlays existentes
        for (let p = 1; p <= this.totalPages; p++) {
            if (this.pageRenders[p] && this.pageRenders[p].overlay) {
                this.pageRenders[p].overlay.innerHTML = '';
            }
        }

        // Dibujar cada coincidencia pasiva
        this.matches.forEach((m, idx) => {
            const pInfo = this.pageRenders[m.pagina];
            if (!pInfo) return;

            const box = document.createElement('div');
            box.className = 'pdf-search-match-box';
            box.id = `match-box-${idx}`;
            box.dataset.matchIdx = idx;

            // Coordenadas PDF points a pixels
            const scaleX = parseFloat(pInfo.overlay.style.width) / m.ancho_pagina;
            const scaleY = parseFloat(pInfo.overlay.style.height) / m.alto_pagina;

            const [x0, y0, x1, y1] = m.bbox;
            box.style.left = `${x0 * scaleX}px`;
            box.style.top = `${y0 * scaleY}px`;
            box.style.width = `${Math.max(6, (x1 - x0) * scaleX)}px`;
            box.style.height = `${Math.max(12, (y1 - y0) * scaleY)}px`;

            box.addEventListener('click', () => {
                this.currentMatchIndex = idx;
                this.focusCurrentMatch();
            });

            pInfo.overlay.appendChild(box);
        });
    }

    focusCurrentMatch() {
        if (this.currentMatchIndex < 0 || this.currentMatchIndex >= this.matches.length) return;

        // Actualizar clases activas y remover badges anteriores de búsqueda
        document.querySelectorAll('.pdf-search-match-box.active').forEach(el => {
            el.classList.remove('active');
            const pin = el.querySelector('.pdf-match-pin');
            if (pin) pin.remove();
        });

        const activeBox = document.getElementById(`match-box-${this.currentMatchIndex}`);
        if (activeBox) {
            activeBox.classList.add('active');

            // Añadir pin flotante fluorescente indicando el número de coincidencia
            const pin = document.createElement('span');
            pin.className = 'pdf-match-pin';
            pin.innerText = `🔍 ${this.currentMatchIndex + 1}/${this.matches.length}`;
            activeBox.appendChild(pin);
        }

        this.updateSearchCounterUI();

        const match = this.matches[this.currentMatchIndex];
        this.goToPage(match.pagina, false);

        if (activeBox) {
            activeBox.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }
    }

    nextMatch() {
        if (this.matches.length === 0) return;
        this.currentMatchIndex = (this.currentMatchIndex + 1) % this.matches.length;
        this.focusCurrentMatch();
    }

    prevMatch() {
        if (this.matches.length === 0) return;
        this.currentMatchIndex = (this.currentMatchIndex - 1 + this.matches.length) % this.matches.length;
        this.focusCurrentMatch();
    }

    clearSearch() {
        if (this.searchInput) this.searchInput.value = '';
        this.matches = [];
        this.currentMatchIndex = -1;
        this.updateSearchCounterUI();
        for (let p = 1; p <= this.totalPages; p++) {
            if (this.pageRenders[p] && this.pageRenders[p].overlay) {
                this.pageRenders[p].overlay.innerHTML = '';
            }
        }
        const searchBar = document.getElementById('pdf-finder-toolbar');
        if (searchBar) searchBar.classList.add('hidden');
    }

    /**
     * Visual Grounding Forense:
     * Salta a una página y resalta con exactitud matemática el elemento (texto o imagen).
     */
    highlightSource(pageNum, bbox, label = 'Evidencia Documental') {
        const page = parseInt(pageNum, 10);
        if (isNaN(page) || page < 1 || page > this.totalPages) return;

        this.goToPage(page);

        const pInfo = this.pageRenders[page];
        if (!pInfo) return;

        // Limpiar grounding anterior
        const oldG = document.querySelectorAll('.pdf-grounding-target');
        oldG.forEach(el => el.remove());

        if (Array.isArray(bbox) && bbox.length === 4) {
            const [x0, y0, x1, y1] = bbox;
            const scaleX = parseFloat(pInfo.overlay.style.width) / pInfo.pageWidthPts;
            const scaleY = parseFloat(pInfo.overlay.style.height) / pInfo.pageHeightPts;

            const gBox = document.createElement('div');
            gBox.className = 'pdf-grounding-target animate-pulse-glow';
            gBox.style.left = `${x0 * scaleX}px`;
            gBox.style.top = `${y0 * scaleY}px`;
            gBox.style.width = `${Math.max(10, (x1 - x0) * scaleX)}px`;
            gBox.style.height = `${Math.max(12, (y1 - y0) * scaleY)}px`;

            const badge = document.createElement('span');
            badge.className = 'pdf-grounding-label';
            badge.innerText = label;
            gBox.appendChild(badge);

            pInfo.overlay.appendChild(gBox);

            setTimeout(() => {
                gBox.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
            }, 100);
        } else {
            // Si no hay bbox preciso, hacer scroll a la cabecera de la página
            const card = document.getElementById(`pdf-page-card-${page}`);
            if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    goToPage(pageNum, smoothScroll = true) {
        if (pageNum < 1 || pageNum > this.totalPages) return;
        this.currentPage = pageNum;
        this.updateCurrentPageUI(pageNum);

        const card = document.getElementById(`pdf-page-card-${pageNum}`);
        if (card) {
            card.scrollIntoView({ behavior: smoothScroll ? 'smooth' : 'auto', block: 'start' });
        }
    }

    updateCurrentPageUI(pageNum) {
        if (this.pageCurrentSpan) this.pageCurrentSpan.innerText = pageNum;
    }

    updateCurrentPageOnScroll() {
        if (!this.container) return;
        const containerTop = this.container.getBoundingClientRect().top;
        for (let p = 1; p <= this.totalPages; p++) {
            const card = document.getElementById(`pdf-page-card-${p}`);
            if (card) {
                const rect = card.getBoundingClientRect();
                if (rect.top <= containerTop + 150 && rect.bottom >= containerTop + 50) {
                    if (this.currentPage !== p) {
                        this.currentPage = p;
                        this.updateCurrentPageUI(p);
                    }
                    break;
                }
            }
        }
    }

    async changeZoom(delta) {
        const newScale = Math.min(3.0, Math.max(0.6, this.scale + delta));
        if (Math.abs(newScale - this.scale) > 0.01) {
            this.scale = newScale;
            if (this.zoomLevelSpan) this.zoomLevelSpan.innerText = `${Math.round(this.scale * 100)}%`;
            for (let p = 1; p <= this.totalPages; p++) {
                const pInfo = this.pageRenders[p];
                if (pInfo) {
                    await this.renderPageCanvas(p, pInfo.canvas, pInfo.overlay);
                }
            }
            if (this.matches.length > 0) {
                this.renderAllSearchHighlights();
                this.focusCurrentMatch();
            }
        }
    }

    async fitWidth() {
        if (!this.container) return;
        const containerWidth = this.container.clientWidth - 48; // padding
        const firstPage = this.pageRenders[1];
        if (firstPage && firstPage.pageWidthPts) {
            this.scale = containerWidth / firstPage.pageWidthPts;
            if (this.zoomLevelSpan) this.zoomLevelSpan.innerText = `${Math.round(this.scale * 100)}%`;
            for (let p = 1; p <= this.totalPages; p++) {
                const pInfo = this.pageRenders[p];
                if (pInfo) {
                    await this.renderPageCanvas(p, pInfo.canvas, pInfo.overlay);
                }
            }
            if (this.matches.length > 0) {
                this.renderAllSearchHighlights();
            }
        }
    }
}

// Inicialización global accesible para templates y chat
window.PydectivePdfViewer = PydectivePdfViewer;

window.highlightSourceInPdf = function(pageNum, bbox, label) {
    if (window.activePdfViewer) {
        window.activePdfViewer.highlightSource(pageNum, bbox, label);
    } else {
        console.warn('[PyDective] Visor de PDF no inicializado aún.');
    }
};

window.triggerSearchInPdf = function(term) {
    if (window.activePdfViewer) {
        const searchBar = document.getElementById('pdf-finder-toolbar');
        if (searchBar) searchBar.classList.remove('hidden');
        const input = document.getElementById('pdf-search-input');
        if (input) {
            input.value = term;
            window.activePdfViewer.executeSearch(term);
            input.focus();
        }
    }
};
