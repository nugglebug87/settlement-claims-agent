'use strict';

function attachBrowserHelper(claim) {
  const section=document.createElement('section');
  section.id='browser-claim-context';
  section.dataset.claimId=claim.id;
  section.innerHTML=`<h3>Fill ordinary answers on the official website</h3><p>Use the optional Chrome/Edge helper to inspect page fields and review each mapping before filling. The site may save answers immediately, so the helper asks for transmission authorization. Signing, checkboxes, attachments, and submission stay manual.</p><p><a class="text-link" href="/api/browser-extension">Download browser helper ZIP</a></p><ol><li>Extract the ZIP. Open Chrome or Edge extension settings, enable Developer mode, and choose Load unpacked for the extracted folder.</li><li>Keep this claim review open. Click the helper in the browser toolbar and choose Load claim from workspace.</li><li>Open the <a class="text-link" href="${esc(claim.packet.official_url)}" target="_blank" rel="noopener noreferrer">official form</a> in another tab, open the helper again, and inspect the form.</li><li>Review mappings, authorize sending the selected answers, and fill. Check every answer on the official page before completing the remaining steps.</li></ol><p class="fine">The reference expires in ten minutes. Redirected URLs need review in the workspace. This helper never clicks a submit button or records a submission confirmation.</p>`;
  $('#dialog-content').appendChild(section);
}

