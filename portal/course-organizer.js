(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const stages = [{key:"CI",name:"Introductorio",count:2},{key:"F",name:"Filosofía",count:6},{key:"T",name:"Teología",count:8}];
    const codes = stages.flatMap(s=>Array.from({length:s.count},(_,i)=>({code:(s.key==="CI"?"CI":Math.ceil((i+1)/2)+s.key)+"-"+(i+1),stage:s.key,name:s.name})));
    const validGroup = value => value === null || codes.some(x=>x.code===value);
    const normalize = text => String(text||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLocaleLowerCase("es");
    let profile, verify, opened=false, generation=0, controller, snapshot, selected="all", library=false, busy=false, uncertain=false, drag, mover;
    function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
    function button(label,action,cls="back-link"){const b=node("button",label,cls);b.type="button";b.addEventListener("click",action);return b;}
    function status(text,error=false){$("organizerStatus").textContent=text;$("organizerStatus").className="organizer-status"+(error?" error":"");}
    function isDenied(error){return error?.code==="42501"||[401,403].includes(error?.status);}
    async function read(period,signal){
        const {data,error,status:code}=await window.PortalAuth.getClient().rpc("portal_course_board_read",{p_period:period||null}).retry(false).abortSignal(signal);
        if(error)throw {...error,status:code};
        if(!Array.isArray(data?.periods)||!Array.isArray(data.subjects)||!Array.isArray(data.classes)||data.periods.length>10000||data.subjects.length>10000||data.classes.length>10000||
            data.period_id!==null&&!uuid.test(data.period_id)||
            data.periods.some(p=>!uuid.test(p.id)||typeof p.name!=="string")||
            data.subjects.some(s=>!uuid.test(s.id)||typeof s.name!=="string"||typeof s.code!=="string")||
            data.classes.some(c=>!uuid.test(c.id)||!uuid.test(c.subject_id)||c.period_id!==data.period_id||typeof c.name!=="string"||typeof c.active!=="boolean"||!validGroup(c.group_code)||!Number.isInteger(c.revision)||c.revision<0))throw new Error("Respuesta de clases inválida");
        return data;
    }
    function closeMover(){if(mover){mover.remove();mover=undefined;}}
    function leave(){generation++;controller?.abort();controller=undefined;opened=false;snapshot=undefined;busy=uncertain=false;drag=undefined;closeMover();$("courseOrganizer").hidden=true;$("organizerSources").replaceChildren();$("organizerGroups").replaceChildren();$("organizerPeriod").replaceChildren();status("");}
    function clear(){leave();profile=verify=undefined;selected="all";library=false;$("organizerSearch").value="";}
    function sync(){
        $("organizerPeriod").disabled=busy;$("organizerRefresh").disabled=busy;$("organizerLibrary").disabled=busy;
        for(const b of $("courseOrganizer").querySelectorAll("[data-move]"))b.disabled=busy||uncertain||!snapshot?.period_id;
        for(const card of $("courseOrganizer").querySelectorAll(".organizer-subject"))card.draggable=!busy&&!uncertain&&Boolean(snapshot?.period_id);
    }
    async function load(period){
        if(!profile||!opened)return;const g=++generation;controller?.abort();controller=new AbortController();busy=true;sync();status("Cargando materias y cursos…");
        $("organizerSources").replaceChildren();$("organizerGroups").replaceChildren();snapshot=undefined;
        try{const data=await read(period,controller.signal);if(g!==generation||!opened)return;snapshot=data;uncertain=false;
            $("organizerPeriod").replaceChildren(...data.periods.map(p=>new Option(p.name,p.id)));$("organizerPeriod").value=data.period_id||"";
            status(data.period_id?"Arrastra una materia a su curso o usa el botón Mover. Los cambios se guardan al momento.":"Crea primero un periodo académico en el formulario de abajo.");render();
        }catch(error){if(g!==generation)return;if(isDenied(error)){const callback=verify;clear();callback?.();return;}status("No se pudieron cargar las materias. Pulsa Actualizar para reintentar.",true);}
        finally{if(g===generation){busy=false;sync();}}
    }
    function render(){
        if(!snapshot)return;const term=snapshot.periods.find(p=>p.id===snapshot.period_id);
        $("organizerLibrary").textContent=library?"Volver a clases del periodo":"Agregar desde catálogo";
        $("organizerListTitle").textContent=library?"Materias para abrir en este periodo":selected==="all"?"Todas las clases del periodo":selected==="none"?"Clases sin curso asignado":"Materias de "+selected;
        $("organizerScope").textContent=term?"Periodo: "+term.name+". Organizar una clase conserva sus alumnos, tareas y calificaciones.":"Selecciona un periodo académico.";
        const used=new Set(snapshot.classes.map(c=>c.subject_id));
        let rows=library?snapshot.subjects.filter(s=>!used.has(s.id)).map(s=>({...s,subject_id:s.id,id:null,group_code:null,revision:0,period_id:snapshot.period_id})):snapshot.classes.filter(c=>selected==="all"||(selected==="none"?c.group_code===null:c.group_code===selected));
        const needle=normalize($("organizerSearch").value.trim());rows=rows.filter(c=>normalize(c.name+" "+(c.group_code||"")).includes(needle));
        const source=$("organizerSources");source.replaceChildren();$("organizerCount").textContent=rows.length+" materias";
        for(const row of rows){
            const li=node("li",undefined,"organizer-subject"),name=node("strong",row.name),meta=node("p",library?"Se abrirá una clase en este periodo":(row.group_code||"Sin curso asignado")+(row.active?"":" · Inactiva"));
            li.append(name,meta);li.draggable=!busy&&!uncertain;li.setAttribute("aria-describedby","organizerScope");
            const move=button(library?"Abrir y asignar curso":"Mover",()=>moveDialog(row));move.dataset.move="true";move.setAttribute("aria-label",(library?"Abrir y asignar curso a ":"Mover ")+row.name);li.append(move);
            li.addEventListener("dragstart",event=>{if(busy||uncertain){event.preventDefault();return;}drag={row,period:snapshot.period_id};event.dataTransfer.setData("text/plain",JSON.stringify({id:row.id,subject:row.subject_id}));event.dataTransfer.effectAllowed="move";li.classList.add("dragging");});
            li.addEventListener("dragend",()=>{drag=undefined;li.classList.remove("dragging");document.querySelectorAll(".organizer-drop.active").forEach(x=>x.classList.remove("active"));});source.append(li);
        }
        if(!rows.length)source.append(node("li",library?"Todas las materias del catálogo ya tienen clase en este periodo.":"No hay materias que coincidan con esta selección.","organizer-empty"));
        const groups=$("organizerGroups");groups.replaceChildren();
        for(const stage of stages){const section=node("section",undefined,"organizer-stage");section.append(node("h3",stage.name));const tiles=node("div",undefined,"organizer-stage-grid");for(const c of codes.filter(x=>x.stage===stage.key))tiles.append(tile(c.code,c.code));section.append(tiles);groups.append(section);}
        groups.append(tile(null,"Sin curso asignado"));sync();
    }
    function tile(group,label){const count=snapshot.classes.filter(c=>c.group_code===group).length;
        const b=button(label,()=>{selected=group||"none";library=false;render();$("organizerListTitle").focus({preventScroll:true});if(matchMedia("(max-width:1100px)").matches)$("organizerSources").parentElement.scrollIntoView({block:"start",behavior:"smooth"});},"organizer-drop");b.dataset.group=group||"none";b.setAttribute("aria-pressed",String(selected===(group||"none")));b.append(node("small",count+" materias"));
        b.addEventListener("dragover",e=>{if(drag&&!busy&&!uncertain&&drag.period===snapshot.period_id&&(drag.row.id||group!==null)){e.preventDefault();b.classList.add("active");e.dataTransfer.dropEffect="move";}});
        b.addEventListener("dragleave",()=>b.classList.remove("active"));
        b.addEventListener("drop",e=>{e.preventDefault();b.classList.remove("active");if(!drag||busy||uncertain||drag.period!==snapshot.period_id)return;const row=drag.row;drag=undefined;void move(row,group);});return b;
    }
    function moveDialog(row){
        if(busy||uncertain||mover)return;const d=node("dialog",undefined,"learning-dialog course-group-dialog");mover=d;const form=node("form"),title=node("h2",row.id?"Mover materia":"Abrir materia en el periodo"),select=node("select"),label=node("label","Curso de destino");
        select.id="organizerMoveGroup";label.htmlFor=select.id;
        if(row.id)select.append(new Option("Sin curso asignado","none"));else{select.required=true;select.append(new Option("Selecciona un curso",""));}
        for(const c of codes)select.append(new Option(c.code+" · "+c.name,c.code));select.value=row.group_code||(row.id?"none":"");
        const submit=node("button","Guardar cambio","learning-button");submit.type="submit";const cancel=button("Cancelar",()=>{closeMover();},"learning-button secondary");
        form.append(title,node("p",row.name),label,select,node("p",$("organizerScope").textContent),submit,cancel);d.append(form);document.body.append(d);d.showModal();select.focus();
        d.addEventListener("cancel",event=>{event.preventDefault();closeMover();});form.addEventListener("submit",event=>{event.preventDefault();if(!select.reportValidity())return;const group=select.value==="none"?null:select.value;closeMover();void move(row,group);});
    }
    async function move(row,group){
        if(!profile||!opened||busy||uncertain||!snapshot||row.period_id!==snapshot.period_id||!validGroup(group))return;
        if(row.id&&row.group_code===group){status("La materia ya pertenece a ese curso.");return;}
        const g=generation;busy=true;sync();status("Guardando "+row.name+"…");
        try{const {data,error,status:code}=await window.PortalAuth.getClient().rpc("portal_course_board_write",{p_subject:row.subject_id,p_period:snapshot.period_id,p_course:row.id,p_group:group,p_revision:row.revision}).retry(false);
            if(g!==generation||!opened)return;if(error)throw {...error,status:code};if(data?.saved!==true||!uuid.test(data.id)||!Number.isInteger(data.revision))throw new Error("Guardado sin confirmar");
            const saved={...row,id:data.id,group_code:group,revision:data.revision,active:row.id?row.active:true};const index=snapshot.classes.findIndex(c=>c.id===data.id);
            if(index<0)snapshot.classes.push(saved);else snapshot.classes[index]=saved;
            busy=false;render();status(row.name+" ahora está en "+(group||"Sin curso asignado")+".");window.PortalCourseGroups?.reload();
            $("organizerGroups").querySelector('[data-group="'+(group||"none")+'"]')?.focus({preventScroll:true});
        }catch(error){if(g!==generation)return;if(isDenied(error)){const callback=verify;clear();callback?.();return;}
            uncertain=true;status(["PT409","22023"].includes(error?.code)?error.message+" Pulsa Actualizar.":"No se confirmó el cambio. Pulsa Actualizar para comprobar dónde quedó la materia antes de repetir.",true);
        }finally{if(g===generation){busy=false;sync();}}
    }
    async function pickerData(period,signal){
        try{return await read(period,signal);}catch(error){
            if(!["PGRST202","42883"].includes(error?.code))throw error;
            // Compatibilidad mientras se instala la RPC nueva. Recorrer todas las páginas.
            const classes=[];const seen=new Set();let more=true;
            while(more){
                if(classes.length>=10000)throw new Error("Lista demasiado grande");
                const {data,error,status}=await window.PortalAuth.getClient().rpc("portal_admin_read",{p_resource:"active_classes",p_search:"",p_offset:classes.length,p_limit:100}).retry(false).abortSignal(signal);
                if(error)throw {...error,status};
                if(!Array.isArray(data?.items)||data.items.length>100||typeof data.has_more!=="boolean"||data.has_more&&!data.items.length)throw new Error("Página inválida");
                for(const c of data.items){if(!uuid.test(c.id)||!uuid.test(c.period_id)||!uuid.test(c.subject_id)||typeof c.subject_name!=="string"||seen.has(c.id))throw new Error("Clase inválida");seen.add(c.id);classes.push({...c,name:c.subject_name,group_code:window.PortalCourseGroups?.get(c.id)?.group_code||null,revision:0});}
                more=data.has_more;
            }
            const periods=[...new Map(classes.map(c=>[c.period_id,{id:c.period_id,name:c.period_name,starts_on:c.starts_on,ends_on:c.ends_on}])).values()].sort((a,b)=>b.starts_on.localeCompare(a.starts_on));
            const today=new Intl.DateTimeFormat("en-CA",{timeZone:"America/Matamoros"}).format(new Date());
            const chosen=period||periods.find(p=>p.starts_on<=today&&p.ends_on>=today)?.id||periods[0]?.id||null;
            return {periods,period_id:chosen,subjects:[],classes:classes.filter(c=>c.period_id===chosen)};
        }
    }
    function mountPicker(container,{name="class_id",selected:initial,signal,isAlive=()=>true,onDenied=()=>{}}={}){
        const wrapper=node("div",undefined,"course-picker"),filters=node("div",undefined,"course-picker-filters");
        const period=node("select"),stage=node("select"),course=node("select"),search=node("input"),select=node("select"),message=node("p",undefined,"lookup-status");
        let rows=[],sequence=0,requestController;
        function field(labelText,input,id){const block=node("div"),label=node("label",labelText);input.id=id;label.htmlFor=id;block.append(label,input);return block;}
        stage.append(new Option("Todas las etapas","all"),...stages.map(s=>new Option(s.name,s.key)),new Option("Sin clasificar","none"));
        select.name=name;select.required=true;search.type="search";search.placeholder="Buscar materia";search.autocomplete="off";
        const retry=button("Reintentar lista",()=>void loadPicker(period.value||initial?.period_id||null));retry.hidden=true;message.setAttribute("role","status");
        filters.append(field("Periodo académico",period,"classPickerPeriod"),field("Etapa",stage,"classPickerStage"),field("Curso",course,"classPickerCourse"));
        wrapper.append(filters,field("Buscar materia",search,"classPickerSearch"),field("Clase",select,"admin-"+name),message,retry);container.append(wrapper);
        function updateCourses(){const previous=course.value;course.replaceChildren(new Option("Todos los cursos","all"));for(const c of codes.filter(c=>stage.value==="all"||c.stage===stage.value))course.append(new Option(c.code,c.code));if([...course.options].some(o=>o.value===previous))course.value=previous;}
        function draw(preferred){
            const prior=preferred||select.value;select.replaceChildren(new Option("Selecciona una clase",""));const needle=normalize(search.value.trim());
            const filtered=rows.filter(c=>c.active&&(stage.value==="all"||stage.value==="none"&&!c.group_code||codes.find(x=>x.code===c.group_code)?.stage===stage.value)&&(course.value==="all"||c.group_code===course.value)&&normalize(c.name).includes(needle));
            for(const code of [...codes.map(c=>c.code),null]){
                const groupRows=filtered.filter(c=>c.group_code===code).sort((a,b)=>a.name.localeCompare(b.name,"es"));if(!groupRows.length)continue;
                const info=codes.find(c=>c.code===code),group=node("optgroup");group.label=info?info.name+" · "+info.code:"Sin curso asignado";
                for(const c of groupRows)group.append(new Option(c.name,c.id));select.append(group);
            }
            if(filtered.some(c=>c.id===prior))select.value=prior;
            message.textContent=filtered.length?filtered.length+" clases disponibles. Selecciona una materia.":"No hay clases con estos filtros. Prueba otro periodo o curso.";
        }
        async function loadPicker(id){
            if(!isAlive()||signal?.aborted)return;const n=++sequence;requestController?.abort();requestController=new AbortController();const local=requestController;
            if(signal)signal.addEventListener("abort",()=>local.abort(),{once:true});
            period.disabled=stage.disabled=course.disabled=select.disabled=true;retry.hidden=true;message.textContent="Cargando clases…";select.replaceChildren(new Option("Cargando clases…",""));rows=[];
            try{const data=await pickerData(id,local.signal);if(n!==sequence||!isAlive()||signal?.aborted)return;
                period.replaceChildren(...data.periods.map(p=>new Option(p.name,p.id)));period.value=data.period_id||"";rows=data.classes;updateCourses();draw(initial?.id);initial=undefined;
                period.disabled=stage.disabled=course.disabled=select.disabled=false;
            }catch(error){if(n!==sequence||!isAlive()||signal?.aborted)return;if(isDenied(error)){onDenied(error);return;}
                select.replaceChildren(new Option("No se pudieron cargar las clases",""));message.textContent="Pulsa Reintentar lista. Tus otros datos se conservan.";retry.hidden=false;
                console.warn("Lista de clases:",error?.code||"respuesta_invalida",error?.status||"");
            }
        }
        stage.addEventListener("change",()=>{updateCourses();draw();});course.addEventListener("change",()=>draw());search.addEventListener("input",()=>{if(!select.disabled)draw();});period.addEventListener("change",()=>void loadPicker(period.value));
        updateCourses();void loadPicker(initial?.period_id||null);return select;
    }
    $("organizerPeriod").addEventListener("change",()=>{selected="all";void load($("organizerPeriod").value);});
    $("organizerRefresh").addEventListener("click",()=>void load($("organizerPeriod").value));
    $("organizerSearch").addEventListener("input",()=>render());
    $("organizerLibrary").addEventListener("click",()=>{library=!library;selected="all";render();});
    $("organizerAll").addEventListener("click",()=>{selected="all";library=false;render();});
    window.addEventListener("portal-catalog-changed",()=>{if(opened&&!busy)void load($("organizerPeriod").value);});
    window.addEventListener("portal-academic-deleted",()=>{if(opened&&!busy)void load($("organizerPeriod").value);});
    window.PortalCourseOrganizer=Object.freeze({clear,leave,mountPicker,show(value,check){clear();if(value.role==="control_escolar"){profile=value;verify=check;}},openRoute(){if(!profile||opened)return;opened=true;$("courseOrganizer").hidden=false;void load(null);}});
})();
