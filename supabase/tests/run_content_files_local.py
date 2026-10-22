#!/usr/bin/env python3
"""Archivos docentes en PostgreSQL/RLS desechable. Sin Supabase real.
Storage usa fixtures de metadata; no valida transporte HTTP ni contenido binario.
"""
import json,time,uuid
import run_learning_local as h

def content(action,data=None,who=h.P,topic=None,course=None,commit=True):
    return h.actor(who,'select public.portal_content_files('+','.join([h.quote(action),h.quote(course or h.K),h.quote(topic or TOPIC),h.quote(json.dumps(data or {}))+'::jsonb'])+')',commit=commit)

def blob(path,who=h.P,mime='application/pdf',size=20):
    return h.actor(who,"insert into storage.objects(bucket_id,name,owner_id,metadata) values('portal-content',"+h.quote(path)+','+h.quote(who)+','+h.quote(json.dumps({'size':size,'mimetype':mime}))+"::jsonb) returning name",commit=True)

def count_objects(who):return h.actor(who,"select count(*) from storage.objects where bucket_id='portal-content'")
def cleanup():return json.loads(h.sql(h.actor(h.C,'select public.portal_admin_cleanup_files(true)',commit=True)).stdout)
MODULE=h.uid(70);TOPIC=h.uid(71)

