(function () {
    "use strict";

    const content = document.getElementById("panelContent");
    const message = document.getElementById("panelMessage");
    const recovery = document.getElementById("panelRecovery");
    const logoutButton = document.getElementById("logoutButton");
    const retryButton = document.getElementById("retryButton");
    const title = document.getElementById("panelTitle");
    const subtitle = document.getElementById("panelSubtitle");
    const name = document.getElementById("profileName");
    const role = document.getElementById("profileRole");
    const state = document.getElementById("profileState");
    const headings = {
        student: "Panel de alumno",
        professor: "Panel de profesor",
        control_escolar: "Panel de Control Escolar"
    };

    let client;
    let busy = true;
    let version = 0;
    let logoutReason = "sesion_invalida";

    document.getElementById("currentYear").textContent = new Date().getFullYear();

    function showMessage(text, type = "info") {
        message.textContent = text;
        message.className = text ? "login-message visible " + type : "login-message";
    }

    function setBusy(value) {
        busy = value;
        document.getElementById("panelMain").setAttribute("aria-busy", String(value));
        logoutButton.disabled = value;
        retryButton.disabled = value;
    }

    function clearProfile() {
        content.hidden = true;
        window.PortalSubjects?.clear();
        window.PortalTeaching?.clear();
        window.PortalControl?.clear();
        window.PortalManagement?.clear();
        window.PortalLearning?.clear();
        window.PortalLearningFiles?.clear();
        window.PortalWorkspace?.clear();
        name.textContent = "";
        role.textContent = "";
        state.textContent = "";
        title.textContent = "Mi portal";
        subtitle.textContent = "Verificando tu acceso…";
        document.title = "Mi portal | Seminario Diocesano San José";
    }

    function goToLogin(reason) {
        const target = new URL("index.html", window.location.href);
        if (reason) target.searchParams.set("estado", reason);
        window.location.replace(target.href);
    }

    function showUnavailable(text) {
        clearProfile();
        subtitle.textContent = "Tu acceso todavía no pudo verificarse.";
        recovery.hidden = false;
        showMessage(text, "error");
    }

    async function endSession(reason) {
        const operation = ++version;
        logoutReason = reason;
        clearProfile();
        recovery.hidden = true;
        setBusy(true);
        showMessage("Cerrando sesión…");
        try {
            const { error } = await client.auth.signOut({ scope: "local" });
            if (error) throw error;
            goToLogin(reason);
        } catch {
            if (operation !== version) return;
            logoutReason = "sesion_invalida";
            showUnavailable("No se pudo cerrar la sesión. Comprueba tu conexión y vuelve a intentarlo.");
        } finally {
            if (operation === version) setBusy(false);
        }
    }

    async function verifyAccess() {
        const operation = ++version;
        clearProfile();
        if (document.visibilityState === "hidden") {
            setBusy(false);
            return;
        }
        recovery.hidden = true;
        setBusy(true);
        showMessage("Verificando tu acceso…");

        try {
            const result = await window.PortalAuth.checkAccess();
            if (operation !== version) return;
            logoutButton.hidden = !result.hasSession;
            if (result.status === "signed_out") {
                goToLogin();
            } else if (result.status === "invalid_session") {
                await endSession("sesion_invalida");
            } else if (result.status === "denied") {
                await endSession("sin_acceso");
            } else if (result.status === "authorized") {
                // El rol viene de profiles, nunca de la URL ni de user_metadata.
                title.textContent = headings[result.profile.role];
                subtitle.textContent = "Consulta tu perfil y administra tu sesión.";
                name.textContent = result.profile.full_name;
                role.textContent = window.PortalAuth.roleLabels[result.profile.role];
                state.textContent = "Activo";
                document.title = headings[result.profile.role] + " | Seminario Diocesano San José";
                content.hidden = false;
                showMessage("");
                if (result.profile.role === "student") {
                    subtitle.textContent = "Consulta tu perfil y tus materias.";
                    if (window.PortalSubjects) {
                        window.PortalSubjects.show(verifyAccess);
                    } else {
                        document.getElementById("subjectsSection").hidden = false;
                        document.getElementById("subjectsStatus").textContent =
                            "No fue posible cargar tus materias. Recarga la página para reintentar.";
                    }
                } else if (result.profile.role === "professor") {
                    subtitle.textContent = "Consulta tus materias asignadas y sus alumnos.";
                    if (window.PortalTeaching) {
                        window.PortalTeaching.show(verifyAccess);
                    } else {
                        document.getElementById("teachingSection").hidden = false;
                        document.getElementById("teachingStatus").textContent =
                            "No fue posible cargar tus materias asignadas. Recarga la página para reintentar.";
                    }
                } else if (result.profile.role === "control_escolar") {
                    subtitle.textContent = "Organiza las personas, clases e inscripciones del Seminario.";
                    if (window.PortalControl) {
                        window.PortalControl.show(verifyAccess);
                        window.PortalManagement?.show(verifyAccess);
                    } else {
                        document.getElementById("controlSection").hidden = false;
                        document.getElementById("periodListStatus").textContent =
                            "No fue posible cargar los catálogos. Recarga la página para reintentar.";
                    }
                }
                window.PortalLearning?.show(result.profile, verifyAccess);
                window.PortalWorkspace?.show(result.profile);
            } else {
                showUnavailable("No fue posible verificar tu acceso. Comprueba tu conexión e inténtalo nuevamente.");
            }
        } catch {
            if (operation === version) {
                showUnavailable("El acceso no está disponible en este momento. Inténtalo más tarde.");
            }
        } finally {
            if (operation === version) setBusy(false);
        }
    }

    logoutButton.addEventListener("click", function () {
        if (!busy) void endSession("sesion_cerrada");
    });
    retryButton.addEventListener("click", function () {
        if (!busy) window.location.reload();
    });

    // Limpiar datos antes de guardar una página en la caché del navegador.
    window.addEventListener("pagehide", function () {
        version += 1;
        clearProfile();
    });
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) void verifyAccess();
    });
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            version += 1;
            clearProfile();
        } else {
            void verifyAccess();
        }
    });

    try {
        client = window.PortalAuth.getClient();
        client.auth.onAuthStateChange(function (event) {
            if (event === "SIGNED_OUT") {
                version += 1;
                clearProfile();
                goToLogin(logoutReason);
            } else if (
                ["SIGNED_IN", "TOKEN_REFRESHED", "USER_UPDATED"].includes(event) &&
                !busy && document.visibilityState !== "hidden"
            ) {
                const operation = ++version;
                clearProfile();
                setBusy(true);
                window.setTimeout(function () {
                    if (operation === version) void verifyAccess();
                }, 0);
            }
        });
        void verifyAccess();
    } catch {
        showUnavailable("El acceso no está disponible en este momento. Inténtalo más tarde.");
        setBusy(false);
        console.error("Portal: revisa la configuración pública de Supabase y la carga del SDK.");
    }
})();
