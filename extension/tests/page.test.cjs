const {test, before, after, beforeEach} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const {chromium} = require('playwright');
const scope = vm.createContext({});
vm.runInContext(readFileSync(require('node:path').join(__dirname, '../page.js'), 'utf8'), scope);
const claimPage = scope.claimPage;
const url = 'https://official.example/claim?case=test';
let browser, context, page;
before(async () => {
  browser = await chromium.launch({headless: true, executablePath: process.env.TEST_BROWSER_PATH || undefined});
  context = await browser.newContext();
  await context.route('**/*', route => route.fulfill({contentType: 'text/html', body: `
    <form onsubmit="window.submitted=true;return false">
    <label>First name<input name="firstName" required></label>
    <label>Email<input type="email" name="email"></label>
    <label>Signature<input name="signature"></label>
    <label>I certify<input type="checkbox"></label>
    <label>Account number<input name="accountNumber"></label>
    <fieldset disabled><label>Disabled<input name="disabled"></label></fieldset>
    <button type="submit">Submit</button></form>`}));
  page = await context.newPage();
});
beforeEach(async () => {await page.goto(url);});
after(async () => {await browser?.close();});
const checked = async request => {
  const result = await page.evaluate(claimPage, request);
  if (result.error) throw new Error(result.error);
  return result;
};
const inspect = () => checked({action: 'inspect', url});
const fill = (info, mappings, destination = url) => checked({
  action: 'fill', url: destination, fingerprint: info.fingerprint, mappings,
});

test('fills reviewed ordinary answers with input events, leaving legal and submit controls alone', async () => {
  const info = await inspect();
  assert.equal(info.fields[0].reason, '');
  assert.ok(info.fields[2].reason && info.fields[3].reason && info.fields[4].reason && info.fields[5].reason);
  await page.evaluate(() => {window.changes = 0; document.querySelector('input').addEventListener('change', () => window.changes++);});
  assert.deepEqual(await fill(info, [{index: 0, label: 'First name', value: 'Synthetic'}]), {completed: 1, uncertain: false});
  assert.equal(await page.locator('[name=firstName]').inputValue(), 'Synthetic');
  assert.equal(await page.locator('[name=signature]').inputValue(), '');
  assert.equal(await page.locator('[type=checkbox]').isChecked(), false);
  assert.equal(await page.evaluate(() => window.submitted), undefined);
  assert.equal(await page.evaluate(() => window.changes), 1);
});

test('blocks destination mismatch, changed fields, signatures and duplicate targets before filling', async () => {
  const info = await inspect();
  const ordinary = {index: 0, label: 'First name', value: 'Synthetic'};
  await assert.rejects(fill(info, [ordinary], url + '&different=1'), /exact reviewed HTTPS/);
  await assert.rejects(fill(info, [ordinary, {...ordinary}]), /mapped twice/);
  await assert.rejects(fill(info, [{index: 2, label: 'First name', value: 'Synthetic'}]), /unsafe/);
  await assert.rejects(fill(info, [{...ordinary, label: 'Certification'}]), /unsafe/);
  await page.locator('[name=firstName]').evaluate(el => {el.name = 'changed';});
  await assert.rejects(fill(info, [ordinary]), /fields changed/);
  assert.equal(await page.locator('[name=changed]').inputValue(), '');
});

test('validates the entire plan before changing values and never overwrites an existing answer', async () => {
  const info = await inspect();
  await assert.rejects(fill(info, [
    {index: 0, label: 'First name', value: 'Synthetic'},
    {index: 1, label: 'Email', value: 'not an email'},
  ]), /format/);
  assert.equal(await page.locator('[name=firstName]').inputValue(), '');
  await page.locator('[name=firstName]').fill('Existing');
  await assert.rejects(fill(info, [{index: 0, label: 'First name', value: 'Synthetic'}]), /different answer/);
});

test('reports uncertain results when a site changes answers while processing input', async () => {
  const info = await inspect();
  await page.locator('[name=firstName]').evaluate(el => el.addEventListener('input', () => {el.value = 'Changed by site';}));
  assert.deepEqual(await fill(info, [{index: 0, label: 'First name', value: 'Synthetic'}]), {completed: 1, uncertain: true});
});

test('stops before another field if the page changes its purpose during filling', async () => {
  const info = await inspect();
  await page.locator('[name=firstName]').evaluate(el => el.addEventListener('input', () => {
    document.querySelector('[name=email]').setAttribute('aria-describedby', 'legal');
    const note = document.createElement('span'); note.id = 'legal'; note.textContent = 'Certify under penalty of perjury';
    document.body.appendChild(note);
  }));
  assert.deepEqual(await fill(info, [
    {index: 0, label: 'First name', value: 'Synthetic'},
    {index: 1, label: 'Email', value: 'test@example.com'},
  ]), {completed: 1, uncertain: true});
  assert.equal(await page.locator('[name=email]').inputValue(), '');
});
