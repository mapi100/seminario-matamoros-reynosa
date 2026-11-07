"""Categorías directas, permisos y finales en PostgreSQL aislado, sin datos reales."""
import json
import run_kardex_local as k
h=k.h;q=h.quote

def query(action,data,who=h.P,course=h.L):return h.actor(who,'select public.portal_gradebook_write('+','.join([q(course),q(action),q(json.dumps(data))+'::jsonb'])+')',commit=True)
def write(action,data,**kw):return json.loads(h.sql(query(action,data,**kw)).stdout)
def read(who=h.P,resource='book',course=h.L):return json.loads(h.sql(h.actor(who,'select public.portal_gradebook_read('+','.join([q(course),q(resource)])+')')).stdout)
def student():return read()['students'][0]
def save(marks,publish=False,override=None,reason='',token=None,**kw):return query('category_marks_save',{'publish':publish,'confirmed':publish,'reason':reason,'students':[{'id':k.E2,'token':token or student()['summary']['token'],'marks':marks,'override':override}]},**kw)
try:
 k.bootstrap();h.sql(f"insert into public.teaching_assignments(id,professor_id,subject_id,period_id)values('{h.uid(91)}','{h.P}','{h.S2}','{h.T}')")
 schema={'entry_mode':'categories','categories':[{'code':c,'weight':w,'mode':'equal'} for c,w in zip(['tasks','exams','projects','participation'],[30,50,0,20])],'items':[]}
 data={'schema':schema,'revision':0,'confirmed':True}
 for who in [h.A,h.B,h.IC,h.N]:h.test('otro rol o inactivo no configura',query('category_scheme_publish',data,who=who),error='42501')
 h.test('profesor no asignado no configura',query('category_scheme_publish',data,course=h.K),error='42501')
 bad=json.loads(json.dumps(data));bad['schema']['categories'][0]['weight']=40
 h.test('porcentajes suman 100',query('category_scheme_publish',bad),error='22023')
 write('category_scheme_publish',data);h.check('criterios publicados sin actividades',read()['published']==schema and read()['assignments']==[])
 h.test('revisión vieja de criterios no sobrescribe',query('category_scheme_publish',data),error='PT409')
 h.test('tabla no accesible directamente',"select has_table_privilege('authenticated','public.learning_category_grades','SELECT,INSERT,UPDATE,DELETE')",'f')
 for helper in ['_gradebook_write_before_categories(uuid,text,jsonb)','_gradebook_read_before_categories(uuid,text,integer,integer)','_grading_calculate_before_categories(uuid,uuid,boolean)','_grading_validate_before_categories(uuid,jsonb)']:
  h.test('helper privado',"select has_function_privilege('authenticated',"+q('public.'+helper)+",'execute')",'f')
 h.check('falta nota significa pendiente',student()['summary']['average'] is None)
 token=student()['summary']['token'];h.sql(save({'tasks':80,'exams':90,'participation':100}))
 h.check('borradores calculan 89 sin publicar',student()['draft_summary']['average']==89 and student()['summary']['average'] is None)
 own=read(h.A,'own');h.check('alumno no ve borradores',own['summary']['average'] is None and 'category_grades' not in own and 'token' not in own['summary'])
 h.test('cambio concurrente bloquea escritura',save({'tasks':80},token=token),error='PT409')
 h.test('categoría cero no admite una nota',save({'tasks':80,'exams':90,'projects':50,'participation':100}),error='22023')
 h.test('no publica con categoría faltante',save({'tasks':80,'exams':90},True),error='22023')
 h.test('fuera de escala no publica',save({'tasks':101,'exams':90,'participation':100},True),error='22023')
 h.test('cambiar final previa requiere razón',save({'tasks':80,'exams':90,'participation':100},True),error='22023')
 h.test('publicación fallida conserva notas de categorías privadas',"select count(*) from public.learning_category_grades where published_score is not null",'0')
 h.sql(save({'tasks':80,'exams':90,'participation':100},True,95,'Ajuste de cierre autorizado por el profesor'))
 h.test('final ajustada en historial',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'95.00')
 own=read(h.A,'own');h.check('alumno ve cálculo 89 y final publicada 95',own['summary']['average']==89 and own['final_score']==95)
 h.test('sin actividades artificiales',"select count(*) from public.learning_assignments",'0')
 h.test('cálculo y ajuste conservados',f"select snapshot->'calculation'->>'average' from public.learning_final_calculations where enrollment_id='{k.E2}'",'89.00')
 h.sql(save({'tasks':0,'exams':0,'participation':0},True,reason='Corrección de notas con calificaciones cero'))
 h.test('cero cuenta como nota, no como pendiente',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'0.00')
 # Desactivar peso conserva la nota antigua, pero no la usa; reactivar vuelve a exigirla.
 schema['categories']=[{'code':c,'weight':w,'mode':'equal'} for c,w in zip(['tasks','exams','projects','participation'],[0,100,0,0])]
 write('category_scheme_publish',{'schema':schema,'revision':1,'confirmed':True,'reason':'Solo se evaluará el examen final del curso'})
 h.sql(save({'exams':75},True,reason='Nota proporcionada por el docente del curso'))
 h.test('categorías con peso cero excluidas del cálculo',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'75.00')
 # Un error en la segunda final revierte también revisiones/eventos de la primera.
 second=h.uid(160);h.sql(f"update public.profiles set active=true where id='{h.B}';insert into public.enrollments(id,student_id,subject_id,period_id)values('{second}','{h.B}','{h.S2}','{h.T}')")
 people=read()['students'];tokens={x['enrollment_id']:x['summary']['token'] for x in people}
 revision=h.sql(f"select revision from public.learning_category_grades where enrollment_id='{k.E2}' and category='exams'").stdout
 payload={'publish':True,'confirmed':True,'reason':'','students':[{'id':k.E2,'token':tokens[k.E2],'marks':{'exams':75}},{'id':second,'token':tokens[second],'marks':{'exams':90},'override':95}]}
 h.test('error en segunda final revierte lote entero',query('category_marks_save',payload),error='22023')
 h.check('revisión de primera nota intacta',revision==h.sql(f"select revision from public.learning_category_grades where enrollment_id='{k.E2}' and category='exams'").stdout)
 h.test('segunda categoría no quedó parcialmente guardada',f"select count(*) from public.learning_category_grades where enrollment_id='{second}'",'0')
 payload['students'][1]['override']=None;payload['confirmed']=False
 h.test('publicación requiere confirmación explícita',query('category_marks_save',payload),error='22023')
 activity=h.write(h.P,'assignment_save',h.L,{'title':'Actividad presencial anterior','published':True})['id']
 h.check('actividad conservada no bloquea categorías',student()['summary']['ready'])
 h.test('conserva actividad existente',f"select title from public.learning_assignments where id='{activity}'",'Actividad presencial anterior')
 # Activos/asignaciones se vuelven a comprobar en cada llamada.
 h.sql(f"update public.teaching_assignments set active=false where professor_id='{h.P}'")
 h.test('revocar asignación impide capturar',query('category_marks_save',{'publish':False,'students':[]}),error='42501')
 h.check('Control Escolar conserva acceso por rol',read(h.C)['students'][0]['summary']['average']==75)
 h.sql((h.ROOT/'supabase/migrations/20261107000000_category_grade_entry.sql').read_text())
 h.test('reinstalar conserva notas',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'75.00')
 print('PASS categorías sin actividades, publicación/ajuste, escala, privacidad y reinstalación')
finally:h.run('docker','rm','-f',h.NAME,check=False)
