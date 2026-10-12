'use strict';

// Self-contained because Chrome serializes this function into the isolated page world.
async function claimPage(request) {
  try {
  const normalize = value => {const url = new URL(value); url.hash = ''; return url.href;};
  const blocked = /sign(?:ature|ing|ed)|certif|attest|declar|perjury|consent|agree|acknowledg|release|password|passcode|captcha|verification|security.?code|\botp\b|\bssn\b|social.?security|bank|routing|account.?number|credit.?card|card.?number|passport/i;
  if (request.action === 'packet') {
    if (location.origin !== request.origin) throw new Error('Workspace tab changed. Load the claim again.');
    const id = request.claimId || document.querySelector('#browser-claim-context')?.dataset.claimId;
    if (!id || !/^[a-f0-9-]{36}$/.test(id)) throw new Error('Open a claim review in your workspace first.');
    const response = await fetch(`/api/claims/${id}/browser-packet`, {credentials: 'same-origin', cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not validate this claim.');
    return data;
  }
  if (location.protocol !== 'https:' || normalize(location.href) !== normalize(request.url)) {
    throw new Error('Open the exact reviewed HTTPS official form URL. Redirected forms need source review in the workspace.');
  }
  const elements = [...document.querySelectorAll('input,textarea,select')];
  const describe = (element, index) => {
    const labels = [...(element.labels || [])].map(label => label.textContent.trim());
    const described = (element.getAttribute('aria-describedby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.textContent || '').join(' ');
    const aria = element.getAttribute('aria-label') || (element.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.textContent || '').join(' ');
    const label = labels.join(' ') || aria.trim() || element.placeholder || element.name || element.id;
    const context = [label, described, element.name, element.id, element.autocomplete,
      element.closest('fieldset')?.querySelector('legend')?.textContent].join(' ');
    const type = element.tagName === 'TEXTAREA' ? 'textarea' : element.type;
    const visible = !!element.getClientRects().length && getComputedStyle(element).visibility === 'visible';
    const supported = ['text', 'email', 'tel', 'number', 'date', 'textarea'].includes(type);
    const reason = blocked.test(context) ? 'Sensitive or legal field; complete manually' :
      !visible || element.matches(':disabled') || element.readOnly ? 'Hidden, disabled, or read-only' :
      !supported ? 'Checkboxes, choices, uploads, and buttons stay manual' : !label ? 'Unlabelled field' : '';
    return {index, label: label.slice(0, 500), type, name: element.name, id: element.id, required: element.required, reason};
  };
  const fields = elements.map(describe);
  const fingerprint = JSON.stringify(fields);
  if (request.action === 'inspect') return {fields, fingerprint};
  if (request.action !== 'fill' || request.fingerprint !== fingerprint) {
    throw new Error('The page fields changed. Inspect and review the mappings again.');
  }
  if (!request.mappings?.length || request.mappings.length > 50) throw new Error('Select at least one answer.');
  const seen = new Set();
  const plan = request.mappings.map(mapping => {
    const field = fields[mapping.index], element = elements[mapping.index];
    if (!field || field.reason || seen.has(mapping.index) || blocked.test(mapping.label)) {
      throw new Error('A selected field is unsafe, unsupported, or mapped twice.');
    }
    seen.add(mapping.index);
    if (!['string', 'number'].includes(typeof mapping.value)) throw new Error('Only recorded text and numeric answers can be filled.');
    const value = String(mapping.value);
    if (value.length > 10000 || (element.maxLength >= 0 && value.length > element.maxLength)) {
      throw new Error(`${field.label}: answer exceeds the field length.`);
    }
    if (element.value && element.value !== value) throw new Error(`${field.label}: already contains a different answer. Review it manually.`);
    // Validate on a detached clone before changing any live field.
    const probe = element.cloneNode(false); probe.value = value;
    if (probe.value !== value || !probe.checkValidity()) throw new Error(`${field.label}: answer does not fit this field's format.`);
    return {element, value, index: mapping.index, previous: element.value};
  });
  let completed = 0;
  for (const {element, value, index, previous} of plan) {
    if (!element.isConnected || element.value !== previous ||
        JSON.stringify(describe(element, index)) !== JSON.stringify(fields[index])) {
      return {completed, uncertain: true};
    }
    const prototype = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value);
    element.dispatchEvent(new Event('input', {bubbles: true}));
    element.dispatchEvent(new Event('change', {bubbles: true}));
    completed++;
    if (element.value !== value) return {completed, uncertain: true};
  }
  return {completed, uncertain: false};
  } catch (error) {
    return {error: error.message};
  }
}
