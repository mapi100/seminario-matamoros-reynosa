"""Privacidad, filtros y avisos de Actividad en PostgreSQL desechable."""
import json

import run_kardex_local as fixture

h = fixture.h
q = h.quote
MIGRATION = h.ROOT / 'supabase/migrations/20261127010000_people_filters_and_activity_notices.sql'
READER = h.uid(190)
ASSIGNMENT = h.uid(191)
FIRST_ENROLLMENT = h.uid(192)


def read(actor=h.C, count=False, before=None):
    return json.loads(h.sql(h.actor(actor,
        f"select public.portal_control_activity_read({str(count).lower()},{q(before)})")).stdout)


def mark(actor=h.C, notice=None, all_notices=False):
    return json.loads(h.sql(h.actor(actor,
        f"select public.portal_control_activity_mark({q(notice)},{str(all_notices).lower()})", commit=True)).stdout)


def people(role, search='', offset=0, limit=30):
    return json.loads(h.sql(h.actor(h.C,
        f"select public.portal_people_by_role({q(role)},{q(search)},{offset},{limit})")).stdout)


def school_save(enrollment, score, commit=True):
    snapshot = json.loads(h.sql(h.actor(h.C, f"select public.portal_school_finals_read('{h.K}')")).stdout)
    items = q(json.dumps([{'enrollment_id': enrollment, 'score': score}]))
    return h.sql(h.actor(h.C, f"select public.portal_school_finals_save('{h.K}',"
        f"{q(snapshot['token'])},{items}::jsonb,'Acta de prueba revisada')", commit=commit))


def student_save(who, details):
    source = json.loads(h.sql(h.actor(who, f"select public.portal_student_record_read('record','{h.A}')")).stdout)
    body = {
        'full_name': source['student']['full_name'], 'birth_date': source['identity']['birth_date'],
        'curp': source['identity']['curp'], 'details': details
    }
    return h.sql(h.actor(who, f"select public.portal_student_record_save('{h.A}',"
        f"{q(source['token'])},{q(json.dumps(body))}::jsonb)", commit=True))


