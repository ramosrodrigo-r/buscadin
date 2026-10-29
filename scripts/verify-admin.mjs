// Real browser E2E against isolated, temporary SQLite and local processes.
// node scripts/verify-admin.mjs /absolute/path/to/playwright/index.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(process.argv[2]).href);
const dir=await fs.mkdtemp(path.join(os.tmpdir(),'buscadin-admin-e2e-'));
const env={...process.env,DATABASE_URL:`sqlite+aiosqlite:///${dir}/test.db`,ADMIN_PASSWORD:'test-only-password-isolated-browser',ADMIN_ORIGIN:'http://127.0.0.1:8082',SITE_OFFICIAL_DOMAINS:'jobs.example',SITE_API_TOKEN:'test-only-portal-token',TELEGRAM_ADMIN_USER_ID:'0',PORTAL_PORT:'8083',SITE_BASE_URL:'http://127.0.0.1:8083'};
const processes=[];
async function launch(args,wait=false){const proc=spawn('uv',args,{env,stdio:['ignore','pipe','pipe']});processes.push(proc);let log='';proc.stdout.on('data',chunk=>log+=chunk);proc.stderr.on('data',chunk=>log+=chunk);if(wait)await new Promise((resolve,reject)=>proc.on('exit',code=>code===0?resolve():reject(Error(log))));return proc;}
async function ready(url){for(let i=0;i<80;i++){try{const r=await fetch(url);if(r.ok)return;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}throw Error('Server did not start: '+url);}
let browser;
try{
 await launch(['run','alembic','upgrade','head'],true);
 await launch(['run','buscadin-admin']);await launch(['run','buscadin-portal']);
 await ready(env.ADMIN_ORIGIN);await ready(env.SITE_BASE_URL+'/healthz');
 browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(env.ADMIN_ORIGIN);await page.locator('#password').fill(env.ADMIN_PASSWORD);await page.getByRole('button',{name:'Entrar no painel'}).click();
 await page.getByRole('heading',{name:'Fila de vagas'}).waitFor();
 await page.getByRole('button',{name:'+ Cadastrar vaga'}).click();
 await page.locator('#title').fill('Anotação de vídeos — teste <script>alert(1)</script>');await page.locator('#company').fill('Empresa de teste');
 await page.locator('#source_url').fill('https://jobs.example/source');await page.locator('#application_url').fill('https://jobs.example/apply');
 await page.locator('#eligibility_status').selectOption('confirmed_br');await page.locator('#evidence').fill('A fonte informa: residentes no Brasil.');
 await page.locator('#education').selectOption('not_required');await page.locator('#education_evidence').fill('Não exige graduação.');
 await page.locator('#description').fill('Conteúdo de teste isolado.');await page.getByRole('button',{name:'Salvar rascunho'}).click();
 await page.getByRole('heading',{name:'Revisar oportunidade'}).waitFor();
 await page.locator('#summary').fill('Oportunidade de teste para revisão humana, sem publicação em produção.');
 await page.getByRole('button',{name:'Conferir prévia'}).click();await page.getByRole('button',{name:'Confirmar publicação'}).waitFor();
 await fs.mkdir('.preview/admin',{recursive:true});
 await page.screenshot({path:'.preview/admin/editor-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Confirmar publicação'}).click();await page.getByRole('button',{name:'Retirar do catálogo'}).waitFor();
 assert.equal((await fetch(env.SITE_BASE_URL+'/vagas/1')).status,200);
 await page.locator('#reason').fill('Fim do teste');page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Retirar do catálogo'}).click();
 await page.getByRole('button',{name:'Conferir prévia'}).waitFor();
 await page.waitForFunction(()=>!document.querySelector('#unpublish'));
 assert.equal((await fetch(env.SITE_BASE_URL+'/vagas/1')).status,404);
 for(const width of [1440,390,320]){
   await page.setViewportSize({width,height:900});
   for(const route of ['jobs','job/1','sources','referrals','audit']){
     await page.goto(env.ADMIN_ORIGIN+'/#'+route);await page.locator('#workspace h1').waitFor();
     assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Overflow ${route} ${width}`);
     if(route==='jobs'||route==='job/1')await page.screenshot({path:`.preview/admin/${route==='jobs'?'queue':'editor'}-${width}.png`,fullPage:true});
   }
 }
 // UI states use a bounded fixture; live provider checks run separately.
 let crawlPosts=0;
 await page.route('**/api/crawl',route=>{
   if(route.request().method()==='POST')crawlPosts++;
   return route.fulfill({json:crawlPosts?{status:'completed',results:[{source:'micro1',inserted:2,skipped:4,failed:0}]}:{status:'idle',results:[]}});
 });
 await page.goto(env.ADMIN_ORIGIN+'/#sources');await page.getByRole('button',{name:'Buscar nas quatro empresas'}).waitFor();
 assert.equal(crawlPosts,0);
 await page.getByRole('button',{name:'Buscar nas quatro empresas'}).click();
 await page.getByText('2 novas · 4 já conhecidas · 0 falhas').waitFor();assert.equal(crawlPosts,1);
 await page.screenshot({path:'.preview/admin/crawlers-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Sair da conta'}).click();await page.locator('#password').waitFor({state:'visible'});
 assert.equal((await page.request.get(env.ADMIN_ORIGIN+'/api/jobs')).status(),401);
 assert.deepEqual(errors,[]);
 console.log('PASS: login, create, preview, publish, public visibility, withdraw, logout; five screens at 1440/390/320px; no JS errors.');
}finally{if(browser)await browser.close();for(const proc of processes)if(proc.exitCode===null)proc.kill('SIGTERM');}
