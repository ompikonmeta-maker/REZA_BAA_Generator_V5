// PDF A4 dari halaman panduan yang disajikan server (font ikon lokal ikut termuat)
const {chromium}=require('/opt/node22/lib/node_modules/playwright');
const [url,out]=process.argv.slice(2);
(async()=>{const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'});
const p=await (await b.newContext()).newPage();await p.goto(url,{waitUntil:'networkidle'});
await p.evaluate(()=>[...document.images].forEach(i=>i.loading='eager'));
await p.evaluate(()=>Promise.all([...document.images].map(i=>i.complete?0:new Promise(r=>{i.onload=i.onerror=r;})).concat(document.fonts.ready)));
await p.emulateMedia({media:'print'});
await p.pdf({path:out,format:'A4',printBackground:true,preferCSSPageSize:true,displayHeaderFooter:true,
  headerTemplate:'<span></span>',footerTemplate:'<div style="font:9px system-ui;color:#778;width:100%;text-align:center">Panduan BAA.flow · <span class="pageNumber"></span>/<span class="totalPages"></span></div>'});
await b.close();console.log('pdf',out);})();
