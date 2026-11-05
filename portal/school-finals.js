(function () {
    "use strict";
    const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    let generation=0,controller,dialog,context,host,source,busy=false;
    const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
    const button=(text,run,primary=false)=>{const b=el('button',text,'back-link'+(primary?' control-create':''));b.type='button';b.addEventListener('click',run);return b;};
    function close(){if(dialog){dialog.close();dialog.remove();dialog=undefined;}}
    function clear(){generation++;controller?.abort();controller=undefined;close();host?.classList.remove("school-finals");context=host=source=undefined;busy=false;}
    function message(text,error=false){if(!host)return;const n=host.querySelector('.school-final-status');if(n){n.textContent=text;n.className='school-final-status control-message'+(error?' error':'');}}
    function errorText(e){return ['22023','PT409'].includes(e?.code)?e.message:['PGRST202','42883','42P01'].includes(e?.code)?'Falta instalar la actualización de Control Escolar en Supabase.':'No se confirmó la respuesta. Actualiza para comprobar las notas antes de volver a publicar.';}
    async function rpc(name,args){controller=new AbortController();const r=await window.PortalAuth.getClient().rpc(name,args).retry(false).abortSignal(controller.signal);if(r.error)throw {...r.error,status:r.status};return r.data;}
    function valid(data){return data?.course?.id===context.courseId&&/^[a-f0-9]{32}$/.test(data.token)&&Array.isArray(data.students)&&data.students.length<=500&&data.students.every(s=>uuid.test(s.enrollment_id)&&typeof s.name==='string'&&[s.published_score,s.draft_score].every(x=>x===null||typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=100));}
    async function reload(notice=''){
        if(!host||!context)return;const operation=++generation;controller?.abort();close();source=undefined;host.replaceChildren(el('p','Cargando alumnos y finales…','school-final-status control-message'));
        try{const data=await rpc('portal_school_finals_read',{p_course:context.courseId});if(operation!==generation)return;if(!valid(data))throw new Error('Respuesta inválida');source=data;draw();message(notice);}
        catch(e){if(operation!==generation||context?.onUnauthorized(e))return;message(errorText(e),true);host.append(button('Actualizar',()=>void reload()));}
    }
    function draw(){
        const heading=el('div',undefined,'school-final-heading'),title=el('div');title.append(el('h2','Calificación final'),el('p',source.course.name+' · '+source.course.period_name));heading.append(title,button('Actualizar notas',()=>void reload()));
        host.replaceChildren(heading,el('p','Captura las notas finales proporcionadas por el docente. Al confirmar, se publican en el historial y las boletas. Las actividades y ponderaciones se conservan.'),el('p','Escala de 0 a 10. Un espacio vacío conserva la nota actual.','learning-meta'));
        const status=el('p','','school-final-status control-message');status.setAttribute('role','status');host.append(status);
        if(!source.students.length){message('No hay alumnos activos inscritos en esta clase.');return;}
        const form=el('form',undefined,'school-final-form'),scroll=el('div',undefined,'learning-table-scroll school-final-scroll'),table=el('table',undefined,'learning-grades-table'),head=el('thead'),row=el('tr'),body=el('tbody'),inputs=[];
        for(const label of ['Seminarista','Matrícula','Final publicada','Final a publicar'])row.append(el('th',label));head.append(row);table.append(head,body);scroll.append(table);
        for(const s of source.students){const tr=el('tr'),name=el('th',s.name),cell=el('td'),input=el('input');name.scope='row';input.type='number';input.min='0';input.max='10';input.step='0.1';input.inputMode='decimal';input.setAttribute('aria-label','Calificación final de '+s.name);
            const score=s.published_score??s.draft_score;input.value=score===null?'':window.PortalGradeScale.format(score);input.dataset.enrollment=s.enrollment_id;cell.append(input);
            tr.append(name,el('td',s.student_number||'Pendiente'),el('td',s.published_score===null?'Pendiente':window.PortalGradeScale.format(s.published_score)),cell);body.append(tr);inputs.push({student:s,input});}
        const reasonLabel=el('label','Motivo de la captura o corrección'),reason=el('textarea');reason.rows=2;reason.maxLength=1000;reason.value='Captura final proporcionada por el docente';reasonLabel.append(reason);
        const submit=el('button','Revisar y publicar finales','back-link control-create');submit.type='submit';form.append(scroll,reasonLabel,submit);host.append(form);
        form.addEventListener('submit',event=>{event.preventDefault();if(busy||!form.reportValidity())return;const changes=[];
            for(const {student:s,input} of inputs){if(input.value==='')continue;const shown=s.published_score===null?'':window.PortalGradeScale.format(s.published_score);if(input.value===shown)continue;
                let score;try{score=window.PortalGradeScale.toWire(input.value,s.published_score);}catch(error){message(error.message,true);input.focus();return;}if(!Number.isFinite(score))return;changes.push({enrollment_id:s.enrollment_id,score,name:s.name,before:s.published_score});}
            if(!changes.length){message('No hay calificaciones nuevas o modificadas.');return;}review(changes,reason.value.trim());});
    }
    function review(changes,reason){
        close();const operation=generation,token=source.token,courseId=context.courseId,d=el('dialog',undefined,'learning-dialog school-final-dialog');dialog=d;
        const title=el('h2','Confirmar finales de '+source.course.name);title.id='schoolFinalConfirmTitle';d.setAttribute('aria-labelledby',title.id);
        const list=el('ul',undefined,'school-final-review');for(const c of changes)list.append(el('li',c.name+': '+(c.before===null?'Pendiente':window.PortalGradeScale.format(c.before))+' → '+window.PortalGradeScale.format(c.score)));
        const confirmLabel=el('label',undefined,'school-confirm'),confirm=el('input');confirm.type='checkbox';confirmLabel.append(confirm,el('span','He revisado las notas y confirmo su publicación como calificaciones finales.'));
        const status=el('p','','control-message');status.setAttribute('role','status');let reloadOnClose=false;const save=button('Publicar '+changes.length+' finales',()=>void publish(),true),cancel=button('Volver',()=>{if(!busy){close();if(reloadOnClose)void reload();}});save.disabled=true;
        confirm.addEventListener('change',()=>{save.disabled=!confirm.checked||busy;});d.append(title,el('p',source.course.period_name),list,confirmLabel,status,el('div'));d.lastChild.append(save,cancel);d.addEventListener('cancel',e=>{if(busy)e.preventDefault();else {close();if(reloadOnClose)void reload();}});document.body.append(d);d.showModal();confirm.focus();
        async function publish(){
            if(busy||!confirm.checked||generation!==operation)return;busy=true;save.disabled=cancel.disabled=confirm.disabled=true;status.textContent='Publicando finales…';
            try{const data=await rpc('portal_school_finals_save',{p_course:courseId,p_token:token,p_items:changes.map(({enrollment_id,score})=>({enrollment_id,score})),p_reason:reason});
                if(generation!==operation||dialog!==d)return;if(data?.saved!==true||!valid(data))throw new Error('Sin confirmación');busy=false;close();await reload('Calificaciones finales publicadas. Ya están disponibles para sus boletas.');}
            catch(e){if(generation!==operation||context?.onUnauthorized(e))return;status.textContent=errorText(e);status.className='control-message error';reloadOnClose=true;cancel.textContent='Cerrar y actualizar';}
            finally{if(generation===operation&&dialog===d){busy=false;cancel.disabled=false;/* La publicación incierta requiere una lectura nueva. */}}
        }
    }
    async function render(target,ctx){clear();host=target;host.classList.add("school-finals");context=ctx;await reload();}
    window.PortalSchoolFinals=Object.freeze({clear,render});
})();
