(function () {
    "use strict";
    const nav=document.getElementById("workspaceNav"), toggle=document.getElementById("menuToggle");
    const routes={inicio:"Inicio","mis-materias":"Mis materias","materias-asignadas":"Mis clases",personas:"Personas",clases:"Clases",inscripciones:"Inscripciones",profesores:"Asignar profesores","catalogos-academicos":"Materias y periodos",actividad:"Actividad","mi-perfil":"Mi perfil"};
    const adminRoutes={personas:"people",clases:"classes",inscripciones:"enrollments",profesores:"assignments",actividad:"events"};
    let profile;
    function syncMenu(){const closed=matchMedia("(max-width:760px)").matches&&!nav.classList.contains("menu-open");nav.inert=closed;nav.setAttribute("aria-hidden",String(closed||nav.hidden));}
    function closeMenu(){nav.classList.remove("menu-open");toggle.setAttribute("aria-expanded","false");toggle.setAttribute("aria-label","Abrir menú");syncMenu();}
    function clear(){profile=undefined;nav.hidden=true;closeMenu();document.getElementById("controlHome").hidden=true;document.getElementById("welcomeTitle").textContent="Bienvenido al Portal Escolar";document.getElementById("workspaceBreadcrumb").textContent="Mi campus";for(const link of nav.querySelectorAll("a")){link.hidden=true;link.removeAttribute("aria-current");}for(const kind of ["student","teacher"]){document.getElementById(kind+"Search").value="";document.getElementById(kind+"Period").replaceChildren(new Option("Todos los periodos",""));document.getElementById(kind+"FilterStatus").textContent="";}}
    function navigate(focus=false){
        if(!profile)return;
        let route=location.hash.slice(1)||"inicio";
        const link=nav.querySelector('[data-route="'+(Object.hasOwn(routes,route)?route:"inicio")+'"]');
        if(!Object.hasOwn(routes,route)||!link||link.hidden)route="inicio";
        document.body.dataset.view=route;
        for(const panel of document.querySelectorAll("[data-screen]"))panel.classList.toggle("view-hidden",!panel.dataset.screen.split(" ").includes(route));
        for(const item of nav.querySelectorAll("a")){if(item.dataset.route===route)item.setAttribute("aria-current","page");else item.removeAttribute("aria-current");}
        document.getElementById("workspaceBreadcrumb").textContent="Mi campus / "+routes[route];
        if(Object.hasOwn(adminRoutes,route))window.PortalManagement?.openResource(adminRoutes[route]);
        else window.PortalManagement?.leave();
        closeMenu();
        if(focus){document.getElementById("panelMain").focus({preventScroll:true});window.scrollTo({top:0,behavior:"instant"});}
    }
    function show(value){profile=value;nav.hidden=false;syncMenu();for(const link of nav.querySelectorAll("a"))link.hidden=Boolean(link.dataset.roles&&!link.dataset.roles.split(" ").includes(profile.role));document.getElementById("welcomeTitle").textContent="Bienvenido, "+profile.full_name;document.getElementById("controlHome").hidden=profile.role!=="control_escolar";navigate();}
    toggle.addEventListener("click",()=>{const open=nav.classList.toggle("menu-open");toggle.setAttribute("aria-expanded",String(open));toggle.setAttribute("aria-label",open?"Cerrar menú":"Abrir menú");syncMenu();});
    document.addEventListener("keydown",event=>{if(event.key==="Escape"&&nav.classList.contains("menu-open")){closeMenu();toggle.focus();}});
    window.addEventListener("hashchange",()=>navigate(true));
    matchMedia("(max-width:760px)").addEventListener("change",syncMenu);
    document.addEventListener("pointerdown",event=>{if(nav.classList.contains("menu-open")&&!nav.contains(event.target)&&!toggle.contains(event.target))closeMenu();});
    for(const [kind,listId,nameClass,periodClass] of [["student","subjectsList","subject-name","subject-period"],["teacher","teachingList","teaching-name","teaching-period"]]){
        const search=document.getElementById(kind+"Search"),period=document.getElementById(kind+"Period"),list=document.getElementById(listId);
        function filter(){const cards=[...list.children],selected=period.value;const periods=[...new Set(cards.map(card=>card.querySelector('.'+periodClass)?.textContent).filter(Boolean))];if([...period.options].slice(1).map(o=>o.value).join("|")!==periods.join("|")){period.replaceChildren(new Option("Todos los periodos",""),...periods.map(value=>new Option(value,value)));period.value=periods.includes(selected)?selected:"";}
            const needle=search.value.trim().toLocaleLowerCase("es");let visible=0;for(const card of cards){const text=(card.querySelector('.'+nameClass)?.textContent||card.textContent).toLocaleLowerCase("es")+' '+(card.querySelector('.subject-code,.teaching-code')?.textContent||'').toLocaleLowerCase("es");card.hidden=Boolean(needle&&!text.includes(needle)||period.value&&card.querySelector('.'+periodClass)?.textContent!==period.value);if(!card.hidden)visible++;}document.getElementById(kind+"FilterStatus").textContent=(needle||period.value)?visible+" coincidencias entre las materias mostradas.":"";}
        search.addEventListener("input",filter);period.addEventListener("change",filter);new MutationObserver(filter).observe(list,{childList:true});
    }
    window.PortalWorkspace=Object.freeze({show,clear});
})();
