#!/usr/bin/env python3
"""stream-clipper toolbox: VOD -> chat -> candidates -> 1080p clips -> subtitles -> shorts.

Needs Python 3.9+, curl and ffmpeg (with libass). Optional: yt-dlp (Twitch VODs),
faster-whisper (local transcription). Run any command with -h for options.

  info URL                         VOD facts -> vod.json (Kick native, Twitch via yt-dlp)
  chat vod.json                    full Kick chat replay -> chat.json
  score chat.json                  chat spikes -> candidates.json (same scoring as clip_recorder.js)
  context chat.json START END      chat lines in a window, to see what people laughed at
  sheet vod.json START END OUT.jpg 12 frames of a window on one image (visual check)
  cut vod.json START END OUT.mp4   clip at the best quality up to --height (default 1080)
  audio IN.mp4 OUT.m4a             audio only (small upload for transcription)
  words IN.srt OUT.json            SRT (e.g. from Descript) -> word timings
  transcribe IN.mp4 OUT.json       word timings with faster-whisper, if installed
  render IN.mp4 WORDS.json OUT.mp4 --format short|wide  burned-in TikTok-style captions

Times are VOD seconds or H:MM:SS.
"""
import argparse, json, math, os, re, ssl, subprocess, sys, tempfile, time, urllib.request
import concurrent.futures as cf
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, '..', 'assets', 'fonts')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'
BUCKET = 5


# ---------------------------------------------------------------- helpers
def secs(v):
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).split(':')]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def tc(t):
    t = int(round(t))
    return f'{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}'


def _ctx():
    ca = os.environ.get('SSL_CERT_FILE') or ('/root/.ccr/ca-bundle.crt' if os.path.exists('/root/.ccr/ca-bundle.crt') else None)
    return ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()


