"""Calificaciones por grupo en PostgreSQL aislado. Solo datos ficticios."""
import json
import uuid

import run_kardex_local as fixture

h = fixture.h
q = h.quote
MIGRATION = h.ROOT / 'supabase/migrations/20261127000000_group_final_grades.sql'
READ = 'public.portal_group_final_grades_read'
SAVE = 'public.portal_group_final_grades_save'


def read(period=h.T, group='CI-1', actor=h.C):
    return json.loads(h.sql(h.actor(actor, f'select {READ}({q(period)},{q(group)})')).stdout)


def publish(items, *, token, period=h.T, group='CI-1', actor=h.C, reason='Corrección de acta revisada', confirm=True):
    args = [q(period), q(group), q(token), q(json.dumps(items)) + '::jsonb', q(reason), str(confirm).lower()]
    return h.actor(actor, f'select {SAVE}(' + ','.join(args) + ')', commit=True)


def grade(enrollment_id, score):
    return {'enrollment_id': enrollment_id, 'score': score}


def saved_rows(table):
    return h.sql(f"select coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text),'[]')::text from public.{table} t").stdout


def main():
    fixture.bootstrap()
    extra_course = h.uid(200)
    extra_subject = h.uid(201)
    other_group_enrollment = h.uid(202)
    alumni_enrollment = h.uid(203)
    inactive_course = h.uid(204)
    inactive_subject = h.uid(205)
    inactive_enrollment = h.uid(206)
    ready_student = h.uid(207)
    new_enrollment = h.uid(208)
    h.sql(f"""
        update public.course_offerings set active=true where id='{h.K}';
        update public.enrollments set active=true where id='{h.EA}';
        insert into public.subjects(id,code,name) values
            ('{extra_subject}','OTRA','Materia de otro grupo'),
            ('{inactive_subject}','ANT','Materia inactiva');
        insert into public.course_offerings(id,subject_id,period_id,active) values
            ('{extra_course}','{extra_subject}','{h.T}',true),
            ('{inactive_course}','{inactive_subject}','{h.T}',false);
        insert into public.course_formation_groups(course_id,group_code) values
            ('{h.K}','CI-1'),('{h.L}','CI-1'),('{extra_course}','1F-1'),('{inactive_course}','CI-1');
        insert into auth.users(id,email) values('{ready_student}','ready@example.invalid');
        insert into public.profiles(id,full_name,role) values('{ready_student}','Seminarista Gamma','student');
        insert into public.student_formation_periods(student_id,period_id,stage_code,semester,updated_by) values
            ('{h.A}','{h.T}','introductorio',1,'{h.C}'),
            ('{h.B}','{h.T}','introductorio',1,'{h.C}'),
            ('{ready_student}','{h.T}','introductorio',1,'{h.C}'),
            ('{h.A}','{fixture.T2}','filosofia',1,'{h.C}');
        insert into public.enrollments(id,student_id,subject_id,period_id,active) values
            ('{other_group_enrollment}','{ready_student}','{extra_subject}','{h.T}',true),
            ('{alumni_enrollment}','{h.B}','{h.S}','{h.T}',true),
            ('{inactive_enrollment}','{h.B}','{inactive_subject}','{h.T}',true),
            ('{new_enrollment}','{ready_student}','{h.S2}','{h.T}',true);
        insert into public.enrollment_grades(enrollment_id,score,published) values
            ('{alumni_enrollment}',70,true),('{inactive_enrollment}',91,true),('{new_enrollment}',97,false);
        insert into public.kardex_students(student_id,student_number) values('{h.A}','TEST-001');
        update public.kardex_institution set rector_name='Rector ficticio',prefect_name='Prefecto ficticio' where id=true;
    """)
    for actor in [h.A, h.P, h.IC, h.N]:
        h.test('solo Control Escolar activo consulta', h.actor(actor, f"select {READ}()"), error='42501')
        h.test('solo Control Escolar activo publica', publish([grade(h.EA, 88)], token='x', actor=actor), error='42501')
    for signature in [
        f'{READ}(uuid,text)', f'{SAVE}(uuid,text,text,jsonb,text,boolean)',
        'public._group_final_grades_snapshot(uuid,text)'
    ]:
        h.test('sin permiso para anon', f"select has_function_privilege('anon',{q(signature)},'execute')", 'f')
    h.test('ayudante privado', "select has_function_privilege('authenticated','public._group_final_grades_snapshot(uuid,text)','execute')", 'f')

    data = read()
    snap = data['snapshot']
    token = snap['token']
    h.check('grupos ordenados y con registros en el periodo', [g['code'] for g in data['groups']] == ['CI-1', '1F-1'])
    h.check('solo el grupo y el periodo elegidos', snap['period_id'] == h.T and snap['group_code'] == 'CI-1')
    h.check('se selecciona el primer grupo con clase y seminaristas', read(group=None)['snapshot']['group_code'] == 'CI-1')
    h.check('tres estudiantes y tres cursos en CI-1', len(snap['students']) == len(snap['courses']) == 3)
    h.check('inscripción fuera de grupo separada', snap['outside_count'] == 1)
    cells = {c['enrollment_id']: c for c in snap['cells']}
    h.check('una inscripción inexistente no se vuelve una nota pendiente', len(cells) == 5)
    h.check('escala interna y nota publicada original', cells[h.EA]['score'] == 50 and cells[fixture.E2]['score'] == 80)
    h.check('la nota sin publicar se mantiene pendiente', cells[new_enrollment]['score'] is None and cells[new_enrollment]['editable'])
    h.check('histórico es visible en solo lectura', cells[alumni_enrollment]['score'] == 70 and not cells[alumni_enrollment]['editable'])
    h.check('clase inactiva no editable', cells[inactive_enrollment]['score'] == 91 and not cells[inactive_enrollment]['editable'])
    h.check('datos de borrador personales no viajan en la respuesta', all(
        set(cell) == {'enrollment_id', 'student_id', 'course_id', 'score', 'editable', 'requires_reason'}
        for cell in snap['cells']
    ))
    h.check('periodo nuevo sin grupo devuelve listas vacías', read(fixture.T3, None)['snapshot'] is None)
    h.check('otro periodo tiene su propia formación', read(fixture.T2, '1F-1')['snapshot']['students'][0]['id'] == h.A)

    preview = json.loads(h.sql(h.actor(h.C, f"select public.portal_report_card_read('preview','{h.A}','{h.T}','{{}}',null,0)")).stdout)
    h.check('boleta original lista para emitir en el entorno de prueba', preview['ready'], preview)
    h.sql(h.actor(h.C, f"select public.portal_report_card_issue('{h.A}','{h.T}','{{}}',{q(preview['token'])},{q(str(uuid.uuid4()))})", commit=True))
    original_issues = saved_rows('report_card_issues')
    original_scores = saved_rows('enrollment_grades')

    h.test('sin confirmación no hay escritura', publish([grade(h.EA, 88)], token=token, confirm=False), error='22023')
    h.test('nota fuera de escala rechaza el lote', publish([grade(h.EA, 88), grade(fixture.E2, 101)], token=token), error='22023')
    h.test('RPC conserva un decimal visible', publish([grade(h.EA, 87.3)], token=token), error='22023')
    h.test('corregir publicada exige motivo', publish([grade(h.EA, 88)], token=token, reason=''), error='22023')
    h.test('nota duplicada rechaza el lote', publish([grade(h.EA, 88)] * 2, token=token), error='22023')
    for wrong in [other_group_enrollment, alumni_enrollment, inactive_enrollment, fixture.E3]:
        h.test('no modifica inscripciones ajenas, históricas o inactivas',
               publish([grade(h.EA, 88), grade(wrong, 86)], token=token), error='22023')
    h.check('publicaciones rechazadas dejan las notas intactas', saved_rows('enrollment_grades') == original_scores)

    # Simular un docente que guarda primero el borrador de una final.
    h.sql(f"update public.enrollment_grade_drafts set revision=revision+1,score=84 where enrollment_id='{fixture.E2}'")
    h.test('borrador concurrente invalida vista previa', publish([grade(fixture.E2, 87)], token=token), error='PT409')
    token = read()['snapshot']['token']
    h.sql(f"""
        create function public.test_group_failure() returns trigger language plpgsql as $$
        begin
            if new.enrollment_id='{fixture.E2}'::uuid then raise exception 'fallo simulado'; end if;
            return new;
        end;
        $$;
        create trigger test_group_failure before update on public.enrollment_grades
        for each row execute function public.test_group_failure();
    """)
    changes = [grade(h.EA, 88), grade(fixture.E2, 87)]
    h.test('fallo en una segunda materia revierte la primera', publish(changes, token=token), error='P0001')
    h.check('no dejó notas ni auditorías parciales',
            saved_rows('enrollment_grades') == original_scores and saved_rows('enrollment_grade_events').strip() == '[]')
    h.sql("drop trigger test_group_failure on public.enrollment_grades; drop function public.test_group_failure()")

    result = json.loads(h.sql(publish([*changes, grade(new_enrollment, 0)], token=token)).stdout)
    h.check('corrige dos materias y publica un cero deliberado', result['saved'] and result['changed'] == 3)
    actual = {c['enrollment_id']: c['score'] for c in result['snapshot']['cells']}
    h.check('las tres notas aparecen como publicadas', actual[h.EA] == 88 and actual[fixture.E2] == 87 and actual[new_enrollment] == 0)
    h.test('usa el registro de publicación existente', f"select count(*) from public.enrollment_grade_events where actor_id='{h.C}' and action='publish'", '3')
    audit = saved_rows('enrollment_grade_events')
    h.test('reintentar una confirmación anterior no duplica cambios', publish(changes, token=token), error='PT409')
    no_op = json.loads(h.sql(publish(changes, token=result['snapshot']['token'], reason='')).stdout)
    h.check('las notas iguales no crean revisiones', no_op['changed'] == 0 and saved_rows('enrollment_grade_events') == audit)
    h.check('conserva datos de otras inscripciones', actual[alumni_enrollment] == 70 and actual[inactive_enrollment] == 91)
    h.check('las copias emitidas conservan sus notas y folio', saved_rows('report_card_issues') == original_issues)
    grades = saved_rows('enrollment_grades')
    h.sql(MIGRATION.read_text())
    h.check('reinstalar solo reemplaza funciones', saved_rows('enrollment_grades') == grades and saved_rows('report_card_issues') == original_issues)
    print('PASS matrices históricas, permisos, confirmación, auditoría y publicación atómica')


if __name__ == '__main__':
    try:
        main()
    finally:
        h.run('docker', 'rm', '-f', h.NAME, check=False)
