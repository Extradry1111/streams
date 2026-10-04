// Records docs/src/demo.html into a video, then make_gifs.sh turns it into docs/demo.gif.
const { chromium } = require(process.env.PW || 'playwright');
const path = require('path'), fs = require('fs');
(async () => {
  const out = path.join(__dirname, 'out'); fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch();
  const c = await b.newContext({ viewport: { width: 960, height: 540 }, recordVideo: { dir: out, size: { width: 960, height: 540 } } });
  const p = await c.newPage();
  await p.goto('file://' + path.join(__dirname, 'demo.html'));
  await p.waitForTimeout(13000);
  const v = await p.video().path(); await c.close(); await b.close();
  fs.renameSync(v, path.join(out, 'demo.webm'));
})();
