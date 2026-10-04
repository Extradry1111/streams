// clip_recorder.js — вставляется на страницу VOD (Twitch / Kick) через javascript_tool
// расширения Claude in Chrome. Пишет чат-реплей с привязкой к времени видео,
// считает, какая часть стрима реально просмотрена, и находит пики реакции чата.
//
// Использование (каждая строка — отдельный вызов javascript_tool):
//   <содержимое этого файла>                 -> устанавливает window.__clipRec
//   __clipRec.start({ rate: 4 })             -> muted, x4, начинает запись чата
//   __clipRec.status()                       -> позиция, покрытие, сколько сообщений
//   __clipRec.analyze({ top: 15 })           -> кандидаты в клипы 30-120 c
//   __clipRec.context(3720, 3810)            -> сообщения чата в окне (для оценки)
//   __clipRec.seek(3720)                     -> перемотка
//   __clipRec.uncovered()                    -> непросмотренные куски (для догонки)
//   __clipRec.stop()
//
// Повторная вставка файла безопасна: уже накопленные данные не теряются.
(() => {
  if (window.__clipRec) return 'already installed; ' + JSON.stringify(window.__clipRec.status());

  const BUCKET = 5; // секунд в одной ячейке гистограммы

  // Слова/эмоуты смеха. Эмоуты на Twitch/Kick — это <img>, поэтому текст берём
  // вместе с alt-атрибутами (см. msgText).
  const LAUGH = /(KEKW|OMEGALUL|LULW?|LMAO|LMFAO|ROFL|\bLOL\b|ICANT|\bxd+\b|pepeLaugh|KEKL|\b(?:ha){2,}|\b(?:ah){2,}|😂|🤣|💀)/i;
  // \b не работает с кириллицей, поэтому границы слова — через lookaround.
  const LAUGH_RU = /(?<![а-яё])(а?(?:ха){2,}х?|а?(?:хах)+|(?:ах){2,}а?|п+х+[ах]*|ору+|орнул\S*|ржу|ржака|угар|азаз\S*)(?![а-яё])/i;
  const CLIP = /(\bclip\b|clip it|клип|клипни|в клипы|момент)/i;
  const HYPE = /(\bW+\b|POGGERS|\bPog\b|PogChamp|monkaS|\bWTF\b|\bOMG\b|\?{3,}|!{3,})/;
  const HYPE_RU = /(?<![а-яё])(жесть|капец|нифига|ничего себе|ну всё|ахренеть|офигеть)(?![а-яё])/i;
  const isLaugh = (s) => LAUGH.test(s) || LAUGH_RU.test(s);
  const isHype = (s) => HYPE.test(s) || HYPE_RU.test(s);

  // Кандидаты контейнера сообщений. Если ни один не найден — передайте свой
  // селектор: __clipRec.start({ chatSelector: '...' }). Узнать его можно через
  // find / read_page («список сообщений чата под плеером/справа»).
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
      '[class*="chatroom"] [class*="messages"]',
    ],
  };

  const platform = location.hostname.includes('twitch') ? 'twitch'
    : location.hostname.includes('kick') ? 'kick' : 'other';

  const S = {
    msgs: [],          // {t, text}
    covered: new Set(), // индексы ячеек, которые реально проиграли
    observer: null,
    chatEl: null,
    timer: null,
    lastT: null,
  };

  const video = () => {
    const vs = [...document.querySelectorAll('video')];
    return vs.sort((a, b) => (b.duration || 0) - (a.duration || 0))[0] || null;
  };

  const msgText = (el) => {
    let s = (el.innerText || '').replace(/\s+/g, ' ').trim();
    const alts = [...el.querySelectorAll('img[alt]')].map((i) => i.alt).filter(Boolean);
    if (alts.length) s += ' ' + alts.join(' ');
    return s.slice(0, 300);
  };

  // В чат-реплее Twitch у сообщения обычно есть таймкод VOD (1:02:03 / 12:34).
  // Если он есть и правдоподобен — берём его, а не currentTime (точнее при x4).
  const parseStamp = (text, now) => {
    const m = text.match(/^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b/);
    if (!m) return null;
    const t = (+(m[1] || 0)) * 3600 + (+m[2]) * 60 + (+m[3]);
    return Math.abs(t - now) < 180 ? t : null;
  };

  const findChat = (sel) => {
    const list = sel ? [sel] : (CHAT_SELECTORS[platform] || []);
    for (const s of list) {
      const el = document.querySelector(s);
      if (el) return { el, sel: s };
    }
    return null;
  };

  const onAdded = (node) => {
    if (node.nodeType !== 1) return;
    const v = video();
    if (!v) return;
    const text = msgText(node);
    if (!text) return;
    const now = v.currentTime;
    S.msgs.push({ t: parseStamp(text, now) ?? now, text });
  };

  const tick = () => {
    const v = video();
    if (!v) return;
    const t = v.currentTime;
    // покрытие засчитываем только при реальном проигрывании без прыжков
    if (!v.paused && S.lastT !== null && t >= S.lastT && t - S.lastT < 30) {
      for (let x = Math.floor(S.lastT / BUCKET); x <= Math.floor(t / BUCKET); x++) S.covered.add(x);
    }
    S.lastT = t;
  };

  const api = {
    start(opts = {}) {
      const v = video();
      if (!v) return { ok: false, error: 'video element not found — плеер ещё не загрузился?' };
      const found = findChat(opts.chatSelector);
      if (!found) {
        return { ok: false, error: 'chat container not found', platform,
          hint: 'Откройте чат-реплей (он может быть свёрнут), найдите список сообщений через find/read_page и вызовите start({chatSelector}).' };
      }
      api.stop();
      S.chatEl = found.el;
      S.observer = new MutationObserver((muts) => {
        for (const m of muts) m.addedNodes.forEach(onAdded);
      });
      S.observer.observe(found.el, { childList: true });
      S.timer = setInterval(tick, 500);
      v.muted = true;
      if (opts.rate) v.playbackRate = opts.rate;
      if (typeof opts.from === 'number') v.currentTime = opts.from;
      S.lastT = v.currentTime;
      v.play().catch(() => {});
      return { ok: true, platform, chatSelector: found.sel, duration: Math.round(v.duration), rate: v.playbackRate };
    },

    stop() {
      if (S.observer) S.observer.disconnect();
      if (S.timer) clearInterval(S.timer);
      S.observer = null; S.timer = null;
      return 'stopped';
    },

    seek(t) {
      const v = video();
      if (!v) return 'no video';
      v.currentTime = t;
      S.lastT = t;
      return Math.round(v.currentTime);
    },

    setRate(r) { const v = video(); if (v) v.playbackRate = r; return v && v.playbackRate; },

    status() {
      const v = video();
      const dur = v ? v.duration : 0;
      const total = dur ? Math.ceil(dur / BUCKET) : 0;
      return {
        platform,
        recording: !!S.observer,
        t: v ? Math.round(v.currentTime) : null,
        duration: dur ? Math.round(dur) : null,
        paused: v ? v.paused : null,
        rate: v ? v.playbackRate : null,
        // если rate сам сбросился на 1 — плеер его перезаписал, поставьте снова
        messages: S.msgs.length,
        coveragePct: total ? Math.round((S.covered.size / total) * 1000) / 10 : 0,
        chatAttached: !!(S.chatEl && S.chatEl.isConnected),
      };
    },

    // Непросмотренные интервалы длиннее minGap секунд: их надо догнать.
    uncovered(minGap = 30) {
      const v = video();
      if (!v || !v.duration) return [];
      const total = Math.ceil(v.duration / BUCKET);
      const out = [];
      let s = null;
      for (let i = 0; i <= total; i++) {
        const miss = i < total && !S.covered.has(i);
        if (miss && s === null) s = i;
        if (!miss && s !== null) {
          if ((i - s) * BUCKET >= minGap) out.push([s * BUCKET, i * BUCKET]);
          s = null;
        }
      }
      return out;
    },

    analyze(opts = {}) {
      return analyzeMessages(S.msgs, opts);
    },

    // Сообщения в окне [t0, t1] — чтобы Claude прочитал, над чем смеются.
    context(t0, t1, limit = 120) {
      const inWin = S.msgs.filter((m) => m.t >= t0 && m.t <= t1);
      const step = Math.max(1, Math.ceil(inWin.length / limit));
      return inWin.filter((_, i) => i % step === 0)
        .map((m) => `${fmt(m.t)} ${m.text}`).join('\n');
    },

    // Сырые данные на случай, если нужно сохранить их вне страницы.
    dump(from = 0, n = 2000) { return S.msgs.slice(from, from + n); },

    // Восстановить ранее сохранённые сообщения (после перезагрузки страницы).
    load(msgs) { S.msgs.push(...msgs); return S.msgs.length; },
  };

  function fmt(t) {
    t = Math.max(0, Math.round(t));
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
  }

  // Поиск пиков. Чистая функция — её можно проверить отдельно от браузера.
  function analyzeMessages(msgs, opts = {}) {
    const top = opts.top ?? 15;
    const minLen = opts.minLen ?? 30;
    const maxLen = opts.maxLen ?? 120;
    const preRoll = opts.preRoll ?? 20; // завязка до реакции чата
    const postRoll = opts.postRoll ?? 6;
    if (!msgs.length) return { candidates: [], note: 'no messages recorded' };

    const n = Math.ceil((Math.max(...msgs.map((m) => m.t)) + 1) / BUCKET);
    const cnt = new Array(n).fill(0), laugh = new Array(n).fill(0), clip = new Array(n).fill(0), hype = new Array(n).fill(0);
    for (const m of msgs) {
      const b = Math.floor(m.t / BUCKET);
      cnt[b]++;
      if (isLaugh(m.text)) laugh[b]++;
      if (CLIP.test(m.text)) clip[b]++;
      if (isHype(m.text)) hype[b]++;
    }

    // Базовый уровень — средняя скорость чата в ±5 минут, без ±30 c вокруг точки,
    // чтобы сам всплеск не поднимал себе базу.
    const W = Math.round(300 / BUCKET), E = Math.round(30 / BUCKET);
    const pre = [0];
    for (let i = 0; i < n; i++) pre.push(pre[i] + cnt[i]);
    const sum = (a, b) => pre[Math.min(n, Math.max(0, b))] - pre[Math.min(n, Math.max(0, a))];
    const raw = new Array(n);
    for (let i = 0; i < n; i++) {
      const lo = Math.max(0, i - W), hi = Math.min(n, i + W + 1);
      const exLo = Math.max(lo, i - E), exHi = Math.min(hi, i + E + 1);
      const k = (hi - lo) - (exHi - exLo);
      const base = k > 0 ? (sum(lo, hi) - sum(exLo, exHi)) / k : cnt[i];
      raw[i] = (cnt[i] + 2 * laugh[i] + 3 * clip[i] + 0.5 * hype[i]) / (base + 1);
    }
    const sm = raw.map((_, i) => ((raw[i - 1] ?? raw[i]) + raw[i] + (raw[i + 1] ?? raw[i])) / 3);

    const used = new Array(n).fill(false);
    const order = sm.map((v, i) => i).sort((a, b) => sm[b] - sm[a]);
    const out = [];
    for (const p of order) {
      if (out.length >= top) break;
      if (used[p] || sm[p] < (opts.minScore ?? 1.5)) continue;
      let l = p, r = p;
      while (l > 0 && sm[l - 1] > sm[p] * 0.5 && !used[l - 1]) l--;
      while (r < n - 1 && sm[r + 1] > sm[p] * 0.4 && !used[r + 1]) r++;
      let start = l * BUCKET - preRoll;
      let end = (r + 1) * BUCKET + postRoll;
      if (end - start < minLen) { const pad = (minLen - (end - start)) / 2; start -= pad; end += pad; }
      if (end - start > maxLen) { const c = p * BUCKET; start = Math.max(start, c - maxLen * 0.6); end = start + maxLen; }
      start = Math.max(0, Math.round(start)); end = Math.round(end);
      const b0 = Math.floor(start / BUCKET), b1 = Math.min(n - 1, Math.floor(end / BUCKET));
      if (used.slice(b0, b1 + 1).some(Boolean)) continue;
      for (let i = b0; i <= b1; i++) used[i] = true;
      let L = 0, C = 0, M = 0;
      for (let i = b0; i <= b1; i++) { L += laugh[i]; C += clip[i]; M += cnt[i]; }
      out.push({
        start, end, len: end - start, startTc: fmt(start), endTc: fmt(end),
        peakTc: fmt(p * BUCKET), score: Math.round(sm[p] * 10) / 10,
        msgs: M, laughs: L, clipCalls: C,
        kind: L >= C && L * 3 >= M ? 'funny' : C > 0 ? 'clip-call' : 'hype',
      });
    }
    return { buckets: n, messages: msgs.length, candidates: out };
  }

  window.__clipRec = api;
  window.__clipAnalyze = analyzeMessages; // для тестов
  return 'installed on ' + platform + '; call __clipRec.start({rate: 4})';
})();
