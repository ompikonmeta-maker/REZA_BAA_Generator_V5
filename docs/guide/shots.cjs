// Screenshot panduan (tema terang) + posisi penanda bernomor (disimpan ke meta.json)
const {chromium}=require('/opt/node22/lib/node_modules/playwright');
const fs=require('fs');
const OUT='shots';fs.mkdirSync(OUT,{recursive:true});
const META=fs.existsSync('meta.json')?JSON.parse(fs.readFileSync('meta.json')):{};
const ONLY=process.argv[2]||'';      // jalankan sebagian: admin | op | fresh
const G='http://localhost:8140',F='http://localhost:8141';
const W=1366,H=820;
const CSS=`#ocr-note{display:none!important}#toast{display:none!important}.wb-pop{display:none!important}*{caret-color:transparent!important}`;
(async()=>{const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'});
const mk=async()=>{const c=await b.newContext({viewport:{width:W,height:H},deviceScaleFactor:1.5,colorScheme:'light'});
  // intro animasi tidak ikut difoto: anggap semua akun sudah melihatnya
  await c.route(/\/api\/auth\/(me|login)$/,async r=>{const res=await r.fetch();let j;try{j=await res.json();}catch(e){return r.fulfill({response:res});}if(j&&typeof j==='object')j.intro_seen=true;r.fulfill({response:res,json:j});});
  await c.addInitScript(()=>{try{localStorage.setItem('md3-theme','light');}catch(e){}});
  const p=await c.newPage();p.on('pageerror',e=>console.log('ERR',e.message));return p;};
const light=async p=>{await p.evaluate(()=>{try{MD3.setTheme('light');}catch(e){}});await p.addStyleTag({content:CSS});await p.waitForTimeout(500);};
const login=async(p,base,u,pw,wait=5200)=>{await p.goto(base);await p.waitForTimeout(600);await p.fill('#lg-user',u);await p.fill('#lg-pass',pw);await p.click('#lg-btn');await p.waitForTimeout(wait);await light(p);};
const sw=async(p,id,land)=>{if(await p.evaluate(()=>PJ.id)!==String(id)){await p.evaluate(([id,l])=>pjSwitch(String(id),l),[id,land||'dashboard']);await p.waitForTimeout(5500);await light(p);}};
const box=async(p,sels)=>p.evaluate(sels=>sels.map(s0=>{let el=null;const [s,up]=s0.split(' >>up ');
    if(s.startsWith('ct:')){const t=s.slice(3);el=[...document.querySelectorAll('.card')].find(c=>{const h=c.querySelector('.ct,h3');const r=c.getBoundingClientRect();return h&&h.textContent.trim()===t&&r.width&&r.top<innerHeight;});}
    else if(s.startsWith('txt:')){const [tag,t]=s.slice(4).split('|');el=[...document.querySelectorAll(tag)].find(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&e.textContent.trim().includes(t);});}
    else el=[...document.querySelectorAll(s)].find(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight;});
    if(el&&up)el=el.closest(up)||el;
    if(!el)return null;const r=el.getBoundingClientRect();return {x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)};}),sels);
const cap=async(p,name,sels=[],clip=null)=>{try{await p.waitForTimeout(700);const m=await box(p,sels);
    const c=clip||{x:0,y:0,width:W,height:H};
    await p.screenshot({path:`${OUT}/${name}.jpg`,type:'jpeg',quality:84,clip:c});
    META[name]={w:c.width,h:c.height,marks:m.map((r,i)=>r?{x:r.x-c.x,y:r.y-c.y,w:r.w,h:r.h}:(console.log('  miss',name,sels[i]),null))};
    fs.writeFileSync('meta.json',JSON.stringify(META,null,1));console.log('ok',name);}catch(e){console.log('FAIL',name,e.message.split('\n')[0]);}};
