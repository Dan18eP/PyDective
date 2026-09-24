// PyDective Application Logic

let activeParams = ["nombre", "total", "fecha", "nit"];
let selectedFile = null;
let chatHistory = [];
let jobStartTime = null;
let timerInterval = null;

let selectedVisionEngine = "rapidocr";

document.addEventListener("DOMContentLoaded", () => {
    initDropzone();
    initParamInputs();
    renderActiveParams();
    initEngineSelector();
});

// Dropzone Initialization
function initDropzone() {
    const dropzone = document.getElementById("dropzone-area");
    const fileInput = document.getElementById("pdf-file-input");
    const clearBtn = document.getElementById("btn-clear-file");

    if (!dropzone || !fileInput) return;

    ["dragenter", "dragover"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type === "application/pdf") {
            handleFileSelect(files[0]);
        } else {
            showToast("Por favor carga un archivo PDF válido.", "warning");
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });

    if (clearBtn) {
        clearBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            clearSelectedFile();
        });
    }
}

function handleFileSelect(file) {
    selectedFile = file;
    const promptEl = document.getElementById("dropzone-prompt");
    const previewEl = document.getElementById("file-preview");
    const nameEl = document.getElementById("preview-filename");
    const sizeEl = document.getElementById("preview-filesize");

    if (promptEl) promptEl.classList.add("hidden");
    if (previewEl) previewEl.classList.remove("hidden");
    if (nameEl) nameEl.textContent = file.name;
    if (sizeEl) sizeEl.textContent = formatBytes(file.size);
}

function clearSelectedFile() {
    selectedFile = null;
    const fileInput = document.getElementById("pdf-file-input");
    const promptEl = document.getElementById("dropzone-prompt");
    const previewEl = document.getElementById("file-preview");

    if (fileInput) fileInput.value = "";
    if (previewEl) previewEl.classList.add("hidden");
    if (promptEl) promptEl.classList.remove("hidden");
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

// Parameter Tag Inputs
function initParamInputs() {
    const input = document.getElementById("param-input");
    const addBtn = document.getElementById("btn-add-param");

    if (!input) return;

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            addParamFromInput();
        }
    });

    if (addBtn) {
        addBtn.addEventListener("click", () => {
            addParamFromInput();
        });
    }
}

function addParamFromInput() {
    const input = document.getElementById("param-input");
    if (!input) return;
    const val = input.value.trim().toLowerCase();
    if (val) {
        addParamTag(val);
        input.value = "";
    }
}

function addParamTag(param) {
    const cleaned = param.trim().toLowerCase();
    if (!cleaned) return;
    if (!activeParams.includes(cleaned)) {
        activeParams.push(cleaned);
        renderActiveParams();
    }
}

function removeParamTag(index) {
    activeParams.splice(index, 1);
    renderActiveParams();
}

function renderActiveParams() {
    const container = document.getElementById("active-params-container");
    if (!container) return;

    container.innerHTML = "";
    if (activeParams.length === 0) {
        container.innerHTML = `<span class="text-dim" style="font-size: 0.85rem; padding: 0.25rem 0.5rem;">Ningún parámetro ingresado. Agrega al menos uno.</span>`;
        return;
    }

    activeParams.forEach((param, idx) => {
        const tag = document.createElement("div");
        tag.className = "param-tag";
        tag.innerHTML = `
            <span>${param}</span>
            <span class="param-tag-remove" onclick="removeParamTag(${idx})">&times;</span>
        `;
        container.appendChild(tag);
    });
}

function initEngineSelector() {
    const cards = document.querySelectorAll(".engine-card");
    cards.forEach(card => {
        card.addEventListener("click", () => {
            cards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            const radio = card.querySelector(".engine-radio");
            if (radio) {
                radio.checked = true;
                selectedVisionEngine = radio.value;
            }
        });
    });
}

