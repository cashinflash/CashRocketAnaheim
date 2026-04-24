
// Cash Rocket Anaheim — static tag for dashboard attribution.
window.CRA_SOURCE_SITE = 'cashrocket_anaheim';
const API_BASE = window.BACKEND_URL || 'https://cashrocketanaheim-apply.onrender.com';
let lang='en', loanAmt=null;
let plaidOk=false, assetTok=null, bankB64=null, idB64=null, psB64=null, pdfOk=true;

// ── TRANSLATIONS ──
const T={en:{'form-title':'Payday Loan Application','form-sub':'Fast approval · Up to $255 · California residents only','sl1':'Personal','sl2':'Income','sl3':'Financial','sl4':'Documents','t1':'Personal Information','t2':'Source of Income','t2b':'Banking Information','t3':'Financial Information','t3b':'Active Military Information','sub3b':'Covered Borrower Identification Statement','t3c':'Initial Disclosures','t4':'Document Upload','sub4':'Please upload the required documents','l-name':'Name','l-la':'Loan Amount','l-ssn':'Social Security Number','l-ssn2':'Confirm Social Security Number','l-dob':'Date of Birth','l-addr':'Home Address','l-ph':'Phone Number','l-em':'Email','l-soi':'Source of Income','l-emp':'Employer Name','l-pf':'Pay Frequency','l-pd':'Pay Day','l-lpd':'Last Pay Date','l-pm':'Payment Method','l-gp':'Gross Pay Per Check','l-at':'Type of Account','l-rtn':'ABA/Routing Number','l-acn':'Account Number','l-bn':'Bank Name','l-ro':'Do you rent or own?','l-bk':'Are you currently filing for or considering bankruptcy?','l-con':'Electronic Disclosure Consent','l-contxt':'I agree to the Consent to Electronic Disclosure and to the Privacy Policy.','l-id':'Valid Government ID','l-bv':'Bank Verification','l-ps':'Proof of Income / Pay Stubs','bo-rec':'Recommended','bo-pt':'Connect Bank','bo-ps':'Instant via Plaid','bo-ut':'Upload Statement','bo-us':'PDF from last 30 days','bv-sub':'Connect your bank instantly or upload your most recent bank statement.','plaid-btxt':'Connect with Plaid','dzt-id':'Upload Valid ID','dzs-id':'Tap to select or drag and drop','dzt-bk':'Upload Bank Statement','dzs-bk':'PDF format only','dzt-ps':'Upload Proof of Income','dzs-ps':'Optional — skip if direct deposits show in bank statement','h-id':"Must be valid. Expired IDs will NOT be accepted.",'h-bk':'Must be PDF format. Screenshots will NOT be accepted.','h-ph':'Please enter a valid phone number.','h-soi':'Alimony, child support, or separate income need not be revealed if you do not wish to have it considered as a basis for repaying this cash advance.','bt1':'Continue →','bt2':'Continue →','bt3':'Continue →','bt-sub':'Submit Application →','bt-b2':'← Back','bt-b3':'← Back','bt-b4':'← Back','s-ttl':'Application Submitted!','step1-txt':'Your application is being reviewed by our team','step2-txt':'You will receive a call or text with your decision','step3-txt':'If approved, funds sent to your debit card within minutes*','store-label':'Our Store Location','back-home-btn':'← Back to Website','s-sub':'Thank you! We have received your application and are currently reviewing your information. You will be contacted shortly with a decision.','sec-txt':'256-bit SSL encrypted · Your information is secure','l-chk':'Personal Checking','l-sav':'Savings','l-own':'Own','l-rnt':'Rent','l-oth':'Other','l-yes':'Yes','l-no':'No','l-mnot':'I am not','l-mis':'I am'},es:{'form-title':'Solicitud de Préstamo','form-sub':'Aprobación rápida · Hasta $255 · Solo residentes de California','sl1':'Personal','sl2':'Ingresos','sl3':'Financiero','sl4':'Documentos','t1':'Información Personal','t2':'Fuente de Ingresos','t2b':'Información Bancaria','t3':'Información Financiera','t3b':'Información Militar Activa','sub3b':'Declaración de Identificación de Prestatario Cubierto','t3c':'Divulgaciones Iniciales','t4':'Carga de Documentos','sub4':'Por favor suba los documentos requeridos','l-name':'Nombre','l-la':'Monto del Préstamo','l-ssn':'Número de Seguro Social','l-ssn2':'Confirmar Número de Seguro Social','l-dob':'Fecha de Nacimiento','l-addr':'Domicilio','l-ph':'Número de Teléfono','l-em':'Correo Electrónico','l-soi':'Fuente de Ingresos','l-emp':'Nombre del Empleador','l-pf':'Frecuencia de Pago','l-pd':'Día de Pago','l-lpd':'Última Fecha de Pago','l-pm':'Método de Pago','l-gp':'Pago Bruto por Cheque','l-at':'Tipo de Cuenta','l-rtn':'Número ABA/Ruta','l-acn':'Número de Cuenta','l-bn':'Nombre del Banco','l-ro':'¿Renta o es propietario?','l-bk':'¿Está considerando bancarrota?','l-con':'Consentimiento de Divulgación Electrónica','l-contxt':'Acepto el Consentimiento para Divulgación Electrónica y la Política de Privacidad.','l-id':'Identificación Oficial Válida','l-bv':'Verificación Bancaria','l-ps':'Comprobante de Ingresos','bo-rec':'Recomendado','bo-pt':'Conectar Banco','bo-ps':'Instantáneo via Plaid','bo-ut':'Subir Estado de Cuenta','bo-us':'PDF de los últimos 30 días','bv-sub':'Conecte su banco instantáneamente o suba su estado de cuenta.','plaid-btxt':'Conectar con Plaid','dzt-id':'Subir ID Válida','dzs-id':'Toque para seleccionar','dzt-bk':'Subir Estado de Cuenta','dzs-bk':'Solo formato PDF','dzt-ps':'Subir Comprobante de Ingresos','dzs-ps':'Opcional','h-id':'Debe ser válida. No se aceptarán IDs vencidas.','h-bk':'Debe ser PDF. No se aceptarán capturas de pantalla.','h-ph':'Ingrese un número de teléfono válido.','h-soi':'Los ingresos por pensión alimenticia no necesitan ser revelados si no desea que se consideren.','bt1':'Continuar →','bt2':'Continuar →','bt3':'Continuar →','bt-sub':'Enviar Solicitud →','bt-b2':'← Regresar','bt-b3':'← Regresar','bt-b4':'← Regresar','s-ttl':'¡Solicitud Enviada!','step1-txt':'Su solicitud está siendo revisada por nuestro equipo','step2-txt':'Recibirá una llamada o mensaje con su decisión','step3-txt':'Si aprobado, fondos enviados a su tarjeta de débito en minutos*','store-label':'Nuestra Ubicación','back-home-btn':'← Volver al Sitio Web','s-sub':'¡Gracias! Hemos recibido su solicitud. Será contactado en breve con una decisión.','sec-txt':'Cifrado SSL de 256 bits · Su información está segura','l-chk':'Cuenta Corriente','l-sav':'Ahorros','l-own':'Propietario','l-rnt':'Renta','l-oth':'Otro','l-yes':'Sí','l-no':'No','l-mnot':'No soy','l-mis':'Soy'}};

