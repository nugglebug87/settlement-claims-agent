'use strict';

async function renderAgents() {
  heading('Your settlement agents.','Search for opportunities, then prepare their official form answers for your approval.');
  const data=await api('/sources');
  const ready=state.data.opportunities.filter(o=>o.verified&&o.classification==='open_claim'&&o.eligibility.status==='eligible');
  $('#view').innerHTML=`<div class="grid-2"><section class="panel panel-body"><p class="eyebrow">CLAIMS SEARCH AGENT</p><h2>Find claims to review.</h2><p>Search your configured sources now, then narrow the collection by company or product. Discovered leads require official-source review before claim preparation.</p><form id="agent-search"><label>Company or product (optional)<input type="search" name="query" id="claim-finder-query" maxlength="200" placeholder="e.g. Equifax or a brand you used"></label><fieldset><legend>Sources to search (choose up to five)</legend>${data.sources.map(s=>`<label class="check"><input type="checkbox" name="sources" value="${esc(s.id)}">${esc(s.name)} · ${esc(readable(s.stream))}</label>`).join('')}</fieldset><button class="primary" type="submit" ${data.sources.length?'':'disabled'}>Find claims</button></form><p class="fine">${data.sources.length?'Each selected source is read fresh, including paused sources. The company or product filter runs inside your app. This does not enable monitoring.':'Add discovery sources before running a search.'}</p>${button('view-sources','Manage sources','secondary')}<div id="agent-search-result" role="status"></div></section><section class="panel panel-body"><p class="eyebrow">FORM FILLER AGENT</p><h2>Prepare your answers.</h2><p>Map the official form’s fields to your saved profile facts. The agent fills a review packet without guessing missing answers.</p><form id="agent-fill"><label>Verified eligible settlement<select name="opportunity" required>${ready.map(o=>`<option value="${esc(o.id)}">${esc(o.title)}</option>`).join('')}</select></label><button class="primary" type="submit" ${ready.length?'':'disabled'}>Set up form & fill answers</button></form><p class="fine">${ready.length?'Each claim needs your review and approval.':'Review an official source and resolve eligibility answers to unlock preparation.'}</p>${button('view-opportunities','Review opportunities','secondary')}</section></div><div class="notice">Official website autofill, signature execution, and automatic submission are not connected yet. This agent prepares form answers inside your private app. After approval, open the official form and complete the filing there; record the actual confirmation afterward.</div><div class="section-title"><h2>Claim finder results</h2></div><p id="claim-finder-summary" class="fine"></p><div class="panel" id="claim-finder-results"></div>`;
  const filterResults=()=>{
    if(!$('#claim-finder-query'))return;
    const query=$('#claim-finder-query').value.trim().toLowerCase();
    const items=state.data.opportunities.filter(o=>['open_claim','unknown'].includes(o.classification)&&o.eligibility.status!=='ineligible'&&(!query||[o.title,o.summary,o.defendant,o.administrator].some(v=>String(v||'').toLowerCase().includes(query))));
    const reviewed=items.filter(o=>o.verified&&o.classification==='open_claim'&&o.eligibility.status==='eligible');
    $('#claim-finder-summary').textContent=`${items.length} results in your collection; ${reviewed.length} verified open claims match your recorded facts. Other results need source review or eligibility answers. A keyword match does not establish eligibility.`;
    $('#claim-finder-results').innerHTML=opportunitiesTable(items);
  };
  $('#claim-finder-query').addEventListener('input',filterResults);
  filterResults();
  $('#agent-search').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const ids=new FormData(e.target).getAll('sources');
    if(!ids.length||ids.length>5)throw new Error('Choose between one and five sources.');
    const target=$('#agent-search-result');
    const outcomes=[];
    for(const [index,id] of ids.entries()){
      const source=data.sources.find(s=>s.id===id);
      target.textContent=`Reading ${index+1} of ${ids.length}: ${source.name}…`;
      try{
        const result=await api(`/sources/${encodeURIComponent(id)}/run`,'POST');
        outcomes.push(result.status==='failed'?`${source.name}: failed — ${result.message}`:`${source.name}: ${result.imported} new leads, ${result.duplicates} duplicates.`);
      }catch(error){outcomes.push(`${source.name}: failed — ${error.message}`);}
    }
    state.data=await api('/dashboard');
    filterResults();
    target.textContent=outcomes.join(' ');
  });};
  $('#agent-fill').onsubmit=e=>{e.preventDefault();formFieldsDialog(new FormData(e.target).get('opportunity'));};
}

