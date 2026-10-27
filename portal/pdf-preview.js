(function () {
    "use strict";
    // Los módulos file:// y sus workers están restringidos por los navegadores.
    // En archivos locales se carga únicamente código/recursos estáticos por HTTPS;
    // los bytes del documento permanecen en el navegador.
    const localFiles = window.location.protocol === "file:";
    const assets = localFiles ? new URL("https://cdn.jsdelivr.net/npm/pdfjs-dist@5.4.624/") : new URL("vendor/pdfjs/", document.currentScript.src);
    const build = localFiles ? "build/" : "";
    let libraryPromise;
    function library() {
        if (!libraryPromise) libraryPromise = import(new URL(build + "pdf.min.mjs", assets).href).then(pdf => {
            pdf.GlobalWorkerOptions.workerSrc = new URL(build + "pdf.worker.min.mjs", assets).href;
            return pdf;
        }).catch(error => { libraryPromise = undefined; throw error; });
        return libraryPromise;
    }
    function node(tag, text, className) {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (className) element.className = className;
        return element;
    }
    function render(host, blob) {
        let alive = true, documentTask, pdf, renderTask, version = 0, pageNumber = 1, zoom = 1, busy = true, scheduled;
        const controls = node("div", undefined, "content-pdf-controls"), pageLabel = node("span", "Cargando PDF…", "content-pdf-page-label");
        pageLabel.setAttribute("aria-live", "polite");
        function button(label, text, action) {
            const control = node("button", text, "content-pdf-control"); control.type = "button"; control.setAttribute("aria-label", label); control.title = label;
            control.addEventListener("click", action); return control;
        }
        const previous = button("Página anterior del PDF", "‹", () => { pageNumber--; void draw().catch(failed); });
        const next = button("Página siguiente del PDF", "›", () => { pageNumber++; void draw().catch(failed); });
        const smaller = button("Reducir PDF", "−", () => { zoom = Math.max(.5, zoom - .25); void draw().catch(failed); });
        const larger = button("Acercar PDF", "+", () => { zoom = Math.min(2.5, zoom + .25); void draw().catch(failed); });
        const fit = button("Ajustar PDF al ancho", "Ajustar al ancho", () => { zoom = 1; void draw().catch(failed); });
        controls.append(previous, pageLabel, next, smaller, larger, fit);
        const viewport = node("div", undefined, "content-pdf-viewport"), canvas = node("canvas", undefined, "content-pdf-page");
        canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", "Página del documento PDF");
        const text = node("p", "", "content-pdf-accessible-text"), status = node("p", "Preparando el documento…", "learning-status content-pdf-status");
        status.setAttribute("role", "status"); viewport.append(canvas); host.replaceChildren(controls, status, viewport, text);
        function update() {
            previous.disabled = busy || !pdf || pageNumber <= 1; next.disabled = busy || !pdf || pageNumber >= pdf.numPages;
            smaller.disabled = busy || zoom <= .5; larger.disabled = busy || zoom >= 2.5; fit.disabled = busy;
            if (pdf) pageLabel.textContent = "Página " + pageNumber + " de " + pdf.numPages;
        }
        function failed() { if (alive) { busy = false; status.textContent = "No se pudo dibujar esta página. Intenta cambiar de página o abre el PDF en otra pestaña."; update(); } }
        async function draw() {
            if (!alive || !pdf) return;
            const current = ++version, previousTask = renderTask;
            previousTask?.cancel();
            if (previousTask) await previousTask.promise.catch(() => {});
            if (!alive || current !== version) return;
            busy = true; update(); status.textContent = "Cargando página…";
            const page = await pdf.getPage(pageNumber);
            if (!alive || current !== version) return;
            const original = page.getViewport({scale:1}), width = Math.max(160, viewport.clientWidth - 32);
            const scale = Math.min(width / original.width, 6000 / original.height) * zoom;
            const size = page.getViewport({scale});
            if (![size.width, size.height].every(value => Number.isFinite(value) && value > 0)) throw new Error("Tamaño de página inválido");
            // Acotar el lienzo evita reservar memoria desproporcionada por página.
            const ratio = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(6000000 / (size.width * size.height)));
            canvas.width = Math.max(1, Math.floor(size.width * ratio)); canvas.height = Math.max(1, Math.floor(size.height * ratio));
            canvas.style.width = size.width + "px"; canvas.style.height = size.height + "px";
            canvas.setAttribute("aria-label", "Página " + pageNumber + " de " + pdf.numPages + " del PDF");
            renderTask = page.render({canvasContext:canvas.getContext("2d"),viewport:size,transform:[ratio,0,0,ratio,0,0]});
            try { await renderTask.promise; } catch (error) { if (alive && current === version) throw error; }
            if (!alive || current !== version) return;
            busy = false; status.textContent = ""; update();
            const content = await page.getTextContent();
            if (alive && current === version) text.textContent = content.items.map(item => item.str || "").join(" ").slice(0, 100000);
        }
        const observer = new ResizeObserver(() => {
            cancelAnimationFrame(scheduled);
            scheduled = requestAnimationFrame(() => { if (pdf && alive) void draw().catch(failed); });
        }); observer.observe(viewport); update();
        const ready = (async () => {
            const lib = await library();
            if (!alive) return;
            const bytes = new Uint8Array(await blob.arrayBuffer());
            if (!alive) return;
            documentTask = lib.getDocument({data:bytes,isEvalSupported:false,useSystemFonts:true,
                cMapUrl:new URL("cmaps/", assets).href,cMapPacked:true,
                standardFontDataUrl:new URL("standard_fonts/", assets).href,wasmUrl:new URL("wasm/", assets).href});
            pdf = await documentTask.promise;
            if (alive) await draw();
        })();
        function destroy() {
            alive = false; version++; observer.disconnect(); cancelAnimationFrame(scheduled); renderTask?.cancel();
            if (documentTask) void documentTask.destroy().catch(() => {});
            canvas.width = 0; canvas.height = 0; host.replaceChildren();
        }
        return Object.freeze({ready,destroy});
    }
    window.PortalPDFPreview = Object.freeze({render});
})();
