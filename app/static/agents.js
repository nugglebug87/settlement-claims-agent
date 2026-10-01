'use strict';

async function renderAgents() {
  heading('Your settlement agents.','Search for opportunities, then prepare their official form answers for your approval.');
  const data=await api('/sources');
  const ready=state.data.opportunities.filter(o=>o.verified&&o.classification==='open_claim'&&o.eligibility.status==='eligible');
  $('#view').innerHTML=`<div class="grid-2"><section class="panel panel-body"><p class="eyebrow">CLAIMS SEARCH AGENT</p><h2>Find a possible match.</h2><p>Read a configured discovery source and compare candidates with your saved eligibility facts. New discoveries require official source review.</p><form id="agent-search"><label>Search source<select name="source" required>${data.sources.map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${esc(readable(s.stream))}</option>`).join('')}</select></label><button class="primary" type="submit" ${data.sources.length?'':'disabled'}>Search for claims</button></form><p class="fine">${data.sources.length?'Search reads the selected source now, including paused sources. It does not enable daily monitoring.':'Add discovery sources before running a search.'}</p>${button('view-sources','Manage sources','secondary')}<div id="agent-search-result" role="status"></div></section><section class="panel panel-body"><p class="eyebrow">FORM FILLER AGENT</p><h2>Prepare your answers.</h2><p>Map the official form’s fields to your saved profile facts. The agent fills a review packet without guessing missing answers.</p><form id="agent-fill"><label>Verified eligible settlement<select name="opportunity" required>${ready.map(o=>`<option value="${esc(o.id)}">${esc(o.title)}</option>`).join('')}</select></label><button class="primary" type="submit" ${ready.length?'':'disabled'}>Set up form & fill answers</button></form><p class="fine">${ready.length?'Each claim needs your review and approval.':'Review an official source and resolve eligibility answers to unlock preparation.'}</p>${button('view-opportunities','Review opportunities','secondary')}</section></div><div class="notice">Official website autofill, signature execution, and automatic submission are not connected yet. This agent prepares form answers inside your private app. After approval, open the official form and complete the filing there; record the actual confirmation afterward.</div><div class="section-title"><h2>Matches from your recorded facts</h2></div><div class="panel">${opportunitiesTable(state.data.opportunities.filter(o=>o.eligibility.status!=='ineligible').slice(0,10))}</div>`;
  $('#agent-search').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const id=new FormData(e.target).get('source');
    $('#agent-search-result').textContent='Reading source…';
    const result=await api(`/sources/${encodeURIComponent(id)}/run`,'POST');
    await reload();
    const target=$('#agent-search-result');
    if(target)target.textContent=result.status==='failed'?result.message:`Search complete: ${result.imported} new opportunities, ${result.duplicates} duplicates. Review the matches below.`;
  });};
  $('#agent-fill').onsubmit=e=>{e.preventDefault();formFieldsDialog(new FormData(e.target).get('opportunity'));};
}

function mappedFieldRow(field={}) {
  return `<div class="rule-entry"><label>Official field label<input class="mapped-label" required maxlength="300" value="${esc(field.label||'')}" placeholder="e.g. First name"></label><label>Saved profile fact<select class="mapped-key" required><option value="">Choose a fact</option>${Object.keys(state.profile.facts).filter(k=>/^[a-zA-Z][a-zA-Z0-9_]*$/.test(k)).map(k=>`<option value="${esc(k)}" ${k===field.profile_key?'selected':''}>${esc(k)}</option>`).join('')}</select></label><label>Answer type<select class="mapped-kind">${['text','number','checkbox'].map(k=>`<option value="${k}" ${field.kind===k?'selected':''}>${k==='checkbox'?'True / false':readable(k)}</option>`).join('')}</select></label><label class="check"><input class="mapped-required" type="checkbox" ${field.required===false?'':'checked'}>Required on the official form</label><button type="button" class="quiet remove-row">Remove field</button></div>`;
}

function formFieldsDialog(id) {
  const opportunity=state.data.opportunities.find(o=>o.id===id);
  if(!opportunity)return;
  modal('Prepare the official form answers',`<p>${esc(opportunity.title)}</p><a class="text-link" href="${esc(opportunity.official_url)}" target="_blank" rel="noopener noreferrer">Inspect official form ↗</a><p>Use the exact field labels from the official form. Add missing facts in your eligibility profile first. Signatures and legal certifications are reviewed separately, not mapped as ordinary facts.</p><form id="mapped-fields-form"><div id="mapped-fields">${(opportunity.provenance.form_fields?.length?opportunity.provenance.form_fields:[{}]).map(mappedFieldRow).join('')}</div><button type="button" class="secondary" id="add-mapped-field">+ Add official field</button><label class="check"><input type="checkbox" required>I reviewed the official form and included all ordinary required fields with accurate mappings.</label><div class="dialog-footer"><button class="primary" type="submit">Fill answers & prepare review packet</button></div></form>`);
  $('#add-mapped-field').onclick=()=>$('#mapped-fields').insertAdjacentHTML('beforeend',mappedFieldRow());
  $('#mapped-fields-form').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const fields=$$('.rule-entry',e.target).map(row=>({label:$('.mapped-label',row).value.trim(),profile_key:$('.mapped-key',row).value,kind:$('.mapped-kind',row).value,required:$('.mapped-required',row).checked}));
    await api(`/opportunities/${id}/form-fields`,'PUT',{fields,official_fields_reviewed:true});
    const claim=await api(`/opportunities/${id}/prepare`,'POST');
    await reload();showClaim(claim.id);
  });};
}