function setLang(l,btn){lang=l;document.querySelectorAll('.lang-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');Object.entries(T[l]).forEach(([id,txt])=>{const el=document.getElementById(id);if(el)el.textContent=txt;});}

// ── PROGRESS ──
function upProg(n){for(let i=1;i<=4;i++){const c=document.getElementById('sc'+i),l=document.getElementById('sl'+i);if(!c||!l)continue;if(i<n){c.className='sc done';c.textContent='✓';l.className='sl';}else if(i===n){c.className='sc active';c.textContent=i;l.className='sl active';}else{c.className='sc todo';c.textContent=i;l.className='sl';}}for(let i=1;i<=3;i++){const cn=document.getElementById('cn'+i);if(cn)cn.className='cn'+(i<n?' done':'');}}

function showS(n){for(let i=1;i<=4;i++){const el=document.getElementById('s'+i);if(el)el.style.display=i===n?'block':'none';}upProg(n);window.scrollTo({top:0,behavior:'smooth'});window.parent.postMessage({type:'cif-scroll-top'},'*');sendHeight();}
function back(to){showS(to);}

// ── VALIDATION ──
function req(id,eid){const el=document.getElementById(id),er=document.getElementById(eid);if(!el||!el.value.trim()){if(el)el.classList.add('err');if(er)er.classList.add('show');return false;}if(el)el.classList.remove('err');if(er)er.classList.remove('show');return true;}
function rr(name,eid){const c=document.querySelector('input[name="'+name+'"]:checked'),er=document.getElementById(eid);if(!c){if(er)er.classList.add('show');return false;}if(er)er.classList.remove('show');return true;}