function mappedFieldRow(field={}) {
  return `<div class="rule-entry"><label>Official field label<input class="mapped-label" required maxlength="300" value="${esc(field.label||'')}" placeholder="e.g. First name"></label><label>Saved profile fact<select class="mapped-key" required><option value="">Choose a fact</option>${Object.keys(state.profile.facts).filter(k=>/^[a-zA-Z][a-zA-Z0-9_]*$/.test(k)).map(k=>`<option value="${esc(k)}" ${k===field.profile_key?'selected':''}>${esc(k)}</option>`).join('')}</select></label><label>Answer type<select class="mapped-kind">${['text','number','checkbox'].map(k=>`<option value="${k}" ${field.kind===k?'selected':''}>${k==='checkbox'?'True / false':readable(k)}</option>`).join('')}</select></label><label class="check"><input class="mapped-required" type="checkbox" ${field.required===false?'':'checked'}>Required on the official form</label><label class="check"><input class="mapped-evidence" type="checkbox" ${field.evidence_when_selected?'checked':''}>This benefit requires proof when selected (true / false fields only)</label>${pdfTargetEditor(field)}<button type="button" class="quiet remove-row">Remove field</button></div>`;
}

function formFieldsDialog(id) {
  const opportunity=state.data.opportunities.find(o=>o.id===id);
  if(!opportunity)return;
  modal('Prepare the official form answers',`<p>${esc(opportunity.title)}</p><a class="text-link" href="${esc(opportunity.official_url)}" target="_blank" rel="noopener noreferrer">Inspect official form ↗</a><p>Use the exact field labels from the official form. Add missing facts in your eligibility profile first. Signatures and legal certifications are reviewed separately, not mapped as ordinary facts.</p><form id="mapped-fields-form"><section class="notice"><h3>Fill a PDF draft</h3><p>Use a blank official PDF. Map ordinary answers only; leave signature and certification areas untouched. Uploads are processed in memory.</p><label>Blank PDF (optional)<input id="pdf-source" type="file" accept="application/pdf,.pdf"></label><button id="inspect-pdf" type="button" class="secondary">Inspect PDF pages & fields</button><p id="pdf-details" role="status"></p><label>Answer to position on the page<select id="pdf-placement-field"></select></label><div id="pdf-pages"></div></section><div id="mapped-fields">${(opportunity.provenance.form_fields?.length?opportunity.provenance.form_fields:[{}]).map(mappedFieldRow).join('')}</div><button type="button" class="secondary" id="add-mapped-field">+ Add official field</button><label class="check"><input type="checkbox" required>I reviewed the official form and included all ordinary required fields with accurate mappings.</label><div class="dialog-footer"><button class="primary" type="submit">Fill answers & prepare review packet</button></div></form>`);
  $('#add-mapped-field').onclick=()=>$('#mapped-fields').insertAdjacentHTML('beforeend',mappedFieldRow());
  const pdfDigest=attachPdfSetup(opportunity);
  $('#mapped-fields-form').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const fields=$$('.rule-entry',e.target).map(row=>({label:$('.mapped-label',row).value.trim(),profile_key:$('.mapped-key',row).value,kind:$('.mapped-kind',row).value,required:$('.mapped-required',row).checked,evidence_when_selected:$('.mapped-evidence',row).checked,pdf_target:collectPdfTarget(row)}));
    await api(`/opportunities/${id}/form-fields`,'PUT',{fields,official_fields_reviewed:true,pdf_sha256:fields.some(f=>f.pdf_target)?pdfDigest():null});
    const claim=await api(`/opportunities/${id}/prepare`,'POST');
    await reload();showClaim(claim.id);
  });};
}
