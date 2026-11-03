(function () {
    "use strict";
    const bucket='portal-personal',maxFiles=10,maxSize=5*1024*1024,uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const groups=[['Sacramentos',[['bautismo','Boleta de bautismo'],['comunion','Primera comunión'],['confirmacion','Confirmación'],['otros_sacramentos','Otro documento sacramental']]],
        ['Formación previa',[['preparatoria','Certificado de preparatoria'],['titulo_universitario','Título universitario'],['otros_estudios','Otro certificado de estudios']]],
        ['Seguro médico',[['seguro_medico','Seguro médico']]],['Otros documentos',[['otro','Otro documento personal']]]];
    const kinds=new Map(groups.flatMap(([,types])=>types));
    const node=(tag,text,css)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(css)n.className=css;return n;};
    const button=(text,run,css='back-link')=>{const b=node('button',text,css);b.type='button';b.addEventListener('click',run);return b;};
    let current;
    function clear(){const s=current;current=undefined;if(!s)return;s.alive=false;s.controller.abort();for(const url of s.urls)URL.revokeObjectURL(url);s.urls.clear();s.host.replaceChildren();s.onBusy?.();}
    function mount(host,options){
        if(current?.host===host)return;clear();if(!host||!uuid.test(options.studentId))return;
        const s={host,student:options.studentId,alive:true,busy:false,locked:false,loaded:false,items:[],urls:new Set(),controller:new AbortController(),onBusy:options.onBusy};current=s;
        const count=node('p',undefined,'personal-files-count'),help=node('p','Hasta 10 PDF en total, de 5 MB por archivo. Solo el alumno y Control Escolar pueden acceder. Los archivos se guardan al pulsar Subir PDF.','personal-files-help');
        const fields=node('div',undefined,'personal-files-upload'),typeLabel=node('label','Tipo de documento'),select=node('select');select.id='personalFileKind';
        select.append(new Option('Selecciona el tipo de documento',''));for(const [name,types]of groups){const group=node('optgroup');group.label=name;for(const [key,label]of types)group.append(new Option(label,key));select.append(group);}typeLabel.append(select);
        const fileLabel=node('label','Seleccionar PDF'),input=node('input');input.id='personalFileInput';input.type='file';input.accept='.pdf,application/pdf';input.multiple=true;fileLabel.append(input);
        const tools=node('div',undefined,'personal-actions'),upload=button('Subir PDF',()=>void send(),'back-link control-create'),refresh=button('Actualizar archivos',()=>void load());upload.id='personalFilesUpload';refresh.id='personalFilesRefresh';tools.append(upload,refresh);
        const selected=node('p',undefined,'personal-files-help'),message=node('p',undefined,'control-message'),list=node('div',undefined,'personal-files-groups');message.id='personalFilesStatus';message.setAttribute('role','status');message.setAttribute('aria-live','polite');list.id='personalFilesList';
        fields.append(typeLabel,fileLabel);host.append(help,count,fields,selected,tools,message,list);
        function live(){if(!s.alive||current!==s)throw new DOMException('Operación cancelada','AbortError');}
        function note(text,error=false){if(!s.alive)return;message.textContent=text;message.className='control-message'+(error?' error':'');}
        function sync(){if(!s.alive)return;host.setAttribute('aria-busy',String(s.busy));input.disabled=select.disabled=s.busy||s.locked||!s.loaded||s.items.length>=maxFiles;
            upload.disabled=s.busy||s.locked||!s.loaded||!input.files.length||!kinds.has(select.value)||s.items.length>=maxFiles;refresh.disabled=s.busy;
            for(const b of list.querySelectorAll('button'))b.disabled=s.busy||s.locked;
            selected.textContent=input.files.length?input.files.length+' PDF seleccionados; se guardarán con el tipo elegido.':'';
        }
        function busy(value){s.busy=value;sync();s.onBusy?.();}
        function forbidden(error){if(error?.source==='storage')return false;if(error?.code==='42501'||[401,403].includes(Number(error?.status||error?.statusCode))){clear();void options.onForbidden?.();return true;}return false;}
        function readError(error){return ['PGRST202','42883','42P01'].includes(error?.code)?'Falta instalar los archivos personales en Supabase. Contacta al responsable del portal.':
            ['22023','PT409'].includes(error?.code)?error.message:'No se pudo consultar el archivo. Comprueba tu conexión y actualiza.';}
        async function rpc(action,data={}){const result=await window.PortalAuth.getClient().rpc('portal_student_files',{p_action:action,p_student:s.student,p_data:data}).retry(false).abortSignal(s.controller.signal);live();if(result.error)throw {...result.error,status:result.status};return result.data;}
        function valid(f){return f&&uuid.test(f.id)&&f.student_id===s.student&&kinds.has(f.kind)&&typeof f.name==='string'&&f.name.length<=160&&/\.pdf$/i.test(f.name)&&Number.isSafeInteger(f.size)&&f.size>0&&f.size<=maxSize&&f.object_path===s.student+'/'+f.id+'.pdf'&&['pending','ready','deleting'].includes(f.state)&&uuid.test(f.uploaded_by)&&typeof f.created_at==='string';}
        function draw(){list.replaceChildren();const ready=s.items.filter(f=>f.state==='ready').length;count.textContent=ready+' de 10 archivos guardados'+(s.items.length-ready?' · '+(s.items.length-ready)+' cargas pendientes de completar o limpiar':'');
            for(const [title,types]of groups){const block=node('section',undefined,'personal-files-group'),ul=node('ul');block.append(node('h3',title));const rows=s.items.filter(f=>types.some(([key])=>key===f.kind));
                for(const f of rows){const li=node('li'),info=node('div'),actions=node('div',undefined,'personal-actions');info.append(node('strong',kinds.get(f.kind)),node('p',f.name+' · '+Math.ceil(f.size/1024)+' KB'));
                    if(f.state==='ready'){actions.append(button('Descargar',()=>void download(f)));}else info.append(node('p',f.state==='pending'?'Carga incompleta. Actualiza para comprobarla o límpiala antes de volver a subir.':'Eliminación pendiente. Pulsa Completar eliminación para liberar el espacio.','personal-files-pending'));
                    actions.append(button(f.state==='ready'?'Quitar archivo':f.state==='pending'?'Limpiar carga incompleta':'Completar eliminación',()=>void remove(f),'back-link personal-files-remove'));li.append(info,actions);ul.append(li);}
                if(!rows.length)block.append(node('p',title==='Formación previa'?'Aquí puedes guardar certificados de preparatoria y títulos universitarios, si corresponde.':title==='Seguro médico'?'Aquí puedes guardar tu constancia o póliza de seguro médico.':'Todavía no hay documentos en este apartado.','personal-files-help'));else block.append(ul);list.append(block);}
        }
        async function load(){if(s.busy||!s.alive)return;busy(true);s.loaded=false;note('Consultando archivos privados…');
            try{const data=await rpc('list');if(data?.student_id!==s.student||data.max_files!==maxFiles||data.max_size!==maxSize||!Array.isArray(data.items)||data.items.length>maxFiles||!data.items.every(valid)||new Set(data.items.map(f=>f.id)).size!==data.items.length)throw new Error('Respuesta inválida');s.items=data.items;s.loaded=true;s.locked=false;input.value='';draw();note('Archivos actualizados.');}
            catch(error){if(s.alive&&!forbidden(error)){s.loaded=false;s.locked=true;list.replaceChildren();count.textContent='';note(readError(error),true);}}
            finally{if(s.alive)busy(false);}
        }
        function safeName(file){const clean=file.name.replace(/[\x00-\x1f\x7f/\\]/g,'_').trim();return clean.length>160?clean.slice(0,156)+'.pdf':clean;}
        async function send(){if(s.busy||s.locked||!s.loaded||!kinds.has(select.value)||!input.files.length)return;const files=Array.from(input.files),kind=select.value;
            if(files.length+s.items.length>maxFiles){note('Solo puedes guardar 10 PDF en total. Selecciona menos archivos.',true);return;}
            busy(true);let saved=0,mutating=false,success=false;
            try{for(const f of files){if(!/\.pdf$/i.test(f.name)||f.size<1||f.size>maxSize)throw new Error('Selecciona únicamente PDF de hasta 5 MB, sin archivos vacíos.');const signature=await f.slice(0,1024).text();live();if(!signature.includes('%PDF-'))throw new Error('Uno de los archivos no tiene una cabecera PDF válida. No se inició la carga.');}
                for(const f of files){note('Subiendo PDF '+(saved+1)+' de '+files.length+'…');mutating=true;const reserved=await rpc('reserve',{name:safeName(f),size:f.size,kind});if(reserved?.saved!==true||!valid(reserved.item)||reserved.item.state!=='pending')throw new Error('Reserva sin confirmar');
                    const uploaded=await window.PortalAuth.getClient().storage.from(bucket).upload(reserved.item.object_path,f,{contentType:'application/pdf',upsert:false,cacheControl:'0'});live();if(uploaded.error)throw {...uploaded.error,message:uploaded.error.message,source:'storage'};
                    const completed=await rpc('complete',{id:reserved.item.id});if(completed?.saved!==true||!valid(completed.item)||completed.item.state!=='ready')throw new Error('Carga sin confirmar');saved++;}
                success=true;input.value='';
            }catch(error){if(s.alive&&!forbidden(error)){if(mutating){s.locked=true;note(saved+' PDF confirmados. No se pudo confirmar el resto de la carga. Pulsa Actualizar archivos para comprobar el resultado y limpiar cargas incompletas antes de repetir.',true);}else note(error.message||'No se pudo leer el PDF.',true);}}
            finally{if(s.alive)busy(false);}
            if(success&&s.alive){await load();if(s.loaded)note(saved+' PDF guardados. Ya puedes descargarlos.');}
        }
        async function download(f){if(s.busy||s.locked||f.state!=='ready')return;busy(true);note('Preparando descarga privada…');
            try{const r=await window.PortalAuth.getClient().storage.from(bucket).download(f.object_path);live();if(r.error)throw {...r.error,message:r.error.message,source:'storage'};if(!(r.data instanceof Blob)||r.data.size!==f.size)throw new Error('Descarga incompleta');
                const url=URL.createObjectURL(new Blob([r.data],{type:'application/octet-stream'}));s.urls.add(url);const a=node('a');a.href=url;a.download=f.name;a.hidden=true;host.append(a);a.click();a.remove();setTimeout(()=>{URL.revokeObjectURL(url);s.urls.delete(url);},1000);note('Descarga preparada.');
            }catch(error){if(s.alive&&!forbidden(error))note('No se pudo descargar el PDF. Comprueba tu conexión y actualiza los archivos.',true);}
            finally{if(s.alive)busy(false);}
        }
        async function remove(f){if(s.busy||s.locked||!confirm((f.state==='ready'?'¿Quitar este PDF del expediente?':'¿Limpiar esta carga del expediente?')+'\n'+f.name+'\nEsta acción no modifica los otros documentos ni tus datos personales.'))return;
            busy(true);let success=false;
            try{const r=await rpc('remove',{id:f.id});if(r?.saved!==true)throw new Error('Retirada sin confirmar');if(!r.removed){if(!valid(r.item)||r.item.state!=='deleting')throw new Error('Retirada inválida');const removed=await window.PortalAuth.getClient().storage.from(bucket).remove([r.item.object_path]);live();if(removed.error)throw {...removed.error,message:removed.error.message,source:'storage'};const released=await rpc('release',{id:f.id});if(released?.saved!==true||released.removed!==true)throw new Error('Limpieza sin confirmar');}success=true;}
            catch(error){if(s.alive&&!forbidden(error)){s.locked=true;note('No se pudo confirmar la eliminación. Pulsa Actualizar archivos y completa la eliminación pendiente antes de repetir.',true);}}
            finally{if(s.alive)busy(false);}
            if(success&&s.alive){await load();if(s.loaded)note('Archivo retirado. El espacio ya está disponible.');}
        }
        input.addEventListener('change',sync);select.addEventListener('change',sync);void load();
    }
    window.PortalPersonalFiles=Object.freeze({mount,clear,isBusy:()=>Boolean(current?.busy)});
})();