function go(from){
  let ok=true;
  if(from===1){
    ok=req('firstName','e-fn')&req('lastName','e-ln')&req('city','e-city')&req('state','e-state')&req('zip','e-zip')&req('email','e-em')&&ok;
    if(!loanAmt){document.getElementById('e-la').classList.add('show');ok=false;}else document.getElementById('e-la').classList.remove('show');
    const s=document.getElementById('ssn'),s2=document.getElementById('ssn2');
    const sv=s.value.replace(/\D/g,''),s2v=s2.value.replace(/\D/g,'');
    if(sv.length!==9){s.classList.add('err');document.getElementById('e-ssn').classList.add('show');ok=false;}else{s.classList.remove('err');document.getElementById('e-ssn').classList.remove('show');}
    if(sv!==s2v||s2v.length!==9){s2.classList.add('err');document.getElementById('e-ssn2').classList.add('show');ok=false;}else{s2.classList.remove('err');document.getElementById('e-ssn2').classList.remove('show');}
    const dob=document.getElementById('dob');
    const dobv=dob.value;
    if(!dobv||dobv.length!==10||!/^\d{2}\/\d{2}\/\d{4}$/.test(dobv)){dob.classList.add('err');document.getElementById('e-dob').classList.add('show');ok=false;}else{dob.classList.remove('err');document.getElementById('e-dob').classList.remove('show');}
    const ph=document.getElementById('phone');
    if(ph.value.replace(/\D/g,'').length<10){ph.classList.add('err');document.getElementById('e-ph').classList.add('show');ok=false;}else{ph.classList.remove('err');document.getElementById('e-ph').classList.remove('show');}
  }
  if(from===2){
    ok=req('soi','e-soi')&req('employer','e-emp')&req('payFreq','e-pf')&req('payDay','e-pd')&req('lastPayDate','e-lpd')&req('payMethod','e-pm')&req('grossPay','e-gp')&req('routing','e-rtn')&&ok;
    ok=rr('acctType','e-at')&&ok;
    const a=document.getElementById('acctNum'),a2=document.getElementById('acctNum2');
    if(!a.value||a.value!==a2.value){a.classList.add('err');document.getElementById('e-acn').classList.add('show');ok=false;}else{a.classList.remove('err');document.getElementById('e-acn').classList.remove('show');}
  }
  if(from===3){
    ok=rr('rentOwn','e-ro')&&ok;
    ok=rr('bankruptcy','e-bk')&&ok;
    ok=rr('military','e-mil')&&ok;
    const cb=document.getElementById('consent'),er=document.getElementById('e-con');if(!cb.checked){er.classList.add('show');ok=false;}else er.classList.remove('show');
  }
  if(!ok){const firstErr=document.querySelector('.err, .em.show');if(firstErr)firstErr.scrollIntoView({behavior:'smooth',block:'center'});return;}
  showS(from+1);
}

