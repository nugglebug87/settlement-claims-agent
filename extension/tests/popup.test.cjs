const {test, before, after, beforeEach} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync, mkdirSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {chromium} = require('playwright');
const scope = vm.createContext({});
vm.runInContext(readFileSync(path.join(__dirname, '../page.js'), 'utf8'), scope);
const appOrigin = 'https://claims-agent-production-f24f.up.railway.app';
const officialUrl = 'https://official.example/claim?case=synthetic';
const id = '00000000-0000-0000-0000-000000000001';
let browser, context, app, official, popup, current, reference, activeId, requests;
before(async () => {
  browser = await chromium.launch({headless: true});
  context = await browser.newContext();
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === appOrigin) {
      if (url.pathname.endsWith('/browser-packet')) {
        requests++; return route.fulfill({json: current});
      }
      return route.fulfill({contentType: 'text/html', body: '<div id="browser-claim-context" data-claim-id="' + id + '">Synthetic claim review</div>'});
    }
    if (url.origin === 'https://official.example') {
      return route.fulfill({contentType: 'text/html', body: '<form><label>First name<input name="firstName"></label><label>Signature<input name="signature"></label><button>Submit</button></form>'});
    }
    if (url.origin === 'https://helper.test') {
      const name = url.pathname.slice(1);
      if (!['popup.html', 'popup.css', 'popup.js', 'page.js'].includes(name)) return route.abort();
      return route.fulfill({contentType: name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html',
        body: readFileSync(path.join(__dirname, '..', name))});
    }
    return route.abort();
  });
  app = await context.newPage(); official = await context.newPage(); popup = await context.newPage();
  await popup.setViewportSize({width: 416, height: 600});
  // Chrome toolbar actions cannot be driven in a headless test. Mock only that API boundary;
  // execute the real injected function in real browser tabs and use actual fetch responses.
  await popup.exposeFunction('testQuery', () => [{id: activeId, url: activeId === 1 ? app.url() : official.url()}]);
  await popup.exposeFunction('testStorageGet', () => ({claimReference: reference}));
  await popup.exposeFunction('testStorageSet', data => {reference = data.claimReference;});
  await popup.exposeFunction('testStorageRemove', () => {reference = undefined;});
  await popup.exposeFunction('testInjection', async (tabId, args) =>
    [{result: await (tabId === 1 ? app : official).evaluate(scope.claimPage, args[0])}]);
  await popup.addInitScript(() => {
    window.chrome = {
      tabs: {query: () => window.testQuery()},
      storage: {session: {get: () => window.testStorageGet(), set: data => window.testStorageSet(data), remove: () => window.testStorageRemove()}},
      scripting: {executeScript: options => window.testInjection(options.target.tabId, options.args)},
    };
  });
});
beforeEach(async () => {
  reference = undefined; activeId = 1; requests = 0;
  current = {claim_id: id, title: 'Synthetic claim', packet_hash: 'test-hash', official_url: officialUrl,
    fields: [{label: 'First name', kind: 'text', value: 'Synthetic'}, {label: 'Signature', kind: 'text', value: 'Do not fill'}]};
  await app.goto(appOrigin); await official.goto(officialUrl); await popup.goto('https://helper.test/popup.html');
});
after(async () => {await browser?.close();});
const waitStatus = text => popup.waitForFunction(text => document.querySelector('#status').textContent.includes(text), text);
async function loadAndInspect() {
  await popup.locator('#load').click(); await waitStatus('Loaded');
  assert.deepEqual(Object.keys(reference).sort(), ['appTabId', 'claimId', 'expiresAt', 'hash', 'origin']);
  activeId = 2;
  // Closing and reopening the toolbar popup loses answers but retains its session reference.
  await popup.reload(); await popup.locator('#inspect').click(); await waitStatus('ordinary fields available');
}

test('popup loads a reference, revalidates and fills only after reviewed transmission consent', async () => {
  await loadAndInspect();
  assert.equal(await popup.locator('#mappings select').count(), 1);
  assert.equal(await popup.locator('#fill').isDisabled(), true);
  await popup.locator('#mappings select').selectOption('0');
  assert.equal(await official.locator('[name=firstName]').inputValue(), '');
  await popup.locator('#authorize').check();
  mkdirSync(path.join(__dirname, '../../output'), {recursive: true});
  await popup.screenshot({path: path.join(__dirname, '../../output/browser-helper-review.png'), fullPage: true});
  await popup.locator('#fill').click(); await waitStatus('Filled and checked 1');
  assert.equal(await official.locator('[name=firstName]').inputValue(), 'Synthetic');
  assert.equal(await official.locator('[name=signature]').inputValue(), '');
  assert.equal(reference, undefined);
  assert.equal(requests, 3);
});

test('a changed packet blocks filling and an expired reference requires loading again', async () => {
  await loadAndInspect();
  await popup.locator('#mappings select').selectOption('0'); await popup.locator('#authorize').check();
  current.packet_hash = 'changed';
  await popup.locator('#fill').click(); await waitStatus('packet changed');
  assert.equal(await official.locator('[name=firstName]').inputValue(), '');
  reference.expiresAt = Date.now() - 1;
  await popup.locator('#inspect').click(); await waitStatus('Load the claim again');
  assert.equal(reference, undefined);
});
