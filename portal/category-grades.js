(function () {
    'use strict';
    const codes=['tasks','exams','projects','participation'],labels={tasks:'Tareas',exams:'Exámenes',projects:'Proyectos',participation:'Participación'};
    let state,version=0,dialog,busy=false,controller;
    const el=(tag,value,cls)=>{const n=document.createElement(tag);if(value!==undefined)n.textContent=value;if(cls)n.className=cls;return n;};
    const button=(label,action,primary=false)=>{const b=el('button',label,'learning-button'+(primary?'':' secondary'));b.type='button';b.addEventListener('click',action);return b;};
    const format=value=>typeof value==='number'?window.PortalGradeScale.format(value):'Pendiente';
    function close(force=false){if(busy&&!force)return;if(dialog){dialog.close();dialog.remove();dialog=undefined;}}
    function clear(){version++;controller?.abort();close(true);state?.target.classList.remove("category-book");state=undefined;busy=false;}
    function note(message,error=false){if(!state)return;state.status.textContent=message;state.status.className='learning-status'+(error?' error':'');}
    function errorText(e){if(e?.code==='PT409')return 'Las notas o los porcentajes cambiaron. Cierra y actualiza el libro antes de continuar.';if(['PGRST202','42883','42P01'].includes(e?.code)||e?.message==='Acción inválida')return 'Falta instalar la actualización de captura por categorías en Supabase.';if(e?.code==='22023')return window.PortalTerms.seminarian(e.message);return 'No se confirmó la respuesta. Cierra y actualiza el libro para comprobar el resultado antes de volver a guardar.';}
    async function write(action,data){controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);try{const r=await window.PortalAuth.getClient().rpc('portal_gradebook_write',{p_course:state.ctx.courseId,p_action:action,p_data:data}).retry(false).abortSignal(controller.signal);if(r.error)throw {...r.error,status:r.status};if(r.data?.saved!==true)throw Error('Sin confirmación');return r.data;}finally{clearTimeout(timer);}}
    function modal(title){
        close();const d=el('dialog',undefined,'learning-dialog category-dialog'),h=el('h2',title);h.id='categoryDialogTitle';d.setAttribute('aria-labelledby',h.id);d.append(h);document.body.append(d);dialog=d;
        const form=el('form'),fields=el('div'),status=el('p','','learning-status'),actions=el('div',undefined,'category-actions');status.setAttribute('role','status');form.append(fields,status,actions);d.append(form);
        d.addEventListener('cancel',e=>{e.preventDefault();close();});return {d,form,fields,status,actions};
    }
    function number(label,value,grade=true){const i=el('input');i.type='number';i.min='0';i.max=grade?'10':'100';i.step=grade?'0.1':'0.01';i.value=value??'';i.inputMode='decimal';i.setAttribute('aria-label',label);return i;}
    function checkbox(label){const l=el('label',undefined,'category-confirm'),i=el('input');i.type='checkbox';l.append(i,el('span',label));return {label:l,input:i};}
    async function submit(form,action,payload){
        if(busy||form.locked||!form.form.reportValidity())return;const v=version;busy=true;for(const b of form.actions.querySelectorAll('button'))b.disabled=true;form.status.textContent='Guardando…';
        try{await write(action,payload);if(v!==version)return;busy=false;close();await state.ctx.refresh();}
        catch(e){if(v!==version||state?.ctx.onUnauthorized(e))return;form.locked=e?.code!=='22023';form.status.textContent=errorText(e);form.status.className='learning-status error';if(!form.locked)form.actions.querySelector('button').disabled=false;const cancel=form.actions.querySelector('[data-cancel]');if(cancel)cancel.disabled=false;/* Un conflicto o respuesta incierta requiere releer, sin reenvío. */}
        finally{if(v===version)busy=false;}
    }
    function configuration(){
        const {data}=state,existing=data.published,source=existing||data.draft;
        const form=modal('Configurar evaluación por categorías'),weights={},grid=el('div',undefined,'category-weight-grid'),total=el('p','','weighted-total');
        form.fields.append(el('p','Reparte el 100 % entre las categorías que uses. Una categoría en 0 % no se califica ni cuenta. No necesitas crear tareas ni actividades.'));
        if(existing?.entry_mode!=='categories'&&existing)form.fields.append(el('p','Al confirmar se usará una nota por categoría. Las actividades y sus notas se conservarán; las finales y boletas ya emitidas no cambian.','learning-status'));
        for(const [idx,code] of codes.entries()){const label=el('label',labels[code]),n=number('Porcentaje de '+labels[code],source?.categories?.find(c=>c.code===code)?.weight??[30,50,20,0][idx],false);n.required=true;label.append(n);grid.append(label);weights[code]=n;}
        const reasonLabel=el('label','Motivo del cambio (si modificas criterios publicados)'),reason=el('textarea');reason.rows=2;reason.maxLength=1000;reasonLabel.append(reason);
        const confirm=checkbox('He revisado los porcentajes y confirmo esta forma de evaluación.'),save=button('Guardar porcentajes',()=>{},true),cancel=button('Cancelar',()=>close());cancel.dataset.cancel='true';save.type='submit';
        form.fields.append(grid,total,reasonLabel,confirm.label);form.actions.append(save,cancel);
        function sync(){const sum=codes.reduce((a,c)=>a+Math.round(Number(weights[c].value)*100),0)/100;total.textContent='Total: '+sum+' % de 100 %';total.classList.toggle('invalid',sum!==100);save.disabled=Boolean(form.locked)||busy||sum!==100||!confirm.input.checked||codes.some(c=>weights[c].value===''||!weights[c].checkValidity());}
        form.form.addEventListener('input',sync);form.form.addEventListener('change',sync);
        form.form.addEventListener('submit',e=>{e.preventDefault();if(save.disabled||busy)return;const schema={entry_mode:'categories',categories:codes.map(code=>({code,weight:Number(weights[code].value),mode:'equal'})),items:[]};void submit(form,'category_scheme_publish',{schema,revision:data.revision,confirmed:confirm.input.checked,reason:reason.value.trim()});});
        sync();form.d.showModal();weights.tasks.focus();
    }
    function enabled(){return codes.filter(c=>state.data.published?.categories.find(x=>x.code===c)?.weight>0);}
    function marks(row){const out={};for(const c of enabled()){const i=row.inputs[c];if(i.value!==''&&!i.checkValidity())throw Error('Introduce notas de 0 a 10, con un decimal.');out[c]=i.value===''?null:window.PortalGradeScale.toWire(i.value,row.original[c]);}return out;}
    function average(m){if(!enabled().length||enabled().some(c=>m[c]===null))return null;return Math.round(enabled().reduce((n,c)=>n+Math.round(m[c]*100)*Math.round(state.data.published.categories.find(x=>x.code===c).weight*100),0)/10000)/100;}
    function draft(){
        if(busy)return;const students=[];
        try{for(const row of state.rows){const m=marks(row);if(enabled().some(c=>m[c]!==row.original[c]))students.push({id:row.student.enrollment_id,token:row.student.summary.token,marks:m});}}
        catch(e){note(e.message,true);return;}
        if(!students.length){note('No hay notas modificadas para guardar.');return;}
        const form=modal('Guardar categorías como borrador');form.fields.append(el('p','Se guardarán las categorías de '+students.length+' seminaristas. Las finales publicadas y las boletas conservarán sus valores.'));
        const save=button('Guardar borrador',()=>void submit(form,'category_marks_save',{publish:false,students}),true),cancel=button('Cancelar',()=>close());cancel.dataset.cancel='true';form.actions.append(save,cancel);form.d.showModal();
    }
    function review(){
        if(busy)return;const candidates=[];
        try{for(const row of state.rows){const m=marks(row);candidates.push({row,m,average:average(m)});}}catch(e){note(e.message,true);return;}
        const form=modal('Revisar y publicar finales'),list=el('div',undefined,'category-review-list'),fields=[];
        form.fields.append(el('p','Las categorías y la final se publicarán juntas para los seminaristas seleccionados. Puedes ajustar la final; el cálculo original se conservará.'));
        for(const c of candidates){const box=el('section',undefined,'category-review-row'),pick=checkbox(c.row.student.name),adjustLabel=el('label','Final ajustada (opcional)'),adjust=number('Ajuste final de '+c.row.student.name);adjustLabel.append(adjust);pick.input.disabled=c.average===null;pick.input.checked=c.average!==null;adjust.disabled=c.average===null;
            box.append(pick.label,el('p',c.average===null?'Pendiente: completa las categorías que cuentan.':'Final calculada: '+format(c.average)+' · Publicada: '+format(c.row.student.final_score)),adjustLabel);list.append(box);fields.push({...c,pick,adjust});}
        const reasonLabel=el('label','Motivo de ajustes o correcciones (mínimo 10 caracteres si corresponde)'),reason=el('textarea');reason.rows=2;reason.maxLength=1000;reasonLabel.append(reason);
        const confirm=checkbox('He revisado las notas seleccionadas y confirmo su publicación en las boletas y el historial.'),save=button('Publicar finales seleccionadas',()=>{},true),cancel=button('Volver',()=>close());save.type='submit';cancel.dataset.cancel='true';
        form.fields.append(list,reasonLabel,confirm.label);form.actions.append(save,cancel);
        function sync(){save.disabled=Boolean(form.locked)||busy||!confirm.input.checked||!fields.some(f=>f.pick.input.checked);}
        form.form.addEventListener('change',sync);form.form.addEventListener('submit',e=>{e.preventDefault();if(save.disabled||busy)return;
            try{const students=fields.filter(f=>f.pick.input.checked).map(f=>({id:f.row.student.enrollment_id,token:f.row.student.summary.token,marks:f.m,override:f.adjust.value===''?null:window.PortalGradeScale.toWire(f.adjust.value)}));void submit(form,'category_marks_save',{publish:true,confirmed:confirm.input.checked,reason:reason.value.trim(),students});}
            catch(e){form.status.textContent=e.message;}
        });sync();form.d.showModal();
    }
    function render(target,data,ctx){
        clear();target.classList.add("category-book");state={target,data,ctx,rows:[]};const heading=el('div',undefined,'weighted-toolbar');heading.append(el('h2','Calificaciones por categoría'),button('Configurar evaluación',configuration,true),button('Actualizar libro',()=>ctx.refresh()),button('Exportar seminaristas mostrados',ctx.exportCSV));
        const status=el('p','','learning-status');status.setAttribute('role','status');state.status=status;target.replaceChildren(heading,status);
        if(!data.published){target.append(el('p','Configura los porcentajes para capturar una nota de Tareas, Exámenes, Proyectos y Participación por seminarista. No se requieren actividades.'));return;}
        target.append(el('p',data.published.categories.map(c=>labels[c.code]+': '+c.weight+' %'+(c.weight===0?' (no cuenta)':'')).join(' · ')),el('p','Escala de 0 a 10. La final se calcula al completar las categorías que cuentan. Vacío significa pendiente; 0 es una nota real. Guardar borrador conserva la final publicada. Revisar y publicar finales confirma las categorías y la final juntas.'));
        const scroll=el('div',undefined,'learning-table-scroll category-scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','Calificaciones por categoría; desplázate para ver las columnas');const table=el('table',undefined,'learning-grades-table category-table'),head=el('thead'),hr=el('tr'),body=el('tbody');for(const label of ['Seminarista',...codes.map(c=>labels[c]),'Final calculada','Final publicada']){const th=el('th',label);th.scope='col';hr.append(th);}head.append(hr);table.append(head,body);scroll.append(table);target.append(scroll);
        for(const student of data.students){const tr=el('tr'),name=el('th',student.name),row={student,inputs:{},original:{}};name.scope='row';tr.append(name);
            for(const c of codes){const td=el('td');if(!enabled().includes(c)){td.append(el('span','No cuenta','learning-meta'));tr.append(td);continue;}
                const old=student.category_grades?.find(x=>x.category===c);row.original[c]=old?.score??null;
                const i=number(labels[c]+' de '+student.name,row.original[c]===null?'':window.PortalGradeScale.format(row.original[c]));i.dataset.category=c;i.dataset.enrollment=student.enrollment_id;td.append(i);row.inputs[c]=i;tr.append(td);}
            row.calculated=el('td','Pendiente','category-calculated');row.calculated.setAttribute('aria-live','polite');tr.append(row.calculated,el('td',format(student.final_score)));body.append(tr);state.rows.push(row);
            function sync(){try{row.calculated.textContent=format(average(marks(row)));}catch{row.calculated.textContent='Revisa las notas';}}
            for(const i of Object.values(row.inputs))i.addEventListener('input',sync);sync();
        }
        const actions=el('div',undefined,'category-actions');actions.append(button('Guardar borrador',draft),button('Revisar y publicar finales',review,true));target.append(actions);
        if(!data.students.length){actions.querySelectorAll('button').forEach(b=>b.disabled=true);target.append(el('p','No hay seminaristas activos inscritos.'));}
        const pagination=el('div',undefined,'category-actions');if(ctx.offset)pagination.append(button('Anterior',()=>ctx.refresh(ctx.offset-30)));pagination.append(el('p','Seminaristas '+(data.students.length?ctx.offset+1:0)+'–'+(ctx.offset+data.students.length)));if(data.has_more)pagination.append(button('Siguiente',()=>ctx.refresh(ctx.offset+30)));target.append(pagination);
        const advanced=el('details'),summary=el('summary','Más opciones');advanced.append(summary,el('p','Si necesitas evaluar actividades individuales, puedes conservarlas y usar el libro por actividades.'),button('Evaluar mediante actividades',ctx.configureActivities));target.append(advanced);
    }
    function configureExisting(target,data,ctx){clear();const status=el('p','','learning-status');target.prepend(status);state={target,data,ctx,status,rows:[]};configuration();}
    window.PortalCategoryGrades=Object.freeze({clear,render,configureExisting});
})();
