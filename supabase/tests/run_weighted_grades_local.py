#!/usr/bin/env python3
"""Ponderaciones, privacidad y publicación atómica en PostgreSQL desechable."""
import copy,json
import run_kardex_local as k
h=k.h

def query(action,data,who=None):
    return h.actor(who or h.P,"select public.portal_gradebook_write("+h.quote(h.L)+","+h.quote(action)+","+h.quote(json.dumps(data))+"::jsonb)",commit=True)
def save(action,data,who=None):
    return json.loads(h.sql(query(action,data,who)).stdout)
def read(who=None,resource='book',course=None,offset=0):
    return json.loads(h.sql(h.actor(who or h.P,"select public.portal_gradebook_read("+h.quote(course or h.L)+","+h.quote(resource)+f",{offset},30)")).stdout)
def student(who=None):return read(who)['students'][0]
def final_data(s=None,**kw):
    s=s or student();return {'confirmed':True,'reason':'Cierre calculado y revisado por el profesor','students':[{'id':s['enrollment_id'],'token':s['summary'].get('token'),**kw}]}

def main():
    k.bootstrap()
    h.sql(f"insert into public.teaching_assignments(id,professor_id,subject_id,period_id) values('{h.uid(92)}','{h.P}','{h.S2}','{h.T}')")
    activities=[]
    for name,category in [('Tarea 1','tasks'),('Tarea 2','tasks'),('Parcial','exams'),('Final','exams'),('Proyecto','projects'),('Participación','participation'),('Práctica','practice')]:
        r=h.write(h.P,'assignment_save',h.L,{'title':name,'published':True,'grading_category':category,'requires_submission':category in ['tasks','projects','practice']})
        activities.append(r['id'])
    categories=[{'code':c,'weight':w,'mode':'custom' if c=='exams' else 'equal'} for c,w in [('tasks',30),('exams',50),('projects',20),('participation',0)]]
    scheme={'categories':categories,'items':[{'id':aid,'category':c,'share':w} for aid,c,w in zip(activities,['tasks','tasks','exams','exams','projects','participation','practice'],[1,1,40,60,1,1,1])]}
    for who in [h.A,h.IC,h.N]:h.test('cannot configure '+who,query('scheme_save',{'schema':scheme,'revision':0},who),error='42501')
    for resource in ['book',None,'other']:
        if resource=='book':h.test('student cannot read book',h.actor(h.A,f"select public.portal_gradebook_read('{h.L}','book')"),error='42501')
    h.test('anonymous forbidden',h.actor(None,f"select public.portal_gradebook_read('{h.L}','own')",role='anon'),error='42501')
    for name in ['learning_grading_schemes','learning_grade_exemptions','learning_final_calculations']:
        h.test('table private '+name,f"select has_table_privilege('authenticated','public.{name}','SELECT,INSERT,UPDATE,DELETE')",'f')
    for function in ['_grading_calculate(uuid,uuid,boolean)','_grading_validate(uuid,jsonb)','_learning_write_before_weights(text,uuid,jsonb)','_learning_read_before_weights(text,uuid,integer,integer)','_publish_grade_before_weights(uuid,uuid,integer)','_save_grade_before_weights(uuid,uuid,numeric,integer)']:
        h.test('helper private '+function,"select has_function_privilege('authenticated',"+h.quote('public.'+function)+",'EXECUTE')",'f')
    h.check('unconfigured means no invented average',not read(h.A,'own')['summary']['configured'])
    h.check('legacy final untouched',read(h.A,'own')['final_score']==80)
    save('scheme_save',{'schema':scheme,'revision':0})
    h.check('draft does not appear to student',not read(h.A,'own')['summary']['configured'] and 'draft' not in read(h.A,'own'))
    h.test('stale scheme revision',query('scheme_save',{'schema':scheme,'revision':0}),error='PT409')
    invalid=copy.deepcopy(scheme);invalid['categories'][0]['weight']=40
    save('scheme_save',{'schema':invalid,'revision':1})
    h.test('weights must add to 100',query('scheme_publish',{'schema':invalid,'revision':2,'confirmed':True}),error='22023')
    invalid=copy.deepcopy(scheme);invalid['items'][2]['share']=50
    save('scheme_save',{'schema':invalid,'revision':2})
    h.test('custom shares must add to 100',query('scheme_publish',{'schema':invalid,'revision':3,'confirmed':True}),error='22023')
    save('scheme_save',{'schema':scheme,'revision':3})
    h.test('explicit publication required',query('scheme_publish',{'schema':scheme,'revision':4}),error='22023')
    save('scheme_publish',{'schema':scheme,'revision':4,'confirmed':True})
    h.check('configured, no grades remains null',student()['summary']['average'] is None)
    def assess(i,score,publish=True):
        s=student();g=next(x for x in s['grades'] if x['assignment_id']==activities[i]);
        return save('assessment_save',{'enrollment_id':k.E2,'assignment_id':activities[i],'revision':g['revision'],'score':score,'feedback':'Comentario','publish':publish,'token':s['summary']['token']})
    assess(0,100);assess(1,45)
    own=read(h.A,'own')['summary']
    h.check('two equally weighted tasks average 72.5',own['average']==72.5 and own['coverage']==30,own)
    h.check('pending assessments are not zero',own['categories'][1]['average'] is None and own['pending']==3)
    h.test('cannot finalize pending exams',query('final_publish',final_data()),error='22023')
    for i,s in [(2,80),(3,80),(4,90),(5,0),(6,0)]:assess(i,s)
    s=student();h.check('weighted result 79.75',s['summary']['average']==79.75 and s['summary']['coverage']==100 and s['summary']['ready'],s['summary'])
    h.check('practice and 0 percent category excluded',s['summary']['categories'][3]['average'] is None)
    h.check('custom exam effective weights 20 and 30',[(x['weight']) for x in s['summary']['items'] if x['category']=='exams']==[20,30])
    assess(2,0,publish=False)
    s=student();h.check('draft grade changes private preview only',s['summary']['average']==79.75 and s['draft_summary']['average']==63.75)
    own=read(h.A,'own');h.check('student sees published 80, never draft 0',next(x for x in own['assignments'] if x['id']==activities[2])['score']==80)
    h.check('student receives no draft flags or token',all(x not in own['summary'] for x in ['unpublished','ready','reasons','token']))
    h.test('draft grade blocks final confirmation',query('final_publish',final_data()),error='22023')
    assess(2,80)
    before=student();assess(0,99)
    h.test('stale review rejected',query('final_publish',final_data(before)),error='PT409');assess(0,100)
    s=student();save('assessment_save',{'enrollment_id':k.E2,'assignment_id':activities[1],'token':s['summary']['token'],'exempt':True,'reason':'Actividad justificada por el profesor'})
    h.check('exemption redistributes within category only',student()['summary']['average']==88,student()['summary'])
    s=student();save('assessment_save',{'enrollment_id':k.E2,'assignment_id':activities[0],'token':s['summary']['token'],'exempt':True,'reason':'Exención justificada'})
    h.check('fully exempt category blocks final',not student()['summary']['ready'] and student()['summary']['coverage']==70)
    assess(0,100);assess(1,45)
    s=student()
    batch=[{'enrollment_id':k.E2,'assignment_id':activities[i],'revision':next(g['revision'] for g in s['grades'] if g['assignment_id']==activities[i]),'token':s['summary']['token'],'score':v,'feedback':'Comentario'} for i,v in [(0,90),(1,999)]]
    h.test('invalid bulk entry rolls back whole batch',query('assessments_save',{'items':batch,'publish':True}),error='22023')
    h.check('no partial bulk write',student()['summary']['average']==79.75)
    batch[1]['score']=50
    save('assessments_save',{'items':batch,'publish':False})
    h.check('bulk drafts preserve published average',student()['summary']['average']==79.75 and student()['draft_summary']['average']==79)
    assess(0,100);assess(1,45)
    invalid_final=final_data();invalid_final['students'].append({'id':h.EA,'token':'invalid'})
    h.test('invalid final batch is atomic',query('final_publish',invalid_final),error='42501')
    h.test('failed final batch preserves previous grade',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'80.00')
    save('final_publish',final_data())
    h.test('confirmed final feeds existing kardex table',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'79.75')
    h.test('legacy grade publisher cannot bypass weighted review',h.actor(h.P,f"select public.publish_teaching_grade('{h.uid(92)}','{k.E2}',1)"),error='22023')
    h.test('legacy manual final draft cannot bypass weighted review',h.actor(h.P,f"select public.save_teaching_grade('{h.uid(92)}','{k.E2}',99,1)"),error='22023')
    h.check('final snapshot records calculation',bool(json.loads(h.sql(f"select snapshot from public.learning_final_calculations where enrollment_id='{k.E2}'").stdout)['schema']))
    h.test('override requires reason',query('final_publish',{**final_data(override=90),'reason':''}),error='22023')
    save('final_publish',final_data(override=90));h.test('explicit override saved',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'90.00')
    h.check('override audited',int(h.sql("select count(*) from public.learning_audit where action='weighted_final_publish'").stdout)==2)
    changed=copy.deepcopy(scheme);changed['categories'][0]['weight']=20;changed['categories'][3]['weight']=10
    revision=read()['revision'];save('scheme_save',{'schema':changed,'revision':revision})
    h.test('changing published criteria requires reason',query('scheme_publish',{'schema':changed,'revision':revision+1,'confirmed':True}),error='22023')
    save('scheme_publish',{'schema':changed,'revision':revision+1,'confirmed':True,'reason':'Revisión de criterios acordada con el grupo'})
    h.check('zero in participation is real evaluated score',student()['summary']['average']==72.5 and student()['summary']['coverage']==100)
    h.test('reweighting does not silently replace final',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'90.00')
    h.sql(f"insert into public.learning_assignments(course_id,title,published) values('{h.L}','Actividad nueva',false)")
    h.check('new unclassified activity blocks final',not student()['summary']['ready'])
    h.test('previously published final remains intact',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'90.00')
    h.test('no submission for classroom exam',h.actor(h.A,h.wquery('submit',h.L,{'assignment_id':activities[2],'body':'Prueba'}),commit=True),error='22023')
    h.test('teacher cannot access another course',h.actor(h.P,f"select public.portal_gradebook_read('{h.K}')"),error='42501')
    h.check('Control Escolar sees same calculation',student(h.C)['summary']['average']==72.5)
    h.test('student cannot grade peer',query('assessment_save',{'enrollment_id':k.E2,'assignment_id':activities[0]},h.A),error='42501')
    h.test('student cannot finalize',query('final_publish',final_data(),h.A),error='42501')
    h.test('invalid pagination',h.actor(h.C,f"select public.portal_gradebook_read('{h.L}','book',-1)"),error='22023')
    s=student();g=next(g for g in s['grades'] if g['assignment_id']==activities[0])
    save('assessment_unpublish',{'enrollment_id':k.E2,'assignment_id':activities[0],'revision':g['revision'],'token':s['summary']['token']})
    h.check('withdrawing a note recalculates published progress',student()['summary']['coverage']==90 and next(a for a in read(h.A,'own')['assignments'] if a['id']==activities[0])['score'] is None)
    h.test('withdrawing an activity grade preserves published final',f"select score from public.enrollment_grades where enrollment_id='{k.E2}'",'90.00')
    other=h.uid(160)
    h.sql(f"insert into public.course_offerings(id,subject_id,period_id) values('{other}','{h.S2}','{k.T2}'); insert into public.enrollments(student_id,subject_id,period_id) values('{h.A}','{h.S2}','{k.T2}')")
    h.check('weights never carry to another period without configuration',not read(h.A,'own',course=other)['summary']['configured'])
    h.test('unassigned teacher cannot read another active class',h.actor(h.P,f"select public.portal_gradebook_read('{other}')"),error='42501')
    preview=json.loads(h.sql(h.actor(h.C,f"select public.portal_admin_delete_preview('class','{h.L}')")).stdout)
    h.sql(h.actor(h.C,f"select public.portal_admin_delete('class','{h.L}','{preview['token']}','ELIMINAR')",commit=True))
    h.test('explicit class deletion cleans new scheme',f"select count(*) from public.learning_grading_schemes where course_id='{h.L}'",'0')
    h.test('explicit class deletion cleans final calculation metadata',f"select count(*) from public.learning_final_calculations where enrollment_id='{k.E2}'",'0')
    print('PASS',h.checks,'checks')

if __name__=='__main__':
    try:main()
    finally:h.run('docker','rm','-f',h.NAME,check=False)
