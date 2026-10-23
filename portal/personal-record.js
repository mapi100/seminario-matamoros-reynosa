(function () {
    "use strict";
    const $ = id => document.getElementById(id);
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const section = $("personalRecordSection"), form = $("personalForm");
    const groups = [
        {title:"Identificación",help:"Usa el nombre que aparece en tus documentos. La CURP y el nacimiento se comparten con tu kardex; no se validan ante RENAPO desde el portal.",fields:[
            ["full_name","Nombre completo",160,"text","name"], ["curp","CURP",18,"text","off"], ["birth_date","Fecha de nacimiento",10,"date","bday"],
            ["birth_country","País de nacimiento",100], ["birth_state","Estado de nacimiento",100], ["birth_city","Municipio / ciudad de nacimiento",100],
            ["nationality","Nacionalidad",100]]},
        {title:"Contacto",help:"El correo de acceso identifica tu cuenta y se muestra como referencia. Un correo de contacto adicional no cambia tu cuenta ni tu contraseña.",fields:[
            ["phone","Teléfono personal con lada",40,"tel","tel"], ["alternate_phone","Teléfono alternativo (opcional)",40,"tel"], ["contact_email","Correo de contacto adicional (opcional)",320,"email"]]},
        {title:"Domicilio",help:"Registra el domicilio donde pueden localizar a tu familia o a ti fuera del Seminario.",fields:[
            ["street","Calle",180,"text","address-line1"], ["exterior_number","Número exterior",20], ["interior_number","Número interior (opcional)",20],
            ["neighborhood","Colonia / localidad",100,"text","address-line2"], ["postal_code","Código postal",16,"text","postal-code"],
            ["city","Municipio / ciudad",100,"text","address-level2"], ["state","Estado / provincia",100,"text","address-level1"], ["country","País",100,"text","country-name"]]},
        {title:"Familia y emergencias",help:"Indica a quién debemos contactar en caso de emergencia. Los datos de madre y padre son opcionales; el contacto de emergencia puede ser otra persona de confianza.",fields:[
            ["emergency_name","Nombre del contacto de emergencia",160], ["emergency_relationship","Parentesco / relación",80], ["emergency_phone","Teléfono de emergencia con lada",40,"tel"],
            ["mother_name","Nombre de la madre (opcional)",160], ["mother_phone","Teléfono de la madre (opcional)",40,"tel"],
            ["father_name","Nombre del padre (opcional)",160], ["father_phone","Teléfono del padre (opcional)",40,"tel"]]},
        {title:"Formación previa",help:"Esta información ayuda a Control Escolar a completar tu expediente. Las materias, programas y calificaciones oficiales se administran por separado.",fields:[
            ["home_diocese","Diócesis de origen",160], ["home_parish","Parroquia de origen",160], ["previous_school","Escuela de procedencia",200],
            ["previous_level","Último nivel de estudios",80], ["previous_qualification","Certificado / título obtenido (si corresponde)",160], ["previous_graduation_year","Año de egreso (si corresponde)",4]]},
        {title:"Datos escolares",help:"Estos datos se consultan desde tus inscripciones y el kardex. Control Escolar administra la matrícula, el ingreso, el egreso y la clasificación de las materias.",fields:[]}
    ];
    let profile, recheck, opened=false, generation=0, operation=0, currentRoute, target, record, tab=0, offset=0, pendingTarget;
    let dirty=false, saving=false, uncertain=false, staleDraft=false, baseline, resume;
    const controllers = new Set(), inputs = new Map(), panels = [], tabs = [];
    const create = (tag,text,className) => {const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=String(text);if(className)n.className=className;return n;};
    const control = () => profile?.role === "control_escolar";
    const fmtDate = value => value ? new Intl.DateTimeFormat("es-MX",{dateStyle:"medium"}).format(new Date(value.length===10?value+"T12:00:00":value)) : "Sin registrar";
    function note(text,type="") {$("personalStatus").textContent=text;$("personalStatus").className="control-message"+(type?" "+type:"");}
    function button(text,action,className="back-link") {const n=create("button",text,className);n.type="button";n.addEventListener("click",action);return n;}
    function payload() {
        const values={full_name:"",curp:"",birth_date:"",details:{}};
        for (const [key,input] of inputs) {
            const value=input.value.trim();
            if (Object.hasOwn(values,key) && key!=="details") values[key]=value;
            else values.details[key]=value;
        }
        return values;
    }
    function remember() {
        if (!profile || !opened || !target || !record) return;
        resume={user:profile.id,role:profile.role,target,route:currentRoute,tab,token:record.token,values:dirty?payload():null};
    }
    function leave(preserve=false) {
        if (preserve) remember(); else resume=undefined;
        generation++;operation++;for(const c of controllers)c.abort();controllers.clear();
        opened=false;target=undefined;record=undefined;dirty=false;saving=false;uncertain=false;staleDraft=false;baseline=undefined;
        inputs.clear();panels.length=0;tabs.length=0;section.hidden=true;$("personalEditor").hidden=true;$("personalLookup").hidden=true;
        for(const id of ["personalGroups","personalTabs","personalStudents","personalMissing"])$(id).replaceChildren();
        for(const id of ["personalStudentName","personalAccount","personalReviewState","personalProgressText"])$(id).textContent="";
        $("personalProgress").value=0;$("personalSearch").value="";note("");sync();
    }
    function clear(discard=false) {leave(!discard);profile=undefined;recheck=undefined;pendingTarget=undefined;if(discard)resume=undefined;}
    function forbidden(error) {
        if(error?.code!=="42501"&&![401,403].includes(error?.status))return false;
        const verify=recheck;clear(true);if(verify)void verify();return true;
    }
    function errorText(error) {
        if(["22023","PT409"].includes(error?.code)&&typeof error.message==="string"&&error.message.length<350)return error.message;
        if(["PGRST202","42883","42P01"].includes(error?.code))return "El expediente personal necesita instalarse en Supabase. Contacta al responsable del portal.";
        return "No se pudo consultar el expediente. Comprueba tu conexión y pulsa Actualizar datos.";
    }
    async function rpc(name,args) {
        const c=new AbortController();controllers.add(c);
        try {const result=await window.PortalAuth.getClient().rpc(name,args).retry(false).abortSignal(c.signal);if(result.error)throw {...result.error,status:result.status};if(!result.data||typeof result.data!=="object")throw new Error("Respuesta inválida");return result.data;}
        finally {controllers.delete(c);}
    }
    function valid(data,id) {
        return data?.student?.id===id&&uuid.test(id)&&typeof data.student.full_name==="string"&&typeof data.student.active==="boolean"&&data.identity&&data.details&&typeof data.details==="object"&&!Array.isArray(data.details)&&data.school&&Array.isArray(data.school.programs)&&/^[a-f0-9]{32}$/.test(data.token)&&Number.isSafeInteger(data.revision)&&data.revision>=0&&typeof data.review?.reviewed==="boolean"&&typeof data.can_review==="boolean"&&Array.isArray(data.completion?.missing)&&Number.isInteger(data.completion.completed)&&data.completion.total===9;
    }
    function acceptDiscard() {
        if(saving){note("Espera a que termine el guardado.");return false;}
        return !dirty||confirm("Tienes cambios sin guardar en el expediente. ¿Deseas descartarlos?");
    }
    function sync() {
        const locked=saving||uncertain||staleDraft;
        $("personalSave").disabled=locked||!record;$("personalSave").textContent=saving?"Guardando…":control()?"Guardar expediente":"Guardar mis datos";
        $("personalReload").disabled=saving;$("personalChooseOther").disabled=saving;$("personalMarkReviewed").disabled=saving||dirty||uncertain||staleDraft||!record||record.review.reviewed;
        $("personalDirty").textContent=uncertain?"Guardado sin confirmar":dirty?"Cambios sin guardar":"Datos guardados";
        for(const input of inputs.values())input.disabled=saving;
        form.setAttribute("aria-busy",String(saving));
    }
    function age() {
        const value=inputs.get("birth_date")?.value,output=$("personalAge");if(!output)return;
        const today=record?.identity.age_as_of;
        if(!value||!today||value>today){output.textContent="Se calcula con la fecha de nacimiento";return;}
        const [by,bm,bd]=value.split("-").map(Number),[ty,tm,td]=today.split("-").map(Number);
        output.textContent=(ty-by-(tm<bm||tm===bm&&td<bd?1:0))+" años · al "+fmtDate(today);
    }
    function selectTab(index,focus=false) {
        tab=Math.max(0,Math.min(groups.length-1,index));
        for(let i=0;i<tabs.length;i++){const selected=i===tab;tabs[i].setAttribute("aria-selected",String(selected));tabs[i].tabIndex=selected?0:-1;panels[i].hidden=!selected;}
        $("personalPrevious").hidden=tab===0;$("personalNext").hidden=tab===groups.length-1;
        if(focus)tabs[tab]?.focus();
    }
    function addField(container,definition) {
        const [key,label,max,type="text",autocomplete="off"]=definition;
        const group=create("label",label,"personal-field"),id="personal-"+key;group.htmlFor=id;
        const input=create("input");input.id=id;input.name=key;input.autocomplete=autocomplete;input.type=type;input.maxLength=max;
        if(key==="full_name")input.required=true;
        if(key==="birth_date"){input.max=record.identity.age_as_of;input.min=String(Number(record.identity.age_as_of.slice(0,4))-120)+record.identity.age_as_of.slice(4);}
        if(key==="curp"){input.pattern="[A-Z][AEIOUX][A-Z]{2}[0-9]{6}[HM][A-Z]{5}[A-Z0-9][0-9]";input.spellcheck=false;input.autocapitalize="characters";input.addEventListener("input",()=>{input.value=input.value.toUpperCase();});}
        if(key==="previous_graduation_year"){input.inputMode="numeric";input.pattern="[0-9]{4}";}
        input.value=key==="full_name"?record.student.full_name:key==="curp"||key==="birth_date"?record.identity[key]||"":record.details[key]||"";
        group.append(input);container.append(group);inputs.set(key,input);
        if(key==="curp")group.append(create("small","Si todavía no la conoces, puedes dejarla pendiente y completar los demás datos."));
    }
    function readonly(container,label,value,id) {
        const group=create("div",undefined,"personal-field");group.append(create("span",label));const out=create("output",value||"Sin registrar");if(id)out.id=id;group.append(out);container.append(group);return out;
    }
    function render() {
        inputs.clear();panels.length=0;tabs.length=0;$("personalTabs").replaceChildren();$("personalGroups").replaceChildren();
        $("personalStudentName").textContent=record.student.full_name;$("personalAccount").textContent=(record.student.active?"Alumno activo":"Alumno inactivo · expediente conservado")+" · "+(record.school.student_number||"Matrícula pendiente");
        $("personalReviewState").textContent=record.review.reviewed?"Revisado por Control Escolar"+(record.review.reviewer?" · "+record.review.reviewer:"")+" · "+fmtDate(record.review.reviewed_at):record.updated_at?"Pendiente de revisión por Control Escolar":"Por completar";
        $("personalProgressText").textContent="Datos básicos guardados: "+record.completion.completed+" de 9";$("personalProgress").value=record.completion.completed;
        $("personalMissing").replaceChildren(...record.completion.missing.map(label=>create("li",label)));if(!record.completion.missing.length)$("personalMissing").append(create("li","Los datos básicos sugeridos están capturados."));
        for(let i=0;i<groups.length;i++) {
            const group=groups[i],t=button(group.title,()=>selectTab(i)),panel=create("fieldset",undefined,"personal-tabpanel"),fields=create("div",undefined,"personal-fields");
            t.id="personalTab"+i;t.setAttribute("role","tab");t.setAttribute("aria-controls","personalPanel"+i);
            panel.id="personalPanel"+i;panel.setAttribute("role","tabpanel");panel.setAttribute("aria-labelledby",t.id);panel.append(create("legend",group.title),create("p",group.help,"personal-group-help"),fields);
            for(const field of group.fields)addField(fields,field);
            if(i===0)readonly(fields,"Edad calculada",null,"personalAge");
            if(i===1)readonly(fields,"Correo de acceso · no se modifica aquí",record.student.login_email);
            if(i===5){readonly(fields,"Matrícula",record.school.student_number);readonly(fields,"Fecha de ingreso",fmtDate(record.school.entered_on));readonly(fields,"Fecha de egreso",fmtDate(record.school.completed_on));readonly(fields,"Inscripciones en el historial",String(record.school.enrollments));
                const trajectory=create("div",undefined,"personal-readonly");trajectory.append(create("strong","Etapas y semestres por periodo"));for(const r of record.school.formation_history||[])trajectory.append(create("p",r.period_name+" · "+r.stage_name+" · Semestre "+r.semester+" de "+r.semesters));if(!record.school.formation_history?.length)trajectory.append(create("p","Control Escolar todavía no ha asignado tu etapa y semestre."));fields.append(trajectory);
                const programs=create("div",undefined,"personal-readonly");programs.append(create("strong","Programas vinculados"));for(const p of record.school.programs)programs.append(create("p",p.name+" · "+p.plan_name));if(!record.school.programs.length)programs.append(create("p","Control Escolar todavía no ha clasificado tus inscripciones por programa."));fields.append(programs);
                if(control())fields.append(button("Abrir kardex de este alumno",()=>window.PortalKardex?.requestStudent(target)));else fields.append(button("Ver mis cursos",()=>{location.hash="mis-materias";}));}
            tabs.push(t);panels.push(panel);$("personalTabs").append(t);$("personalGroups").append(panel);
        }
        baseline=JSON.stringify(payload());dirty=false;uncertain=false;staleDraft=false;$("personalReviewTools").hidden=!control();$("personalEditor").hidden=false;$("personalLookup").hidden=true;$("personalChooseOther").hidden=!control();age();selectTab(tab);sync();
    }
    async function load(id,restore) {
        if(!profile||!opened||!uuid.test(id))return;const g=generation,op=++operation;target=id;record=undefined;dirty=false;uncertain=false;staleDraft=false;inputs.clear();panels.length=0;tabs.length=0;$("personalGroups").replaceChildren();$("personalTabs").replaceChildren();$("personalEditor").hidden=true;note("Consultando expediente…");sync();
        try {const data=await rpc("portal_student_record_read",{p_resource:"record",p_student:id});if(!profile||!opened||g!==generation||op!==operation)return;if(!valid(data,id)||data.can_review!==control())throw new Error("Expediente inválido");record=data;render();
            if(restore?.values){for(const [key,input] of inputs)input.value=Object.hasOwn(restore.values,key)?restore.values[key]:restore.values.details[key]||"";dirty=JSON.stringify(payload())!==baseline;staleDraft=dirty&&restore.token!==record.token;tab=restore.tab;selectTab(tab);age();sync();note(staleDraft?"Tu borrador se conservó, pero el expediente cambió. Copia los cambios que necesites y actualiza antes de guardar.":dirty?"Se conservaron tus cambios sin guardar al volver al portal.":"El expediente ya contiene los datos de tu borrador.",staleDraft?"error":"");}
            else note("Expediente actualizado.","success");resume=undefined;
        } catch(error){if(profile&&g===generation&&op===operation&&!forbidden(error))note(errorText(error),"error");}
    }
    async function search(reset=true) {
        if(!profile||!opened||!control())return;const g=generation,op=++operation;if(reset){offset=0;$("personalStudents").replaceChildren();}$("personalMore").disabled=true;note("Buscando alumnos…");
        try {const data=await rpc("portal_student_record_read",{p_resource:"students",p_search:$("personalSearch").value.trim(),p_offset:offset,p_limit:30});if(!profile||!opened||g!==generation||op!==operation)return;if(!Array.isArray(data.items)||data.items.length>30||typeof data.has_more!=="boolean")throw new Error("Lista inválida");
            for(const p of data.items){if(!uuid.test(p.id)||typeof p.full_name!=="string")throw new Error("Alumno inválido");const li=create("li"),info=create("div");info.append(create("strong",p.full_name),create("p",(p.student_number||"Matrícula pendiente")+" · "+(p.active?"Activo":"Inactivo")));li.append(info,button("Abrir expediente",()=>{if(acceptDiscard()){tab=0;void load(p.id);}}));$("personalStudents").append(li);}
            offset+=data.items.length;$("personalMore").hidden=!data.has_more;note(offset?offset+" alumnos mostrados.":"No hay alumnos que coincidan.");
        } catch(error){if(profile&&g===generation&&op===operation&&!forbidden(error))note(errorText(error),"error");}
        finally {if(g===generation&&op===operation)$("personalMore").disabled=false;}
    }
    function validation() {
        for(const [key,input] of inputs)if(!input.checkValidity()){selectTab(groups.findIndex(group=>group.fields.some(field=>field[0]===key)));input.reportValidity();return false;}
        return true;
    }
    async function mutate(review=false) {
        if(!profile||!opened||!record||saving||uncertain||staleDraft||review&&!control()||!review&&!validation())return;
        if(review&&dirty){note("Guarda tus cambios antes de marcar el expediente como revisado.","error");return;}
        const g=generation,op=operation,id=target;const args={p_student:id,p_token:record.token};if(!review)args.p_data=payload();saving=true;sync();note(review?"Registrando revisión…":"Guardando datos…");
        try {const data=await rpc(review?"portal_student_record_review":"portal_student_record_save",args);if(!profile||!opened||g!==generation||op!==operation)return;if(data.saved!==true||!valid(data,id)||data.can_review!==control())throw new Error("Guardado sin confirmar");record=data;render();
            window.dispatchEvent(new CustomEvent("portal-personal-updated",{detail:{id:target,full_name:data.student.full_name}}));note(review?"Control Escolar marcó los datos actuales como revisados.":"Datos guardados y vinculados a tu expediente y kardex. Los documentos ya emitidos conservan su contenido original.","success");
        } catch(error){if(!profile||g!==generation||op!==operation||forbidden(error))return;if(["22023","PT409"].includes(error?.code)){if(error.code==="PT409")staleDraft=true;note(errorText(error),"error");if(error.code==="22023"&&/CURP|nacimiento|fecha/i.test(error.message))selectTab(0);}else{uncertain=true;note("No se pudo confirmar el guardado. Tus campos se conservan. Pulsa Actualizar datos para comprobar lo que quedó guardado antes de repetir la operación.","error");}}
        finally {if(g===generation&&op===operation){saving=false;sync();}}
    }
    function navigate(route) {
        const allowed=profile&&(profile.role==="student"&&route==="mi-perfil"||control()&&route==="expedientes");
        if(!allowed){if(opened)leave();return;}
        if(opened)return;opened=true;currentRoute=route;section.hidden=false;$("personalRecordTitle").textContent=control()?"Expedientes de alumnos":"Mis datos personales";
        $("personalRecordIntro").textContent=control()?"Consulta y revisa el expediente vinculado a cada alumno, sus inscripciones y su kardex.":"Completa tus datos por secciones. Puedes guardar aunque falte información.";
        const restore=resume?.route===route?resume:undefined;tab=restore?.tab||0;
        if(control()) {if(pendingTarget||restore?.target){const id=pendingTarget||restore.target;pendingTarget=undefined;void load(id,restore?.target===id?restore:undefined);}else{$("personalLookup").hidden=false;$("personalChooseOther").hidden=true;void search();}}
        else void load(profile.id,restore);
    }
    form.addEventListener("input",()=>{if(!record)return;dirty=JSON.stringify(payload())!==baseline;age();sync();});
    form.addEventListener("submit",event=>{event.preventDefault();void mutate();});
    $("personalMarkReviewed").addEventListener("click",()=>void mutate(true));
    $("personalPrevious").addEventListener("click",()=>selectTab(tab-1,true));$("personalNext").addEventListener("click",()=>selectTab(tab+1,true));
    $("personalTabs").addEventListener("keydown",event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();selectTab(event.key==="Home"?0:event.key==="End"?groups.length-1:tab+(event.key==="ArrowRight"?1:-1),true);});
    $("personalSearchForm").addEventListener("submit",event=>{event.preventDefault();void search();});$("personalMore").addEventListener("click",()=>void search(false));
    $("personalReload").addEventListener("click",()=>{if(!acceptDiscard())return;resume=undefined;if(target)void load(target);else void search();});
    $("personalChooseOther").addEventListener("click",()=>{if(!acceptDiscard())return;operation++;record=undefined;target=undefined;dirty=false;inputs.clear();$("personalGroups").replaceChildren();$("personalEditor").hidden=true;$("personalLookup").hidden=false;$("personalChooseOther").hidden=true;void search();});
    window.addEventListener("beforeunload",event=>{if(opened&&(dirty||saving)){event.preventDefault();event.returnValue="";}});
    window.PortalPersonalRecord=Object.freeze({clear,navigate,discardDraft(){resume=undefined;},canNavigate(route){return !opened||route===currentRoute||acceptDiscard();},show(value,verify){clear();if(resume&&(resume.user!==value.id||resume.role!==value.role))resume=undefined;profile=["student","control_escolar"].includes(value.role)?value:undefined;recheck=verify;$("personalProfileLink").textContent=value.role==="student"?"Completar mis datos personales":"Ver mi perfil";if(!profile)resume=undefined;},requestStudent(id){if(!control()||!uuid.test(id)||!acceptDiscard())return;if(opened){tab=0;void load(id);}else{pendingTarget=id;location.hash="expedientes";}}});
})();