// Job Submission & SSE Streaming
async function submitJob() {
    if (!selectedFile) {
        showToast("Selecciona o arrastra un archivo PDF para continuar.", "warning");
        return;
    }

    if (activeParams.length === 0) {
        showToast("Debes ingresar al menos un parámetro de búsqueda.", "warning");
        return;
    }

    const submitBtn = document.getElementById("btn-submit-job");
    const spinner = document.getElementById("submit-spinner");
    const btnText = document.getElementById("submit-btn-text");
    const progressPanel = document.getElementById("live-progress-panel");

    if (submitBtn) submitBtn.disabled = true;
    if (spinner) spinner.classList.remove("hidden");
    if (btnText) btnText.textContent = "Analizando Documento...";
    if (progressPanel) progressPanel.classList.remove("hidden");

    startTimer();
    appendTerminal(`> Modo de visión: ${selectedVisionEngine.toUpperCase()}`);
    appendTerminal("> Enviando archivo y parámetros al orquestador...");

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("parametros", JSON.stringify(activeParams));
    formData.append("motor_vision", selectedVisionEngine);
    
    const catalogarCheck = document.getElementById("catalogar-imagenes-checkbox");
    if (catalogarCheck) {
        formData.append("catalogar_imagenes", catalogarCheck.checked);
    }

    try {
        const response = await fetch("/procesar/stream", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.message || `Error del servidor: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop(); // Keep partial line in buffer

            for (const chunk of lines) {
                if (!chunk.trim()) continue;
                const eventLines = chunk.split("\n");
                let eventData = "";

                for (const line of eventLines) {
                    if (line.startsWith("data: ")) {
                        eventData = line.substring(6);
                    }
                }

                if (eventData) {
                    try {
                        const parsed = JSON.parse(eventData);
                        handleStreamEvent(parsed);
                    } catch (e) {
                        console.error("Error parsing SSE event data:", e);
                    }
                }
            }
        }
    } catch (err) {
        stopTimer();
        showToast(err.message, "danger");
        appendTerminal(`[ERROR] ${err.message}`);
        if (submitBtn) submitBtn.disabled = false;
        if (spinner) spinner.classList.add("hidden");
        if (btnText) btnText.textContent = "Reintentar Análisis";
    }
}

function handleStreamEvent(event) {
    const statusText = document.getElementById("progress-status-text");
    const progressBar = document.getElementById("progress-bar-fill");
    const pagesLabel = document.getElementById("pages-processed-label");

    if (event.tipo === "inicio") {
        if (statusText) statusText.textContent = `Calculado SHA-256 (${event.pdf_hash.substring(0, 10)}...). Total: ${event.total_paginas} páginas. Motor: ${event.motor_vision || selectedVisionEngine}`;
        if (progressBar) progressBar.style.width = "15%";
        initPageGrid(event.total_paginas);
        appendTerminal(`> Hash SHA-256: ${event.pdf_hash}`);
        appendTerminal(`> Total páginas: ${event.total_paginas} | Motor: ${event.motor_vision || selectedVisionEngine}`);
    } else if (event.tipo === "progreso_motor") {
        if (event.estado === "analizando_vlm") {
            if (statusText) statusText.textContent = `Pág ${event.numero_pagina}: Ejecutando inferencia multimodal Microsoft Florence-2 VLM en CPU...`;
            appendTerminal(`> Pág ${event.numero_pagina}: Inferencia Florence-2 VLM en CPU iniciada...`);
        } else if (event.estado === "completado") {
            appendTerminal(`> Pág ${event.numero_pagina}: Florence-2 VLM completado en ${event.duracion_ms} ms`);
        }
    } else if (event.tipo === "pagina") {
        updatePageBlock(event.numero_pagina, event.carril);
        if (statusText) statusText.textContent = `Página ${event.numero_pagina} procesada (${event.duracion_ms.toFixed(1)} ms)`;
        if (pagesLabel) pagesLabel.textContent = `${event.paginas_completadas} / ${event.total_paginas}`;
        
        const pct = Math.min(85, Math.floor((event.paginas_completadas / event.total_paginas) * 80) + 15);
        if (progressBar) progressBar.style.width = `${pct}%`;
        appendTerminal(`> Pág ${event.numero_pagina}: ${event.carril} (${event.duracion_ms.toFixed(1)} ms)`);
    } else if (event.tipo === "completado") {
        stopTimer();
        if (progressBar) progressBar.style.width = "100%";
        if (statusText) statusText.textContent = "Procesamiento completado con éxito. Redirigiendo...";
        appendTerminal(`> Dictamen consolidado en ${event.duracion_total_ms.toFixed(1)} ms. Caché: ${event.nivel_cache}`);
        if (event.comparativa_motores && event.comparativa_motores.resumen) {
            appendTerminal(`> Benchmark A/B: ${event.comparativa_motores.resumen}`);
        }
        setTimeout(() => {
            window.location.href = `/resultados/${event.pdf_hash}`;
        }, 600);
    }
}

function initPageGrid(totalPages) {
    const grid = document.getElementById("pages-live-grid");
    if (!grid) return;
    grid.innerHTML = "";
    for (let i = 1; i <= totalPages; i++) {
        const block = document.createElement("div");
        block.id = `page-block-${i}`;
        block.className = "page-block";
        block.textContent = `Pág ${i}`;
        grid.appendChild(block);
    }
}

function updatePageBlock(pageNum, carril) {
    const block = document.getElementById(`page-block-${pageNum}`);
    if (block) {
        block.className = `page-block page-${carril}`;
    }
}

function appendTerminal(msg) {
    const terminal = document.getElementById("stream-terminal");
    if (!terminal) return;
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.textContent = msg;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

function startTimer() {
    jobStartTime = performance.now();
    const badge = document.getElementById("elapsed-badge");
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        const elapsed = (performance.now() - jobStartTime) / 1000;
        if (badge) badge.textContent = `${elapsed.toFixed(2)}s`;
    }, 50);
}

function stopTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

// Pydective Chat Integration
function askQuickPrompt(text) {
    const input = document.getElementById("chat-input-field");
    if (input) {
        input.value = text;
        sendChatMessage();
    }
}

async function sendChatMessage() {
    const input = document.getElementById("chat-input-field");
    const container = document.getElementById("chat-messages-container");
    const hashEl = document.getElementById("doc-pdf-hash");

    if (!input || !container || !hashEl) return;
    const pregunta = input.value.trim();
    if (!pregunta) return;

    const pdfHash = hashEl.textContent.trim();

    // Append User Bubble
    const userBubble = document.createElement("div");
    userBubble.className = "chat-bubble bubble-user";
    userBubble.textContent = pregunta;
    container.appendChild(userBubble);
    input.value = "";
    container.scrollTop = container.scrollHeight;

    // Append Assistant Loading Bubble
    const assistantBubble = document.createElement("div");
    assistantBubble.className = "chat-bubble bubble-assistant";
    assistantBubble.innerHTML = `<span class="text-muted">Consultando evidencias L1...</span>`;
    container.appendChild(assistantBubble);
    container.scrollTop = container.scrollHeight;

    try {
        let fullRespuesta = "";
        let finalCitas = [];
        let finalEvidencias = [];

        // Intento 1: Streaming Server-Sent Events (SSE) en tiempo real (Opción 3)
        let streamingSuccess = false;
        try {
            const streamRes = await fetch(`/chat/${pdfHash}/stream`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    pregunta: pregunta,
                    historial: chatHistory
                })
            });

            if (streamRes.ok && streamRes.body) {
                const reader = streamRes.body.getReader();
                const decoder = new TextDecoder();
                let streamBuffer = "";
                assistantBubble.innerHTML = `<div class="chat-markdown-body"></div>`;
                const textContainer = assistantBubble.querySelector(".chat-markdown-body");

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    streamBuffer += decoder.decode(value, { stream: true });
                    const lines = streamBuffer.split("\n");
                    streamBuffer = lines.pop() || "";

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith("data: ")) {
                            try {
                                const payload = JSON.parse(trimmed.substring(6));
                                if (payload.token) {
                                    fullRespuesta += payload.token;
                                    textContainer.textContent = fullRespuesta;
                                    container.scrollTop = container.scrollHeight;
                                }
                                if (payload.citas && payload.citas.length > 0) {
                                    finalCitas = payload.citas;
                                }
                                if (payload.final) {
                                    streamingSuccess = true;
                                }
                            } catch (e) {
                                // Ignore non-JSON ping lines
                            }
                        }
                    }
                }
                if (fullRespuesta.trim()) {
                    streamingSuccess = true;
                }
            }
        } catch (streamErr) {
            console.warn("SSE stream failed, falling back to standard chat endpoint:", streamErr);
            streamingSuccess = false;
        }

        // Intento 2: Fallback estándar si SSE no produjo respuesta
        if (!streamingSuccess || !fullRespuesta.trim()) {
            const response = await fetch(`/chat/${pdfHash}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    pregunta: pregunta,
                    historial: chatHistory
                })
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.message || "Error al consultar Pydective Chat");
            }

            const data = await response.json();
            fullRespuesta = data.respuesta;
            finalCitas = data.citas || [];
            finalEvidencias = data.evidencias_relacionadas || [];
        }

        chatHistory.push({ role: "user", content: pregunta });
        chatHistory.push({ role: "assistant", content: fullRespuesta });

        let citasHtml = "";
        if (finalEvidencias && finalEvidencias.length > 0) {
            citasHtml = `<div class="citations-list" style="margin-top: 0.65rem;">` +
                finalEvidencias.map(ev => {
                    const bboxStr = JSON.stringify(ev.bbox || []);
                    const label = (ev.text || "Evidencia").substring(0, 25).replace(/'/g, "\\'");
                    return `<button type="button" class="citation-pill citation-pill-interactive" onclick="window.highlightSourceInPdf(${ev.page}, ${bboxStr}, '${label}')" title="Localizar en visor: Pág ${ev.page}">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <span>Pág ${ev.page}</span>
                    </button>`;
                }).join("") +
                `</div>`;
        } else if (finalCitas && finalCitas.length > 0) {
            citasHtml = `<div class="citations-list" style="margin-top: 0.65rem;">` +
                finalCitas.map(c => {
                    const match = c.match(/\d+/);
                    const pageNum = match ? parseInt(match[0], 10) : 1;
                    return `<button type="button" class="citation-pill citation-pill-interactive" onclick="if(window.activePdfViewer) window.activePdfViewer.goToPage(${pageNum})" title="Ir a Pág ${pageNum}">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <span>${c}</span>
                    </button>`;
                }).join("") +
                `</div>`;
        }

        // Formatear saltos de línea para legibilidad
        const formattedRespuesta = fullRespuesta
            .replace(/\n\n/g, "</p><p>")
            .replace(/\n/g, "<br>");

        assistantBubble.innerHTML = `<div class="chat-markdown-body"><p>${formattedRespuesta}</p></div>${citasHtml}`;
        container.scrollTop = container.scrollHeight;
    } catch (err) {
        assistantBubble.innerHTML = `<p style="color: var(--danger);">[Error] ${err.message}</p>`;
    }
}

// Toast Notifications
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        background: rgba(18, 26, 47, 0.95);
        color: #fff;
        padding: 0.85rem 1.25rem;
        border-radius: 8px;
        margin-top: 0.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        font-size: 0.9rem;
        animation: fadeIn 0.3s ease;
    `;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Cross-Platform Clipboard Copy (Compatible con Linux Wayland/X11 y Windows)
function copyToClipboard(text, btn) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            copyFeedback(btn);
        }).catch(() => {
            fallbackCopyText(text, btn);
        });
    } else {
        fallbackCopyText(text, btn);
    }
}

function fallbackCopyText(text, btn) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand("copy");
        copyFeedback(btn);
    } catch (err) {
        showToast("No se pudo copiar automáticamente al portapapeles", "warning");
    }
    document.body.removeChild(textArea);
}

function copyFeedback(btn) {
    if (!btn) return;
    const originalText = btn.innerHTML;
    btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> Copiado`;
    btn.classList.add("copied");
    setTimeout(() => {
        btn.innerHTML = originalText;
        btn.classList.remove("copied");
    }, 1500);
}

