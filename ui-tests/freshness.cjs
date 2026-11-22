const {chromium}=require('playwright');
const fs=require('fs');
const assert=require('node:assert/strict');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
const page=await browser.newPage();
await page.route('**/*',r=>r.abort());
const errors=[];page.on('pageerror',e=>errors.push(String(e)));
const data=JSON.parse(fs.readFileSync(process.argv[2]||'dist/data/bundle.json','utf8'));
const now=Date.now();
data.jobs=data.jobs.slice(0,5).map((j,i)=>({...j,id:'fixture-'+i,first_seen_at:[now-3600000,now-2*86400000,now-10*86400000,null,now+86400000][i]}));
data.jobs.forEach(j=>{if(j.first_seen_at)j.first_seen_at=new Date(j.first_seen_at).toISOString()});
let html=fs.readFileSync('dist/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace(/<link\b[^>]*>/g,'');
await page.setContent(html);await page.addStyleTag({path:'dist/style.css'});
await page.evaluate(d=>window.RADAR_DATA=d,data);await page.addScriptTag({path:'dist/app.js'});
await page.locator('[data-new-jobs]').click();
await page.waitForFunction(()=>document.querySelector('#resultCount').textContent.includes(': 1 из'));
assert.equal(await page.locator('[data-filter="freshness"]').inputValue(),'1');
assert.equal(await page.locator('#sort').inputValue(),'newest');
await page.locator('#filterToggle').click();
await page.locator('[data-filter="freshness"]').selectOption('7');
assert.match(await page.locator('#resultCount').textContent(),/: 2 из/);
await page.locator('[data-filter="freshness"]').selectOption('30');
assert.match(await page.locator('#resultCount').textContent(),/: 3 из/);
assert.equal(await page.locator('tbody .jobtitle').first().textContent(),data.jobs[0].title);
await page.locator('#reset').click();
assert.match(await page.locator('#resultCount').textContent(),/: 5 из/);
for(const width of [320,375,390,430,768,1024,1440]){
 await page.setViewportSize({width,height:900});
 const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,elements:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,cls:e.className,id:e.id,right:e.getBoundingClientRect().right})).slice(-15)}));
 assert(overflow.scroll<=width,`Overflow at ${width}: ${JSON.stringify(overflow)}`);
}
assert.equal(await page.locator('tbody .badge.new').count(),1);
assert.deepEqual(errors,[]);
console.log('PASS: freshness ranges, unknown/future dates, newest sorting, overview shortcut, reset and seven viewport widths');
await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