async function renderClaimFinder() {
  heading('Claim Finder','Find settlements to review in three simple steps.');
  $('#view').innerHTML='<div class="loading">Opening Claim Finder…</div>';
  const data=await api('/sources');
  if(state.view!=='overview')return;
  const defaults=[...data.sources].sort((a,b)=>Number(b.enabled)-Number(a.enabled)).slice(0,5).map(s=>s.id);
  $('#view').innerHTML=`<ol class="finder-steps"><li><strong>1. Find claims</strong><span>Enter a company or leave the box blank to browse.</span></li><li><strong>2. Check eligibility</strong><span>Open a result and compare the official rules with your facts.</span></li><li><strong>3. Prepare your form</strong><span>Eligible claims can move to Form Filler for your review.</span></li></ol><section class="panel panel-body finder-search"><h2>Find a settlement</h2><form id="agent-search"><label for="claim-finder-query">Company or product (optional)</label><div class="finder-search-row"><input type="search" name="query" id="claim-finder-query" maxlength="200" placeholder="e.g. a company or brand you used"><button class="primary" type="submit" ${data.sources.length?'':'disabled'}>Find claims</button></div><p class="finder-help">Leave blank to see all available leads. A company name filters results in your collection; it does not prove you qualify.</p>${data.sources.length?`<details class="finder-options"><summary>Search options · ${defaults.length} sources selected</summary><fieldset><legend>Choose up to five sources</legend>${data.sources.map(s=>`<label class="check"><input type="checkbox" name="sources" value="${esc(s.id)}" ${defaults.includes(s.id)?'checked':''}>${esc(s.name)}</label>`).join('')}</fieldset>${button('view-sources','Manage sources','quiet')}</details>`:`<div class="notice"><strong>Set up your first search</strong><p>No search sources are connected yet. Open source settings to connect a source, then return here to find claims.</p>${button('view-sources','Set up search sources','secondary')}</div>`}</form><p class="finder-help">Search checks your connected sources for fresh leads. Some sources may need setup before they can run.</p><div id="agent-search-result" role="status" aria-live="polite"></div></section><div class="section-title"><h2 id="finder-results-heading">Claims to review</h2>${button('view-profile','Add eligibility details','secondary')}</div><label class="check"><input id="finder-all-saved" type="checkbox" ${state.finderAll?'checked':''}>Show all saved claims, including closed claims and announcements</label><p id="claim-finder-summary" class="finder-help"></p><div id="claim-finder-results" class="finder-results"></div><details class="finder-options"><summary>Have a settlement notice already?</summary><p>Add the official notice to your collection to review its eligibility rules.</p>${button('new-opportunity','Add a settlement notice','secondary')}</details>`;
  const filterResults=()=>{
    if(state.view!=='overview'||!$('#claim-finder-query'))return;
    const query=$('#claim-finder-query').value.trim().toLowerCase();
    const items=state.data.opportunities.filter(o=>(state.finderAll||(['open_claim','unknown'].includes(o.classification)&&!o.priority.expired&&o.eligibility.status!=='ineligible'))&&(!query||[o.title,o.summary,o.defendant,o.administrator].some(v=>String(v||'').toLowerCase().includes(query))));
    $('#finder-results-heading').textContent=state.finderAll?'All saved claims':'Claims to review';
    $('#claim-finder-summary').textContent=`${items.length} ${items.length===1?'claim':'claims'} ${state.finderAll?'saved':'to review'}. Check the official rules before preparing a form.`;
    $('#claim-finder-results').innerHTML=items.length?items.map(o=>{
      const ready=o.verified&&o.classification==='open_claim'&&o.eligibility.status==='eligible'&&!o.priority.expired;
      const status=o.priority.expired?'Deadline passed':!['open_claim','unknown'].includes(o.classification)?readable(o.classification):o.eligibility.status==='ineligible'?'Does not match your saved facts':ready?'Matches your saved facts':!o.verified||o.classification==='unknown'?'Official details need review':'More eligibility details needed';
      return `<article class="panel panel-body finder-card"><p>${badge(status,ready?'':'amber')}</p><h3>${esc(o.title)}</h3><p class="finder-description">${esc(o.summary||'Open this claim to check the official eligibility rules and benefits.')}</p><dl class="finder-facts"><div><dt>Claim deadline</dt><dd>${date(o.deadline)}</dd></div><div><dt>Estimated payment</dt><dd>${money(o.expected_payout)}</dd></div></dl>${button('opportunity','Review claim →','secondary',o.id)}</article>`;
    }).join(''):empty(query?'No claims match that name yet.':'No claims to review yet.',query?'Try another company or clear the box to browse all leads. Find claims checks connected sources for new leads.':'Click Find claims to check connected sources. You can also add a settlement notice you received.');
  };
  $('#claim-finder-query').addEventListener('input',filterResults);
  $('#finder-all-saved').onchange=e=>{state.finderAll=e.target.checked;filterResults();};
  const sourceInputs=$$('input[name=sources]');
  sourceInputs.forEach(input=>input.addEventListener('change',()=>{
    const count=sourceInputs.filter(i=>i.checked).length;
    $('.finder-options summary').textContent=`Search options · ${count} sources selected`;
    sourceInputs.forEach(i=>i.disabled=!i.checked&&count>=5);
  }));
  sourceInputs.forEach(i=>i.disabled=!i.checked&&defaults.length>=5);
  filterResults();
  $('#agent-search').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const ids=new FormData(e.target).getAll('sources');
    if(!ids.length||ids.length>5)throw new Error('Open Search options and choose between one and five sources.');
    const target=$('#agent-search-result'), submitButton=$('button[type=submit]',e.target);
    const outcomes=[];
    let failures=0, imported=0;
    submitButton.textContent='Searching…';
    try{
      for(const [index,id] of ids.entries()){
        const source=data.sources.find(s=>s.id===id);
        target.textContent=`Checking source ${index+1} of ${ids.length}: ${source.name}…`;
        try{
          const result=await api(`/sources/${encodeURIComponent(id)}/run`,'POST');
          if(result.status==='failed'){failures++;outcomes.push(`${source.name}: ${result.message}`);}
          else{imported+=result.imported;outcomes.push(`${source.name}: ${result.imported} new leads, ${result.duplicates} already saved.`);}
        }catch(error){failures++;outcomes.push(`${source.name}: ${error.message}`);}
      }
      state.data=await api('/dashboard');
      filterResults();
      target.innerHTML=`<p>${failures===ids.length?'Search could not read any selected sources. Saved results remain below.':`Search finished. ${imported} new leads added.${failures?' Some sources could not be read.':''}`}</p><details><summary>View search details</summary><ul>${outcomes.map(message=>`<li>${esc(message)}</li>`).join('')}</ul>${failures?button('view-sources','Open source settings','secondary'):''}</details>`;
    }finally{submitButton.textContent='Find claims';}
  });};
}

