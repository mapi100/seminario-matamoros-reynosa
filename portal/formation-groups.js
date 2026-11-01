(function () {
    "use strict";
    const $=id=>document.getElementById(id), uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const stages=[['introductorio','Introductorio',2,'CI'],['filosofia','Filosofía',6,'F'],['teologia','Teología',8,'T']];
    const groups=stages.flatMap(([stage,name,count,prefix])=>Array.from({length:count},(_,i)=>({stage,name,semester:i+1,code:(prefix==='CI'?'CI':Math.ceil((i+1)/2)+prefix)+'-'+(i+1)})));
    const node=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;};
    const button=(text,run,cls='back-link')=>{const b=node('button',text,cls);b.type='button';b.addEventListener('click',run);return b;};
    const norm=text=>String(text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('es');
    const compare=(a,b)=>a.full_name.localeCompare(b.full_name,'es')||a.id.localeCompare(b.id);
    const code=row=>groups.find(g=>g.stage===row.stage_code&&g.semester===row.semester)?.code||'';
    let period, snapshot, selectedCode='', generation=0, verify, changed, dialog, dialogBusy=false, focusBack;
    const controllers=new Set();
    function status(text,error=false){$('formationGroupStatus').textContent=text;$('formationGroupStatus').className='control-message'+(error?' error':'');}
    async function rpc(name,args){const c=new AbortController();controllers.add(c);try{
        const r=await window.PortalAuth.getClient().rpc(name,args).retry(false).abortSignal(c.signal);
        if(r.error)throw {...r.error,status:r.status};return r.data;
    }finally{controllers.delete(c);}}
    function close(force=false){if(dialogBusy&&!force)return;const d=dialog;dialog=undefined;dialogBusy=false;if(d){d.close();d.remove();}if(!force&&focusBack?.isConnected)focusBack.focus();focusBack=undefined;}
    function clear(){generation++;for(const c of controllers)c.abort();controllers.clear();close(true);period=undefined;snapshot=undefined;verify=changed=undefined;
        $('formationStages').replaceChildren();$('formationGroupContent').replaceChildren();status('');}
    function valid(data){
        if(data?.period_id!==period||typeof data.token!=='string'||!/^[a-f0-9]{32}$/.test(data.token)||!Array.isArray(data.students)||!Array.isArray(data.classes)||!Array.isArray(data.enrollments))return false;
        if(data.students.length>10000||data.classes.length>5000||data.enrollments.length>100000)return false;
        if(data.students.some(r=>!uuid.test(r.id)||typeof r.full_name!=='string'||!Number.isInteger(r.revision)||r.revision<0||(r.stage_code!==null&&!code(r))))return false;
        if(data.classes.some(r=>!uuid.test(r.id)||typeof r.name!=='string'||!groups.some(g=>g.code===r.group_code)||!Number.isInteger(r.revision)))return false;
        const students=new Set(data.students.map(r=>r.id)),classes=new Set(data.classes.map(r=>r.id)),pairs=new Set();
        if(students.size!==data.students.length||classes.size!==data.classes.length)return false;
        return data.enrollments.every(r=>{const key=r.class_id+':'+r.student_id;if(!students.has(r.student_id)||!classes.has(r.class_id)||typeof r.active!=='boolean'||pairs.has(key))return false;pairs.add(key);return true;});
    }
    function errorText(e){return ['PGRST202','42883','42P01'].includes(e?.code)?'Falta instalar el SQL de grupos en Supabase. La consulta individual sigue disponible.':
        ['PT409','22023'].includes(e?.code)?e.message:'No se pudo cargar el grupo. Pulsa Actualizar para reintentar.';}
    function denied(e){if(e?.code==='42501'||[401,403].includes(e?.status)){const v=verify;clear();void v?.();return true;}return false;}
    function members(g){return snapshot.students.filter(r=>code(r)===g.code).sort(compare);}
    function courses(g){return snapshot.classes.filter(r=>r.group_code===g.code).sort((a,b)=>a.name.localeCompare(b.name,'es')||a.id.localeCompare(b.id));}
    function paint(){
        const grid=$('formationStages');grid.replaceChildren();
        for(const [stage,name] of stages){const col=node('div',undefined,'formation-group-column');col.append(node('h3',name));const tiles=node('div',undefined,'formation-group-tiles');
            for(const g of groups.filter(x=>x.stage===stage)){const b=button('',()=>{selectedCode=g.code;paint();});b.classList.add('formation-group-tile');b.dataset.group=g.code;b.setAttribute('aria-pressed',String(selectedCode===g.code));
                b.append(node('strong',g.code),node('small',members(g).length+' seminaristas · '+courses(g).length+' materias'));tiles.append(b);}col.append(tiles);grid.append(col);}
        const target=$('formationGroupContent');target.replaceChildren();const unassigned=snapshot.students.filter(r=>!code(r)).length;
        const g=groups.find(x=>x.code===selectedCode);
        if(!g){target.append(node('p','Elige un curso para ver sus seminaristas y materias. '+unassigned+' sin curso asignado en este periodo.'));return;}
        const people=members(g),classes=courses(g),head=node('div',undefined,'formation-group-heading'),title=node('div');
        title.append(node('h3',g.code+' · '+g.name),node('p',people.length+' seminaristas · '+classes.length+' materias activas'));
        const actions=node('div',undefined,'formation-group-actions');actions.append(button('Agregar seminaristas',()=>openDialog('assign',g),'back-link control-create'));
        const enroll=button('Inscribir en materias',()=>openDialog('enroll',g));enroll.disabled=!people.length||!classes.length;actions.append(enroll);head.append(title,actions);target.append(head);
        const corrections=node('div',undefined,'formation-group-actions');
        const removePeople=button('Quitar seminaristas',()=>openRemove('students',g),'back-link formation-group-danger');removePeople.disabled=!people.length;
        const removeClasses=button('Quitar materias',()=>openRemove('classes',g),'back-link formation-group-danger');removeClasses.disabled=!classes.length;corrections.append(removePeople,removeClasses);target.append(corrections);
        const list=node('ul',undefined,'formation-group-members');for(const r of people)list.append(node('li',r.full_name));
        if(people.length)target.append(list);else target.append(node('p','Este curso aún no tiene seminaristas. Usa Agregar seminaristas.'));
        if(!classes.length)target.append(node('p','Organiza las materias de este curso y periodo en Materias y periodos para poder inscribir al grupo.'));
        if(classes.length){const details=node('details'),summary=node('summary','Ver materias del curso ('+classes.length+')'),ul=node('ul');for(const c of classes)ul.append(node('li',c.name));details.append(summary,ul);target.append(details);}
    }
    async function show(value,recheck,onChanged){clear();if(!uuid.test(value))return;period=value;verify=recheck;changed=onChanged;const g=generation;status('Consultando grupos…');
        try{const data=await rpc('portal_formation_group_read',{p_period:period});if(g!==generation||!period)return;if(!valid(data))throw new Error('Grupo inválido');snapshot=data;paint();status(snapshot.students.length+' seminaristas activos. Selecciona su curso; las etapas se guardan por periodo.');}
        catch(e){if(g===generation&&!denied(e))status(errorText(e),true);}
    }
    function openDialog(action,g){
        if(!snapshot||dialog)return;focusBack=document.activeElement;const gen=generation,data=snapshot,scope=period,periodName=$('formationPeriod').selectedOptions[0]?.textContent||'';
        const people=action==='assign'?[...data.students].sort((a,b)=>Number(!!code(a))-Number(!!code(b))||compare(a,b)):members(g);
        const classes=courses(g),chosen=new Set(action==='enroll'?people.map(r=>r.id):[]),chosenClasses=new Set(action==='enroll'?classes.map(r=>r.id):[]);
        let refreshOnClose=false;
        function cancelDialog(){if(dialogBusy)return;const v=verify,cb=changed;close();if(refreshOnClose){void show(scope,v,cb);void cb?.();}}
        const d=node('dialog',undefined,'management-dialog formation-group-dialog');dialog=d;d.setAttribute('aria-labelledby','formationGroupDialogTitle');
        const title=node('h2',(action==='assign'?'Agregar seminaristas a ':'Inscribir en materias de ')+g.code);title.id='formationGroupDialogTitle';
        const subtitle=node('p',periodName+' · '+g.name+' · Semestre '+g.semester),body=node('div'),review=node('div'),message=node('p',undefined,'control-message');message.setAttribute('role','status');
        const filters=node('div',undefined,'formation-group-filters'),filterLabel=node('label','Curso actual'),filter=node('select');filter.id='formationGroupFilter';
        filter.append(new Option('Todos los cursos','all'),new Option('Sin curso asignado',''));
        for(const group of groups)filter.append(new Option(group.code,group.code));filter.value=action==='assign'&&people.some(r=>!code(r))?'':'all';filterLabel.append(filter);
        const searchLabel=node('label','Buscar por nombre o matrícula'),search=node('input');search.type='search';search.placeholder='Buscar seminarista';search.id='formationGroupSearch';searchLabel.append(search);
        if(action==='assign')filters.append(filterLabel);filters.append(searchLabel);body.append(filters);
        const count=node('p');count.id='formationGroupSelectionCount';
        const list=node('ul',undefined,'formation-group-checklist');list.id='formationGroupPeople';
        const controls=node('div',undefined,'formation-group-actions'),selectAll=button('Seleccionar resultados',()=>{for(const p of visible())if(action==='enroll'||code(p)!==g.code)chosen.add(p.id);invalidate();paintPeople();}),none=button('Quitar selección',()=>{chosen.clear();invalidate();paintPeople();});controls.append(selectAll,none);
        body.append(controls,count,list);
        const classesList=node('ul',undefined,'formation-group-checklist');classesList.id='formationGroupClasses';
        const reactivate=node('input');reactivate.type='checkbox';reactivate.id='formationGroupReactivate';
        if(action==='enroll'){
            body.append(node('h3','Materias que recibirán al grupo'),node('p','Puedes desmarcar seminaristas o materias para hacer excepciones.'));
            for(const c of classes){const li=node('li'),label=node('label'),check=node('input');check.type='checkbox';check.value=c.id;check.checked=true;check.addEventListener('change',()=>{check.checked?chosenClasses.add(c.id):chosenClasses.delete(c.id);invalidate();});label.append(check,node('span',c.name));li.append(label);classesList.append(li);}body.append(classesList);
            const restore=node('label',undefined,'formation-group-restore');restore.append(reactivate,node('span','Reactivar también las inscripciones dadas de baja (conservarán sus calificaciones)'));body.append(restore);
            reactivate.addEventListener('change',invalidate);
        }else body.append(node('p','Los seminaristas de otro curso se moverán solo en este periodo. Sus inscripciones actuales no se modifican.'));
        const actions=node('div',undefined,'dialog-actions'),next=button('Revisar cambios',prepare,'back-link control-create'),back=button('Volver a la selección',()=>{body.hidden=false;review.hidden=true;next.hidden=false;back.hidden=confirm.hidden=true;message.textContent='';next.focus();}),confirm=button('Confirmar',()=>void save(),'back-link control-create'),cancel=button('Cancelar',cancelDialog);
        next.id='formationGroupReview';confirm.id='formationGroupConfirm';cancel.id='formationGroupCancel';back.hidden=confirm.hidden=review.hidden=true;
        actions.append(next,back,confirm,cancel);d.append(title,subtitle,body,review,message,actions);document.body.append(d);
        function visible(){const needle=norm(search.value);return people.filter(p=>(action==='enroll'||filter.value==='all'||code(p)===filter.value)&&(!needle||norm(p.full_name+' '+(p.student_number||'')).includes(needle)));}
        function invalidate(){review.hidden=true;body.hidden=false;next.hidden=false;back.hidden=confirm.hidden=true;message.textContent='';next.disabled=!chosen.size||(action==='enroll'&&!chosenClasses.size);}
        function paintPeople(){list.replaceChildren();const rows=visible();for(const p of rows){const li=node('li'),label=node('label'),check=node('input');check.type='checkbox';check.value=p.id;check.checked=chosen.has(p.id);check.disabled=action==='assign'&&code(p)===g.code;
                check.addEventListener('change',()=>{check.checked?chosen.add(p.id):chosen.delete(p.id);invalidate();paintPeople();});const info=node('span');info.append(node('strong',p.full_name),node('small',code(p)?code(p)+(code(p)===g.code?' · Ya pertenece al curso':' → '+g.code):'Sin curso asignado → '+g.code));label.append(check,info);li.append(label);list.append(li);}
            if(!rows.length)list.append(node('li','No hay seminaristas que coincidan con estos filtros.'));
            const hidden=[...chosen].filter(id=>!rows.some(p=>p.id===id)).length;
            count.textContent=chosen.size+' seleccionados · '+rows.length+' mostrados'+(hidden?' · '+hidden+' seleccionados fuera del filtro':'');
            next.disabled=!chosen.size||(action==='enroll'&&!chosenClasses.size);
        }
        function totals(){let added=0,existing=0,inactive=0;const map=new Map(data.enrollments.map(r=>[r.class_id+':'+r.student_id,r.active]));for(const c of chosenClasses)for(const s of chosen){const key=c+':'+s;if(!map.has(key))added++;else if(map.get(key))existing++;else inactive++;}return {added,existing,inactive};}
        function prepare(){
            if(!chosen.size||(action==='enroll'&&!chosenClasses.size))return;review.replaceChildren();message.textContent='';
            if(chosen.size>500||chosenClasses.size>100||action==='enroll'&&chosen.size*chosenClasses.size>5000){message.textContent='Reduce la selección: máximo 500 seminaristas, 100 materias y 5000 inscripciones por lote.';return;}
            review.append(node('h3','Revisa antes de guardar'),node('p',periodName+' · '+g.code));
            const peopleSelected=people.filter(p=>chosen.has(p.id));
            if(action==='assign'){const moved=peopleSelected.filter(p=>code(p)&&code(p)!==g.code).length;review.append(node('p',chosen.size+' seminaristas se asignarán a '+g.code+'. '+moved+' cambiarán de curso en este periodo. No se inscribirán en materias todavía.'));}
            else {const t=totals();review.append(node('p',chosen.size+' seminaristas × '+chosenClasses.size+' materias.'),node('p',t.added+' inscripciones nuevas · '+t.existing+' ya existentes (se omiten) · '+t.inactive+(reactivate.checked?' bajas que se reactivarán.':' bajas que se conservarán.')));}
            const ul=node('ul');for(const p of peopleSelected)ul.append(node('li',p.full_name+(action==='assign'?' · '+(code(p)||'Sin curso')+' → '+g.code:'')));review.append(ul);
            if(action==='enroll'){review.append(node('h3','Materias seleccionadas'));const ul=node('ul');for(const c of classes.filter(c=>chosenClasses.has(c.id)))ul.append(node('li',c.name));review.append(ul);}
            body.hidden=true;review.hidden=false;next.hidden=true;back.hidden=confirm.hidden=false;confirm.textContent=action==='assign'?'Guardar curso de '+chosen.size+' seminaristas':'Confirmar inscripciones';confirm.focus();
        }
        async function save(){
            if(dialogBusy||review.hidden||dialog!==d||gen!==generation)return;dialogBusy=true;for(const control of d.querySelectorAll('button,input,select'))control.disabled=true;d.setAttribute('aria-busy','true');message.textContent='Guardando el lote…';
            try{const result=await rpc('portal_formation_group_write',{p_action:action,p_period:scope,p_stage:g.stage,p_semester:g.semester,p_students:[...chosen].sort(),p_classes:action==='enroll'?[...chosenClasses].sort():[],p_reactivate:action==='enroll'&&reactivate.checked,p_token:data.token});
                if(gen!==generation||dialog!==d)return;if(result?.saved!==true||(action==='assign'? !['assigned','unchanged'].every(k=>Number.isInteger(result[k])&&result[k]>=0)||result.assigned+result.unchanged!==chosen.size: !['enrolled','reactivated','already_enrolled','kept_inactive'].every(k=>Number.isInteger(result[k])&&result[k]>=0)||result.enrolled+result.reactivated+result.already_enrolled+result.kept_inactive!==chosen.size*chosenClasses.size))throw new Error('Guardado sin confirmar');
                const v=verify,callback=changed;dialogBusy=false;close();await show(scope,v,callback);if(gen+1!==generation)return;
                status(action==='assign'?result.assigned+' seminaristas asignados; '+result.unchanged+' ya pertenecían al curso.':result.enrolled+' inscripciones nuevas · '+result.reactivated+' reactivadas · '+result.already_enrolled+' ya existentes · '+result.kept_inactive+' bajas conservadas.');
                void callback?.();
            }catch(e){if(gen!==generation||dialog!==d)return;if(denied(e))return;message.textContent=['PT409','22023'].includes(e?.code)?errorText(e):'No se pudo confirmar el guardado. Cierra y actualiza para comprobar el resultado antes de repetir.';
                // No se reenvía un lote incierto ni una revisión que quedó desactualizada.
                dialogBusy=false;refreshOnClose=true;cancel.disabled=false;cancel.textContent='Cerrar y actualizar';
            }finally{if(dialog===d)d.setAttribute('aria-busy','false');}
        }
        d.addEventListener('cancel',event=>{event.preventDefault();cancelDialog();});
        search.addEventListener('input',()=>{invalidate();paintPeople();});filter.addEventListener('change',()=>{invalidate();paintPeople();});
        paintPeople();d.showModal();search.focus();
    }
    function openRemove(kind,g){
        if(!snapshot||dialog)return;
        const rows=kind==='students'?members(g):courses(g);if(!rows.length)return;
        const gen=generation,data=snapshot,scope=period,periodName=$('formationPeriod').selectedOptions[0]?.textContent||'';
        const label=kind==='students'?'seminaristas':'materias',chosen=new Set();
        let refreshOnClose=false;
        focusBack=document.activeElement;
        const d=node('dialog',undefined,'management-dialog formation-group-dialog formation-group-remove');dialog=d;
        d.setAttribute('aria-labelledby','formationGroupRemoveTitle');
        const title=node('h2','Quitar '+label+' de '+g.code);title.id='formationGroupRemoveTitle';
        const scopeText=node('p',periodName+' · '+g.code+' · '+g.name);scopeText.className='formation-removal-scope';
        const help=node('p',kind==='students'?
            'Se quitará su etapa y semestre solo en este periodo. Sus cuentas, expedientes e inscripciones en materias se conservan.':
            'Las materias quedarán sin curso asignado en este periodo. Las clases, profesores, tareas, inscripciones y calificaciones se conservan. Podrás volver a organizarlas en Materias y periodos.');
        const selection=node('div'),filters=node('div',undefined,'formation-group-filters'),searchLabel=node('label','Buscar '+(kind==='students'?'seminarista':'materia')),search=node('input');
        search.type='search';search.id='formationRemoveSearch';search.placeholder='Buscar por nombre';searchLabel.append(search);filters.append(searchLabel);
        const list=node('ul',undefined,'formation-group-checklist');list.id='formationRemoveList';const count=node('p');count.id='formationRemoveCount';
        const controls=node('div',undefined,'formation-group-actions');
        controls.append(button('Seleccionar resultados',()=>{for(const r of visible())chosen.add(r.id);paintList();}),button('Quitar selección',()=>{chosen.clear();paintList();}));
        selection.append(filters,controls,count,list);
        const review=node('div');review.id='formationRemoveReview';review.hidden=true;
        const confirmation=node('div',undefined,'formation-group-filters');confirmation.hidden=true;
        const confirmationLabel=node('label','Escribe CONFIRMAR para continuar'),input=node('input');input.id='formationRemoveConfirmation';input.autocomplete='off';input.spellcheck=false;input.setAttribute('autocapitalize','characters');confirmationLabel.append(input);confirmation.append(confirmationLabel);
        const message=node('p',undefined,'control-message');message.id='formationRemoveStatus';message.setAttribute('role','status');
        const actions=node('div',undefined,'dialog-actions'),next=button('Revisar selección',prepare,'back-link'),back=button('Volver a la selección',()=>{selection.hidden=false;review.hidden=confirmation.hidden=true;next.hidden=false;back.hidden=confirm.hidden=true;input.value='';message.textContent='';next.focus();}),confirm=button('Confirmar y quitar',()=>void save(),'back-link formation-group-danger'),cancel=button('Cancelar',cancelDialog);
        next.id='formationRemoveNext';confirm.id='formationRemoveConfirm';cancel.id='formationRemoveCancel';back.hidden=confirm.hidden=true;confirm.disabled=true;
        actions.append(next,back,confirm,cancel);const scroll=node('div',undefined,'formation-removal-scroll');scroll.append(title,scopeText,help,selection,review,confirmation,message);d.append(scroll,actions);document.body.append(d);
        function cancelDialog(){if(dialogBusy)return;const v=verify,cb=changed;close();if(refreshOnClose){void show(scope,v,cb);void cb?.();}}
        function name(r){return kind==='students'?r.full_name:r.name;}
        function visible(){const needle=norm(search.value);return rows.filter(r=>!needle||norm(name(r)).includes(needle));}
        function paintList(){list.replaceChildren();const current=visible();for(const r of current){const li=node('li'),label=node('label'),check=node('input');check.type='checkbox';check.value=r.id;check.checked=chosen.has(r.id);check.addEventListener('change',()=>{check.checked?chosen.add(r.id):chosen.delete(r.id);paintList();});label.append(check,node('span',name(r)));li.append(label);list.append(li);}
            if(!current.length)list.append(node('li','No hay resultados para esta búsqueda.'));
            const outside=[...chosen].filter(id=>!current.some(r=>r.id===id)).length;
            count.textContent=chosen.size+' seleccionados · '+current.length+' mostrados'+(outside?' · '+outside+' seleccionados fuera del filtro':'');next.disabled=!chosen.size;
        }
        function prepare(){if(!chosen.size)return;
            if(chosen.size>(kind==='students'?500:100)){message.textContent='Selecciona como máximo '+(kind==='students'?500:100)+' registros por lote.';return;}
            review.replaceChildren(node('h3','Confirma el periodo y la selección'),node('p',periodName+' · '+g.code+' · Quitar '+chosen.size+' '+label+' de este bloque.'));
            const ul=node('ul');for(const r of rows.filter(r=>chosen.has(r.id)))ul.append(node('li',name(r)));review.append(ul);
            if(kind==='students'){
                const existing=data.enrollments.filter(e=>chosen.has(e.student_id)&&e.active).length;
                if(existing)review.append(node('p',(existing===1?'Hay 1 inscripción activa de estos seminaristas en el periodo. Seguirá activa;':'Hay '+existing+' inscripciones activas de estos seminaristas en el periodo. Seguirán activas;')+' si también fueron un error, revísalas en Clases o Inscripciones.'));
            }
            review.append(node('p','Los demás periodos conservarán sus asignaciones.'));
            selection.hidden=true;review.hidden=confirmation.hidden=false;next.hidden=true;back.hidden=confirm.hidden=false;input.value='';confirm.disabled=true;message.textContent='';input.focus();
        }
        async function save(){if(dialogBusy||review.hidden||input.value.trim().toUpperCase()!=='CONFIRMAR'||dialog!==d||gen!==generation)return;
            dialogBusy=true;for(const c of d.querySelectorAll('button,input'))c.disabled=true;d.setAttribute('aria-busy','true');message.textContent='Quitando asignaciones del grupo…';
            try{const result=await rpc('portal_formation_group_remove',{p_kind:kind,p_period:scope,p_stage:g.stage,p_semester:g.semester,p_ids:[...chosen].sort(),p_token:data.token,p_confirmation:input.value.trim()});
                if(gen!==generation||dialog!==d)return;if(result?.saved!==true||result.kind!==kind||result.period_id!==scope||result.group_code!==g.code||result.removed!==chosen.size)throw new Error('Corrección sin confirmar');
                const v=verify,cb=changed;dialogBusy=false;close();await show(scope,v,cb);if(gen+1!==generation)return;
                status(result.removed+' '+label+' retirados de '+g.code+' en '+periodName+'. Las demás asignaciones se conservan.');if(kind==='classes')void window.PortalCourseGroups?.reload();void cb?.();
            }catch(e){if(gen!==generation||dialog!==d)return;if(denied(e))return;
                message.textContent=['PGRST202','42883'].includes(e?.code)?'Falta instalar el SQL para quitar asignaciones de los grupos.':
                    ['22023','PT409'].includes(e?.code)?e.message:'No se pudo confirmar la corrección. Cierra y actualiza para comprobar el resultado antes de repetir.';
                dialogBusy=false;refreshOnClose=true;cancel.disabled=false;cancel.textContent='Cerrar y actualizar';
            }finally{if(dialog===d)d.setAttribute('aria-busy','false');}
        }
        input.addEventListener('input',()=>{confirm.disabled=input.value.trim().toUpperCase()!=='CONFIRMAR';});
        search.addEventListener('input',paintList);d.addEventListener('cancel',event=>{event.preventDefault();cancelDialog();});
        paintList();d.showModal();search.focus();
    }
    window.PortalFormationGroups=Object.freeze({show,clear});
})();
