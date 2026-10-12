'use strict';

const workspaceOrigins = ['https://claims-agent-production-f24f.up.railway.app', 'http://localhost:8000'];
const $ = selector => document.querySelector(selector);
const sensitive = /sign(?:ature|ing|ed)|certif|attest|declar|perjury|consent|agree|acknowledg|release|password|passcode|captcha|verification|security.?code|\botp\b|\bssn\b|social.?security|bank|routing|account.?number|credit.?card|card.?number|passport/i;
let packet, inspection, targetTabId, reference;
const status = message => {$('#status').textContent = message;};
function resetReview() {
  packet = inspection = null;
  $('#review').hidden = true;
  $('#authorize').checked = false;
  $('#fill').disabled = true;
  $('#mappings').replaceChildren();
}
async function activeTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab?.id) throw new Error('Choose the page you want to inspect.');
  return tab;
}
async function inject(tabId, request) {
  const results = await chrome.scripting.executeScript({target: {tabId}, func: claimPage, args: [request]});
  const result = results[0]?.result;
  if (!result) throw new Error('Could not inspect this page. Open the extension again on the intended tab.');
  if (result.error) throw new Error(result.error);
  return result;
}
async function freshPacket() {
  const {claimReference} = await chrome.storage.session.get('claimReference');
  if (!claimReference || claimReference.expiresAt <= Date.now() || !workspaceOrigins.includes(claimReference.origin)) {
    await chrome.storage.session.remove('claimReference');
    throw new Error('Load the claim again from your workspace.');
  }
  reference = claimReference;
  const current = await inject(reference.appTabId, {action: 'packet', origin: reference.origin, claimId: reference.claimId});
  if (current.packet_hash !== reference.hash) throw new Error('The claim packet changed. Load and review it again.');
  return current;
}
function renderMappings() {
  const rows = [];
  for (const [index, field] of packet.fields.entries()) {
    if (sensitive.test(field.label)) continue;
    const label = document.createElement('label');
    const name = document.createElement('strong'); name.textContent = field.label;
    const answer = document.createElement('span'); answer.className = 'answer'; answer.textContent = String(field.value);
    const select = document.createElement('select'); select.dataset.answerIndex = index;
    select.add(new Option('Leave this answer manual', ''));
    for (const destination of inspection.fields.filter(f => !f.reason)) {
      select.add(new Option(`${destination.label} [${destination.type}]`, destination.index));
    }
    select.addEventListener('change', () => {$('#authorize').checked = false; $('#fill').disabled = true;});
    label.append(name, answer, select); rows.push(label);
  }
  $('#mappings').replaceChildren(...rows);
  $('#manual').replaceChildren(...inspection.fields.filter(f => f.reason).map(f => {
    const li = document.createElement('li'); li.textContent = `${f.label || f.type}: ${f.reason}`; return li;
  }));
  $('#title').textContent = packet.title;
  $('#destination').textContent = `Official destination: ${packet.official_url}`;
  $('#review').hidden = false;
}
async function run(button, operation) {
  button.disabled = true;
  try {await operation();} catch (error) {resetReview(); status(error.message);}
  finally {button.disabled = false; if (button.id === 'fill') button.disabled = true;}
}
$('#load').onclick = event => run(event.target, async () => {
  resetReview();
  await chrome.storage.session.remove('claimReference');
  const tab = await activeTab();
  const origin = new URL(tab.url).origin;
  if (!workspaceOrigins.includes(origin)) throw new Error('Open a claim review in your Settlement Claims workspace, then load it here.');
  const current = await inject(tab.id, {action: 'packet', origin});
  await chrome.storage.session.set({claimReference: {
    appTabId: tab.id, origin, claimId: current.claim_id, hash: current.packet_hash, expiresAt: Date.now() + 600000,
  }});
  status(`Loaded ${current.title}. Keep this workspace tab open, open the exact official form in another tab, then use Inspect official form.`);
});
$('#inspect').onclick = event => run(event.target, async () => {
  resetReview();
  packet = await freshPacket();
  const tab = await activeTab(); targetTabId = tab.id;
  inspection = await inject(targetTabId, {action: 'inspect', url: packet.official_url});
  renderMappings();
  status(`${inspection.fields.filter(f => !f.reason).length} ordinary fields available. Choose the destination for each answer and review the page's save behavior.`);
});
$('#authorize').onchange = () => {$('#fill').disabled = !$('#authorize').checked;};
$('#fill').onclick = event => run(event.target, async () => {
  if (!$('#authorize').checked || !inspection) throw new Error('Review and authorize the selected mappings first.');
  const current = await freshPacket();
  const tab = await activeTab();
  if (tab.id !== targetTabId) throw new Error('The active tab changed. Inspect again.');
  const mappings = [...$('#mappings').querySelectorAll('select')].filter(select => select.value !== '').map(select => {
    const answer = current.fields[Number(select.dataset.answerIndex)];
    return {index: Number(select.value), label: answer.label, value: answer.value};
  });
  const result = await inject(targetTabId, {action: 'fill', url: current.official_url, fingerprint: inspection.fingerprint, mappings});
  resetReview();
  await chrome.storage.session.remove('claimReference');
  status(result.uncertain ? `The site changed during filling after ${result.completed} fields. Some answers may have been saved. Check the page before continuing; do not retry blindly.` :
    `Filled and checked ${result.completed} ordinary answers. The site may have saved them. Review the full official form; complete signing, certifications, attachments, and submission yourself. No claim submission was performed by the extension.`);
});
$('#clear').onclick = event => run(event.target, async () => {
  await chrome.storage.session.remove('claimReference'); resetReview(); status('Loaded claim reference cleared.');
});
status('Open a claim review in the workspace to load it, or inspect the official form for a claim already loaded.');
