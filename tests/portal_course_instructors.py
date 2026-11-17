"""Docentes en tarjetas y aula: SDK real, API ficticia, escritorio/móvil y temas."""
import asyncio,copy,json,shutil
from urllib.parse import urlparse
from playwright.async_api import async_playwright,expect
import portal_subjects as h
import portal_learning as l
import portal_course_organizer as o
import portal_class_directory as directory

NAMES=[{'name':'Pbro. Gerardo Iván Espinoza Franco'},{'name':'Maestra de ejemplo'}]


async def course_fixture(browser,role,mobile=False,instructors=NAMES):
    data=l.sample_data(role)
    data['course']['instructors']=copy.deepcopy(instructors)
    return await l.fixture(browser,role,mobile=mobile,route='curso/'+l.COURSE+'/inicio',data=data)


async def main():
    async with async_playwright()as pw:
        browser=await pw.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        for role in ['student','professor','control_escolar']:
            for mobile in [False,True]:
                c,page,state,data=await course_fixture(browser,role,mobile)
                teachers=page.locator('#learningCourseInstructors')
                await expect(teachers).to_be_visible()
                await expect(teachers.locator('h2')).to_have_text('Docentes del curso')
                assert await teachers.locator('li').all_text_contents()==[p['name']for p in NAMES]
                for theme in ['light','dark','oled']:
                    await page.evaluate("([theme])=>{document.documentElement.dataset.theme=theme;document.documentElement.dataset.themeTone=theme==='light'?'light':'dark'}",[theme])
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    color=await teachers.locator('li').first.evaluate('(e)=>getComputedStyle(e).color')
                    assert color=={'light':'rgb(36, 52, 71)','dark':'rgb(232, 238, 247)','oled':'rgb(240, 242, 246)'}[theme],color
                    if role in ['student','control_escolar']:
                        await page.evaluate('document.activeElement.blur();scrollTo(0,0)')
                        await page.screenshot(path=str(h.ARTIFACTS/f'docentes-aula-{role}-{mobile}-{theme}.png'),full_page=True)
                assert float(await teachers.locator('li').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)'))>=20
                # Cambiar de curso sustituye los nombres y no conserva el docente anterior.
                async def other(route):
                    args=route.request.post_data_json
                    if args.get('p_resource')!='course' or args.get('p_course')!=l.OTHER:return await route.fallback()
                    result=copy.deepcopy(data['course']);result['course'].update(data['courses'][1]);result['instructors']=[{'name':'Docente de la segunda materia'}]
                    return await route.fulfill(status=200,content_type='application/json',body=json.dumps(result))
                await c.route(h.API+'/rest/v1/rpc/portal_learning_read',other)
                await page.evaluate("location.hash='curso/"+l.OTHER+"/inicio'")
                await expect(teachers.locator('li')).to_have_text('Docente de la segunda materia')
                assert not state['errors'] and not state['route_errors'] and not data['errors']
                assert not data['writes']
                await c.close()
                print('PASS aula '+role+(' móvil'if mobile else' escritorio')+' en claro/oscuro/OLED',flush=True)

        for value,expected,state_name in [([], 'Pendiente de asignación','empty'),(None,'Nombre del docente no disponible. Actualiza la información.','unavailable'),([{'name':'<img src=x onerror=alert(1)> Maestra & ejemplo'}],'<img src=x onerror=alert(1)> Maestra & ejemplo','assigned')]:
            c,page,state,data=await course_fixture(browser,'student',instructors=value)
            teachers=page.locator('#learningCourseInstructors');await expect(teachers).to_contain_text(expected)
            await expect(teachers).to_have_attribute('data-instructors-state',state_name)
            assert await teachers.locator('img,script,svg').count()==0
            assert not state['errors'] and not state['route_errors']
            await c.close()
        print('PASS sin asignación, consulta no disponible y nombres tratados como texto',flush=True)

        for mobile in [False,True]:
            c,page,state,admin,data=await o.fixture(browser,mobile)
            data['classes'][0]['instructors']=NAMES
            data['classes'][0]['name']='Catecismo I'
            data['classes'][1]['instructors']=[]
            await directory.enter(page)
            await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
            card=page.locator('[data-class-id="'+data['classes'][0]['id']+'"]')
            await expect(card.locator('.course-instructors')).to_contain_text(NAMES[0]['name'])
            assert await card.locator('.course-instructors li').all_text_contents()==[p['name']for p in NAMES]
            assert await card.locator('.course-instructors').evaluate('(e)=>e.previousElementSibling.textContent')=='Ago-Dic 2026'
            assert await card.locator('.course-instructors').evaluate('(e)=>e.nextElementSibling.textContent')=='Activa'
            await page.evaluate("location.hash='materias-asignadas'")
            await page.locator('#classDirectoryGroups [data-course="CI-1"]').click()
            await expect(card.locator('.course-instructors')).to_contain_text(NAMES[0]['name'])
            await page.evaluate("document.documentElement.dataset.theme='dark';document.documentElement.dataset.themeTone='dark'")
            await page.evaluate('document.activeElement.blur();scrollTo(0,0)')
            await page.screenshot(path=str(h.ARTIFACTS/f'docentes-bloques-{mobile}.png'),full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not state['errors'] and not state['route_errors']
            await c.close()
        print('PASS docentes entre periodo y estado en Clases y Mis cursos, escritorio/móvil',flush=True)
        await browser.close()


if __name__=='__main__':
    h.prepare()
    try:asyncio.run(main())
    finally:h.server.shutdown();h.server.server_close();h.TEMP.cleanup()
