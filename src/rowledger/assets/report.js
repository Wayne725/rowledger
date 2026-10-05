'use strict';
const report = JSON.parse(document.getElementById('result-data').textContent);
const $ = id => document.getElementById(id);
const labels = {matched:'Matched',manual_matched:'Human matched',duplicate_key:'Duplicate key',unmatched:'Unmatched',amount_mismatch:'Amount differs',currency_mismatch:'Currency differs',invalid:'Invalid input',blocked_invalid:'Blocked by input'};
const resolved = row => ['matched','manual_matched'].includes(row.status);
const eligible = row => !resolved(row) && !row.errors.length;
const node = (tag, text, className) => {const element=document.createElement(tag); if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;};
let selected=null, page=0;
const pageSize=50;
$('snapshot').textContent=report.run_id.slice(0,24)+'…';
$('snapshot').title=report.run_id;
const sourceGrid=node('div',undefined,'source-files');
for(const [side,source] of Object.entries(report.sources)){
  const card=node('article');card.append(node('h3',source.name),node('p',`${side} · ${source.records} records${source.sheet ? ' · '+source.sheet : ''}`),node('code',source.sha256));sourceGrid.append(card);
}
$('provenance').append(sourceGrid);
function updateSummary(){
  $('total').textContent=report.rows.length;
  $('matched').textContent=report.rows.filter(row=>row.side==='orders'&&resolved(row)).length;
  $('attention').textContent=report.rows.filter(row=>!resolved(row)).length;
  $('decisions').textContent=report.decisions.length;
  $('source-count').textContent=`${report.sources.orders.records} orders / ${report.sources.payments.records} payments`;
}
function inspect(row){
  selected=row.row_id;
  const detail=$('detail');detail.replaceChildren(node('p','SOURCE DETAIL','eyebrow'),node('div',row.key||'(missing identifier)','detail-key'),node('span',labels[row.status],'status '+row.status),node('p',`${row.source} · ${row.sheet ? row.sheet+' · ' : ''}${row.location}`,'source-label'),node('p',row.explanation));
  if(row.partner_id){const partner=report.rows.find(item=>item.row_id===row.partner_id);detail.append(node('p',`Paired with ${partner.source}, ${partner.location} (${partner.row_id}).`));}
  const fields=node('dl');for(const [key,value] of Object.entries(row.raw)){fields.append(node('dt',key),node('dd',value||'(empty)'));}detail.append(fields);
  if(row.review)detail.append(node('p',`Reviewer: ${row.review.reviewer}. Reason: ${row.review.reason}`));
  if(eligible(row))$(row.side==='orders'?'order-select':'payment-select').value=row.row_id;
  renderRows();
}
function renderRows(){
  const filter=$('filter').value, query=$('search').value.trim().toLocaleLowerCase();
  const rows=report.rows.filter(row=>(filter==='all'||(filter==='attention'?!resolved(row):row.status===filter))&&(!query||JSON.stringify(row.raw).toLocaleLowerCase().includes(query)||row.source.toLocaleLowerCase().includes(query)));
  page=Math.min(page,Math.max(0,Math.ceil(rows.length/pageSize)-1));
  $('rows').replaceChildren();
  for(const row of rows.slice(page*pageSize,(page+1)*pageSize)){
    const tr=node('tr',undefined,selected===row.row_id?'selected':'');
    const keyCell=node('td');const button=node('button',row.key||'(missing)','row-link');button.type='button';button.addEventListener('click',()=>inspect(row));keyCell.append(button,node('small',row.row_id));
    const source=node('td',row.side);source.append(node('small',row.location));
    const amount=node('td',`${row.amount||'—'} ${row.currency}`);
    const status=node('td');status.append(node('span',labels[row.status],'status '+row.status));tr.append(keyCell,source,amount,status);$('rows').append(tr);
  }
  if(!rows.length){const tr=node('tr');const td=node('td','No records in this view.','empty');td.colSpan=4;tr.append(td);$('rows').append(tr);}
  $('results-count').textContent=`${rows.length} records in this view`;
  $('page').textContent=rows.length?`${page*pageSize+1}–${Math.min((page+1)*pageSize,rows.length)} of ${rows.length}`:'0 records';
  $('prev').disabled=page===0;$('next').disabled=(page+1)*pageSize>=rows.length;
}
function updateChoices(){
  for(const side of ['orders','payments']){
    const select=$(side==='orders'?'order-select':'payment-select');select.replaceChildren(node('option','Choose a record'));
    select.firstElementChild.value='';
    for(const row of report.rows.filter(row=>row.side===side&&eligible(row))){const option=node('option',`${row.row_id} · ${row.key} · ${row.amount} ${row.currency}`);option.value=row.row_id;select.append(option);}
  }
}
$('pair').addEventListener('click',()=>{
  const order=report.rows.find(row=>row.row_id===$('order-select').value), payment=report.rows.find(row=>row.row_id===$('payment-select').value);
  const reviewer=$('reviewer').value.trim(), reason=$('reason').value.trim();
  if(!order||!payment||!reviewer||!reason){$('feedback').textContent='Choose both records and enter a reviewer and reason.';return;}
  if(!eligible(order)||!eligible(payment)||order.currency!==payment.currency||order.amount_minor!==payment.amount_minor){$('feedback').textContent='Pairing requires unresolved, valid records with equal currency and exact amount.';return;}
  const decision={order_row_id:order.row_id,payment_row_id:payment.row_id,reviewer,reason};report.decisions.push(decision);
  for(const [row,partner] of [[order,payment],[payment,order]]){row.status='manual_matched';row.partner_id=partner.row_id;row.review=decision;row.explanation='Human-selected pair with exact amount and currency; original keys are preserved.';}
  $('feedback').textContent='Decision added. Export the review to save it, then apply it with RowLedger.';
  $('reason').value='';updateChoices();updateSummary();inspect(order);
});
$('review-toggle').addEventListener('click',()=>{$('pair-panel').hidden=!$('pair-panel').hidden;if(!$('pair-panel').hidden)$('order-select').focus();});
$('filter').addEventListener('change',()=>{page=0;renderRows();});$('search').addEventListener('input',()=>{page=0;renderRows();});
$('prev').addEventListener('click',()=>{page--;renderRows();});$('next').addEventListener('click',()=>{page++;renderRows();});
$('export').addEventListener('click',()=>{
  const document={schema_version:report.schema_version,run_id:report.run_id,decisions:report.decisions};
  const reviewJson=JSON.stringify(document,null,2);$('review-output').hidden=false;$('review-output').open=true;$('review-json').value=reviewJson;
  const url=URL.createObjectURL(new Blob([reviewJson],{type:'application/json'}));
  const link=node('a');link.href=url;link.download='review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  $('export-note').textContent='Review prepared. Save the download or copy the JSON below, then apply it to the original files.';
});
updateSummary();updateChoices();renderRows();