def main():
    fixture.bootstrap()
    h.check('la instalación no genera avisos de notas históricas', read() == {'items': [], 'unread': 0, 'next_before': None})
    h.sql(f"""
        insert into auth.users(id,email) values('{READER}','segunda-control@example.invalid');
        insert into public.profiles(id,full_name,role,active) values('{READER}','Control de prueba dos','control_escolar',true);
        update public.course_offerings set active=true where id='{h.K}';
        update public.enrollments set active=true where id='{h.EA}';
        insert into public.teaching_assignments(id,professor_id,subject_id,period_id,active)
            values('{ASSIGNMENT}','{h.P}','{h.S}','{h.T}',true);
        insert into public.course_formation_groups(course_id,group_code) values('{h.K}','CI-1');
        insert into public.student_formation_periods(student_id,period_id,stage_code,semester,updated_by)
            values('{h.A}','{h.T}','introductorio',1,'{h.C}');
    """)

    first, second = people('student', limit=1), people('student', offset=1, limit=1)
    h.check('filtra en servidor, pagina y conserva inactivos',
            first['has_more'] and not second['has_more'] and
            first['items'][0]['id'] == h.A and second['items'][0]['id'] == h.B and not second['items'][0]['active'])
    h.check('filtra por rol exacto y cuenta inactivos de Control',
            {item['id'] for item in people('control_escolar')['items']} == {h.C, h.IC, READER}
            and [item['id'] for item in people('professor')['items']] == [h.P])
    h.check('buscar por nombre y correo dentro del filtro',
            [item['id'] for item in people('student', 'ALFA')['items']] == [h.A] and
            [item['id'] for item in people('control_escolar', 'segunda-control@')['items']] == [READER] and
            not people('professor', 'segunda-control@')['items'])
    h.test('rechaza un rol inválido', h.actor(h.C, "select public.portal_people_by_role('cualquiera')"), error='22023')
    for who in [h.A, h.P, h.IC, h.N]:
        for sql in [
            "select public.portal_people_by_role('student')",
            "select public.portal_control_activity_read()",
            "select public.portal_control_activity_mark(null,true)"
        ]:
            h.test('rol distinto o inactivo no accede', h.actor(who, sql), error='42501')
    for sig in [
        'portal_people_by_role(text,text,integer,integer)', 'portal_control_activity_read(boolean,bigint)',
        'portal_control_activity_mark(bigint,boolean)', '_control_activity_unread(uuid)'
    ]:
        h.test('RPC privada para anónimo', f"select has_function_privilege('anon','public.{sig}','execute')", 'f')
    for table in ['control_activity_notices', 'control_activity_notice_reads']:
        h.test('tablas privadas', f"select has_table_privilege('authenticated','public.{table}','SELECT,INSERT,UPDATE,DELETE')", 'f')
        h.test('tablas con RLS', f"select relrowsecurity from pg_class where oid='public.{table}'::regclass", 't')
    h.test('secuencia privada', "select has_sequence_privilege('authenticated','public.control_activity_notices_id_seq','USAGE,SELECT,UPDATE')", 'f')

    h.sql(h.actor(h.P, f"select public.save_teaching_grade('{ASSIGNMENT}','{h.EA}',88,0)", commit=True))
    h.check('borrador de profesor no notifica', read()['unread'] == 0)
    h.sql(h.actor(h.P, f"select public.publish_teaching_grade('{ASSIGNMENT}','{h.EA}',1)", commit=True))
    h.check('corrección docente notifica exactamente una vez', read()['unread'] == 1)

    h.sql(f"""
        update public.profiles set active=true where id='{h.B}';
        insert into public.enrollments(id,student_id,subject_id,period_id) values('{FIRST_ENROLLMENT}','{h.B}','{h.S}','{h.T}');
        insert into public.enrollment_grades(enrollment_id,score,published) values('{FIRST_ENROLLMENT}',75,false);
    """)
    school_save(FIRST_ENROLLMENT, 80)
    school_save(h.EA, 88)
    h.check('primera publicación y repetir el mismo valor no notifican', read()['unread'] == 1)
    school_save(h.EA, 90, commit=False)
    h.check('corrección revertida no deja aviso ni cambia la nota', read()['unread'] == 1)
    school_save(h.EA, 90)
    h.check('corrección de Control Escolar notifica', read()['unread'] == 2)

    group = json.loads(h.sql(h.actor(h.C, f"select public.portal_group_final_grades_read('{h.T}','CI-1')")).stdout)['snapshot']
    items = q(json.dumps([{'enrollment_id': h.EA, 'score': 91}]))
    h.sql(h.actor(h.C, f"select public.portal_group_final_grades_save('{h.T}','CI-1',"
        f"{q(group['token'])},{items}::jsonb,'Revisión grupal de prueba',true)", commit=True))
    h.check('la corrección por grupo produce un solo aviso por nota', read()['unread'] == 3)

    student_save(h.A, {'phone': '5550100000'})
    student_save(h.A, {'phone': '5550100000'})
    student_save(h.C, {'phone': '5550100001'})
    h.sql(h.actor(h.C, f"insert into public.management_events(actor_id,action,entity_id,details) "
        f"values('{h.C}','assignment_state','{ASSIGNMENT}','{{}}')", role='postgres', commit=True))
    h.sql(h.actor(h.A, f"insert into public.management_events(actor_id,action,entity_id,details) "
        f"values('{h.A}','student_file_uploaded','{h.A}','{{}}')", role='postgres', commit=True))
    page = read()
    h.check('edición propia efectiva sí, otras acciones del expediente y actividad no',
            page['unread'] == 4 and [x['kind'] for x in page['items']] == ['personal_updated'] + ['final_corrected'] * 3)
    h.check('aviso no expone valores personales ni notas',
            all(set(x) == {'id','kind','created_at','student_name','subject_name','period_name','read'} for x in page['items'])
            and '5550100000' not in json.dumps(page['items']))
    h.check('consulta de campana solo devuelve el número', read(count=True) == {'unread': 4, 'items': [], 'next_before': None})

    latest = page['items'][0]['id']
    h.check('marca uno', mark(notice=latest)['unread'] == 3 and read()['items'][0]['read'])
    h.check('leer es independiente por cuenta', read(READER)['unread'] == 4 and not read(READER)['items'][0]['read'])
    h.check('marca uno es idempotente', mark(notice=latest)['unread'] == 3)
    h.test('no permite marcar todos por omisión', h.actor(h.C, "select public.portal_control_activity_mark()"), error='22023')

    # Exceder una página sin crear notas artificiales en los registros académicos.
    h.sql(f"insert into public.control_activity_notices(kind,student_id) "
          f"select 'personal_updated','{h.A}' from generate_series(1,23)")
    first = read()
    second = read(before=first['next_before'])
    h.check('avisa y pagina sin repetir elementos', len(first['items']) == 20 and len(second['items']) == 7 and
            set(x['id'] for x in first['items']).isdisjoint(x['id'] for x in second['items']))
    h.check('marcar todo incluye avisos fuera de la primera página', mark(all_notices=True)['unread'] == 0 and
            all(x['read'] for x in read(before=first['next_before'])['items']))
    h.check('marca todo no borra avisos ni cambia otra cuenta', len(read()['items']) == 20 and read(READER)['unread'] == 27)

    school_save(h.EA, 92)
    h.check('un aviso nuevo reaparece después de marcar todo', read()['unread'] == 1 and not read()['items'][0]['read'])
    h.sql(MIGRATION.read_text())
    h.check('reinstalación conserva los estados y no crea duplicados', read()['unread'] == 1 and read(READER)['unread'] == 28)
    print('PASS filtros completos, fuentes exactas, permisos y lecturas por cuenta')


if __name__ == '__main__':
    try:
        main()
    finally:
        h.run('docker', 'rm', '-f', h.NAME, check=False)
