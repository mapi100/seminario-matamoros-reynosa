(function () {
    "use strict";
    const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    let profile,recheck,dialog,generation=0,busy=false;const controllers=new Set(),urls=new Set();
    const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
    const button=(text,run,primary=false)=>{const b=el('button',text,'back-link'+(primary?' control-create':''));b.type='button';b.addEventListener('click',run);return b;};
    function close(force=false){if(busy&&!force)return;generation++;for(const c of controllers)c.abort();controllers.clear();if(dialog){dialog.close();dialog.remove();dialog=undefined;}busy=false;}
    function clear(){close(true);profile=recheck=undefined;for(const u of urls)URL.revokeObjectURL(u);urls.clear();}
    function denied(e){if(e?.code==='42501'||[401,403].includes(e?.status)){const v=recheck;clear();void v?.();return true;}return false;}
    async function rpc(name,args){const c=new AbortController();controllers.add(c);try{const r=await window.PortalAuth.getClient().rpc(name,args).retry(false).abortSignal(c.signal);if(r.error)throw {...r.error,status:r.status};return r.data;}finally{controllers.delete(c);}}
    function errorText(e){return ['PT409','22023'].includes(e?.code)?e.message:['PGRST202','42883','42P01'].includes(e?.code)?'Falta instalar la actualización de boletas por grupo en Supabase.':e instanceof Error?e.message:'No se confirmó la respuesta. Comprueba el mismo lote antes de iniciar otro.';}
    function scope(period,code){const m=/^(CI|[1-4][FT])-([1-8])$/.exec(code||'');if(!uuid.test(period)||!m)return null;const semester=Number(m[2]),stage=m[1]==='CI'?'introductorio':m[1].endsWith('F')?'filosofia':'teologia';if(m[1]!=='CI'&&Number(m[1][0])!==Math.ceil(semester/2))return null;return {period,group:code,stage,semester};}
    function validPlan(p,s){return p?.period_id===s.period&&p.group_code===s.group&&p.stage===s.stage&&p.semester===s.semester&&/^[a-f0-9]{32}$/.test(p.token)&&Array.isArray(p.items)&&p.items.length<=200&&new Set(p.items.map(x=>x.student_id)).size===p.items.length&&p.items.every(x=>uuid.test(x.student_id)&&typeof x.name==='string'&&['pending','reuse','issue'].includes(x.action)&&Array.isArray(x.preview?.reasons));}
    function validResult(r,s,p,request){const wanted=new Set(p.items.filter(x=>x.action!=='pending').map(x=>x.student_id));return r?.saved===true&&r.batch_id===request&&r.period_id===s.period&&r.group_code===s.group&&uuid.test(r.batch_id)&&Array.isArray(r.documents)&&r.documents.length===wanted.size&&new Set(r.documents.map(d=>d.student_id)).size===wanted.size&&r.documents.every(d=>uuid.test(d.id)&&wanted.has(d.student_id)&&typeof d.folio==='string'&&d.snapshot?.student?.id===d.student_id&&d.snapshot?.period?.id===s.period)&&Array.isArray(r.pending);}
    async function open(value){
        if(profile?.role!=='control_escolar'||dialog)return;const s=scope(value.period,value.group);if(!s)return;
        const version=++generation,d=el('dialog',undefined,'learning-dialog report-batch-dialog');dialog=d;let plan,pendingRequest,lastResult,readVersion=0;
        const title=el('h2','Boletas de '+s.group+' en ZIP');title.id='reportBatchTitle';d.setAttribute('aria-labelledby',title.id);
        const subtitle=el('p','Consultando periodo y requisitos…'),summary=el('p'),list=el('ul',undefined,'report-batch-list'),status=el('p','','control-message');status.setAttribute('role','status');
        const checkLabel=el('label',undefined,'school-confirm'),check=el('input');check.type='checkbox';check.id='reportBatchReviewed';checkLabel.append(check,el('span','He revisado las notas, matrículas y firmantes de las boletas que se emitirán.'));
        const progress=el('progress');progress.hidden=true;const refresh=button('Actualizar revisión',()=>void load()),download=button('Descargar ZIP',()=>void save(),true),cancel=button('Cerrar',()=>close());download.id='reportBatchDownload';refresh.id='reportBatchRefresh';
        const actions=el('div',undefined,'report-batch-actions');actions.append(download,refresh,cancel);d.append(title,subtitle,summary,list,checkLabel,progress,status,actions);
        d.addEventListener('cancel',event=>{event.preventDefault();close();});document.body.append(d);d.showModal();
        const alive=()=>dialog===d&&generation===version&&profile?.role==='control_escolar';
        function sync(){const ready=plan?.items.filter(x=>x.action!=='pending').length||0,issue=plan?.items.some(x=>x.action==='issue');checkLabel.hidden=!issue||Boolean(pendingRequest);download.textContent=pendingRequest?'Comprobar / descargar ZIP':issue?'Emitir listas y descargar ZIP ('+ready+')':'Descargar ZIP ('+ready+')';download.disabled=busy||!ready||issue&&!check.checked&&!pendingRequest;refresh.disabled=busy;cancel.disabled=busy;check.disabled=busy;}
        check.addEventListener('change',sync);
        async function load(){
            if(busy||!alive())return;const reading=++readVersion;for(const c of controllers)c.abort();plan=undefined;pendingRequest=lastResult=undefined;check.checked=false;list.replaceChildren();status.textContent='Revisando alumnos y calificaciones…';sync();
            try{const p=await rpc('portal_report_group_read',{p_period:s.period,p_stage:s.stage,p_semester:s.semester});if(!alive()||reading!==readVersion)return;if(!validPlan(p,s))throw new Error('Respuesta de boletas inválida');plan=p;subtitle.textContent=p.period_name+' · '+s.group;
                const eligible=p.items.filter(x=>x.action!=='pending').length,newCopies=p.items.filter(x=>x.action==='issue').length;
                summary.textContent=eligible+' de '+p.items.length+' boletas listas para descargar. '+newCopies+' requieren emisión; '+(eligible-newCopies)+' ya están emitidas y actualizadas.';
                if(!p.items.length)list.append(el('li','No hay seminaristas con inscripciones activas en este bloque y periodo.'));
                for(const item of p.items){const li=el('li');li.append(el('strong',item.name),el('small',item.action==='pending'?'Pendiente: '+item.preview.reasons.join(' '):item.action==='reuse'?'Emitida y actualizada: se reutilizará su folio.':'Lista para emitir y guardar.'));list.append(li);}
                status.textContent=eligible<p.items.length?'El ZIP incluirá las listas y un manifiesto con las pendientes. No se crean boletas incompletas.':'Revisa el grupo antes de descargar.';
            }catch(e){if(alive()&&reading===readVersion&&!denied(e)){status.textContent=errorText(e);status.className='control-message error';}}
            finally{if(alive()&&reading===readVersion)sync();}
        }
        async function save(){
            if(!alive()||busy||!plan||download.disabled)return;busy=true;sync();progress.hidden=false;progress.value=0;progress.max=1;
            pendingRequest ||= {p_period:s.period,p_stage:s.stage,p_semester:s.semester,p_token:plan.token,p_request:crypto.randomUUID(),p_confirmed:true};
            try{
                status.textContent='Confirmando y recuperando las boletas…';
                const result=await rpc('portal_report_group_issue',pendingRequest);if(!alive())return;if(!validResult(result,s,plan,pendingRequest.p_request))throw new Error('Lote de boletas incompleto');lastResult=result;
                const files=[],manifest=['Boletas de '+result.group_code+' · '+result.period_name,'Incluidas: '+result.documents.length+' de '+result.total,'Emisiones nuevas: '+result.newly_issued+' · Copias reutilizadas: '+result.reused,''];
                progress.max=result.documents.length;
                for(let i=0;i<result.documents.length;i++){
                    if(!alive())return;const document=result.documents[i];status.textContent='Preparando PDF '+(i+1)+' de '+result.documents.length+'…';
                    const bytes=await window.PortalReportPDF.pdf(document);if(!alive())return;const name=window.PortalReportPDF.filename(document);files.push({name,bytes});manifest.push(name);progress.value=i+1;
                    await new Promise(resolve=>requestAnimationFrame(resolve));
                }
                manifest.push('','PENDIENTES:');if(!result.pending.length)manifest.push('Ninguna.');
                for(const p of result.pending)manifest.push(p.name+': '+p.reasons.join(' '));
                files.push({name:'LEEME_DEL_LOTE.txt',bytes:new TextEncoder().encode(manifest.join('\r\n'))});
                // Revalidar al finalizar la generación, incluso si cambió el rol mientras
                // se preparaban los PDF. La misma solicitud nunca duplica los folios.
                const confirmed=await rpc('portal_report_group_issue',pendingRequest);if(!alive())return;if(!validResult(confirmed,s,plan,pendingRequest.p_request)||confirmed.batch_id!==result.batch_id)throw new Error('No se pudo revalidar el lote');
                const blob=window.PortalReportPDF.zip(files);if(!alive())return;
                const url=URL.createObjectURL(blob);urls.add(url);const a=el('a');a.href=url;a.download=(s.group+'_'+result.period_name).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-zA-Z0-9_-]/g,'_')+'.zip';document.body.append(a);a.click();a.remove();
                setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},1000);
                status.textContent='ZIP preparado: '+result.documents.length+' boletas de una página. '+(result.pending.length?result.pending.length+' pendientes detalladas en LEEME_DEL_LOTE.txt.':'El grupo está completo.');status.className='control-message success';
            }catch(e){if(alive()&&!denied(e)){status.textContent=(lastResult?'El lote ya está guardado. Puedes reintentar la descarga sin emitir copias nuevas. ':'')+errorText(e);status.className='control-message error';}}
            finally{if(alive()){busy=false;progress.hidden=true;sync();}}
        }
        await load();
    }
    window.addEventListener('hashchange',()=>close(true));
    window.PortalReportBatch=Object.freeze({clear,open,show(value,check){clear();if(value.role==='control_escolar'){profile=value;recheck=check;}}});
})();
