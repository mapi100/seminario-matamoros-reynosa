// Reparto reproducible, cambios incrementales y rutas locales. Sin red ni DOM real.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const runtime = readFileSync(new URL('../portal/course-colors.js', import.meta.url), 'utf8');
const generated = readFileSync(new URL('../portal/course-images.js', import.meta.url), 'utf8');
const load = entries => {
    const sandbox = { window: {}, document: { currentScript: { src: 'https://example.invalid/seminario/portal/course-colors.js' } }, URL };
    vm.createContext(sandbox);
    vm.runInContext(generated, sandbox);
    if (entries) sandbox.window.PortalCourseImages = entries;
    vm.runInContext(runtime, sandbox);
    return sandbox.window;
};
const select = (api, code, period = 'Ago-Dic 2026') => {
    const values = new Map();
    api.PortalCourseColors.apply({ style: { setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key) } }, code, period);
    return Object.fromEntries(values);
};
const current = load();
assert.ok(current.PortalCourseImages.length > 0);
const entries = Array.from(current.PortalCourseImages);
const reordered = load([...entries].reverse());
const nextPhoto = { src: 'images/fotografia-agregada-en-el-futuro.jpg', position: '50% 50%' };
const expanded = load([...entries, nextPhoto]);
const chosen = new Set();
let adopted = 0, preserved = 0, differentPeriods = 0;
for (let i = 0; i < 2000; i++) {
    const key = 'MATERIA-' + i;
    const before = select(current, key);
    assert.deepEqual(before, select(current, key));
    assert.deepEqual(before, select(reordered, key));
    const after = select(expanded, key);
    if (after['--course-image'] !== before['--course-image']) {
        assert.ok(after['--course-image'].endsWith('/fotografia-agregada-en-el-futuro.jpg")'));
        adopted++;
    } else preserved++;
    if (before['--course-image'] !== select(current, key, 'Ene-Jun 2027')['--course-image']) differentPeriods++;
    chosen.add(before['--course-image']);
}
assert.ok(adopted > 0 && preserved > 0);
assert.ok(differentPeriods > 1000);
assert.equal(chosen.size, entries.length);
console.log(`PASS 2000 clases: reparto estable; ${adopted} adoptan una foto nueva y ${preserved} conservan su portada.`);

const safe = load([{ src: 'images/foto%20Jos%C3%A9%20%231.jpg', position: '50% 30%' },
    { src: 'https://evil.invalid/a.jpg', position: '50% 50%' },
    { src: 'images/../outside.jpg', position: '50% 50%' },
    { src: 'images/a.jpg?query=1', position: '50% 50%' },
    { src: 'images/%2e%2e/outside.jpg', position: '50% 50%' }]);
assert.ok(select(safe, 'MATERIA')['--course-image'].includes('foto%20Jos%C3%A9%20%231.jpg'));
const empty = select(load([]), 'MATERIA');
assert.ok(empty['--course-color']);
assert.equal(empty['--course-image'], undefined);
console.log('PASS nombres especiales, rutas de imágenes locales y color de respaldo sin catálogo.');