def http(url, as_json=False, tries=8):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json' if as_json else '*/*'})
            with urllib.request.urlopen(req, context=_ctx(), timeout=60) as r:
                data = r.read()
            return json.loads(data) if as_json else data
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) and i >= 2:
                raise
            time.sleep(min(30, 2 ** i) if e.code == 429 else 1 + i)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1 + i)


def ff(*args):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args], check=True)


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# ---------------------------------------------------------------- info
def cmd_info(a):
    url = a.url
    if 'kick.com' in url:
        html = http(url).decode('utf8', 'replace').replace('\\"', '"')
        uid = url.rstrip('/').split('/')[-1]
        i = html.find(f'"id":"{uid}"')
        blob = html[max(0, i - 3000): i + 3000] if i >= 0 else html
        g = lambda pat: (re.search(pat, blob) or re.search(pat, html))
        m3u8 = g(r'"recording_url":"([^"]+\.m3u8)"') or g(r'"source":"([^"]+\.m3u8)"')
        if not m3u8:
            sys.exit('Could not find the recording URL on the page (VOD private, deleted or layout changed).')
        vod = {
            'platform': 'kick', 'url': url, 'id': uid,
            'title': (g(r'"title":"([^"]*)"') or g(r'"session_title":"([^"]*)"')).group(1),
            'channel': url.split('kick.com/')[1].split('/')[0],
            'channel_id': int(g(r'"channel":\{"id":(\d+)').group(1)),
            'start_time': g(r'"start_time":"([^"]+)"').group(1),
            'duration': float(g(r'"duration":(\d+)').group(1)),
            'm3u8': m3u8.group(1).replace('\\/', '/'),
        }
        if vod['duration'] > 10 ** 6:  # older API reports milliseconds
            vod['duration'] /= 1000
    else:
        try:
            j = json.loads(subprocess.run(['yt-dlp', '-J', url], capture_output=True, text=True, check=True).stdout)
        except FileNotFoundError:
            sys.exit('Twitch VODs need yt-dlp: pip install yt-dlp')
        hls = [f for f in j['formats'] if f.get('protocol', '').startswith('m3u8') and f.get('height')]
        best = max(hls, key=lambda f: (f['height'], f.get('tbr') or 0))
        vod = {'platform': 'twitch', 'url': url, 'id': j['id'], 'title': j.get('title'), 'channel': j.get('uploader_id'),
               'start_time': datetime.fromtimestamp(j.get('timestamp', 0), timezone.utc).isoformat(),
               'duration': j.get('duration'), 'm3u8': best.get('manifest_url') or best['url']}
    json.dump(vod, open(a.out, 'w'), indent=1)
    print(json.dumps(vod, indent=1))


# ---------------------------------------------------------------- chat (Kick)
def _ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def cmd_chat(a):
    vod = json.load(open(a.vod))
    if vod['platform'] != 'kick':
        sys.exit('Offline chat download is Kick-only. For Twitch use clip_recorder.js in Chrome.')
    start, dur, ch = _ts(vod['start_time']), vod['duration'], vod['channel_id']

    def slice_(i):
        lo, hi = start + i * a.slice, min(start + dur, start + (i + 1) * a.slice)
        cur, out = int(hi * 1e6), {}
        while True:  # pages walk backwards in time from the cursor (unix microseconds)
            d = http(f'https://web.kick.com/api/v1/chat/{ch}/history?cursor={cur}', as_json=True)['data']
            ms = d.get('messages') or []
            for m in ms:
                t = _ts(m['created_at'])
                if lo <= t < hi:
                    out[m['id']] = (round(t - start, 1), m['sender']['username'], m['content'])
            oldest = min((_ts(m['created_at']) for m in ms), default=None)
            nxt = int(d['cursor']) if d.get('cursor') else None
            if not nxt or nxt >= cur or (oldest is not None and oldest < lo) or nxt / 1e6 < lo:
                break
            cur = nxt
        return i, list(out.values())

    n = math.ceil(dur / a.slice)
    msgs = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, ms in ex.map(slice_, range(n)):
            msgs += ms
            print(f'  {tc(i * a.slice)}  +{len(ms)} msgs', file=sys.stderr, flush=True)
    msgs.sort()
    json.dump(msgs, open(a.out, 'w'))
    print(f'{len(msgs)} messages -> {a.out}')


# ---------------------------------------------------------------- scoring (port of clip_recorder.js)
LAUGH = re.compile(r'(KEKW|OMEGALUL|LULW?|LMAO|LMFAO|ROFL|\bLOL\b|ICANT|\bxd+\b|pepeLaugh|KEKL|HaHaa|emojiDead|emojiLol|emojiRofl|\b(?:ha){2,}|\b(?:ah){2,}|😂|🤣|💀)', re.I)
LAUGH_RU = re.compile(r'(?<![а-яё])(а?(?:ха){2,}х?|а?(?:хах)+|(?:ах){2,}а?|п+х+[ах]*|ору+|орнул\S*|ржу|ржака|угар|азаз\S*)(?![а-яё])', re.I)
CLIP = re.compile(r'(\bclip\b|clip it|clipped|клип|клипни|в клипы|момент)', re.I)
HYPE = re.compile(r'(\bW+\b|POGGERS|\bPog\b|PogChamp|monkaS|\bWTF\b|\bOMG\b|\?{3,}|!{3,})')
HYPE_RU = re.compile(r'(?<![а-яё])(жесть|капец|нифига|ничего себе|ну всё|ахренеть|офигеть)(?![а-яё])', re.I)


def score_buckets(cnt, laugh, clip, hype):
    n = len(cnt)
    W, E = 300 // BUCKET, 30 // BUCKET
    pre = [0]
    for c in cnt:
        pre.append(pre[-1] + c)
    s = lambda a_, b_: pre[min(n, max(0, b_))] - pre[min(n, max(0, a_))]
    raw = []
    for i in range(n):
        lo, hi = max(0, i - W), min(n, i + W + 1)
        exlo, exhi = max(lo, i - E), min(hi, i + E + 1)
        k = (hi - lo) - (exhi - exlo)
        base = (s(lo, hi) - s(exlo, exhi)) / k if k > 0 else cnt[i]
        raw.append((cnt[i] + 2 * laugh[i] + 3 * clip[i] + 0.5 * hype[i]) / (base + 1))
    return [(raw[max(0, i - 1)] + raw[i] + raw[min(n - 1, i + 1)]) / 3 for i in range(n)]


def analyze(cnt, laugh, clip, hype, top=15, min_len=30, max_len=120, pre_roll=20, post_roll=6, skip_edges=300, min_score=1.5):
    n = len(cnt)
    sm = score_buckets(cnt, laugh, clip, hype)
    used = [False] * n
    out = []
    for p in sorted(range(n), key=lambda i: -sm[i]):
        if len(out) >= top:
            break
        if used[p] or sm[p] < min_score or p * BUCKET < skip_edges or (n - 1 - p) * BUCKET < skip_edges:
            continue
        l = r = p
        while l > 0 and sm[l - 1] > sm[p] * 0.5 and not used[l - 1]:
            l -= 1
        while r < n - 1 and sm[r + 1] > sm[p] * 0.4 and not used[r + 1]:
            r += 1
        start, end = l * BUCKET - pre_roll, (r + 1) * BUCKET + post_roll
        if end - start < min_len:
            pad = (min_len - (end - start)) / 2; start -= pad; end += pad
        if end - start > max_len:
            start = max(start, p * BUCKET - max_len * 0.6); end = start + max_len
        start, end = max(0, round(start)), round(end)
        b0, b1 = start // BUCKET, min(n - 1, end // BUCKET)
        if any(used[b0:b1 + 1]):
            continue
        for i in range(b0, b1 + 1):
            used[i] = True
        L, C, M = sum(laugh[b0:b1 + 1]), sum(clip[b0:b1 + 1]), sum(cnt[b0:b1 + 1])
        out.append({'start': start, 'end': end, 'len': end - start, 'startTc': tc(start), 'endTc': tc(end),
                    'peakTc': tc(p * BUCKET), 'score': round(sm[p], 1), 'msgs': M, 'laughs': L, 'clipCalls': C,
                    'kind': 'funny' if L * 3 >= M and L >= C else 'clip-call' if C > 0 else 'hype'})
    return out


def cmd_score(a):
    msgs = json.load(open(a.chat))
    n = int(max(m[0] for m in msgs) // BUCKET) + 1
    cnt, laugh, clip, hype = ([0] * n for _ in range(4))
    seen = set()
    for t, user, text in msgs:
        b = int(t // BUCKET)
        if (b, user) in seen:  # one vote per chatter per bucket: spammers can't fake a spike
            continue
        seen.add((b, user))
        cnt[b] += 1
        laugh[b] += bool(LAUGH.search(text) or LAUGH_RU.search(text))
        clip[b] += bool(CLIP.search(text))
        hype[b] += bool(HYPE.search(text) or HYPE_RU.search(text))
    c = analyze(cnt, laugh, clip, hype, top=a.top, min_len=a.min_len, max_len=a.max_len, skip_edges=a.skip_edges)
    json.dump({'messages': len(msgs), 'candidates': c}, open(a.out, 'w'), indent=1)
    for i, x in enumerate(c, 1):
        print(f"{i:2d} {x['startTc']:>8}-{x['endTc']:<8} {x['len']:3d}s score={x['score']:<5} {x['kind']:<9} laughs={x['laughs']} clip={x['clipCalls']}")


def cmd_context(a):
    t0, t1 = secs(a.start), secs(a.end)
    clean = lambda s: re.sub(r'\[emote:\d+:([^\]]+)\]', r':\1:', s)
    w = [m for m in json.load(open(a.chat)) if t0 <= m[0] <= t1 and not re.fullmatch(r'(\s*\[emote:[^\]]+\]\s*)+', m[2])]
    for m in w[::max(1, len(w) // a.lines)]:
        print(tc(m[0]), clean(m[2])[:120])


# ---------------------------------------------------------------- video
def _variant(master_url, height):
    base = master_url.rsplit('/', 1)[0] + '/'
    txt = http(master_url).decode()
    vs = []
    for m in re.finditer(r'#EXT-X-STREAM-INF:([^\n]*)\n(\S+)', txt):
        h = re.search(r'RESOLUTION=\d+x(\d+)', m.group(1))
        fr = re.search(r'FRAME-RATE=([\d.]+)', m.group(1))
        vs.append((int(h.group(1)) if h else 0, float(fr.group(1)) if fr else 30, m.group(2)))
    if not vs:  # already a media playlist
        return master_url, base
    ok = [v for v in vs if v[0] <= height] or vs
    h, fr, uri = max(ok, key=lambda v: (v[0], v[1]))
    url = uri if uri.startswith('http') else base + uri
    return url, url.rsplit('/', 1)[0] + '/'


def _segments(vod, height):
    url, base = _variant(vod['m3u8'], height)
    segs, t = [], 0.0
    for d, name in re.findall(r'#EXTINF:([\d.]+),[^\n]*\n(?:#[^\n]*\n)*(\S+)', http(url).decode()):
        segs.append((t, float(d), name if name.startswith('http') else base + name)); t += float(d)
    return segs


def _fetch_window(vod, t0, t1, height, tmp):
    segs = [s for s in _segments(vod, height) if s[0] + s[1] > t0 and s[0] < t1]
    files = []
    with cf.ThreadPoolExecutor(6) as ex:
        for i, data in enumerate(ex.map(lambda s: http(s[2]), segs)):
            f = os.path.join(tmp, f'{i:05d}.ts'); open(f, 'wb').write(data); files.append(f)
    lst = os.path.join(tmp, 'list.txt')
    open(lst, 'w').writelines(f"file '{f}'\n" for f in files)
    return lst, segs[0][0]


def cmd_cut(a):
    vod = json.load(open(a.vod))
    t0, t1 = secs(a.start), secs(a.end)
    with tempfile.TemporaryDirectory() as tmp:
        lst, first = _fetch_window(vod, t0, t1, a.height, tmp)
        ff('-f', 'concat', '-safe', '0', '-i', lst, '-ss', f'{t0 - first:.3f}', '-t', f'{t1 - t0:.3f}',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', str(a.crf), '-c:a', 'aac', '-b:a', '192k',
           '-movflags', '+faststart', a.out)
    print(a.out, f'{os.path.getsize(a.out) / 1e6:.1f} MB')


def cmd_sheet(a):
    vod = json.load(open(a.vod))
    t0, t1 = secs(a.start), secs(a.end)
    step = a.step or max(1.0, (t1 - t0) / 12)
    with tempfile.TemporaryDirectory() as tmp:
        lst, first = _fetch_window(vod, t0, t1, 360, tmp)
        frames, t = [], t0
        while t <= t1 and len(frames) < 12:
            f = os.path.join(tmp, f'f{len(frames):02d}.jpg')
            label = tc(t).replace(':', r'\:')
            ff('-ss', f'{t - first:.2f}', '-f', 'concat', '-safe', '0', '-i', lst, '-frames:v', '1', '-vf',
               f"scale=320:-1,drawtext=fontfile={FONTS}/Montserrat-Black.ttf:text='{label}':x=6:y=6:fontsize=16:fontcolor=yellow:box=1:boxcolor=black@0.6", f)
            frames.append(f); t += step
        ins = sum((['-i', f] for f in frames), [])
        lay = '|'.join(f"{'+'.join(['w0'] * (i % 4)) or '0'}_{'+'.join(['h0'] * (i // 4)) or '0'}" for i in range(len(frames)))
        ff(*ins, '-filter_complex', ''.join(f'[{i}:v]' for i in range(len(frames))) + f'xstack=inputs={len(frames)}:layout={lay}:fill=black', a.out)
    print(a.out)


def cmd_audio(a):
    ff('-i', a.inp, '-vn', '-ac', '1', '-c:a', 'aac', '-b:a', '96k', a.out)
    print(a.out, os.path.getsize(a.out))


# ---------------------------------------------------------------- words
def cmd_words(a):
    txt = open(a.srt, encoding='utf8').read().replace('\r', '')
    words = []
    for blk in re.split(r'\n\s*\n', txt.strip()):
        m = re.search(r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.*)', blk, re.S)
        if not m:
            continue
        g = [int(x) for x in m.groups()[:8]]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = re.sub(r'^\s*\[?[A-Za-z0-9 _.-]{1,30}\]?:\s+', '', m.group(9).replace('\n', ' '))  # drop speaker labels
        ws = text.split()
        if not ws:
            continue
        # SRT has no word timing: spread the cue over its words by length
        weights = [len(w) + 2 for w in ws]
        tot, t = sum(weights), s
        for w, k in zip(ws, weights):
            d = (e - s) * k / tot
            words.append({'w': w, 's': round(t, 3), 'e': round(t + d, 3)}); t += d
    json.dump(words, open(a.out, 'w'), ensure_ascii=False, indent=0)
    print(f'{len(words)} words -> {a.out}')


def cmd_transcribe(a):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit('faster-whisper is not installed (pip install faster-whisper). Or transcribe with Descript, '
                 'export SRT and run: clipper.py words clip.srt clip.words.json')
    model = WhisperModel(a.model, compute_type='int8')
    segs, _ = model.transcribe(a.inp, word_timestamps=True, language=a.lang)
    words = [{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3)} for s in segs for w in s.words]
    json.dump(words, open(a.out, 'w'), ensure_ascii=False, indent=0)
    print(f'{len(words)} words -> {a.out}')


# ---------------------------------------------------------------- render
def _chunks(words, max_words, max_chars):
    out, cur = [], []
    for w in words:
        gap = cur and w['s'] - cur[-1]['e'] > 0.45
        long_ = cur and (len(cur) >= max_words or len(' '.join(x['w'] for x in cur + [w])) > max_chars)
        if cur and (gap or long_ or re.search(r'[.!?]$', cur[-1]['w'])):
            out.append(cur); cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def _ass_time(t):
    t = max(0, t)
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def _esc(s):
    return s.replace('\\', '').replace('{', '(').replace('}', ')')


SWEARS = re.compile(r'(fuck|shit|bitch|pussy|cunt|dick|nigg\w*|fag\w*)', re.I)


def censor(word):
    # keep first letter of the swear, star the first vowel: F*CK, MOTHERF*CKER, SH*T
    return SWEARS.sub(lambda m: m.group(0)[0] + re.sub(r'[aeiouy]', '*', m.group(0)[1:], count=1, flags=re.I), word)


def build_ass(words, W, H, fmt, title=None, highlight='&H004DE1FF&', upper=True, clean=True):
    short = fmt == 'short'
    size = round(W * (0.085 if short else 0.042))
    y = round(H * (0.745 if short else 0.86))
    lines = [
        '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {W}', f'PlayResY: {H}', 'WrapStyle: 0', 'ScaledBorderAndShadow: yes', '',
        '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, '
        'ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        f'Style: Cap,Montserrat Black,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,{max(4, size // 11)},{max(2, size // 22)},5,60,60,0,1',
        f'Style: Title,Montserrat Black,{round(W * 0.062)},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,{round(W * 0.018)},0,8,70,70,{round(H * 0.085)},1',
        '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ]
    if title and short:
        lines.append(f'Dialogue: 2,{_ass_time(0)},{_ass_time(10 ** 5)},Title,,0,0,0,,{_esc(title.upper())}')
    for ch in _chunks(words, 3 if short else 6, 16 if short else 40):
        for i, w in enumerate(ch):
            s = w['s']
            e = ch[i + 1]['s'] if i + 1 < len(ch) else max(w['e'], s + 0.25)
            parts = []
            for j, x in enumerate(ch):
                t = _esc(x['w'].upper() if upper else x['w'])
                t = censor(t) if clean else t
                parts.append(f'{{\\c{highlight}\\fscx112\\fscy112}}{t}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}' if j == i else t)
            pop = '\\t(0,80,\\fscx105\\fscy105)' if i == 0 else ''
            lines.append(f'Dialogue: 1,{_ass_time(s)},{_ass_time(e)},Cap,,0,0,0,,{{\\pos({W // 2},{y}){pop}}}' + ' '.join(parts))
    return '\n'.join(lines) + '\n'


def cmd_render(a):
    words = json.load(open(a.words)) if a.words and os.path.exists(a.words) else []
    dur = duration(a.inp)
    t0 = secs(a.trim[0]) if a.trim else 0.0
    t1 = min(dur, secs(a.trim[1])) if a.trim else dur
    words = [dict(w, s=w['s'] - t0, e=min(w['e'], t1) - t0) for w in words if w['s'] >= t0 and w['s'] < t1]
    dur = t1 - t0
    short = a.format == 'short'
    W, H = (1080, 1920) if short else (1920, 1080)
    with tempfile.TemporaryDirectory() as tmp:
        ass = os.path.join(tmp, 'subs.ass')
        open(ass, 'w', encoding='utf8').write(build_ass(words, W, H, a.format, a.title, clean=not a.no_censor))
        subs = f"subtitles={ass}:fontsdir={os.path.abspath(FONTS)}"
        if short:
            # blurred full-bleed background + the action in the middle, cropped to 4:3 so it stays big
            fg_h = round(W * 3 / 4)
            vf = (f"[0:v]split[a][b];[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},gblur=sigma=10,eq=brightness=-0.12,scale={W}:{H}[bg];"
                  f"[b]crop=ih*4/3:ih,scale={W}:{fg_h}[fg];[bg][fg]overlay=0:(H-h)/2-{round(H * 0.04)},{subs},fps={a.fps},format=yuv420p[v]")
        else:
            vf = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,{subs},fps={a.fps},format=yuv420p[v]"
        enc = ['-c:v', 'libx264', '-preset', a.preset, '-profile:v', 'high']
        if a.max_mb:
            kbps = max(800, int((a.max_mb * 8 * 1000 / dur - 128) * 0.95))
            enc += ['-b:v', f'{kbps}k', '-maxrate', f'{int(kbps * 1.4)}k', '-bufsize', f'{kbps * 2}k']
        else:
            enc += ['-crf', str(a.crf)]
        ff('-ss', f'{t0:.3f}', '-t', f'{dur:.3f}', '-i', a.inp, '-filter_complex', vf, '-map', '[v]', '-map', '0:a?', *enc, '-c:a', 'aac', '-b:a', '128k',
           '-movflags', '+faststart', a.out)
    print(a.out, f'{os.path.getsize(a.out) / 1e6:.1f} MB')


# ---------------------------------------------------------------- cli
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('info'); s.add_argument('url'); s.add_argument('-o', '--out', default='vod.json'); s.set_defaults(f=cmd_info)
    s = sp.add_parser('chat'); s.add_argument('vod'); s.add_argument('-o', '--out', default='chat.json')
    s.add_argument('--workers', type=int, default=8); s.add_argument('--slice', type=int, default=1800); s.set_defaults(f=cmd_chat)
    s = sp.add_parser('score'); s.add_argument('chat'); s.add_argument('-o', '--out', default='candidates.json')
    s.add_argument('--top', type=int, default=30); s.add_argument('--min-len', type=int, default=30); s.add_argument('--max-len', type=int, default=120)
    s.add_argument('--skip-edges', type=int, default=300, help='ignore the first/last N seconds (hello/bye spam)'); s.set_defaults(f=cmd_score)
    s = sp.add_parser('context'); s.add_argument('chat'); s.add_argument('start'); s.add_argument('end'); s.add_argument('--lines', type=int, default=40); s.set_defaults(f=cmd_context)
    s = sp.add_parser('sheet'); s.add_argument('vod'); s.add_argument('start'); s.add_argument('end'); s.add_argument('out')
    s.add_argument('--step', type=float); s.set_defaults(f=cmd_sheet)
    s = sp.add_parser('cut'); s.add_argument('vod'); s.add_argument('start'); s.add_argument('end'); s.add_argument('out')
    s.add_argument('--height', type=int, default=1080); s.add_argument('--crf', type=int, default=18); s.set_defaults(f=cmd_cut)
    s = sp.add_parser('audio'); s.add_argument('inp'); s.add_argument('out'); s.set_defaults(f=cmd_audio)
    s = sp.add_parser('words'); s.add_argument('srt'); s.add_argument('out'); s.set_defaults(f=cmd_words)
    s = sp.add_parser('transcribe'); s.add_argument('inp'); s.add_argument('out'); s.add_argument('--model', default='small')
    s.add_argument('--lang'); s.set_defaults(f=cmd_transcribe)
    s = sp.add_parser('render'); s.add_argument('inp'); s.add_argument('words'); s.add_argument('out')
    s.add_argument('--format', choices=['short', 'wide'], default='short'); s.add_argument('--title', help='hook text on top of a short')
    s.add_argument('--no-censor', action='store_true', help='show swear words uncensored in captions')
    s.add_argument('--trim', nargs=2, metavar=('START', 'END'), help='use only this part of the clip (clip-relative times)')
    s.add_argument('--preset', default='medium')
    s.add_argument('--fps', type=int, default=30); s.add_argument('--crf', type=int, default=19)
    s.add_argument('--max-mb', type=float, help='target file size, e.g. 29 to fit a 30 MB upload limit'); s.set_defaults(f=cmd_render)
    a = p.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
