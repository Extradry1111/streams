// clip_recorder.js — injected into a Twitch / Kick VOD page through the Claude in Chrome
// javascript tool. It plays the whole VOD muted at high speed, records the chat replay
// against video time, tracks how much of the VOD was actually played, heals itself
// (player speed resets, paused video, re-rendered chat, page reloads), and finds the
// spikes of laughter in chat.
//
// The whole loop is:
//   <paste this file>                -> installs window.__clipRec (safe to paste again)
//   __clipRec.auto()                 -> start (or resume) watching
//   __clipRec.status()               -> progress; `status().next` says what to do now
//   __clipRec.analyze()              -> clip candidates, 30-120 s each
//   __clipRec.context(t0, t1)        -> chat lines in a window, to see what was funny
//   __clipRec.seek(t) / setRate(r) / pause() / reset()
//
// Every call returns immediately (nothing is async), so it is safe with any tool timeout.
(() => {
  const VERSION = 2;
  if (window.__clipRec && window.__clipRec.version === VERSION) {
    return 'already installed; ' + JSON.stringify(window.__clipRec.status());
  }
  if (window.__clipRec && window.__clipRec.stop) window.__clipRec.stop();

  const BUCKET = 5;          // seconds per histogram cell
  const SAVE_EVERY = 10000;  // ms between localStorage saves
  const MAX_SAVED_MSGS = 25000;

  // Laugh tokens. Emotes are <img>, so message text includes their alt (see msgText).
  const LAUGH = /(KEKW|OMEGALUL|LULW?|LMAO|LMFAO|ROFL|\bLOL\b|ICANT|\bxd+\b|pepeLaugh|KEKL|HaHaa|emojiDead|emojiLol|emojiRofl|\b(?:ha){2,}|\b(?:ah){2,}|😂|🤣|💀)/i;
  // \b does not work with Cyrillic, so word edges use lookarounds.
  const LAUGH_RU = /(?<![а-яё])(а?(?:ха){2,}х?|а?(?:хах)+|(?:ах){2,}а?|п+х+[ах]*|ору+|орнул\S*|ржу|ржака|угар|азаз\S*)(?![а-яё])/i;
  const CLIP = /(\bclip\b|clip it|clipped|клип|клипни|в клипы|момент)/i;
  const HYPE = /(\bW+\b|POGGERS|\bPog\b|PogChamp|monkaS|\bWTF\b|\bOMG\b|\?{3,}|!{3,})/;
  const HYPE_RU = /(?<![а-яё])(жесть|капец|нифига|ничего себе|ну всё|ахренеть|офигеть)(?![а-яё])/i;
  const isLaugh = (s) => LAUGH.test(s) || LAUGH_RU.test(s);
  const isHype = (s) => HYPE.test(s) || HYPE_RU.test(s);

  // Known chat containers. If none matches, the container is auto-detected as
  // "the element that keeps getting new children while the video plays".
  const CHAT_SELECTORS = {
    twitch: [
      '[data-test-selector="video-chat-message-list-wrapper"] ul',
      '.video-chat__message-list-wrapper ul',
      '.video-chat__message-list-wrapper',
    ],
    kick: [
      '#chatroom-messages',
      '#chatroom-replay',
      '[data-testid="chat-messages"]',
    ],
  };

  const platform = /twitch/.test(location.hostname) ? 'twitch'
    : /kick/.test(location.hostname) ? 'kick' : 'other';
  const storeKey = 'clipRec:' + location.hostname + location.pathname;

  const S = {
    mode: 'idle',       // idle | detecting | watching | done
    rate: 4,
    cnt: [], laugh: [], clip: [], hype: [], covered: [],
    msgs: [],           // [t, text]
    seen: new Set(),
    chatSel: null, chatEl: null, observer: null, detector: null,
    timer: null, lastT: null, lastSave: 0,
    pausedSince: null, silentSince: null, lastMsgCount: 0,
    detectStarted: 0, warnings: [], restored: 0, gapTries: {},
  };

  // ---------- helpers ----------
  const video = () => {
    const vs = [...document.querySelectorAll('video')].filter((v) => isFinite(v.duration) && v.duration > 0);
    return vs.sort((a, b) => b.duration - a.duration)[0] || document.querySelector('video');
  };
  const fmt = (t) => {
    t = Math.max(0, Math.round(t));
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
  };
  const twitchT = (t) => {
    t = Math.round(t);
    return `${Math.floor(t / 3600)}h${String(Math.floor((t % 3600) / 60)).padStart(2, '0')}m${String(t % 60).padStart(2, '0')}s`;
  };
  const shareUrl = (t) => {
    const u = new URL(location.href);
    u.search = '';
    u.searchParams.set('t', platform === 'twitch' ? twitchT(t) : String(Math.round(t)));
    return u.toString();
  };
  const msgText = (el) => {
    let s = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    const alts = [...el.querySelectorAll('img[alt]')].map((i) => i.alt).filter(Boolean);
    if (alts.length) s += ' ' + alts.join(' ');
    return s.slice(0, 200);
  };
  // Twitch chat replay prefixes messages with the VOD time (1:02:03). When present and
  // plausible it is more accurate than currentTime at 4x.
  const parseStamp = (text, now) => {
    const m = text.match(/^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?!\d)/);
    if (!m) return null;
    const t = (+(m[1] || 0)) * 3600 + (+m[2]) * 60 + (+m[3]);
    return Math.abs(t - now) < 180 ? t : null;
  };
  const inc = (arr, i) => { while (arr.length <= i) arr.push(0); arr[i]++; };
  const coveredCount = () => S.covered.reduce((a, x) => a + (x ? 1 : 0), 0);
  const totalBuckets = () => { const v = video(); return v && v.duration ? Math.ceil(v.duration / BUCKET) : 0; };
  const coveragePct = () => { const n = totalBuckets(); return n ? Math.min(100, Math.round((coveredCount() / n) * 1000) / 10) : 0; };

  // ---------- persistence (survives reloads of the same VOD page) ----------
  const save = (force) => {
    const now = Date.now();
    if (!force && now - S.lastSave < SAVE_EVERY) return;
    S.lastSave = now;
    const base = { v: VERSION, rate: S.rate, cnt: S.cnt, laugh: S.laugh, clip: S.clip, hype: S.hype,
      covered: S.covered.map((x) => (x ? 1 : 0)).join('') };
    try {
      localStorage.setItem(storeKey, JSON.stringify({ ...base, msgs: S.msgs.slice(-MAX_SAVED_MSGS) }));
    } catch (e) {
      try { localStorage.setItem(storeKey, JSON.stringify({ ...base, msgs: S.msgs.slice(-3000) })); } catch (e2) {}
    }
  };
  const restore = () => {
    try {
      const d = JSON.parse(localStorage.getItem(storeKey) || 'null');
      if (!d || d.v !== VERSION) return;
      S.rate = d.rate || S.rate;
      S.cnt = d.cnt; S.laugh = d.laugh; S.clip = d.clip; S.hype = d.hype;
      S.covered = d.covered.split('').map((c) => c === '1');
      S.msgs = d.msgs || [];
      S.msgs.forEach(([t, text]) => S.seen.add(Math.round(t) + '|' + text));
      S.restored = S.cnt.reduce((a, b) => a + b, 0);
    } catch (e) {}
  };

  // ---------- chat capture ----------
  const record = (node) => {
    if (!node || node.nodeType !== 1) return;
    const v = video();
    if (!v) return;
    const text = msgText(node);
    if (!text) return;
    const now = v.currentTime;
    const t = parseStamp(text, now) ?? now;
    const key = Math.round(t) + '|' + text;   // chat re-renders after seeks: count once
    if (S.seen.has(key)) return;
    S.seen.add(key);
    S.msgs.push([Math.round(t * 10) / 10, text]);
    const b = Math.floor(t / BUCKET);
    inc(S.cnt, b);
    while (S.laugh.length < S.cnt.length) S.laugh.push(0);
    while (S.clip.length < S.cnt.length) S.clip.push(0);
    while (S.hype.length < S.cnt.length) S.hype.push(0);
    if (isLaugh(text)) S.laugh[b]++;
    if (CLIP.test(text)) S.clip[b]++;
    if (isHype(text)) S.hype[b]++;
  };

  const attach = (el, sel) => {
    if (S.observer) S.observer.disconnect();
    S.chatEl = el; S.chatSel = sel;
    S.observer = new MutationObserver((muts) => { for (const m of muts) m.addedNodes.forEach(record); });
    S.observer.observe(el, { childList: true });
    // Lines already on screen came in at unknown times: keep them only when they carry
    // their own VOD timestamp, otherwise they would pile up as a fake spike right here.
    const v = video();
    [...el.children].forEach((n) => { if (v && parseStamp(msgText(n), v.currentTime) !== null) record(n); });
  };

  const cssPath = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 6 && el !== document.body) {
      let p = el.tagName.toLowerCase();
      const tid = el.getAttribute('data-test-selector') || el.getAttribute('data-testid');
      if (tid) { parts.unshift(`${p}[${el.hasAttribute('data-testid') ? 'data-testid' : 'data-test-selector'}="${tid}"]`); break; }
      if (el.parentElement) {
        const same = [...el.parentElement.children].filter((c) => c.tagName === el.tagName);
        if (same.length > 1) p += `:nth-of-type(${same.indexOf(el) + 1})`;
      }
      parts.unshift(p);
      el = el.parentElement;
    }
    return parts.join(' > ');
  };

  const findKnownChat = (sel) => {
    for (const s of (sel ? [sel] : (CHAT_SELECTORS[platform] || []))) {
      const el = document.querySelector(s);
      if (el) return { el, sel: s };
    }
    return null;
  };

  // Watch the whole page while the video plays; the chat list is the parent that keeps
  // receiving new text-bearing children. Player internals are ignored.
  const startDetect = () => {
    const v = video();
    const player = v && (v.closest('[class*="player" i]') || v.parentElement);
    const counts = new Map();
    S.detectStarted = Date.now();
    S.mode = 'detecting';
    if (S.detector) S.detector.disconnect();
    S.detector = new MutationObserver((muts) => {
      for (const m of muts) {
        const p = m.target;
        if (!(p instanceof Element) || (player && player.contains(p)) || p.closest('#clip-rec-hud')) continue;
        for (const n of m.addedNodes) {
          if (n.nodeType === 1 && (n.textContent || '').trim().length > 0) counts.set(p, (counts.get(p) || 0) + 1);
        }
      }
    });
    S.detector.observe(document.body, { childList: true, subtree: true });
    S.detectCounts = counts;
  };
  const finishDetect = () => {
    const best = [...S.detectCounts.entries()].filter(([el]) => el.isConnected).sort((a, b) => b[1] - a[1])[0];
    if (best && best[1] >= 3) {
      S.detector.disconnect(); S.detector = null;
      attach(best[0], cssPath(best[0]));
      S.mode = 'watching';
      return true;
    }
    return false;
  };

  // ---------- main loop ----------
  const tick = () => {
    const v = video();
    if (!v) return;
    const t = v.currentTime;

    if (S.mode === 'detecting') {
      if (Date.now() - S.detectStarted > 6000 && !finishDetect() && Date.now() - S.detectStarted > 30000) {
        S.detector.disconnect(); S.detector = null; S.mode = 'idle'; v.pause();
        S.warnings.push('chat-not-found');
      }
    }
    if (S.mode !== 'watching' && S.mode !== 'detecting') { S.lastT = t; return; }

    // player resets speed -> put it back; muted always
    if (Math.abs(v.playbackRate - S.rate) > 0.01) v.playbackRate = S.rate;
    if (!v.muted) v.muted = true;

    // paused (ad, buffering, overlay) -> try to resume, then ask for help
    if (v.paused && !v.ended) {
      S.pausedSince = S.pausedSince || Date.now();
      v.play().catch(() => {});
    } else S.pausedSince = null;

    // chat element replaced by a re-render -> reattach
    if (S.mode === 'watching' && (!S.chatEl || !S.chatEl.isConnected)) {
      const k = findKnownChat(S.chatSel);
      if (k) attach(k.el, k.sel); else startDetect();
    }

    // coverage: only real forward playback counts
    if (!v.paused && S.lastT !== null && t >= S.lastT && t - S.lastT < 10 * Math.max(1, S.rate)) {
      for (let x = Math.floor(S.lastT / BUCKET); x <= Math.floor(t / BUCKET); x++) S.covered[x] = true;
    }
    S.lastT = t;

    // chat silent at high speed -> slow down (replay may not keep up)
    if (S.mode === 'watching' && !v.paused) {
      if (S.msgs.length !== S.lastMsgCount) { S.lastMsgCount = S.msgs.length; S.silentSince = null; }
      else {
        S.silentSince = S.silentSince || Date.now();
        if (Date.now() - S.silentSince > 60000 / Math.max(1, S.rate) * 2 && S.rate > 2) {
          S.rate = 2; S.silentSince = null; S.warnings.push('slowed-to-2x');
        }
      }
    }

    // reached the end (or close) -> jump to the first gap, else finish
    if (v.ended || (v.duration && t >= v.duration - 1.5)) {
      const gap = api.uncovered(15).find((g) => (S.gapTries[g[0]] || 0) < 3);
      if (gap) {
        S.gapTries[gap[0]] = (S.gapTries[gap[0]] || 0) + 1;
        v.currentTime = gap[0]; S.lastT = gap[0]; v.play().catch(() => {});
      }
      else { S.mode = 'done'; v.pause(); save(true); }
    }
    save(false);
    drawHud();
  };

  // ---------- on-page progress panel ----------
  let hudOn = true;
  const drawHud = () => {
    let el = document.getElementById('clip-rec-hud');
    if (!hudOn) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.id = 'clip-rec-hud';
      el.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:2147483647;pointer-events:none;' +
        'background:rgba(14,14,18,.88);color:#fff;font:12px/1.4 system-ui,sans-serif;padding:8px 10px;' +
        'border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.4);width:340px';
      el.innerHTML = '<div id="clip-rec-hud-t"></div><canvas width="320" height="34" style="display:block;margin-top:6px"></canvas>';
      document.body.appendChild(el);
    }
    const st = api.status();
    const dot = st.mode === 'watching' ? '#ff4d4d' : st.mode === 'done' ? '#3ddc84' : '#f5c542';
    el.querySelector('#clip-rec-hud-t').innerHTML =
      `<b style="color:${dot}">●</b> <b>stream-clipper</b> · ${st.mode}${st.mode === 'watching' ? ' ' + st.rate + 'x' : ''}` +
      `<br>watched ${st.coveragePct}% · ${st.messages.toLocaleString()} chat msgs · at ${fmt(st.t || 0)} / ${fmt(st.duration || 0)}`;
    const c = el.querySelector('canvas'), g = c.getContext('2d');
    const n = totalBuckets() || 1, W = c.width, H = c.height;
    g.clearRect(0, 0, W, H);
    g.fillStyle = 'rgba(255,255,255,.08)'; g.fillRect(0, H - 4, W, 4);
    g.fillStyle = '#9147ff';
    for (let i = 0; i < n; i++) if (S.covered[i]) g.fillRect((i / n) * W, H - 4, Math.max(1, W / n), 4);
    const sc = scores();
    const mx = Math.max(1, ...sc);
    g.fillStyle = '#ffd166';
    for (let i = 0; i < sc.length; i++) {
      const h = (sc[i] / mx) * (H - 6);
      if (h > 0.5) g.fillRect((i / n) * W, H - 5 - h, Math.max(1, W / n), h);
    }
  };

  // ---------- analysis ----------
  // Per-bucket "how unusual is chat here": activity vs the surrounding ±5 min, with
  // bonuses for laughter, clip requests and hype. Pure function of the counters.
  function scoreBuckets(cnt, laugh, clip, hype) {
    const n = cnt.length;
    const W = Math.round(300 / BUCKET), E = Math.round(30 / BUCKET);
    const pre = [0];
    for (let i = 0; i < n; i++) pre.push(pre[i] + (cnt[i] || 0));
    const sum = (a, b) => pre[Math.min(n, Math.max(0, b))] - pre[Math.min(n, Math.max(0, a))];
    const raw = new Array(n);
    for (let i = 0; i < n; i++) {
      const lo = Math.max(0, i - W), hi = Math.min(n, i + W + 1);
      const exLo = Math.max(lo, i - E), exHi = Math.min(hi, i + E + 1);
      const k = (hi - lo) - (exHi - exLo);
      const base = k > 0 ? (sum(lo, hi) - sum(exLo, exHi)) / k : (cnt[i] || 0);
      raw[i] = ((cnt[i] || 0) + 2 * (laugh[i] || 0) + 3 * (clip[i] || 0) + 0.5 * (hype[i] || 0)) / (base + 1);
    }
    return raw.map((_, i) => ((raw[i - 1] ?? raw[i]) + raw[i] + (raw[i + 1] ?? raw[i])) / 3);
  }
  function scores() { return scoreBuckets(S.cnt, S.laugh, S.clip, S.hype); }

  function analyzeBuckets(cnt, laugh, clip, hype, opts = {}) {
    const top = opts.top ?? 15;
    const minLen = opts.minLen ?? 30, maxLen = opts.maxLen ?? 120;
    const preRoll = opts.preRoll ?? 20, postRoll = opts.postRoll ?? 6;
    const skipEdges = opts.skipEdges ?? 300; // stream intro/outro chat is noise
    const n = cnt.length;
    const total = cnt.reduce((a, b) => a + (b || 0), 0);
    if (!total) return { messages: 0, candidates: [], note: 'no chat recorded yet' };
    const sm = scoreBuckets(cnt, laugh, clip, hype);
    const lastB = n - 1;
    const used = new Array(n).fill(false);
    const order = sm.map((_, i) => i).sort((a, b) => sm[b] - sm[a]);
    const out = [];
    for (const p of order) {
      if (out.length >= top) break;
      if (used[p] || sm[p] < (opts.minScore ?? 1.5)) continue;
      if (p * BUCKET < skipEdges || (lastB - p) * BUCKET < skipEdges) continue;
      let l = p, r = p;
      while (l > 0 && sm[l - 1] > sm[p] * 0.5 && !used[l - 1]) l--;
      while (r < n - 1 && sm[r + 1] > sm[p] * 0.4 && !used[r + 1]) r++;
      let start = l * BUCKET - preRoll, end = (r + 1) * BUCKET + postRoll;
      if (end - start < minLen) { const pad = (minLen - (end - start)) / 2; start -= pad; end += pad; }
      if (end - start > maxLen) { start = Math.max(start, p * BUCKET - maxLen * 0.6); end = start + maxLen; }
      start = Math.max(0, Math.round(start)); end = Math.round(end);
      const b0 = Math.floor(start / BUCKET), b1 = Math.min(n - 1, Math.floor(end / BUCKET));
      if (used.slice(b0, b1 + 1).some(Boolean)) continue;
      for (let i = b0; i <= b1; i++) used[i] = true;
      let L = 0, C = 0, M = 0;
      for (let i = b0; i <= b1; i++) { L += laugh[i] || 0; C += clip[i] || 0; M += cnt[i] || 0; }
      out.push({
        start, end, len: end - start, startTc: fmt(start), endTc: fmt(end), peakTc: fmt(p * BUCKET),
        score: Math.round(sm[p] * 10) / 10, msgs: M, laughs: L, clipCalls: C,
        kind: L * 3 >= M && L >= C ? 'funny' : C > 0 ? 'clip-call' : 'hype',
      });
    }
    return { messages: total, candidates: out };
  }

  // ---------- public API ----------
  const api = {
    version: VERSION,

    // Start or resume. Options: rate (default 4), chatSelector, from (seconds), hud.
    auto(opts = {}) {
      const v = video();
      if (!v) return { ok: false, next: 'No video on this page yet. Wait for the player to load (or click the play button), then call __clipRec.auto() again.' };
      if (opts.rate) S.rate = opts.rate;
      if (opts.hud === false) hudOn = false;
      v.muted = true;
      v.playbackRate = S.rate;
      if (typeof opts.from === 'number') v.currentTime = opts.from;
      else if (coveredCount() > 0) { const gap = api.uncovered(15)[0]; if (gap) v.currentTime = gap[0]; }
      S.lastT = v.currentTime;
      S.warnings = S.warnings.filter((w) => w !== 'chat-not-found');
      const k = findKnownChat(opts.chatSelector);
      if (k) { attach(k.el, k.sel); S.mode = 'watching'; } else startDetect();
      if (!S.timer) S.timer = setInterval(tick, 1000);
      v.play().catch(() => {});
      return api.status();
    },

    status() {
      const v = video();
      const st = {
        mode: S.mode, platform,
        t: v ? Math.round(v.currentTime) : null,
        duration: v && isFinite(v.duration) ? Math.round(v.duration) : null,
        rate: S.rate, paused: v ? v.paused : null,
        coveragePct: coveragePct(),
        messages: S.cnt.reduce((a, b) => a + (b || 0), 0),
        restoredFromReload: S.restored,
        chat: S.chatSel, warnings: [...new Set(S.warnings)],
      };
      if (st.duration && st.rate) st.etaMin = Math.max(0, Math.round(((st.duration * (1 - st.coveragePct / 100)) / st.rate) / 60));
      st.next =
        S.mode === 'done' ? 'Finished. Call __clipRec.analyze().' :
        S.warnings.includes('chat-not-found') && S.mode === 'idle' ? 'Chat replay not found. Make sure the chat panel is open and visible (expand it), then call __clipRec.auto() again. If it still fails, find the chat message list with find/read_page and call __clipRec.auto({chatSelector: "<css>"}). If this VOD has no chat replay, use the no-chat fallback.' :
        S.mode === 'idle' ? 'Not started. Call __clipRec.auto().' :
        S.mode === 'detecting' ? 'Looking for the chat (up to 30 s). Check status again in ~15 s.' :
        S.pausedSince && Date.now() - S.pausedSince > 20000 ? 'Video has been paused for over 20 s — probably an ad, an age gate, a "continue watching?" prompt or buffering. Take a screenshot and deal with it (wait out ads, never click them), then check status again.' :
        `Watching. ~${st.etaMin ?? '?'} min left. Do not touch the tab; check status again in 2-3 min.`;
      return st;
    },

    analyze(opts = {}) {
      const r = analyzeBuckets(S.cnt, S.laugh, S.clip, S.hype, opts);
      r.coveragePct = coveragePct();
      r.candidates.forEach((c) => { c.url = shareUrl(c.start); });
      return r;
    },

    context(t0, t1, limit = 120) {
      const inWin = S.msgs.filter(([t]) => t >= t0 && t <= t1);
      if (!inWin.length) return '(no saved chat lines in this window — seek there and read the chat panel)';
      const step = Math.max(1, Math.ceil(inWin.length / limit));
      return inWin.filter((_, i) => i % step === 0).map(([t, s]) => `${fmt(t)} ${s}`).join('\n');
    },

    uncovered(minGap = 30) {
      const n = totalBuckets();
      const out = [];
      let s = null;
      for (let i = 0; i <= n; i++) {
        const miss = i < n && !S.covered[i];
        if (miss && s === null) s = i;
        if (!miss && s !== null) { if ((i - s) * BUCKET >= minGap) out.push([s * BUCKET, i * BUCKET]); s = null; }
      }
      return out;
    },

    seek(t) { const v = video(); if (!v) return null; v.currentTime = t; S.lastT = t; return Math.round(v.currentTime); },
    setRate(r) { S.rate = r; const v = video(); if (v) v.playbackRate = r; return r; },
    // Stop watching (e.g. to review clips at 1x). auto() resumes where coverage is missing.
    pause() { if (S.mode === 'watching' || S.mode === 'detecting') S.mode = 'idle'; const v = video(); if (v) v.pause(); save(true); return api.status(); },
    stop() { api.pause(); if (S.observer) S.observer.disconnect(); if (S.detector) S.detector.disconnect(); clearInterval(S.timer); S.timer = null; return 'stopped'; },
    reset() { api.stop(); try { localStorage.removeItem(storeKey); } catch (e) {} Object.assign(S, { cnt: [], laugh: [], clip: [], hype: [], covered: [], msgs: [], seen: new Set(), warnings: [], restored: 0, mode: 'idle' }); return 'reset'; },
    hud(on = true) { hudOn = on; drawHud(); return on; },
  };

  restore();
  // save on reload/close/tab switch so nothing since the last periodic save is lost
  addEventListener('pagehide', () => save(true));
  document.addEventListener('visibilitychange', () => save(true));
  window.__clipRec = api;
  window.__clipAnalyze = analyzeBuckets; // for tests
  window.__clipRecBucket = BUCKET;
  window.__clipRecTest = { isLaugh, isHype, CLIP }; // for tests and offline runs
  return `installed on ${platform}` + (S.restored ? ` (restored ${S.restored} chat msgs from before reload)` : '') + '; call __clipRec.auto()';
})();
