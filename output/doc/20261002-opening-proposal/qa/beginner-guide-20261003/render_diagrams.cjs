const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const qa = __dirname;
const dist = '/tmp/bigsmall-guide-mermaid-20261003/node_modules/mermaid/dist';
const assets = path.resolve(qa, '../../assets/beginner-guide-20261003');

async function main() {
  await fs.mkdir(assets, {recursive:true});
  const server = http.createServer(async (req, res) => {
    try {
      if(req.url === '/') {
        res.setHeader('Content-Type','text/html; charset=utf-8');
        res.end('<!doctype html><html><head><meta charset="utf-8"></head><body><div id="diagram"></div><script type="module">import mermaid from "/deps/mermaid.esm.min.mjs";window.mermaid=mermaid;</script></body></html>');
        return;
      }
      const relative = decodeURIComponent(req.url.slice('/deps/'.length));
      const full = path.resolve(dist, relative);
      if(!req.url.startsWith('/deps/') || !full.startsWith(dist + path.sep)) {res.writeHead(404);res.end();return;}
      res.setHeader('Content-Type','text/javascript; charset=utf-8');
      res.end(await fs.readFile(full));
    } catch { res.writeHead(404);res.end(); }
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true,args:['--no-sandbox']});
    const page = await browser.newPage({viewport:{width:1800,height:1600},deviceScaleFactor:1});
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>Boolean(window.mermaid));
    await page.addStyleTag({content:'body{margin:20px;background:#fff;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}#diagram{display:inline-block;}'});
    await page.evaluate(()=>window.mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'base',fontFamily:'Noto Sans CJK SC, Microsoft YaHei, sans-serif',themeVariables:{fontSize:'18px',primaryColor:'#edf4fc',primaryTextColor:'#17283d',primaryBorderColor:'#537799',lineColor:'#537799',secondaryColor:'#f2f6ec',tertiaryColor:'#fff3de'},flowchart:{htmlLabels:false,useMaxWidth:false,nodeSpacing:35,rankSpacing:45,curve:'linear'}}));
    const results=[];
    for(let n=1;n<=9;n++){
      const source=await fs.readFile(path.join(qa,`figure-${n}.mmd`),'utf8');
      const out=await page.evaluate(async({source,n})=>{
        await window.mermaid.parse(source);
        const {svg}=await window.mermaid.render(`fig${n}`,source);
        document.getElementById('diagram').innerHTML=svg;
        const el=document.querySelector('#diagram svg');
        const box=el.getBoundingClientRect();
        return {svg,width:box.width,height:box.height};
      },{source,n});
      await fs.writeFile(path.join(assets,`figure-${n}.svg`),out.svg);
      await page.locator('#diagram').screenshot({path:path.join(qa,`figure-${n}.png`)});
      results.push({figure:n,width:out.width,height:out.height,parsed:true,rendered:true});
    }
    await fs.writeFile(path.join(qa,'diagram-render-check.json'),JSON.stringify({renderer:'mermaid 11.4.1',results},null,2));
    console.log(JSON.stringify(results));
  } finally {
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
