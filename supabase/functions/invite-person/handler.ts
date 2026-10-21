// No dependencies. Auth validates the caller; service credentials stay inside the Edge Function.
type Environment = { get(name: string): string | undefined };

export function createHandler(env: Environment, send: typeof fetch = fetch) {
    const origin = env.get("PORTAL_ORIGIN") || "https://seminariomr.org";
    const redirect = origin + "/portal/activar.html";
    const base = env.get("SUPABASE_URL");
    const key = env.get("SUPABASE_SERVICE_ROLE_KEY");
    const enabled = env.get("PORTAL_INVITES_ENABLED") === "true";
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    return async function handler(request: Request) {
        const headers = { "Content-Type": "application/json", "Cache-Control": "no-store", "Vary": "Origin" };
        if (request.headers.get("Origin") !== origin) return new Response(JSON.stringify({ error: "Origen no permitido" }), { status: 403, headers });
        Object.assign(headers, { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" });
        const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers });
        if (request.method === "OPTIONS") return reply(200, {});
        if (request.method !== "POST") return reply(405, { error: "Método no permitido" });
        const authorization = request.headers.get("Authorization") || "";
        if (!/^Bearer [A-Za-z0-9_.-]+$/.test(authorization) || authorization.length > 8192) return reply(401, { error: "Inicia sesión nuevamente" });
        if (!base || !key) return reply(503, { error: "Invitaciones no disponibles" });
        async function call(path: string, body: unknown, token = "Bearer " + key, method = "POST") {
            const response = await send(base + path, { method, headers: { "apikey": key, "Authorization": token, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(12000) });
            let data; try { data = await response.json(); } catch { data = null; }
            return { ok: response.ok, status: response.status, data };
        }
        let actor, requestId, createdId, claimed = false;
        try {
            const user = await call("/auth/v1/user", undefined, authorization, "GET");
            if (!user.ok || !uuid.test(user.data?.id)) return reply(401, { error: "Sesión inválida" });
            actor = user.data.id;
            const profile = await call("/rest/v1/profiles?id=eq." + actor + "&select=role,active", undefined, undefined, "GET");
            if (!profile.ok || profile.data?.length !== 1 || profile.data[0].role !== "control_escolar" || profile.data[0].active !== true) return reply(403, { error: "Acceso denegado" });
            if (!enabled) return reply(503, { error: "El envío de invitaciones aún no está habilitado" });
            if (!request.headers.get("Content-Type")?.startsWith("application/json")) return reply(415, { error: "Datos inválidos" });
            const reader = request.body?.getReader(); if (!reader) return reply(400, { error: "Datos inválidos" });
            let size = 0; const chunks = [];
            while (true) { const next = await reader.read(); if (next.done) break; size += next.value.byteLength; if (size > 4096) { await reader.cancel(); return reply(413, { error: "Datos demasiado extensos" }); } chunks.push(next.value); }
            const bytes = new Uint8Array(size); let position = 0; for (const chunk of chunks) { bytes.set(chunk, position); position += chunk.length; }
            let body; try { body = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); } catch { return reply(400, { error: "Datos inválidos" }); }
            if (!body || Object.keys(body).sort().join() !== "email,full_name,request_id,role" || !uuid.test(body.request_id) || typeof body.email !== "string" || typeof body.full_name !== "string" || !["student", "professor", "control_escolar"].includes(body.role)) return reply(400, { error: "Datos inválidos" });
            requestId = body.request_id;
            const prepared = await call("/rest/v1/rpc/portal_prepare_invite", { p_actor: actor, p_request_id: requestId, p_email: body.email, p_name: body.full_name, p_role: body.role });
            if (!prepared.ok) return reply(prepared.data?.code === "42501" ? 403 : prepared.data?.code === "PT429" ? 429 : 409, { error: "No se pudo iniciar la invitación. Revisa el correo y la lista de personas." });
            if (prepared.data?.state === "sent") return reply(200, { sent: true });
            if (prepared.data?.state !== "claimed") return reply(409, { error: "La invitación está en revisión; comprueba la lista antes de repetirla" });
            claimed = true;
            const invited = await call("/auth/v1/invite?redirect_to=" + encodeURIComponent(redirect), { email: body.email.trim().toLowerCase() });
            if (!invited.ok || !uuid.test(invited.data?.id)) {
                await call("/rest/v1/rpc/portal_fail_invite", { p_actor: actor, p_request_id: requestId, p_state: "uncertain" }); claimed = false;
                return reply(502, { error: "No se pudo confirmar la invitación. Comprueba el envío de correo antes de repetirla." });
            }
            createdId = invited.data.id;
            const finished = await call("/rest/v1/rpc/portal_finish_invite", { p_actor: actor, p_request_id: requestId, p_user_id: createdId });
            if (!finished.ok || finished.data?.sent !== true) {
                if (!["42501", "22023", "23505", "PT409"].includes(finished.data?.code)) throw new Error("Finalización no confirmada");
                // A failed profile transaction is definitive. A timeout goes to the catch
                // path, because the profile may have committed and must not be deleted.
                const removed = await call("/auth/v1/admin/users/" + createdId, undefined, undefined, "DELETE");
                await call("/rest/v1/rpc/portal_fail_invite", { p_actor: actor, p_request_id: requestId, p_state: removed.ok ? "failed" : "uncertain" }); claimed = false;
                return reply(409, { error: "No se pudo habilitar la cuenta. Contacta al responsable del portal." });
            }
            claimed = false;
            return reply(200, { sent: true });
        } catch {
            if (claimed && actor && requestId) {
                try { await call("/rest/v1/rpc/portal_fail_invite", { p_actor: actor, p_request_id: requestId, p_state: "uncertain" }); } catch { /* The persisted claim prevents blind retries. */ }
            }
            return reply(503, { error: "No se pudo confirmar la operación. Revisa la lista antes de repetirla." });
        }
    };
}