async function renderAgents() {
  heading('Form Filler','Prepare answers for an eligible claim, then review your draft.');
  const ready=state.data.opportunities.filter(o=>o.verified&&o.classification==='open_claim'&&o.eligibility.status==='eligible'&&!o.priority.expired);
  $('#view').innerHTML=`<section class="panel panel-body"><h2>Prepare your claim form</h2><p>Choose a settlement whose official rules have been reviewed and whose eligibility matches your saved facts.</p>${ready.length?`<form id="agent-fill"><label>Settlement<select name="opportunity" required>${ready.map(o=>`<option value="${esc(o.id)}">${esc(o.title)}</option>`).join('')}</select></label><button class="primary" type="submit">Prepare form answers</button></form>`:empty('Find an eligible claim first.','Open Claim Finder, review a result, and add any missing eligibility details.','view-overview','Open Claim Finder')}<p class="finder-help">The form uses your saved facts. Add missing answers in your eligibility profile.</p></section><div class="notice">PDF drafts are unsigned. Review and approve each claim, then complete submission on the official website and save its confirmation.</div>`;
  if($('#agent-fill'))$('#agent-fill').onsubmit=e=>{e.preventDefault();formFieldsDialog(new FormData(e.target).get('opportunity'));};
}

function mappedFieldRow(field={}) {
  return `<div class="rule-entry"><label>Official field label<input class="mapped-label" required maxlength="300" value="${esc(field.label||'')}" placeholder="e.g. First name"></label><label>Saved profile fact<select class="mapped-key" required><option value="">Choose a fact</option>${Object.keys(state.profile.facts).filter(k=>/^[a-zA-Z][a-zA-Z0-9_]*$/.test(k)).map(k=>`<option value="${esc(k)}" ${k===field.profile_key?'selected':''}>${esc(k)}</option>`).join('')}</select></label><label>Answer type<select class="mapped-kind">${['text','number','checkbox'].map(k=>`<option value="${k}" ${field.kind===k?'selected':''}>${k==='checkbox'?'True / false':readable(k)}</option>`).join('')}</select></label><label class="check"><input class="mapped-required" type="checkbox" ${field.required===false?'':'checked'}>Required on the official form</label><label class="check"><input class="mapped-evidence" type="checkbox" ${field.evidence_when_selected?'checked':''}>This benefit requires proof when selected (true / false fields only)</label>${pdfTargetEditor(field)}<button type="button" class="quiet remove-row">Remove field</button></div>`;
}