def main():
    h.run('docker','run','--rm','-d','--name',h.NAME,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:17-bookworm')
    for _ in range(100):
        logs=h.run('docker','logs',h.NAME,check=False)
        if 'PostgreSQL init process complete' in logs.stdout+logs.stderr and h.run('docker','exec',h.NAME,'pg_isready','-U','postgres',check=False).returncode==0:break
        time.sleep(.2)
    else:raise AssertionError('Postgres did not start')
    h.sql(h.AUTH);h.sql(h.STORAGE)
    for p in sorted((h.ROOT/'supabase/migrations').glob('*.sql')):h.sql(p.read_text())
    for who,name,role,active in [(h.A,'Alumno','student',True),(h.P,'Profesor','professor',True),(h.P2,'Otro profesor','professor',True),(h.C,'Control','control_escolar',True),(h.IC,'Inactivo','control_escolar',False),(h.N,'Sin inscripción','student',True)]:
        h.sql(f"insert into auth.users values('{who}','{who}@example.invalid');insert into public.profiles(id,full_name,role,active) values('{who}',{h.quote(name)},'{role}',{str(active).lower()})")
    h.sql(f"""
insert into public.subjects(id,code,name) values('{h.S}','HIS','Historia'),('{h.S2}','FIL','Filosofía');
insert into public.academic_periods(id,name,starts_on,ends_on) values('{h.T}','Semestre','2026-08-01','2026-12-18');
insert into public.course_offerings(id,subject_id,period_id) values('{h.K}','{h.S}','{h.T}'),('{h.L}','{h.S2}','{h.T}');
insert into public.enrollments(id,student_id,subject_id,period_id) values('{h.EA}','{h.A}','{h.S}','{h.T}');
insert into public.teaching_assignments(id,professor_id,subject_id,period_id) values('{h.TA}','{h.P}','{h.S}','{h.T}');
insert into public.learning_modules(id,course_id,title) values('{MODULE}','{h.K}','Unidad');
insert into public.learning_topics(id,course_id,module_id,title) values('{TOPIC}','{h.K}','{MODULE}','Tema');
""")
    path=f'{h.K}/{TOPIC}/{uuid.uuid4()}/lectura.pdf'
    h.test('content bucket private',"select public from storage.buckets where id='portal-content'",'f')
    h.test('content bucket has 10 MB limit',"select file_size_limit from storage.buckets where id='portal-content'",10485760)
    h.test('no direct content file table access',"select has_table_privilege('authenticated','public.learning_content_files','SELECT,INSERT,UPDATE,DELETE')",'f')
    h.test('no anonymous content RPC',"select has_function_privilege('anon','public.portal_content_files(text,uuid,uuid,jsonb)','EXECUTE')",'f')
    h.test('private MIME helper not executable',"select has_function_privilege('authenticated','public._content_mime(text)','EXECUTE')",'f')
    for who in [h.A,h.N,h.P2,h.IC]:
        h.test('unauthorized uploader '+who[-2:],blob(path,who),error='42501')
    h.test('assigned professor uploads into draft content',blob(path))
    h.test('teacher cannot use another owner',h.actor(h.P,"insert into storage.objects(bucket_id,name,owner_id) values('portal-content',"+h.quote(path.replace('lectura','otro'))+','+h.quote(h.C)+')',commit=True),error='42501')
    h.test('disallowed HTML upload rejected',blob(path.replace('.pdf','.html')),error='42501')
    h.test('malformed path rejected',blob('invalid/'+str(uuid.uuid4())+'/f.pdf'),error='42501')
    h.test('cross-course upload rejected',blob(path.replace(h.K,h.L)),error='42501')
    data={'object_path':path,'name':'Lectura de Historia.pdf'}
    h.test('attach uploaded PDF',content('attach',data))
    id=h.sql('select id from public.learning_content_files').stdout.strip()
    h.test('lost reply can retry attachment idempotently',content('attach',data))
    h.test('idempotent retry produces one record','select count(*) from public.learning_content_files',1)
    h.test('cannot reuse path with another filename',content('attach',{**data,'name':'Otro.pdf'}),error='22023')
    h.test('cannot attach to another topic',content('attach',data,topic=h.uid(72)),error='42501')
    for who in [h.A,h.P2,h.IC,h.N]:
        h.test('cannot attach as '+who[-2:],content('attach',data,who),error='42501')
    h.test('student cannot read draft metadata',content('list',who=h.A),error='42501')
    h.test('student cannot download draft blob',count_objects(h.A),0)
    h.test('unassigned teacher cannot download draft blob',count_objects(h.P2),0)
    h.test('Control can manage draft files',content('list',who=h.C))
    h.sql(f"update public.learning_modules set published=true where id='{MODULE}'")
    h.test('published module still hides draft topic',content('list',who=h.A),error='42501')
    h.sql(f"update public.learning_topics set published=true where id='{TOPIC}'")
    h.test('enrolled student reads published metadata',content('list',who=h.A))
    h.test('enrolled student downloads published file',count_objects(h.A),1)
    h.test('student course projection contains file',h.actor(h.A,f"select public.portal_learning_read('course','{h.K}')->'modules'->0->'topics'->0->'files'->0->>'name'"),'Lectura de Historia.pdf')
    h.test('student cannot remove teaching file',content('remove',{'id':id},h.A),error='42501')
    h.test('student direct blob deletion does not remove registered file',h.actor(h.A,"delete from storage.objects where name="+h.quote(path)+' returning name',commit=True),'')
    h.test('teacher direct blob deletion cannot bypass registry',h.actor(h.P,"delete from storage.objects where name="+h.quote(path)+' returning name',commit=True),'')
    h.sql(f"update public.enrollments set active=false where id='{h.EA}'")
    h.test('deactivated enrollment loses metadata',content('list',who=h.A),error='42501')
    h.test('deactivated enrollment loses blob',count_objects(h.A),0)
    h.sql(f"update public.enrollments set active=true where id='{h.EA}';update public.learning_modules set published=false where id='{MODULE}'")
    h.test('unpublishing module revokes direct download',count_objects(h.A),0)
    h.sql(f"update public.learning_modules set published=true where id='{MODULE}'")
    h.sql(f"update public.profiles set active=false where id='{h.P}'")
    h.test('revoked teacher cannot register files',content('attach',data),error='42501')
    h.test('revoked teacher loses download',count_objects(h.P),0)
    h.sql(f"update public.profiles set active=true where id='{h.P}'")
    # La validación del registro también comprueba metadata de objetos existentes.
    bad=f'{h.K}/{TOPIC}/{uuid.uuid4()}/formato.pdf'
    h.sql(blob(bad,mime='text/plain'))
    h.test('mismatched MIME cannot register',content('attach',{'object_path':bad,'name':'formato.pdf'}),error='22023')
    h.sql(h.actor(h.P,'delete from storage.objects where name='+h.quote(bad),commit=True))
    big=f'{h.K}/{TOPIC}/{uuid.uuid4()}/grande.pdf'
    h.sql(blob(big,size=10485761))
    h.test('oversize metadata cannot register',content('attach',{'object_path':big,'name':'grande.pdf'}),error='22023')
    h.sql(h.actor(h.P,'delete from storage.objects where name='+h.quote(big),commit=True))
    word=f'{h.K}/{TOPIC}/{uuid.uuid4()}/guia.docx';word_mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    h.sql(blob(word,mime=word_mime));h.test('Word file registration',content('attach',{'object_path':word,'name':'Guía.docx'}))
    pending=[]
    for _ in range(3):
        name=f'{h.K}/{TOPIC}/{uuid.uuid4()}/archivo.pdf';pending.append(name);h.sql(blob(name))
    extra=f'{h.K}/{TOPIC}/{uuid.uuid4()}/extra.pdf'
    h.test('orphan uploads count toward five-object quota',blob(extra),error='42501')
    for n,name in enumerate(pending):h.test('fifth stored object can be registered '+str(n),content('attach',{'object_path':name,'name':f'Archivo {n}.pdf'}))
    h.test('fifth record idempotent at quota',content('attach',{'object_path':pending[-1],'name':'Archivo 2.pdf'}))
    h.test('five attached files stored','select count(*) from public.learning_content_files',5)
    h.test('Control can remove another teacher file',content('remove',{'id':id},h.C))
    h.test('removed file no longer available to student',count_objects(h.A),4)
    q=cleanup();h.check('withdrawn content queued in correct bucket',q['bucket_id']=='portal-content' and q['remaining']==1,q)
    h.test('Control cannot remove unrelated live blob',h.actor(h.C,'delete from storage.objects where name='+h.quote(word)+' returning name',commit=True),'')
    h.test('Control can delete queued content blob',h.actor(h.C,'delete from storage.objects where name='+h.quote(path)+' returning name',commit=True),path)
    h.check('successful removal acknowledged',cleanup()['remaining']==0)
    # Probar contenido y entregas en diferentes buckets durante el borrado completo.
    oldpath=f'{h.K}/{h.uid(99)}/{h.A}/{uuid.uuid4()}/entrega.pdf'
    h.sql("insert into storage.objects(bucket_id,name,owner_id) values('portal-coursework',"+h.quote(oldpath)+','+h.quote(h.A)+')')
    orphan=f'{h.K}/{TOPIC}/{uuid.uuid4()}/incompleto.pdf';h.sql(blob(orphan))
    p=json.loads(h.sql(h.actor(h.C,f"select public.portal_admin_delete_preview('class','{h.K}')")).stdout)
    h.check('delete preview counts both buckets including orphan',p['counts']['stored_files']==6,p)
    h.check('delete preview counts four teaching file records',p['counts']['files']==4,p)
    h.test('class delete removes teaching file rows before topics',h.actor(h.C,f"select public.portal_admin_delete('class','{h.K}','{p['token']}','ELIMINAR')",commit=True))
    h.test('content rows gone','select count(*) from public.learning_content_files',0)
    h.test('other course retained','select count(*) from public.course_offerings',1)
    h.test('all student downloads revoked immediately',count_objects(h.A),0)
    seen=set()
    while (q:=cleanup())['remaining']:
        seen.add(q['bucket_id']);assert q['paths']
        h.sql(h.actor(h.C,'delete from storage.objects where bucket_id='+h.quote(q['bucket_id'])+' and name=any(array['+','.join(map(h.quote,q['paths']))+'])',commit=True))
    h.check('cleanup processed both private buckets',seen=={'portal-content','portal-coursework'},seen)
    h.test('all deleted course blobs removed','select count(*) from storage.objects',0)
    print(f'PASS {h.checks} content-file SQL assertions; fixtures only',flush=True)

if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
