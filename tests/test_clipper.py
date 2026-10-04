# Unit tests for scripts/clipper.py (no network). Run: python3 tests/test_clipper.py
import json, os, random, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'stream-clipper', 'scripts'))
import clipper

fails = 0
def check(ok, msg):
    global fails
    print(('  PASS ' if ok else '  FAIL ') + msg); fails += (not ok)

# scoring: same planted moments as the browser e2e test
random.seed(7)
msgs, t = [], 0.0
while t < 900:
    msgs.append([t, f'u{random.randint(0, 300)}', random.choice(['gg', 'hi chat', 'lol no', 'how now', 'кору горы', 'ok'])]); t += 0.4 + random.random() * 0.8
def spike(at, n, texts):
    for i in range(n): msgs.append([at + random.random() * 20, f's{i}', random.choice(texts)])
spike(200, 130, ['KEKW', 'ахахах', 'ору', '[emote:1:emojiDead]', 'LMAO'])
spike(470, 90, ['OMEGALUL', 'clip it', 'хахаха'])
spike(640, 110, ['RAID HYPE', 'welcome raiders'])
spike(780, 45, ['clip it', 'клипни'])
for i in range(60): msgs.append([700 + random.random() * 20, 'spammer', 'KEKW KEKW'])  # one user, many lines
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, 'chat.json'); json.dump(sorted(msgs), open(p, 'w'))
    out = os.path.join(d, 'c.json')
    subprocess.run([sys.executable, clipper.__file__, 'score', p, '-o', out, '--top', '10', '--skip-edges', '60'], check=True, capture_output=True)
    c = json.load(open(out))['candidates']
find = lambda at: next((x for x in c if x['start'] <= at + 5 and x['end'] >= at + 10), None)
for at, kind in [(200, 'funny'), (470, 'funny'), (640, 'hype'), (780, 'clip-call')]:
    x = find(at); check(bool(x) and x['kind'] == kind and 30 <= x['len'] <= 120, f'moment @{at}s -> {kind}' + (f" (got {x['kind']}, {x['len']}s)" if x else ' (missing)'))
check(find(700) is None or find(700)['score'] < 2, 'a single spammer does not create a spike')
check(c.index(find(200)) < c.index(find(640)), 'funny ranked above raid')

# SRT -> words
srt = "1\n00:00:01,000 --> 00:00:02,000\nWhat the fuck was that?\n\n2\n00:00:03,500 --> 00:00:04,000\nBro.\n"
with tempfile.TemporaryDirectory() as d:
    open(os.path.join(d, 'a.srt'), 'w').write(srt)
    subprocess.run([sys.executable, clipper.__file__, 'words', os.path.join(d, 'a.srt'), os.path.join(d, 'w.json')], check=True, capture_output=True)
    w = json.load(open(os.path.join(d, 'w.json')))
check([x['w'] for x in w] == ['What', 'the', 'fuck', 'was', 'that?', 'Bro.'], 'srt split into words')
check(abs(w[0]['s'] - 1.0) < 1e-6 and abs(w[4]['e'] - 2.0) < 0.01 and all(a['e'] <= b['s'] + 1e-6 for a, b in zip(w, w[1:])), 'word times stay inside the cue, in order')

# captions
check([clipper.censor(x) for x in ['FUCK', 'MOTHERFUCKER', 'SHIT,', 'hello']] == ['F*CK', 'MOTHERF*CKER', 'SH*T,', 'hello'], 'censoring')
ch = clipper._chunks(w, 3, 16)
check(all(len(x) <= 3 for x in ch) and [y['w'] for y in ch[-1]] == ['Bro.'], 'chunks: max 3 words, split on pauses')
ass = clipper.build_ass(w, 1080, 1920, 'short', title='Test title')
check('Montserrat Black' in ass and 'F*CK' in ass and 'TEST TITLE' in ass and ass.count('Dialogue: 1') == len(w), 'ASS: font, censor, title, one event per word')

print('ALL PASSED' if not fails else f'{fails} FAILED'); sys.exit(1 if fails else 0)