// ── FORMATTERS ──
function fmtSSN(el){let v=el.value.replace(/\D/g,'');if(v.length>3&&v.length<=5)v=v.slice(0,3)+'-'+v.slice(3);else if(v.length>5)v=v.slice(0,3)+'-'+v.slice(3,5)+'-'+v.slice(5,9);el.value=v;}
function fmtPhone(el){let v=el.value.replace(/\D/g,'');if(v.length>6)v='('+v.slice(0,3)+') '+v.slice(3,6)+'-'+v.slice(6,10);else if(v.length>3)v='('+v.slice(0,3)+') '+v.slice(3);el.value=v;}
function fmtDOB(el){let v=el.value.replace(/\D/g,'');if(v.length>2&&v.length<=4)v=v.slice(0,2)+'/'+v.slice(2);else if(v.length>4)v=v.slice(0,2)+'/'+v.slice(2,4)+'/'+v.slice(4,8);el.value=v;}

// ── HELPERS ──
function pickAmtDd(v){loanAmt=v?parseInt(v):null;if(loanAmt)document.getElementById('e-la').classList.remove('show');}

function togglePw(inputId, btnId){
  const inp=document.getElementById(inputId);
  const isText=inp.type==='text';
  inp.type=isText?'password':'text';
  document.getElementById(btnId).innerHTML=isText
    ?'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
    :'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
}

function pickRo(name, val, ids){
  document.querySelector('input[name="'+name+'"][value="'+val+'"]').checked=true;
  ids.forEach(id=>{const el=document.getElementById(id);if(el){el.classList.toggle('checked',el.querySelector('input').value===val);}});
  const er=document.querySelector('#e-'+name.replace(/([A-Z])/g,'-$1').toLowerCase());
  if(er)er.classList.remove('show');
}

function toggleCb(){
  const cb=document.getElementById('consent');
  cb.checked=!cb.checked;
  document.getElementById('cb-con').classList.toggle('checked',cb.checked);
  if(cb.checked)document.getElementById('e-con').classList.remove('show');
}

// ── FILES ──
function hFile(type,inp){const f=inp.files[0];if(!f)return;const fr=new FileReader();fr.onload=()=>{const b64=fr.result.split(',')[1];if(type==='id'){idB64=b64;showFD('id',f.name);document.getElementById('e-id').classList.remove('show');}else if(type==='bank'){bankB64=b64;showFD('bk',f.name);document.getElementById('e-bv').classList.remove('show');}else if(type==='ps'){psB64=b64;showFD('ps',f.name);}sendHeight();};fr.readAsDataURL(f);}
function showFD(id,name){const fd=document.getElementById('fd-'+id);document.getElementById('fn-'+id).textContent=name;fd.style.display='flex';}

// ── BANK ──
function pickBank(type,el){document.querySelectorAll('.bo').forEach(o=>o.classList.remove('sel'));el.classList.add('sel');document.getElementById('plaid-area').classList.toggle('show',type==='plaid');document.getElementById('upl-area').classList.toggle('show',type==='pdf');document.getElementById('e-bv').classList.remove('show');sendHeight();}

