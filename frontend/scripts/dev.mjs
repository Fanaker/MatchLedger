import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png'};
createServer(async (req,res)=>{
  try{
    let requested=decodeURIComponent((req.url||'/').split('?')[0]);
    if(requested==='/')requested='/index.html';
    const target=resolve(root,'.'+requested);
    if(target!==root && !target.startsWith(root+sep)){res.writeHead(403);res.end('Forbidden');return}
    const content=await readFile(target);
    res.writeHead(200,{'Content-Type':mime[extname(target)]||'application/octet-stream','Cache-Control':'no-store'});
    res.end(content);
  }catch{res.writeHead(404);res.end('Not found')}
}).listen(5173,'0.0.0.0',()=>console.log('MatchLedger frontend: http://localhost:5173'));