const tf=(p,sel,v)=>p.locator(sel).locator('input').fill(v);
const top=p=>p.evaluate(()=>document.querySelectorAll('.canvas-body,.canvas').forEach(e=>e.scrollTop=0));
const go=async(p,v)=>{await p.evaluate(v=>navTo(v),v);await p.waitForTimeout(1500);await top(p);await p.waitForTimeout(300);};
const set=async(p,s)=>{await p.evaluate(s=>openSettings(s),s);await p.waitForTimeout(1700);};
const creds=JSON.parse(fs.readFileSync('creds.json'));

if(!ONLY||ONLY==='fresh'){const p=await mk();
  await login(p,F,'admin','admin',4500);
  await cap(p,'a_firstpw',['#onbNew','#onbNew2','#onbGo']);
  await tf(p,'#onbNew','rahasia1');await tf(p,'#onbNew2','rahasia1');await p.click('#onbGo');await p.waitForTimeout(1800);await light(p);
  await tf(p,'#onbName','Kopdes Merah Putih');await tf(p,'#onbPre','lok');await p.waitForTimeout(300);
  await cap(p,'a_firstproject',['#onbName','#onbPre','.onb .pjm-sw','#onbGo']);
  await p.context().close();}

if(!ONLY||ONLY==='admin'){const p=await mk();
  await login(p,G,'admin','admin123');await sw(p,1);
  await go(p,'dashboard');
  await cap(p,'a_layout',['#psw','.navitem[data-view="portfolio"]','.navitem[data-view="entry"]','.navitem[data-view="locations"]','#setToggle','#bellWrap','#wb','#themeBtn']);
  await cap(p,'a_dash',['#dChip','txt:span|Team vs target >>up .card','ct:Team','ct:Work rhythm']);
  await go(p,'progress');await cap(p,'a_progress',['#v-progress .card','#wmHost']);
  await go(p,'portfolio');await cap(p,'a_portfolio',['#pfSum','.pf-card','.pf-card .pf-map, .pf-card svg']);
  // mode Setup (project 4)
  await sw(p,4,'setup:overview');await p.waitForTimeout(800);
  await cap(p,'a_setup_overview',['#sxNav','.sx-card[data-k="data"]','.sx-card[data-k="template"]','.sx-card[data-k="team"]','.sx-card[data-k="target"]','#sxActivate']);
  await p.click('.sx-step[data-k="data"]');await p.waitForTimeout(1500);
  await cap(p,'a_setup_fields',['#ldConfirm','#ldTabs','#lf-list .ecard','#lf-sug','#lf-add','#ldConfirmBtn']);
  await p.click('#ldTabs button[data-k="photo"]');await p.waitForTimeout(1300);
  await cap(p,'a_setup_photos',['#ldTabs button[data-k="photo"]','#pc-list','#pc-add']);
  await p.click('#ldTabs button[data-k="inventory"]');await p.waitForTimeout(1300);
  await cap(p,'a_setup_inventory',['#ldTabs button[data-k="inventory"]','#di-list','#ket-chips']);
  await p.evaluate(async()=>{const u=(await api('/api/users')).find(x=>x.username==='rudi');if(u)await api('/api/users/'+u.id,{method:'DELETE'});});
  await p.click('.sx-step[data-k="team"]');await p.waitForTimeout(1500);
  await tf(p,'#tmName','Rudi Hartono');await tf(p,'#tmUser','rudi');await p.click('#tmAdd');await p.waitForTimeout(1600);
  await cap(p,'a_setup_team',['.tm-new','#tmAdd','#tmTemp','.tm-list']);
  await p.click('.sx-step[data-k="target"]');await p.waitForTimeout(1200);
  await cap(p,'a_setup_target',['#sxTot','#sxDate','#sxTSave']);
  // project berikutnya: pilihan "Start from"
  await p.click('.sx-step[data-k="projects"]');await p.waitForTimeout(1500);await p.click('#pjm-new');await p.waitForTimeout(800);
  await tf(p,'#pjm-name','Puskesmas Jateng');await tf(p,'#pjm-pre','PKJ');await p.click('#pjmSrc button[data-s="copy"]');await p.waitForTimeout(500);
  await cap(p,'a_newproject',['#pjmSrc','.pjm-src .sel-dd','#pjm-pre','#setSaveBtn, #pjm-save']);
  await p.evaluate(()=>{PJM.snap=null;});
  // Template (project 1)
  await sw(p,1,'set:templates');await set(p,'templates');
  await cap(p,'a_template',['#map-cur','#tpl-up-btn','#mstep1 >>up .mstep','#mstep2 >>up .mstep','#mstep3 >>up .mstep','#map-save']);
  await p.click('#mstep2');await p.waitForTimeout(1500);
  await cap(p,'a_template_map',['#mstep2 >>up .mstep','.mtg','#map-ring','#map-save']);
  // Location Log + drawer
  await go(p,'locations');
  await cap(p,'a_log',['.lg-seg','txt:md-button|Import locations','#loc-search','#loc-creator','#loc-wil','#locTools','#loc-table tr.lrow td']);
  await p.evaluate(async()=>{const r=await api('/api/locations?q=LOK_00012');openLocDrawer(r.rows[0].id);});await p.waitForTimeout(1800);
  await cap(p,'a_drawer',['#ldHero .ld-ring','.ld-done','.ld-sec + .ld-doc, .ld-doc','txt:div|Installed devices','#ldFoot']);
  await p.keyboard.press('Escape');await p.waitForTimeout(500);
  await go(p,'import');await cap(p,'a_import',['#imp-s1','#imp-tpl','#imp-drop','#imp-s4']);
  await go(p,'notif');await cap(p,'a_notif',['#notif-table tr','txt:md-button|Approve','txt:md-button|Reject','#bellWrap']);
  await go(p,'trash');await cap(p,'a_trash',['.lg-seg','#trash-table']);
  // Project & status, Freeze, ganti prefix
  await set(p,'pjstatus');
  await cap(p,'a_status',['.st-strip','#pjmFreeze','#pjm-next','#pjm-total','.ft-box','.pjm-mem']);
  await p.click('#pjmFreeze');await p.waitForTimeout(500);await p.click('.fzd .chips button:nth-child(1)');
  await cap(p,'a_freeze',['#fzMsg','.fzd .chips','.fzd .fz-ban','#fzOk']);
  await p.click('#fzOk');await p.waitForTimeout(1800);
  await cap(p,'a_frozen',['#fzBan','.st-strip','#pjmMsg','#pjmUnfreeze','#pjmRecode']);
  await p.click('#pjmRecode');await p.waitForTimeout(500);await tf(p,'#rcPre','KMP');await p.click('#rcAn');await p.waitForTimeout(1500);
  await cap(p,'a_recode',['#rcPre','.rc-grid','.rc-map','.rc-ok.w','#rcGo']);
  await p.evaluate(()=>document.querySelector('.fzd').remove());
  await p.context().close();}

