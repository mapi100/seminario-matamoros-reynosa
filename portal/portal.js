(function () {
    "use strict";

    // En file:// cada HTML puede tener su propio almacenamiento de sesión.
    // El acceso local y el panel comparten un solo documento, sin pasar tokens por URL.
    if (window.location.protocol === "file:") {
        const target = new URL("panel.html", window.location.href);
        target.hash = window.location.hash;
        window.location.replace(target.href);
        return;
    }

    const loginForm = document.getElementById("loginForm");
    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");
    const togglePasswordButton = document.getElementById("togglePassword");
    const loginMessage = document.getElementById("loginMessage");
    const logoutButton = document.getElementById("logoutButton");
    const submitButton = loginForm.querySelector('button[type="submit"]');
    const notices = {
        sesion_cerrada: ["Has cerrado sesión.", "info"],
        sesion_invalida: ["Tu sesión no pudo verificarse. Inicia sesión nuevamente.", "error"],
        sin_acceso: ["Tu cuenta no tiene un perfil activo autorizado. Contacta a Control Escolar.", "error"]
    };
    const requestedNotice = new URLSearchParams(window.location.search).get("estado");

    let client;
    let busy = false;
    let hasSession = false;
    let accessVersion = 0;

    document.getElementById("currentYear").textContent = new Date().getFullYear();

    function showMessage(message, type = "info") {
        loginMessage.textContent = message;
        loginMessage.className = message
            ? "login-message visible " + type
            : "login-message";
    }

    function showInitialNotice() {
        if (Object.hasOwn(notices, requestedNotice)) {
            showMessage(...notices[requestedNotice]);
        } else {
            showMessage("");
        }
    }

    function setBusy(value) {
        busy = value;
        loginForm.setAttribute("aria-busy", String(value));
        for (const control of loginForm.elements) control.disabled = value;
        logoutButton.disabled = value;
        submitButton.textContent = value ? "Espera un momento…" : "Iniciar sesión";
    }

    function hidePassword() {
        passwordInput.type = "password";
        togglePasswordButton.textContent = "Mostrar";
        togglePasswordButton.setAttribute("aria-label", "Mostrar contraseña");
    }

    async function endSession(message, type = "info") {
        const version = ++accessVersion;
        setBusy(true);
        passwordInput.value = "";
        hidePassword();
        try {
            const { error } = await client.auth.signOut({ scope: "local" });
            if (error) throw error;
            hasSession = false;
            logoutButton.hidden = true;
            showMessage(message, type);
        } catch {
            showMessage("No se pudo cerrar la sesión. Comprueba tu conexión y vuelve a intentarlo.", "error");
        } finally {
            if (version === accessVersion) setBusy(false);
        }
    }

    async function verifyAccess() {
        const version = ++accessVersion;
        setBusy(true);
        showMessage("Verificando tu acceso…");
        try {
            const result = await window.PortalAuth.checkAccess();
            if (version !== accessVersion) return;
            hasSession = result.hasSession;
            logoutButton.hidden = !hasSession;

            if (result.status === "authorized") {
                loginForm.reset();
                hidePassword();
                window.location.replace(new URL("panel.html", window.location.href).href);
            } else if (result.status === "signed_out") {
                showInitialNotice();
            } else if (result.status === "invalid_session") {
                await endSession(notices.sesion_invalida[0], "error");
            } else if (result.status === "denied") {
                await endSession(notices.sin_acceso[0], "error");
            } else {
                showMessage("No fue posible verificar tu acceso. Comprueba tu conexión e inténtalo nuevamente.", "error");
            }
        } finally {
            if (version === accessVersion) setBusy(false);
        }
    }

    togglePasswordButton.addEventListener("click", function () {
        if (passwordInput.type === "password") {
            passwordInput.type = "text";
            togglePasswordButton.textContent = "Ocultar";
            togglePasswordButton.setAttribute("aria-label", "Ocultar contraseña");
        } else {
            hidePassword();
        }
    });

    document.getElementById("forgotPassword").addEventListener("click", async function () {
        if (busy || !client) return;
        if (!emailInput.value.trim() || !emailInput.reportValidity()) {
            showMessage("Escribe primero el correo de tu cuenta para recuperar el acceso.");
            emailInput.focus();
            return;
        }
        setBusy(true);
        try {
            const { error } = await client.auth.resetPasswordForEmail(emailInput.value.trim(), {
                redirectTo: new URL("activar.html", window.location.href).href
            });
            if (error) throw error;
            showMessage("Si tu cuenta está registrada, recibirás un enlace para crear una contraseña nueva. Revisa también el correo no deseado.");
        } catch {
            showMessage("No fue posible solicitar el enlace. Inténtalo más tarde o contacta a Control Escolar.", "error");
        } finally { setBusy(false); }
    });

    loginForm.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (busy || !client || !loginForm.reportValidity()) return;
        const email = emailInput.value.trim();
        if (!email || !passwordInput.value) {
            showMessage("Completa tu correo electrónico y contraseña.", "error");
            return;
        }

        const version = ++accessVersion;
        setBusy(true);
        showMessage("");
        try {
            const { error } = await client.auth.signInWithPassword({
                email,
                password: passwordInput.value
            });
            passwordInput.value = "";
            hidePassword();
            if (version !== accessVersion) return;
            if (error) {
                showMessage(error.status === 429
                    ? "Demasiados intentos. Espera un momento antes de volver a intentar."
                    : "No se pudo iniciar sesión. Revisa tus datos o contacta a Control Escolar.", "error");
                return;
            }
            await verifyAccess();
        } catch {
            passwordInput.value = "";
            hidePassword();
            if (version === accessVersion) {
                showMessage("No fue posible conectar. Comprueba tu conexión e inténtalo nuevamente.", "error");
            }
        } finally {
            if (version === accessVersion) setBusy(false);
        }
    });

    logoutButton.addEventListener("click", function () {
        if (!busy) void endSession("Has cerrado sesión.");
    });

    window.addEventListener("pagehide", function () {
        accessVersion += 1;
        loginForm.reset();
        hidePassword();
    });
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) void verifyAccess();
    });

    setBusy(true);
    try {
        client = window.PortalAuth.getClient();
        client.auth.onAuthStateChange(function (event) {
            if (event === "SIGNED_OUT") {
                accessVersion += 1;
                hasSession = false;
                logoutButton.hidden = true;
                passwordInput.value = "";
                hidePassword();
                setBusy(false);
                showInitialNotice();
            }
        });
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "visible" && hasSession && !busy) {
                void verifyAccess();
            }
        });
        void verifyAccess();
    } catch {
        showMessage("El acceso no está disponible en este momento. Inténtalo más tarde.", "error");
        console.error("Portal: revisa la configuración pública de Supabase y la carga del SDK.");
    }
})();
