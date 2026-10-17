(function () {
    "use strict";

    const loginForm = document.getElementById("loginForm");
    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");
    const togglePasswordButton = document.getElementById("togglePassword");
    const forgotPasswordButton = document.getElementById("forgotPassword");
    const loginMessage = document.getElementById("loginMessage");
    const sessionPanel = document.getElementById("sessionPanel");
    const logoutButton = document.getElementById("logoutButton");
    const loginHelp = document.getElementById("loginHelp");
    const portalTitle = document.getElementById("portalTitle");
    const portalSubtitle = document.getElementById("portalSubtitle");
    const profileName = document.getElementById("profileName");
    const profileRole = document.getElementById("profileRole");
    const submitButton = loginForm.querySelector('button[type="submit"]');
    const roleLabels = {
        student: "Alumno",
        professor: "Profesor",
        control_escolar: "Control Escolar"
    };

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

    function setBusy(value) {
        busy = value;
        loginForm.setAttribute("aria-busy", String(value));
        for (const control of loginForm.elements) {
            control.disabled = value;
        }
        logoutButton.disabled = value;
        submitButton.textContent = value ? "Espera un momento…" : "Iniciar sesión";
    }

    function hidePassword() {
        passwordInput.type = "password";
        togglePasswordButton.textContent = "Mostrar";
        togglePasswordButton.setAttribute("aria-label", "Mostrar contraseña");
    }

    function showLogin() {
        sessionPanel.hidden = true;
        profileName.textContent = "";
        profileRole.textContent = "";
        loginForm.hidden = false;
        loginHelp.hidden = false;
        logoutButton.hidden = !hasSession;
        portalTitle.textContent = "Iniciar sesión";
        portalSubtitle.textContent = "Ingresa tus credenciales para acceder.";
    }

    function showProfile(profile) {
        loginForm.reset();
        hidePassword();
        loginForm.hidden = true;
        loginHelp.hidden = true;
        profileName.textContent = profile.full_name;
        profileRole.textContent = roleLabels[profile.role];
        sessionPanel.hidden = false;
        logoutButton.hidden = false;
        portalTitle.textContent = "Sesión iniciada";
        portalSubtitle.textContent = "Tu acceso al portal ha sido verificado.";
        showMessage("");
    }

    async function endSession(message, type = "info") {
        accessVersion += 1;
        setBusy(true);
        passwordInput.value = "";
        hidePassword();
        showLogin();
        try {
            const { error } = await client.auth.signOut({ scope: "local" });
            if (error) throw error;
            hasSession = false;
            showLogin();
            showMessage(message, type);
        } catch {
            // Mantener disponible el botón para reintentar el cierre.
            showLogin();
            showMessage("No se pudo cerrar la sesión. Comprueba tu conexión y vuelve a intentarlo.", "error");
        } finally {
            setBusy(false);
        }
    }

    async function verifyAccess() {
        const version = ++accessVersion;
        setBusy(true);
        showLogin();
        showMessage("Verificando tu acceso…");

        try {
            const { data: sessionData, error: sessionError } = await client.auth.getSession();
            if (version !== accessVersion) return;
            if (sessionError) throw sessionError;
            hasSession = Boolean(sessionData.session);
            if (!hasSession) {
                showLogin();
                showMessage("");
                return;
            }

            // getUser verifica la identidad con Auth; no confiar en localStorage.
            const { data: userData, error: userError } = await client.auth.getUser();
            if (version !== accessVersion) return;
            if (userError || !userData.user) {
                await endSession("Tu sesión no pudo verificarse. Inicia sesión nuevamente.", "error");
                return;
            }

            // Los permisos reales se aplican en PostgreSQL mediante RLS.
            const { data: profile, error: profileError } = await client
                .from("profiles")
                .select("full_name, role, active")
                .eq("id", userData.user.id)
                .maybeSingle();

            if (version !== accessVersion) return;
            if (profileError) throw profileError;
            if (
                !profile || profile.active !== true ||
                typeof profile.full_name !== "string" || !profile.full_name.trim() ||
                !Object.hasOwn(roleLabels, profile.role)
            ) {
                await endSession("Tu cuenta no tiene un perfil activo autorizado. Contacta a Control Escolar.", "error");
                return;
            }
            showProfile(profile);
        } catch {
            if (version !== accessVersion) return;
            showLogin();
            showMessage("No fue posible verificar tu acceso. Comprueba tu conexión e inténtalo nuevamente.", "error");
        } finally {
            setBusy(false);
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

    forgotPasswordButton.addEventListener("click", function () {
        showMessage("Para recuperar tu acceso, contacta a Control Escolar.");
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
                const message = error.status === 429
                    ? "Demasiados intentos. Espera un momento antes de volver a intentar."
                    : "No se pudo iniciar sesión. Revisa tus datos o contacta a Control Escolar.";
                showMessage(message, "error");
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
            setBusy(false);
        }
    });

    logoutButton.addEventListener("click", function () {
        if (!busy) void endSession("Has cerrado sesión.");
    });

    setBusy(true);
    try {
        const config = window.PORTAL_SUPABASE_CONFIG;
        const url = new URL(config.url);
        if (
            url.protocol !== "https:" || url.username || url.password ||
            url.search || url.hash || url.pathname !== "/" ||
            !/^sb_publishable_[A-Za-z0-9_-]+$/.test(config.publishableKey) ||
            typeof window.supabase?.createClient !== "function"
        ) throw new Error("Configuración pública inválida");

        client = window.supabase.createClient(url.origin, config.publishableKey, {
            auth: {
                persistSession: true,
                autoRefreshToken: true,
                detectSessionInUrl: false,
                storageKey: "seminario-mr-auth"
            }
        });

        client.auth.onAuthStateChange(function (event) {
            if (event === "SIGNED_OUT") {
                accessVersion += 1;
                hasSession = false;
                showLogin();
                showMessage("");
            }
        });

        // Volver a comprobar el perfil al regresar a la pestaña.
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
