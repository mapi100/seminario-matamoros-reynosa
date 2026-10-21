// Estos dos datos son públicos. Nunca pegues aquí una contraseña,
// una clave sb_secret_ ni la antigua clave service_role.
window.PORTAL_SUPABASE_CONFIG = Object.freeze({
    url: "https://ysiifytzvchubcdxbsxg.supabase.co",
    publishableKey: "sb_publishable_3jtOD5JJc7jLfTrXmUvLEA_cq9DwzN7",
    // Activar solo después de desplegar invite-person y probar SMTP.
    features: Object.freeze({ invitations: false })
});
