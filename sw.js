const CACHE='meat-market-lubbock-v1-5';
const ASSETS=['./','./index.html','./manifest.webmanifest','./icon-192.png','./icon-512.png'];
self.addEventListener('install', event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate', event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('meat-market-lubbock-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch', event=>{
 const req=event.request, url=new URL(req.url);
 if(req.method!=='GET'||url.origin!==self.location.origin||url.pathname.endsWith('/feed.json'))return;
 event.respondWith(fetch(req).then(resp=>{
  if(resp.ok){const clone=resp.clone();caches.open(CACHE).then(c=>c.put(req,clone)).catch(()=>{});}
  return resp;
 }).catch(async()=>await caches.match(req)||Response.error()));
});
