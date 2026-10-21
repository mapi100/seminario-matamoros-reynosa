(function () {
    "use strict";
    const form=document.getElementById("activationForm"),message=document.getElementById("activationMessage"),password=document.getElementById("newPassword"),confirm=document.getElementById("confirmPassword"),save=document.getElementById("activationSave"),next=document.getElementById("activationContinue");
    const params=new URLSearchParams(location.hash.slice(1));
    let link={access:params.get("access_token"),refresh:params.get("refresh_token"),type:params.get("type")};
    params.delete("access_token");params.delete("refresh_token");
    // Tokens belong only to this activation flow. Remove them before any navigation.
    history.replaceState(null,"",location.pathname);
    let ready=false,busy=false,version=0;
    function note(text,error=false){message.textContent=text;message.className="login-message visible "+(error?"error":"info");}
    async function start(){const operation=++version;ready=false;form.hidden=true;
        try{const client=window.PortalAuth.getClient();
            if(link?.access&&link.refresh&&["invite","recovery"].includes(link.type)){const currentLink=link;link=undefined;const response=await client.auth.setSession({access_token:currentLink.access,refresh_token:currentLink.refresh});if(response.error)throw response.error;}
            else if(!sessionStorage.getItem("seminario-activation-pending")){throw new Error("Enlace no válido");}
            const result=await window.PortalAuth.checkAccess();if(operation!==version)return;if(result.status!=="authorized")throw new Error("Acceso no válido");
            sessionStorage.setItem("seminario-activation-pending","1");ready=true;form.hidden=false;note("Enlace verificado. Guarda tu contraseña para continuar.");password.focus();
        }catch{if(operation===version)note("Este enlace no está disponible o tu cuenta aún no tiene acceso. Abre el enlace más reciente o solicita ayuda a Control Escolar.",true);}}
    form.addEventListener("submit",async event=>{event.preventDefault();if(!ready||busy)return;confirm.setCustomValidity(password.value===confirm.value?"":"Las contraseñas deben coincidir.");if(!form.reportValidity())return;
        busy=true;save.disabled=true;const operation=++version;note("Guardando contraseña…");
        try{const accessResult=await window.PortalAuth.checkAccess();if(operation!==version)return;if(accessResult.status!=="authorized")throw new Error("Acceso denegado");const response=await window.PortalAuth.getClient().auth.updateUser({password:password.value});if(response.error)throw response.error;if(operation!==version)return;form.reset();form.hidden=true;ready=false;sessionStorage.removeItem("seminario-activation-pending");note("Contraseña guardada. Ya puedes entrar al portal.");next.hidden=false;next.focus();}
        catch{if(operation===version)note("No se pudo guardar la contraseña. Comprueba tu conexión e inténtalo nuevamente.",true);}
        finally{if(operation===version){password.value="";confirm.value="";busy=false;save.disabled=false;}}});
    confirm.addEventListener("input",()=>confirm.setCustomValidity(""));password.addEventListener("input",()=>confirm.setCustomValidity(""));
    window.addEventListener("pagehide",()=>{version++;ready=false;busy=false;save.disabled=false;form.reset();form.hidden=true;});
    window.addEventListener("pageshow",event=>{if(event.persisted)void start();});
    void start();
})();
