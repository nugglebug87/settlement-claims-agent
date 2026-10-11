'use strict';

async function readPdfFile(input) {
  const file=input.files[0];
  if(!file || file.size>3*1024*1024)throw new Error('Choose an unsigned PDF up to 3 MB.');
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(reader.result.split(',')[1]);
    reader.onerror=()=>reject(new Error('Could not read this PDF.'));
    reader.readAsDataURL(file);
  });
}

function pdfTargetEditor(field={}) {
  const p=field.pdf_target?.position||{};
  return `<fieldset class="pdf-target"><legend>PDF destination (optional)</legend><label>Interactive PDF field name<input class="pdf-name" maxlength="300" value="${esc(field.pdf_target?.field_name||'')}" placeholder="Exact name from the inspected PDF"></label><p class="fine">For a paper form, leave the field name empty and set a page position. Choose this answer below, then click its blank space on the page. Positions use points from the top-left.</p><div class="grid-2">${[['page','Page',1],['x','Left',0],['y','Top',0],['width','Width',160],['height','Height',14]].map(([key,label,value])=>`<label>${label}<input class="pdf-${key}" type="number" min="${key==='page'?1:0}" step="${key==='page'?1:0.1}" value="${esc(p[key]??value)}"></label>`).join('')}</div><label class="check"><input class="pdf-position-enabled" type="checkbox" ${field.pdf_target?.position?'checked':''}>Use this page position</label></fieldset>`;
}

function collectPdfTarget(row) {
  const name=$('.pdf-name',row).value.trim();
  if(name && $('.pdf-position-enabled',row).checked)throw new Error('Choose one interactive field or page position for each answer.');
  if(name)return {field_name:name};
  if(!$('.pdf-position-enabled',row).checked)return null;
  return {position:Object.fromEntries(['page','x','y','width','height'].map(key=>[key,Number($('.pdf-'+key,row).value)]))};
}

function attachPdfSetup(opportunity) {
  let digest=opportunity.provenance.pdf_sha256||null;
  $('#inspect-pdf').onclick=async()=>{
    const button=$('#inspect-pdf');button.disabled=true;
    try {
      const encoded=await readPdfFile($('#pdf-source'));
      const info=await api('/pdf/inspect','POST',{pdf_base64:encoded});
      digest=info.sha256;
      $('#pdf-details').textContent=`${info.pages.length} pages. Interactive fields: ${info.fields.map(f=>f.name+' ('+f.kind+')').join(', ')||'None; use page positions.'}`;
      $('#pdf-pages').innerHTML=info.pages.map(page=>`<figure><figcaption>Page ${page.page}</figcaption><img class="pdf-page-image" data-page="${page.page}" src="${page.image}" alt="Source claim form page ${page.page}"></figure>`).join('');
      $$('.pdf-page-image').forEach(image=>image.onclick=e=>{
        const rows=$$('.rule-entry',$('#mapped-fields'));
        const selected=rows[Number($('#pdf-placement-field').value)];
        if(!selected){toast('Choose an answer to position first.');return;}
        const page=info.pages.find(p=>p.page===Number(image.dataset.page));
        const bounds=image.getBoundingClientRect();
        $('.pdf-page',selected).value=page.page;
        $('.pdf-x',selected).value=((e.clientX-bounds.left)/bounds.width*page.width).toFixed(1);
        $('.pdf-y',selected).value=((e.clientY-bounds.top)/bounds.height*page.height).toFixed(1);
        $('.pdf-name',selected).value='';
        $('.pdf-position-enabled',selected).checked=true;
        toast('Position set. Review the width and the generated draft before approving.');
      });
    } catch(error){toast(error.message);}finally{button.disabled=false;}
  };
  const updateChoices=()=>{
    $('#pdf-placement-field').innerHTML=$$('.rule-entry',$('#mapped-fields')).map((row,index)=>`<option value="${index}">${esc($('.mapped-label',row).value||'Answer '+(index+1))}</option>`).join('');
  };
  $('#mapped-fields').addEventListener('input',updateChoices);
  $('#mapped-fields').addEventListener('click',()=>setTimeout(updateChoices,0));
  $('#add-mapped-field').addEventListener('click',()=>setTimeout(updateChoices,0));
  updateChoices();
  return ()=>digest;
}

function pdfDraftDialog(claim) {
  modal('Generate an unsigned PDF draft',`<p>${esc(claim.packet.title)}</p><p>Choose the exact blank PDF used to review this packet. The app processes it in memory and returns an unsigned draft. It does not save the uploaded PDF or sign, certify, or submit it.</p><p class="fine">Review every completed page and all attachments before approval. A PDF draft does not include evidence files.</p><form id="pdf-export-form"><label>Original blank PDF<input id="pdf-export-source" type="file" accept="application/pdf,.pdf" required></label><button type="submit" class="primary">Download unsigned PDF draft</button></form>`);
  $('#pdf-export-form').onsubmit=e=>{e.preventDefault();submit(e.target,async()=>{
    const encoded=await readPdfFile($('#pdf-export-source'));
    const response=await fetch(`/api/claims/${claim.id}/pdf`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify({pdf_base64:encoded})});
    if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'Could not generate this draft.');}
    const result=await response.json();
    const url=result.download_url;
    const link=document.createElement('a');link.href=url;link.download=`claim-${claim.id}-unsigned-draft.pdf`;link.className='text-link';link.textContent='Save unsigned PDF draft';
    const previous=$('.pdf-save-link',e.target);if(previous)previous.remove();
    link.classList.add('pdf-save-link');e.target.appendChild(link);link.click();
    toast('Unsigned draft generated. If the download did not start, use the save link within two minutes. Review every page before approval.');
  });};
}