function formFieldsDialog(id) {
  const opportunity=state.data.opportunities.find(o=>o.id===id);
  if(!opportunity)return;
  modal('Prepare the official form answers',`<p>${esc(opportunity.title)}</p><a class="text-link" href="${esc(opportunity.official_url)}" target="_blank" rel="noopener noreferrer">Inspect official form ↗</a><p>Use the exact field labels from the official form. Add missing facts in your eligibility profile first. Signatures and legal certifications are reviewed separately, not mapped as ordinary facts.</p><form id="mapped-fields-form"><section class="notice"><h3>Find the official claim form</h3><p>Searches the official notice and up to two linked Documents pages for claim-form PDFs. Retrieved files stay in memory until you close or reload this page. Check the source link before using a form.</p><button id="find-official-form" type="button" class="secondary">Find official claim form</button><div id="official-form-candidates" role="status"></div><h3>Fill a PDF draft</h3><p>Map ordinary answers only; leave signature and certification areas untouched. You can also upload the blank official PDF yourself.</p><label>Blank PDF (optional)<input id="pdf-source" type="file" accept="application/pdf,.pdf"></label><button id="inspect-pdf" type="button" class="secondary">Inspect PDF pages & fields</button><p id="pdf-details" role="status"></p><label>Answer to position on the page<select id="pdf-placement-field"></select></label><div id="pdf-pages"></div></section><div id="mapped-fields">${(opportunity.provenance.form_fields?.length?opportunity.provenance.form_fields:[{}]).map(mappedFieldRow).join('')}</div><button type="button" class="secondary" id="add-mapped-field">+ Add official field</button><label class="check"><input type="checkbox" required>I reviewed the official form and included all ordinary required fields with accurate mappings.</label><div class="dialog-footer"><button class="primary" type="submit">Fill answers & prepare review packet</button></div></form>`);
  $('#add-mapped-field').onclick=()=>$('#mapped-fields').insertAdjacentHTML('beforeend',mappedFieldRow());
  const pdfDigest=attachPdfSetup(opportunity,()=>state.officialPdfs[id]?.pdf_base64||null);
  $('#find-official-form').onclick=async event=>{
    const button=event.currentTarget;button.disabled=true;button.textContent='Searching official pages…';
    const target=$('#official-form-candidates');target.textContent='Checking the official notice and its Documents links…';
    try{
      const result=await api(`/opportunities/${encodeURIComponent(id)}/form-candidates`);
      if(!result.candidates.length){target.textContent='No claim-form PDF was found on the checked pages. Review the official notice link and use the manual PDF upload or website-form helper.';return;}
      target.innerHTML=result.candidates.map((candidate,index)=>`<div class="notice"><p><strong>${esc(candidate.title||'Official form')}</strong> · ${candidate.kind==='pdf'?'PDF form':'website form'}</p><a class="text-link" href="${esc(candidate.url)}" target="_blank" rel="noopener noreferrer">Check source ↗</a>${candidate.kind==='pdf'?`<button type="button" class="secondary retrieve-official-form" data-index="${index}">Retrieve & inspect PDF</button>`:''}</div>`).join('');
      $$('.retrieve-official-form',target).forEach(retrieveButton=>retrieveButton.onclick=async()=>{
        retrieveButton.disabled=true;retrieveButton.textContent='Retrieving…';
        try{
          const candidate=result.candidates[Number(retrieveButton.dataset.index)];
          const pdf=await api(`/opportunities/${encodeURIComponent(id)}/official-form`,'POST',{url:candidate.url});
          state.officialPdfs[id]=pdf;
          $('#pdf-details').textContent=`Retrieved “${pdf.title}” from the official notice. Review the source link, then inspect the PDF below.`;
          $('#inspect-pdf').click();
        }catch(error){toast(error.message);retrieveButton.disabled=false;retrieveButton.textContent='Retrieve & inspect PDF';}
      });
    }catch(error){target.textContent=error.message;}finally{button.disabled=false;button.textContent='Find official claim form';}
  };
  $('#mapped-fields-form').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const fields=$$('.rule-entry',e.target).map(row=>({label:$('.mapped-label',row).value.trim(),profile_key:$('.mapped-key',row).value,kind:$('.mapped-kind',row).value,required:$('.mapped-required',row).checked,evidence_when_selected:$('.mapped-evidence',row).checked,pdf_target:collectPdfTarget(row)}));
    await api(`/opportunities/${id}/form-fields`,'PUT',{fields,official_fields_reviewed:true,pdf_sha256:fields.some(f=>f.pdf_target)?pdfDigest():null});
    const claim=await api(`/opportunities/${id}/prepare`,'POST');
    await reload();showClaim(claim.id);
  });};
}
