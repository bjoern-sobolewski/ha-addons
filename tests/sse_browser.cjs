const {chromium} = require('/test/node_modules/playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
fs.writeFileSync('/output/browser-result.log','');
const log=console.log;console.log=(...args)=>{log(...args);fs.appendFileSync('/output/browser-result.log',args.join(' ')+'\n');};
const f = JSON.parse(fs.readFileSync('/fixtures/browser.json','utf8'));
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function until(check, label, timeout=45000) {const end=Date.now()+timeout; while(Date.now()<end) {if(await check())return;await pause(250);}throw Error(label);}
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1050},locale:'en-US'});
 const login=await context.request.post(f.keeper+'/api/v1/auth/login',{headers:{'X-CPA-Usage-Keeper-Request':'fetch'},data:{password:f.password}}); assert.equal(login.status(),204);
 const page=await context.newPage(); let calls=[]; let documents=0;
 page.on('response',r=>{if(r.url().includes('/api/v1/'))calls.push(r.url());});
 page.on('request',r=>{if(r.isNavigationRequest()&&r.frame()===page.mainFrame())documents++;});
 async function traffic() {const response=await fetch(f.api+'/v1/responses',{method:'POST',headers:{Authorization:'Bearer '+f.key,'Content-Type':'application/json'},body:JSON.stringify({model:'a/quota-test',input:'Reply briefly.',stream:false})});assert.equal(response.status,200);}
 for(const [route,endpoint] of [['overview','usage/overview?'],['realtime','usage/overview/realtime?'],['analysis','usage/analysis?'],['request-events','usage/events?'],['credentials','usage/identities/page?'],['ai-provider','usage/identities/page?']]) {
  await page.goto(f.keeper+'/'+route);
  await until(()=>calls.some(u=>u.includes(endpoint)),'initial '+route);
  await pause(1500);
  const initial=calls.filter(u=>u.includes(endpoint)).length;
  const docCount=documents;
  await page.evaluate(()=>{window.sseCanvases=[...document.querySelectorAll('canvas')];window.sseBars=[...document.querySelectorAll('[data-usage-total]')];});
  const before=await page.locator('[data-usage-total]').evaluateAll(es=>es.map(e=>e.getAttribute('data-usage-total')).join(','));
  await traffic();
  await until(()=>calls.filter(u=>u.includes(endpoint)).length>initial,'SSE refresh '+route);
  await pause(1200);
  assert.equal(documents,docCount,'page must not navigate on '+route);
  assert(await page.evaluate(()=>window.sseCanvases.every(e=>e.isConnected)),'chart remounted '+route);
  if(route==='ai-provider') {
   await until(async()=>before!==await page.locator('[data-usage-total]').evaluateAll(es=>es.map(e=>e.getAttribute('data-usage-total')).join(',')),'credential graph counts');
   assert(await page.evaluate(()=>window.sseBars.every(e=>e.isConnected)),'usage bars remounted');
   await page.screenshot({path:'/output/keeper-usage.png',fullPage:true});
   const detail=page.locator('[data-credential-detail-trigger]').first();
   assert(await detail.count(),'account detail trigger'); {
    await detail.click();await page.getByRole('dialog').waitFor();
    const n=calls.filter(u=>/usage\/identities\/\d+(?:\?|$)/.test(u)).length;
    await traffic();await until(()=>calls.filter(u=>/usage\/identities\/\d+(?:\?|$)/.test(u)).length>n,'open account refresh');
    await page.screenshot({path:'/output/keeper-account.png',fullPage:true});
   }
  }
  console.log('PASS: Keeper '+route+' refreshes over SSE without navigation or chart replacement');
 }
 const panel=await context.newPage();let pcalls=[];
 panel.on('response',r=>{if(r.url().includes('/v8/management/'))pcalls.push(r.url());});
 await panel.goto(f.private+'/management.html');
 await panel.locator('input[name="cpa-management-key"]').fill(f.management);
 await panel.locator('button[type="submit"]').click();
 await until(()=>pcalls.some(u=>u.includes('/observability/usage/api-keys')),'CPAMC initial stats');
 await pause(1500);let before=pcalls.filter(u=>u.includes('/observability/usage/api-keys')).length;
 await traffic();await until(()=>pcalls.filter(u=>u.includes('/observability/usage/api-keys')).length>before,'CPAMC live usage');
 console.log('PASS: CPAMC dashboard refreshes request counts over authenticated SSE');
 await panel.evaluate(()=>localStorage.setItem('providersPage.uiState',JSON.stringify({activeBrand:'codex',filtersByBrand:{}})));
 await panel.goto(f.private+'/management.html#/ai-providers');await panel.locator('[data-usage-total]').first().waitFor();await pause(2000);
 const counts=()=>panel.locator('[data-usage-total]').evaluateAll(es=>es.map(e=>e.getAttribute('data-usage-total')).join(','));const oldCounts=await counts();
 await panel.evaluate(()=>window.sseBars=[...document.querySelectorAll('[data-usage-total]')]);
 await traffic();await until(async()=>oldCounts!==await counts(),'CPAMC usage graph updates');
 assert(await panel.evaluate(()=>window.sseBars.every(e=>e.isConnected)),'CPAMC bars remounted');
 assert.equal(await panel.locator('[data-usage-total]').first().evaluate(e=>Math.round(e.getBoundingClientRect().height)),36,'CPAMC graph height');
 console.log('PASS: CPAMC request-volume graph updates in place');
 await panel.locator('[data-usage-total]').first().scrollIntoViewIfNeeded();await pause(500);
 await panel.screenshot({path:'/output/cpamc-providers.png',fullPage:true});
 console.log('CPAMC visible graph buckets: '+await panel.locator('[data-usage-total]').count());
 // Older backends and cached observations may contain credit-only null headers.
 let nullHeadersInjected=false;
 const observationFixture=await (await fetch(f.private+'/v8/management/quota/observations',{headers:{Authorization:'Bearer '+f.management}})).json();
 const quotaAccount=observationFixture.items.find(item=>item.provider==='codex');assert(quotaAccount,'synthetic quota account');
 await panel.route('**/v8/management/credentials',route=>route.fulfill({json:{files:[{name:'synthetic-oauth.json',type:'codex',provider:'codex',auth_type:'oauth',auth_index:quotaAccount.auth_index,status:'active',disabled:false,runtime_only:false,supports_quota:true}]}}));
 await panel.route('**/v8/management/quota/observations',async route=>{
  const response=await route.fetch();const body=await response.json();
  const account=body.items?.find(item=>item.provider==='codex');
  if(account){body.items.push({...account,window:'reset-credits',headers:null,observed_at:new Date().toISOString(),reset_credits_available_count:3});nullHeadersInjected=true;}
  await route.fulfill({response,json:body});
 });
 await panel.goto(f.private+'/management.html#/auth-files');
 await traffic(); // Publish a fresh quota observation after installing the response fixture.
 await until(()=>nullHeadersInjected,'null-header observation fixture');
 await panel.locator('[data-quota-updated]').first().waitFor();
 assert.equal(await panel.getByText('Unexpected Application Error!',{exact:true}).count(),0,'auth-files crashed on null headers');
 assert.equal(await panel.getByText('This page could not load',{exact:true}).count(),0,'null headers should render normally');
 await panel.screenshot({path:'/output/cpamc-auth-files-null-headers.png',fullPage:true});
 console.log('PASS: CPAMC auth-files renders cached null-header credit observations without a crash');

 await page.setViewportSize({width:390,height:844});await page.goto(f.keeper+'/ai-provider');await page.locator('[data-usage-total]').first().waitFor();await pause(1000);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'mobile horizontal overflow');
 await page.screenshot({path:'/output/keeper-usage-mobile.png',fullPage:true});
 const providerCount=async()=>(await (await fetch('http://mock:9000/stats')).json()).calls;
 const initialProviderCount=await providerCount();const localReads=calls.length;await pause(18000);
 assert.equal(await providerCount(),initialProviderCount,'idle UI caused provider traffic');
 assert(calls.length-localReads<40,'local cache reads formed a refresh loop');
 console.log('PASS: visible live clients and rolling-window clock do not generate provider traffic or refresh loops');
 await browser.close();
})().catch(e=>{fs.appendFileSync('/output/browser-result.log','FAIL: '+e.message+'\n');console.error(e.message);process.exit(1);});