// ── PLAID ──
async function doPlaid(){
  const btn=document.getElementById('plaid-btn'),st=document.getElementById('plaid-st');
  btn.disabled=true;btn.classList.add('loading');st.className='plaid-st';
  try{
    const r=await fetch(API_BASE+'/plaid/link-token');
    const d=await r.json();
    if(!d.link_token)throw new Error('No link token');
    const inIframe=window.self!==window.top;
    const isMobile=/iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if(inIframe&&isMobile){
      const plaidUrl='https://apply.cashrocketanaheim.com/plaid.html?token='+encodeURIComponent(d.link_token)+'&api='+encodeURIComponent(API_BASE);
      window.open(plaidUrl,'_blank');
      btn.disabled=false;btn.classList.remove('loading');
      st.className='plaid-st ok';
      st.innerHTML='✓ Bank connection opened in new tab. Return here when done.';
      st.style.display='flex';
      startPlaidPoll(d.link_token);
      return;
    }
    const handler=Plaid.create({
      token:d.link_token,receivedRedirectUri:null,
      onLoad:()=>{btn.disabled=false;btn.classList.remove('loading');},
      onSuccess:async(pt,meta)=>{
        st.className='plaid-st ok';st.textContent='Connecting...';st.style.display='flex';
        try{
          const ex=await fetch(API_BASE+'/plaid/exchange',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({public_token:pt})});
          const ed=await ex.json();assetTok=ed.asset_report_token;window._plaidAccessToken=ed.access_token||'';plaidOk=true;
          btn.classList.remove('loading');btn.classList.add('connected');
          document.getElementById('plaid-btxt').textContent='✓ Bank Connected!';
          st.textContent='✓ '+(meta.institution?.name||'Bank')+' connected';
          document.getElementById('e-bv').classList.remove('show');sendHeight();
        }catch(e){throw new Error('Exchange failed');}
      },
      onExit:(err)=>{btn.disabled=false;btn.classList.remove('loading');if(err){st.className='plaid-st err';st.textContent='Connection failed. Please try again.';}}
    });
    handler.open();
  }catch(e){btn.disabled=false;btn.classList.remove('loading');st.className='plaid-st err';st.textContent='Error: '+e.message;st.style.display='block';}
}

function startPlaidPoll(lt){
  let attempts=0;
  const iv=setInterval(async()=>{
    attempts++;if(attempts>40){clearInterval(iv);return;}
    try{const r=await fetch(API_BASE+'/plaid/check?token='+encodeURIComponent(lt));const d=await r.json();
    if(d.connected){clearInterval(iv);assetTok=d.asset_report_token;plaidOk=true;
      const btn=document.getElementById('plaid-btn'),st=document.getElementById('plaid-st');
      btn.classList.add('connected');document.getElementById('plaid-btxt').textContent='✓ Bank Connected!';
      st.className='plaid-st ok';st.textContent='✓ '+(d.institution||'Bank')+' connected successfully!';
      document.getElementById('e-bv').classList.remove('show');sendHeight();}}catch(e){}
  },3000);
}