if(!ONLY||ONLY==='op'){
  // operator: frozen screens dulu (project 1 masih frozen dari langkah admin)
  let p=await mk();await login(p,G,'sari','sari12345');await sw(p,1);
  const frozen=await p.evaluate(()=>PJ.cur.status==='frozen');
  if(frozen){await go(p,'dashboard');await cap(p,'o_frozen_dash',['#fzBan']);
    await go(p,'entry');await cap(p,'o_frozen_entry',['#fzPaused .eb']);}
  await p.context().close();
  // admin: unfreeze
  const a=await mk();await login(a,G,'admin','admin123');await sw(a,1);
  await a.evaluate(()=>api('/api/projects/1/unfreeze',{method:'POST'}).catch(()=>{}));await a.context().close();
  // operator baru: password sementara
  p=await mk();await login(p,G,'dewi',creds.dewi,4500);
  await cap(p,'o_firstpw',['#onbNew','#onbNew2','#onbGo']);await p.context().close();
  // sari: kerja harian
  p=await mk();await login(p,G,'sari','sari12345');await sw(p,1);
  await go(p,'dashboard');
  await cap(p,'o_dash',['txt:md-button|New location','#meCont','ct:My week','ct:My drafts']);
  // BAA Entry: lokasi LOK_00019 (paling lengkap)
  await p.evaluate(()=>{const id=(LOC_ROWS||[]).find?null:null;});
  await p.evaluate(async()=>{const r=await api('/api/locations?q=LOK_00019');const l=(r.rows||[])[0];gotoEntry();await openLoc(l.id);});await p.waitForTimeout(2500);
  await cap(p,'o_entry',['#picker','#entry-new','#loc-fields','#wil-field','aside.summary .card','#save-btn']);
  await p.evaluate(()=>document.querySelector('#wil-field').scrollIntoView({block:'center'}));await p.waitForTimeout(400);
  await p.evaluate(()=>{const i=document.querySelector('#wil-field input');i.focus();i.value='cibodas lembang';i.dispatchEvent(new Event('input',{bubbles:true}));});await p.waitForTimeout(1800);
  await cap(p,'o_wilayah',['#wil-field .wl-box','#wil-field .wl-pop .wl-it','#wil-field .wl-man']);
  await p.keyboard.press('Escape');await p.evaluate(()=>document.activeElement&&document.activeElement.blur());await p.mouse.click(5,400);await p.waitForTimeout(400);
  await p.evaluate(()=>document.querySelector('#inv-body').scrollIntoView({block:'center'}));await p.waitForTimeout(600);
  await cap(p,'o_inventory',['#inv-body tr','#inv-add','#inv-body']);
  await p.evaluate(()=>document.querySelector('#photoDock').scrollIntoView({block:'start'}));await p.waitForTimeout(600);
  await cap(p,'o_photos',['#dock-auto','#btn-clrall','#foto-count','#photo-slots']);
  await p.evaluate(()=>document.querySelector('#scanCard').scrollIntoView({block:'center'}));await p.waitForTimeout(600);
  await cap(p,'o_scan',['#scanCard','#scanTag']);
  await p.evaluate(()=>document.querySelector('#sum-ring-pct').scrollIntoView({block:'center'}));await p.waitForTimeout(500);
  await cap(p,'o_summary',['#sum-ring-pct','#sum-loc-row','#sum-scan-row','#save-btn','#exp-pdf','#exp-xlsx']);
  // Location Log + drawer (lokasi sendiri belum lengkap)
  await go(p,'locations');
  await cap(p,'o_log',['#loc-search','.segt, #loc-filter','#loc-table tr.lrow','#locTools']);
  await p.evaluate(async()=>{const r=await api('/api/locations?q=LOK_00021');const l=(r.rows||[])[0];openLocDrawer(l.id);});await p.waitForTimeout(1800);
  await cap(p,'o_drawer',['.ld-tiles','.ld-tile','.ld-doc','#ldFoot']);
  await p.keyboard.press('Escape');await p.waitForTimeout(400);
  // lokasi milik orang lain -> minta akses
  await p.evaluate(async()=>{const r=await api('/api/locations?size=100');const l=(r.rows||[]).find(x=>x.owner_id!==S.user.id);if(l)openLocDrawer(l.id);});await p.waitForTimeout(1800);
  await cap(p,'o_request',['.ld-ro','#ldReq, #ldFoot .ld-btn']);
  await p.keyboard.press('Escape');await p.waitForTimeout(400);
  await p.click('#loc-exp-xlsx');await p.waitForTimeout(900);
  await cap(p,'o_export',['#expOptFilter','#expOptAll','#expOk']);
  await p.context().close();}
if(ONLY==='extra'){const p=await mk();await login(p,G,'admin','admin123');await sw(p,1);
  await set(p,'users');await cap(p,'a_users',['#usr-add','#usr-table tr']);
  await p.evaluate(()=>openUser(null));await p.waitForTimeout(800);await cap(p,'a_user_dlg',['#u-username','.urole, #uRoles','#uPj','#userSave']);
  await p.evaluate(()=>$('#userDlg').close(true));await p.waitForTimeout(500);
  await set(p,'backup');await cap(p,'a_backup',['#bk-download','#bk-file','#bk-restore']);
  await p.context().close();}
await b.close();})();
