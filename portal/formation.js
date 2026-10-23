(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const stages = Object.freeze([
        {code:"introductorio", name:"Curso Introductorio", ecclesial_name:"Etapa propedéutica", semesters:2},
        {code:"filosofia", name:"Filosofía", ecclesial_name:"Etapa discipular", semesters:6},
        {code:"teologia", name:"Teología", ecclesial_name:"Etapa configuradora", semesters:8}
    ]);
    let profile, recheck, generation=0, sequence=0, dialogSequence=0, opened=false, busy=false;
    let periods=[], offset=0, selected, saving=false, uncertain=false, returnFocus;
    const controllers=new Set();
    const stage = code => stages.find(s => s.code===code);
    const el = (tag,text,css) => {const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(css)node.className=css;return node;};
    function button(text,action) {const node=el("button",text,"back-link");node.type="button";node.addEventListener("click",action);return node;}
    function note(text,type="",target=$("formationStatus")) {target.textContent=text;target.className="control-message"+(type?" "+type:"");}
    function validHistory(items) {
        return Array.isArray(items)&&items.every(r=>uuid.test(r.period_id)&&stage(r.stage_code)&&
            Number.isInteger(r.semester)&&r.semester>=1&&r.semester<=stage(r.stage_code).semesters&&typeof r.period_name==="string");
    }
    function label(row) {const s=stage(row.stage_code);return s?s.name+" · Semestre "+row.semester+" de "+s.semesters:"Etapa pendiente de asignar";}
    async function rpc(name,args) {
        const controller=new AbortController();controllers.add(controller);
        try {const result=await window.PortalAuth.getClient().rpc(name,args).retry(false).abortSignal(controller.signal);
            if(result.error)throw {...result.error,status:result.status};return result.data;
        } finally {controllers.delete(controller);}
    }
    function failure(error,target) {
        if(error?.code==="42501"||[401,403].includes(error?.status)) {const verify=recheck;clear();if(verify)void verify();return;}
        const text=["22023","PT409"].includes(error?.code)&&typeof error.message==="string"&&error.message.length<250?error.message:
            ["PGRST202","42883","42P01"].includes(error?.code)?"Falta instalar las etapas formativas en Supabase.":"No se pudo completar la consulta. Actualiza para reintentar.";
        note(text,"error",target);
    }
    function closeDialog(force=false) {
        if(saving&&!force)return;dialogSequence++;selected=undefined;saving=false;uncertain=false;
        if($("formationDialog").open)$("formationDialog").close();$("formationForm").reset();
        $("formationDialogHistory").replaceChildren();note("","",$("formationDialogStatus"));
        $("formationSave").disabled=false;$("formationForm").setAttribute("aria-busy","false");
        $("formationStage").disabled=false;
        $("formationCancel").disabled=false;if(returnFocus?.isConnected&&!force)returnFocus.focus();returnFocus=undefined;
    }
    function leave() {
        opened=false;sequence++;busy=false;closeDialog(true);$("formationSection").hidden=true;
        $("formationStudents").replaceChildren();note("");
    }
    function clear() {
        generation++;profile=undefined;recheck=undefined;for(const c of controllers)c.abort();controllers.clear();leave();
        $("formationOwn").hidden=true;$("formationOwnSummary").replaceChildren();
        $("formationPeriod").replaceChildren();$("formationSearch").value="";$("formationFilter").value="";periods=[];
    }
    function historyList(items,target) {
        target.replaceChildren();if(!items.length){target.append(el("p","Todavía no hay etapas registradas para este seminarista."));return;}
        const list=el("ol",undefined,"formation-history");for(const row of items){const item=el("li");
            item.dataset.stage=row.stage_code;item.append(el("strong",row.period_name),el("p",label(row)),el("small",stage(row.stage_code).ecclesial_name));list.append(item);}target.append(list);
    }
    async function own() {
        const g=generation;
        try {const result=await rpc("portal_formation_read",{p_resource:"own"});if(!profile||g!==generation)return;
            if(!validHistory(result?.history))throw new Error("Trayectoria inválida");
            historyList(result.history,$("formationOwnSummary"));$("formationOwn").hidden=false;
        } catch(error) {if(profile&&g===generation){$("formationOwn").hidden=false;failure(error,$("formationOwnSummary"));}}
    }
    function semesterOptions(code,value="") {
        const s=stage(code),select=$("formationSemester");select.replaceChildren(new Option("Selecciona semestre",""));
        if(s)for(let i=1;i<=s.semesters;i++)select.append(new Option("Semestre "+i+" de "+s.semesters,String(i)));
        select.disabled=!s;select.value=String(value);$("formationStageHelp").textContent=s?s.ecclesial_name+" · "+s.semesters+" semestres":"Selecciona una de las tres etapas.";
    }
    async function edit(row) {
        if(!profile||!opened||busy)return;closeDialog();const g=generation,op=dialogSequence;
        returnFocus=document.activeElement;selected={...row,period_id:$("formationPeriod").value};
        $("formationDialogTitle").textContent=row.full_name;$("formationDialogPeriod").textContent=periods.find(p=>p.id===selected.period_id)?.name||"";
        $("formationStage").value=row.stage_code||"";semesterOptions(row.stage_code,row.semester||"");
        $("formationDialog").showModal();$("formationStage").focus();
        try {const result=await rpc("portal_formation_read",{p_resource:"history",p_student:row.id});
            if(!profile||g!==generation||op!==dialogSequence||!selected)return;if(!validHistory(result?.history))throw new Error("Historial inválido");
            historyList(result.history,$("formationDialogHistory"));
        } catch(error) {if(profile&&g===generation&&op===dialogSequence)failure(error,$("formationDialogStatus"));}
    }
    async function load(reset=true) {
        if(!profile||!opened||busy||!$("formationPeriod").value)return;
        const g=generation,op=++sequence;busy=true;if(reset){offset=0;$("formationStudents").replaceChildren();}
        $("formationMore").disabled=true;note("Consultando seminaristas…");
        try {const result=await rpc("portal_formation_read",{p_resource:"students",p_period:$("formationPeriod").value,
            p_stage:$("formationFilter").value,p_search:$("formationSearch").value.trim(),p_offset:offset,p_limit:30});
            if(!profile||!opened||g!==generation||op!==sequence)return;
            if(!Array.isArray(result?.items)||typeof result.has_more!=="boolean"||result.items.length>30)throw new Error("Lista inválida");
            for(const row of result.items){if(!uuid.test(row.id)||typeof row.full_name!=="string"||!Number.isInteger(row.revision)||
                (row.stage_code!==null&&(!stage(row.stage_code)||!Number.isInteger(row.semester)||row.semester<1||row.semester>stage(row.stage_code).semesters)))throw new Error("Alumno inválido");
                const item=el("li"),info=el("div");info.append(el("h3",row.full_name),el("p",(row.student_number||"Matrícula pendiente")+" · "+(row.active?"Activo":"Inactivo")),el("p",label(row),"formation-label"));
                item.dataset.stage=row.stage_code||"";item.append(info,button(row.revision?"Editar etapa y semestre":"Asignar etapa y semestre",()=>void edit(row)));$("formationStudents").append(item);}
            offset+=result.items.length;$("formationMore").hidden=!result.has_more;
            note(offset?offset+(offset===1?" seminarista mostrado.":" seminaristas mostrados.")+" La asignación corresponde al periodo seleccionado.":"No hay seminaristas que coincidan con los filtros.");
        } catch(error) {if(profile&&g===generation&&op===sequence){$("formationStudents").replaceChildren();failure(error);}}
        finally {if(g===generation&&op===sequence){busy=false;$("formationMore").disabled=false;}}
    }
    async function openRoute(preferredPeriod) {
        if(!profile||profile.role!=="control_escolar"||opened)return;opened=true;$("formationSection").hidden=false;
        const g=generation;note("Preparando etapas y semestres…");
        try {const result=await rpc("portal_formation_read",{p_resource:"settings"});if(!profile||!opened||g!==generation)return;
            if(!Array.isArray(result?.periods)||!result.periods.every(p=>uuid.test(p.id)&&typeof p.name==="string")||
                !Array.isArray(result.stages)||result.stages.length!==3||!result.stages.every(s=>stage(s.code)?.semesters===s.semesters))throw new Error("Configuración inválida");
            periods=result.periods;$("formationPeriod").replaceChildren(...periods.map(p=>new Option(p.name,p.id)));
            if(periods.some(p=>p.id===preferredPeriod))$("formationPeriod").value=preferredPeriod;
            if(!periods.length){note("Crea primero un periodo en Materias y periodos. Después podrás asignar la etapa y el semestre.");return;}
            await load();
        } catch(error) {if(profile&&opened&&g===generation)failure(error);}
    }
    async function save(event) {
        event.preventDefault();if(!profile||!opened||!selected||saving||uncertain||!$("formationForm").reportValidity())return;
        const g=generation,op=dialogSequence,row=selected;saving=true;$("formationSave").disabled=true;$("formationCancel").disabled=true;
        $("formationForm").setAttribute("aria-busy","true");note("Guardando…","",$("formationDialogStatus"));
        $("formationStage").disabled=true;$("formationSemester").disabled=true;
        try {const result=await rpc("portal_formation_save",{p_student:row.id,p_period:row.period_id,p_stage:$("formationStage").value,
            p_semester:Number($("formationSemester").value),p_revision:row.revision});
            if(!profile||g!==generation||op!==dialogSequence)return;if(result?.saved!==true)throw new Error("Guardado sin confirmar");
            saving=false;closeDialog();await load();if(profile&&g===generation)note("Etapa y semestre guardados. Ya están vinculados al expediente y al kardex.","success");
        } catch(error) {if(profile&&g===generation&&op===dialogSequence){
            if(["22023","PT409","42501"].includes(error?.code))failure(error,$("formationDialogStatus"));
            else {uncertain=true;note("No se pudo confirmar el guardado. Cierra y actualiza la lista para comprobar el resultado antes de repetirlo.","error",$("formationDialogStatus"));}
        }} finally {if(g===generation&&op===dialogSequence){saving=false;$("formationSave").disabled=uncertain;$("formationCancel").disabled=false;$("formationStage").disabled=uncertain;$("formationSemester").disabled=uncertain||!stage($("formationStage").value);$("formationForm").setAttribute("aria-busy","false");}}
    }
    for(const s of stages){$("formationFilter").append(new Option(s.name,s.code));$("formationStage").append(new Option(s.name,s.code));
        const card=el("article",undefined,"formation-stage-card");card.dataset.stage=s.code;card.append(el("strong",s.name),el("span",s.ecclesial_name),el("p",s.semesters+" semestres"));$("formationStages").append(card);}
    $("formationStage").addEventListener("change",()=>semesterOptions($("formationStage").value));
    $("formationForm").addEventListener("submit",event=>void save(event));
    $("formationCancel").addEventListener("click",()=>closeDialog());
    $("formationDialog").addEventListener("cancel",event=>{event.preventDefault();closeDialog();});
    $("formationSearchForm").addEventListener("submit",event=>{event.preventDefault();void load();});
    for(const id of ["formationPeriod","formationFilter"])$(id).addEventListener("change",()=>{sequence++;busy=false;void load();});
    $("formationMore").addEventListener("click",()=>void load(false));
    $("formationRefresh").addEventListener("click",()=>{const period=$("formationPeriod").value;leave();void openRoute(period);});
    window.PortalFormation=Object.freeze({stages,clear,leave,openRoute,show(value,verify){clear();profile=value;recheck=verify;if(profile.role==="student")void own();}});
})();