// ── SUBMIT ──
async function submitApp(){
  let ok=true;
  if(!idB64){document.getElementById('e-id').classList.add('show');ok=false;}
  if(!plaidOk&&!bankB64){document.getElementById('e-bv').classList.add('show');ok=false;}
  if(!ok){document.querySelector('.em.show')?.scrollIntoView({behavior:'smooth',block:'center'});return;}
  const btn=document.getElementById('sub-btn');btn.disabled=true;btn.classList.add('loading');
  const v=id=>document.getElementById(id)?.value||'';
  const rv=n=>{const c=document.querySelector('input[name="'+n+'"]:checked');return c?c.value:'';};
  const fd={firstName:v('firstName'),middleName:v('middleName'),lastName:v('lastName'),loanAmount:loanAmt,ssn:v('ssn').replace(/\D/g,''),dob:v('dob'),address:v('addr1'),address2:v('addr2'),city:v('city'),state:v('state'),zip:v('zip'),phone:v('phone'),email:v('email'),sourceOfIncome:v('soi'),employer:v('employer'),payFrequency:v('payFreq'),payDay:v('payDay'),lastPayDate:v('lastPayDate'),paymentMethod:v('payMethod'),grossPay:v('grossPay'),accountType:rv('acctType'),routingNumber:v('routing'),accountNumber:v('acctNum'),bankName:v('bankName'),rentOwn:rv('rentOwn'),bankruptcy:rv('bankruptcy'),military:rv('military'),bankMethod:plaidOk?'Plaid':'PDF Upload',language:lang,hasGovernmentId:!!idB64,hasPaystub:!!psB64};
  try{
    const resp=await fetch(API_BASE+'/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({formData:Object.assign({source_site:window.CRA_SOURCE_SITE},fd),pdfBase64:bankB64||'',assetReportToken:assetTok||'',govIdB64:idB64||'',plaidAccessToken:window._plaidAccessToken||''})});
    const d=await resp.json();
    if(d.success){
  document.getElementById('progress').style.display='none';
  document.querySelector('.hdr')&&(document.querySelector('.hdr').style.display='none');
  for(let i=1;i<=4;i++){const el=document.getElementById('s'+i);if(el)el.style.display='none';}
  document.getElementById('success').classList.add('show');
  window.scrollTo({top:0,behavior:'smooth'});
  sendHeight();
}
    else throw new Error(d.error||'Failed');
  }catch(e){btn.disabled=false;btn.classList.remove('loading');alert('Submission failed: '+e.message);}
}

// ── ADMIN SETTINGS ──
async function chkSettings(){try{const r=await fetch(API_BASE+'/admin/settings');const d=await r.json();pdfOk=d.allowPdfUpload!==false;if(!pdfOk){const o=document.getElementById('bo-pdf');o.classList.add('off');const b=document.getElementById('bo-ubadge');b.textContent=lang==='en'?'Unavailable':'No disponible';b.style.display='inline-block';const sp=document.getElementById('pdf-spacer');if(sp)sp.style.display='none';}}catch(e){}}

// ── GOOGLE PLACES ──
function initGooglePlaces(){ /* Google Places removed — plain text field */ }
window.gm_authFailure = function(){}

// ── DRAG/DROP ──
function initDragDrop(){
  ['id','bk','ps'].forEach(t=>{
    const dz=document.getElementById('dz-'+t);
    if(!dz)return;
    dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('over')});
    dz.addEventListener('dragleave',()=>dz.classList.remove('over'));
    dz.addEventListener('drop',e=>{
      e.preventDefault();dz.classList.remove('over');
      const inp=document.getElementById('fi-'+(t==='id'?'id':t==='bk'?'bk':'ps'));
      if(e.dataTransfer.files[0]){inp.files=e.dataTransfer.files;hFile(t==='id'?'id':t==='bk'?'bank':'ps',inp);}
    });
  });
}

window.onload=()=>{
  chkSettings();
  initDragDrop();
  setTimeout(()=>{try{initGooglePlaces();}catch(e){console.warn('Places init error:',e);}},1500);
};

function sendHeight(){window.parent.postMessage({type:'cif-height',height:document.body.scrollHeight+50},'*');}
window.addEventListener('load',sendHeight);window.addEventListener('resize',sendHeight);setInterval(sendHeight,500);

document.addEventListener('touchmove',function(e){if(e.touches.length>1)e.preventDefault();},{passive:false});
document.addEventListener('gesturestart',function(e){e.preventDefault();},{passive:false});

// ── MOBILE MENU TOGGLE ──
(function(){
  const toggle=document.getElementById('menu-toggle');
  const menu=document.getElementById('mobile-menu');
  const overlay=document.getElementById('mobile-overlay');
  if(!toggle||!menu)return;
  function openMenu(){toggle.classList.add('active');menu.classList.add('open');overlay.classList.add('open');document.body.style.overflow='hidden';}
  function closeMenu(){toggle.classList.remove('active');menu.classList.remove('open');overlay.classList.remove('open');document.body.style.overflow='';}
  toggle.addEventListener('click',()=>{menu.classList.contains('open')?closeMenu():openMenu();});
  overlay.addEventListener('click',closeMenu);
  const closeBtn=document.getElementById('mobile-close-btn');
  if(closeBtn)closeBtn.addEventListener('click',closeMenu);
  document.querySelectorAll('.mobile-nav-item.has-sub>a').forEach(a=>{
    a.addEventListener('click',e=>{e.preventDefault();a.parentElement.classList.toggle('open');});
  });
})();
