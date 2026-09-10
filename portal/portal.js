/* ========================================
   ELEMENTOS
   ======================================== */

const loginForm =
    document.getElementById("loginForm");

const emailInput =
    document.getElementById("email");

const passwordInput =
    document.getElementById("password");

const togglePasswordButton =
    document.getElementById("togglePassword");

const forgotPasswordButton =
    document.getElementById("forgotPassword");

const loginMessage =
    document.getElementById("loginMessage");

const currentYear =
    document.getElementById("currentYear");


/* ========================================
   AÑO AUTOMÁTICO
   ======================================== */

if (currentYear) {
    currentYear.textContent =
        new Date().getFullYear();
}


/* ========================================
   MOSTRAR / OCULTAR CONTRASEÑA
   ======================================== */

togglePasswordButton.addEventListener(
    "click",
    function () {

        const passwordIsHidden =
            passwordInput.type === "password";

        if (passwordIsHidden) {

            passwordInput.type = "text";

            togglePasswordButton.textContent =
                "Ocultar";

            togglePasswordButton.setAttribute(
                "aria-label",
                "Ocultar contraseña"
            );

        } else {

            passwordInput.type = "password";

            togglePasswordButton.textContent =
                "Mostrar";

            togglePasswordButton.setAttribute(
                "aria-label",
                "Mostrar contraseña"
            );

        }

    }
);


/* ========================================
   LOGIN
   ======================================== */

loginForm.addEventListener(
    "submit",
    function (event) {

        event.preventDefault();

        const email =
            emailInput.value.trim();

        const password =
            passwordInput.value;

        clearMessage();

        if (
            email === "" ||
            password === ""
        ) {

            showMessage(
                "Completa tu correo electrónico y contraseña.",
                "error"
            );

            return;

        }

        /*
         * POR AHORA EL LOGIN ES SOLAMENTE VISUAL.
         *
         * En la siguiente etapa este bloque
         * se conectará con Supabase Auth.
         */

        showMessage(
            "El acceso al Portal Escolar estará disponible próximamente.",
            "info"
        );

    }
);


/* ========================================
   RECUPERAR CONTRASEÑA
   ======================================== */

forgotPasswordButton.addEventListener(
    "click",
    function () {

        clearMessage();

        /*
         * Posteriormente Supabase enviará
         * el correo de recuperación.
         */

        showMessage(
            "La recuperación de contraseña estará disponible próximamente.",
            "info"
        );

    }
);


/* ========================================
   MENSAJES
   ======================================== */

function showMessage(
    message,
    type
) {

    loginMessage.textContent =
        message;

    loginMessage.className =
        "login-message visible " + type;

}


function clearMessage() {

    loginMessage.textContent =
        "";

    loginMessage.className =
        "login-message";

}
