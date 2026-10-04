// Mock chat replay: shows pre-generated messages in sync with the video, like a VOD
// chat replay does. Used only by the local tests; not part of the skill.
(function () {
  const cfg = window.MOCK;
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const pick = (a) => a[Math.floor(rnd() * a.length)];
  const nicks = ['vlad_tv', 'kotik228', 'xX_sniper_Xx', 'masha_ok', 'dimon', 'bigfan01', 'nightowl', 'pashok', 'ghost_rider', 'leha'];
  const filler = ['gg', 'what game is this?', 'hi chat', 'nice', 'go go go', 'привет', 'когда стрим завтра?', 'lol no', 'how now', 'кору горы', 'hm', 'W stream', 'бро что за музыка', 'ok'];
  const msgs = [];
  for (let t = 0; t < cfg.duration; t += 0.4 + rnd() * 0.8) msgs.push({ t, text: pick(filler) });
  const spike = (at, len, k, texts, emotes) => {
    for (let i = 0; i < k; i++) msgs.push({ t: at + rnd() * len, text: pick(texts), emote: emotes && rnd() < 0.6 ? pick(emotes) : null });
  };
  spike(5, 40, 60, ['hi', 'привет', 'HeyGuys'], null);                                      // intro noise
  spike(200, 20, 130, ['ахахахах', 'ору', 'LUL', 'he fell off the bridge', 'пхпхпх'], ['KEKW', 'OMEGALUL']); // funny A
  spike(470, 18, 90, ['OMEGALUL', 'clip it', 'хахаха', 'not the cat'], ['KEKW']);           // funny B
  spike(640, 20, 110, ['RAID HYPE ❤️', 'RAID HYPE', 'welcome raiders'], null);             // raid (not funny)
  spike(780, 15, 45, ['clip it', 'клипни', 'CLIP THAT'], null);                             // clip request
  msgs.sort((a, b) => a.t - b.t);

  const emoteSrc = (name) => 'data:image/svg+xml;utf8,' + encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"><rect rx="6" width="28" height="28" fill="#f5c542"/><text x="14" y="19" font-size="11" font-family="sans-serif" text-anchor="middle">${name.slice(0, 3)}</text></svg>`);
  const ts = (t) => { t = Math.floor(t); return `${Math.floor(t / 3600)}:${String(Math.floor(t % 3600 / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`; };

  const v = document.querySelector('video');
  let idx = 0, last = 0;
  setInterval(() => {
    const list = cfg.list();
    const t = v.currentTime;
    if (t < last - 1 || t > last + 20) { // seek: the replay reloads around the new time
      list.innerHTML = '';
      idx = msgs.findIndex((m) => m.t >= t - 5); if (idx < 0) idx = msgs.length;
    }
    last = t;
    while (idx < msgs.length && msgs[idx].t <= t) {
      const m = msgs[idx++];
      list.appendChild(cfg.render(m, pick(nicks), ts(m.t), m.emote ? emoteSrc(m.emote) : null));
      while (list.children.length > 120) list.firstElementChild.remove();
    }
    list.scrollTop = list.scrollHeight;
    if (cfg.chaos) cfg.chaos(v, t);
  }, 150);
})();
