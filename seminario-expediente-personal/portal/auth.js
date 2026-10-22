(function () {
    "use strict";

    const roleLabels = Object.freeze({
        student: "Alumno",
        professor: "Profesor",
        control_escolar: "Control Escolar"
    });
    let client;

    function getClient() {
        if (client) return client;
        const config = window.PORTAL_SUPABASE_CONFIG;
        const url = new URL(config.url);
        if (
            url.protocol !== "https:" || url.username || url.password ||
            url.search || url.hash || url.pathname !== "/" ||
            !/^sb_publishable_[A-Za-z0-9_-]+$/.test(config.publishableKey) ||
            typeof window.supabase?.createClient !== "function"
        ) throw new Error("Configuración pública de Supabase inválida");

        client = window.supabase.createClient(url.origin, config.publishableKey, {
            auth: {
                persistSession: true,
                autoRefreshToken: true,
                detectSessionInUrl: false,
                storageKey: "seminario-mr-auth"
            }
        });
        return client;
    }

    async function checkAccess() {
        let hasSession = false;
        try {
            const authClient = getClient();
            const { data: sessionData, error: sessionError } = await authClient.auth.getSession();
            if (sessionError) throw sessionError;
            hasSession = Boolean(sessionData.session);
            if (!hasSession) return { status: "signed_out", hasSession };

            // Auth verifica la identidad; el contenido de localStorage no la prueba.
            const { data: userData, error: userError } = await authClient.auth.getUser();
            if (userError) {
                if ([401, 403].includes(userError.status) || userError.name === "AuthSessionMissingError") {
                    return { status: "invalid_session", hasSession };
                }
                throw userError;
            }
            if (!userData.user) return { status: "invalid_session", hasSession };

            // PostgreSQL/RLS autoriza la consulta y determina el rol real.
            const { data: profile, error: profileError } = await authClient
                .from("profiles")
                .select("full_name, role, active")
                .eq("id", userData.user.id)
                .maybeSingle();
            if (profileError) throw profileError;
            if (
                !profile || profile.active !== true ||
                typeof profile.full_name !== "string" || !profile.full_name.trim() ||
                !Object.hasOwn(roleLabels, profile.role)
            ) return { status: "denied", hasSession };

            return { status: "authorized", hasSession, profile: { ...profile, id: userData.user.id } };
        } catch {
            return { status: "unavailable", hasSession };
        }
    }

    window.PortalAuth = Object.freeze({ getClient, checkAccess, roleLabels });
})();
