// Tiny static server with HTTP Range support (needed for seeking in <video>).
const http = require('http'), fs = require('fs'), path = require('path');
const dir = __dirname;
module.exports = (port) => http.createServer((req, res) => {
  const host = (req.headers.host || '').split(':')[0];
  let p = req.url.split('?')[0];
  if (p === '/vod.webm' || p === '/chatsim.js') p = p.slice(1);
  else p = host.includes('kick') ? 'kick.html' : 'twitch.html';
  const f = path.join(dir, p);
  const type = p.endsWith('.webm') ? 'video/webm' : p.endsWith('.js') ? 'text/javascript' : 'text/html; charset=utf-8';
  const size = fs.statSync(f).size;
  const m = /bytes=(\d+)-(\d*)/.exec(req.headers.range || '');
  if (m) {
    const s = +m[1], e = m[2] ? +m[2] : size - 1;
    res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${s}-${e}/${size}`, 'Accept-Ranges': 'bytes', 'Content-Length': e - s + 1 });
    fs.createReadStream(f, { start: s, end: e }).pipe(res);
  } else {
    res.writeHead(200, { 'Content-Type': type, 'Content-Length': size, 'Accept-Ranges': 'bytes' });
    fs.createReadStream(f).pipe(res);
  }
}).listen(port);
