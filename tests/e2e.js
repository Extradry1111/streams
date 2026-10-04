// End-to-end test of clip_recorder.js in real Chromium against local mock VOD pages
// that imitate Twitch (known chat selector, speed reset, chat re-render, ad pause,
// page reload) and Kick (unknown chat markup -> auto-detect, distractor DOM updates).
//
//   node tests/e2e.js            # both
//   node tests/e2e.js twitch     # one
// Needs: playwright (Chromium) and ffmpeg (to build tests/mock/vod.webm once).
const { chromium } = require(process.env.PW || 'playwright');
const fs = require('fs'), path = require('path'), { execSync } = require('child_process');

const PORT = 8099, RATE = 8;
const ROOT = __dirname;
const SRC = fs.readFileSync(path.join(ROOT, '../stream-clipper/scripts/clip_recorder.js'), 'utf8');
const OUT = path.join(ROOT, 'out');
fs.mkdirSync(OUT, { recursive: true });
if (!fs.existsSync(path.join(ROOT, 'mock/vod.webm'))) {
  execSync(`ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=480x270:rate=4" -t 900 -vf "drawbox=x=0:y=0:w=iw:h=ih:color=0x18181b@0.55:t=fill,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='MOCK VOD  %{pts\\:hms}':fontcolor=white:fontsize=30:x=(w-tw)/2:y=(h-th)/2" -c:v libvpx -b:v 120k -deadline realtime -cpu-used 8 -an "${path.join(ROOT, 'mock/vod.webm')}"`);
}
const server = require('./mock/server')(PORT);

// Expected moments in the mock chat (see mock/chatsim.js)
const EXPECT = [
  { at: 200, kind: 'funny' }, { at: 470, kind: 'funny' },
  { at: 640, kind: 'hype' }, { at: 780, kind: 'clip-call' },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const check = (ok, msg) => { console.log((ok ? '  PASS ' : '  FAIL ') + msg); if (!ok) failed++; };

async function run(name, url, { reloadAt } = {}) {
  console.log(`\n== ${name}`);
  const browser = await chromium.launch({
    executablePath: process.env.CHROME || undefined,
    args: ['--host-resolver-rules=MAP www.twitch.tv 127.0.0.1, MAP kick.com 127.0.0.1', '--no-proxy-server',
      '--autoplay-policy=no-user-gesture-required'],
  });
  const ctx = await browser.newContext({ viewport: { width: 960, height: 540 }, recordVideo: { dir: OUT, size: { width: 960, height: 540 } } });
  const page = await ctx.newPage();
  await page.goto(url);
  await page.waitForFunction(() => document.querySelector('video') && document.querySelector('video').duration > 0);
  const inject = async () => page.evaluate(SRC);
  console.log('  ' + await inject());
  let st = await page.evaluate((r) => window.__clipRec.auto({ rate: r }), RATE);
  console.log('  auto ->', st.mode, st.chat || '', '|', st.next);
  let reloaded = false, sawDetect = st.mode === 'detecting', snapshots = 0;
  const t0 = Date.now();
  while (Date.now() - t0 < 6 * 60 * 1000) {
    await sleep(3000);
    st = await page.evaluate(() => window.__clipRec.status());
    if (snapshots++ % 5 === 0) console.log(`  t=${st.t}s cov=${st.coveragePct}% msgs=${st.messages} rate=${st.rate} mode=${st.mode} chat=${st.chat}`);
    if (st.mode === 'done') break;
    if (reloadAt && !reloaded && st.coveragePct > reloadAt) {
      reloaded = true;
      const before = st.messages;
      await page.reload();
      await page.waitForFunction(() => document.querySelector('video') && document.querySelector('video').duration > 0);
      console.log('  reloaded page; ' + await inject());
      st = await page.evaluate((r) => window.__clipRec.auto({ rate: r }), RATE);
      check(st.restoredFromReload >= before, `nothing lost on reload (${st.restoredFromReload} restored, ${before} before reload)`);
      check(st.t > 60, `resumed from first unwatched spot (t=${st.t}s), not from 0`);
    }
  }
  const shot = path.join(OUT, `${name}-done.png`);
  await page.screenshot({ path: shot });
  const res = await page.evaluate(() => window.__clipRec.analyze({ skipEdges: 60 }));
  const ctxt = await page.evaluate(() => window.__clipRec.context(195, 230, 8));
  fs.writeFileSync(path.join(OUT, `${name}-analyze.json`), JSON.stringify({ status: st, result: res }, null, 1));
  console.log('  candidates:');
  res.candidates.forEach((c) => console.log(`    ${c.startTc}-${c.endTc} (${c.len}s) score=${c.score} ${c.kind} laughs=${c.laughs} clip=${c.clipCalls} ${c.url}`));
  console.log('  context(195,230):\n    ' + ctxt.split('\n').join('\n    '));

  check(st.mode === 'done', 'finished on its own (mode=done)');
  check(st.coveragePct >= 95, `coverage ${st.coveragePct}% >= 95%`);
  if (name === 'kick') check(sawDetect && await page.evaluate((sel) => document.querySelector(sel) === document.querySelector('.q9z'), st.chat), `auto-detected unknown chat markup (${st.chat})`);
  for (const e of EXPECT) {
    const c = res.candidates.find((x) => x.start <= e.at + 5 && x.end >= e.at + 10);
    check(!!c && c.kind === e.kind, `moment @${e.at}s found as ${e.kind}` + (c ? ` (got ${c.kind} ${c.startTc}-${c.endTc})` : ' (missing)'));
    if (c) check(c.len >= 30 && c.len <= 120, `  length ${c.len}s within 30-120`);
  }
  const rank = (at) => res.candidates.findIndex((x) => x.start <= at + 5 && x.end >= at + 10);
  check(rank(200) < rank(640) && rank(470) < rank(640), 'funny moments ranked above the raid spam');
  check(/KEKW|OMEGALUL/.test(ctxt), 'context() includes emote names from <img alt>');
  check(res.candidates.every((c) => !(c.start < 60)), 'stream intro spam skipped');
  if (name === 'twitch') check((res.candidates[0].url || '').includes('?t=0h0') , `twitch share url uses ?t=XhYYmZZs (${res.candidates[0].url})`);

  const video = await page.video().path();
  await ctx.close(); await browser.close();
  fs.renameSync(video, path.join(OUT, `${name}.webm`));
}

(async () => {
  const which = process.argv[2];
  try {
    if (!which || which === 'twitch') await run('twitch', `http://www.twitch.tv:${PORT}/videos/123456789`, { reloadAt: 45 });
    if (!which || which === 'kick') await run('kick', `http://kick.com:${PORT}/mock_streamer/videos/0b9c-uuid`);
  } catch (e) { console.error(e); failed++; }
  server.close();
  console.log(failed ? `\n${failed} check(s) FAILED` : '\nALL CHECKS PASSED');
  process.exit(failed ? 1 : 0);
})();
