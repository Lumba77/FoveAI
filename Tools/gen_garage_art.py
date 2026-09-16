#!/usr/bin/env python3
"""Generate FoveAI garage artwork → Frontend/multigate/public/garage/.

Backends, tried in order:
  1. Gemini image model  (GEMINI_API_KEY from env — never printed)
  2. Pollinations Flux   (free, no key; browser UA required)

Usage:
  set -a; source /home/lumba/FoveAI/.env; set +a
  .venv/bin/python Tools/gen_garage_art.py [asset ...]      # default: all
  .venv/bin/python Tools/gen_garage_art.py --backend pollinations emblem
"""
import base64, json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'Frontend', 'multigate', 'public', 'garage')
GEMINI_MODEL = 'gemini-2.5-flash-image'

ASSETS = {
    'backdrop': (
        "wide cinematic interior of an inventor's magical garage workshop at night, "
        "very dark cosy, warm yellow orange painted metal walls dimly lit, old "
        "toolboards shelves jars instruments, faint green LED guide lights along "
        "the floor, three ceiling work lamp diodes casting soft cones of warm light "
        "downward, dust motes in light beams, deep shadows, moody sci-fi workshop, "
        "painterly high detail, no text no people no logos", 1536, 640),
    'plate': (
        "flat top-down orthographic macro texture of dark brushed gunmetal steel "
        "plate surface, fine horizontal brushed metal grain filling entire frame, "
        "subtle yellow paint overspray haze near center, four hex socket screws "
        "near corners, photorealistic industrial texture, edge-to-edge surface, "
        "no perspective, no text", 1024, 384),
    'emblem': (
        "circular heavy metal emblem badge like a vintage car emblem, dark gunmetal "
        "ring with hex bolts around the rim, glowing amber red thorium reactor core "
        "symbol in the center radiating warm light, faint green glow in etched "
        "circuit grooves, dramatic lighting, photorealistic, pure black background, "
        "centered, no text", 768, 768),
}

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36',
      'Referer': 'https://pollinations.ai/'}


def strip_watermark(path: str, px: int = 46) -> None:
    try:
        from PIL import Image
        im = Image.open(path)
        im.crop((0, 0, im.width, im.height - px)).save(path)
    except ImportError:
        pass  # pillow optional — watermark strip stays if absent


def gen_gemini(name, prompt, w, h, key):
    url = (f'https://generativelanguage.googleapis.com/v1beta/models/'
           f'{GEMINI_MODEL}:generateContent?key={key}')
    body = json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                       'generationConfig': {'responseModalities': ['IMAGE']}}).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.load(r)
    for cand in resp.get('candidates', []):
        for part in cand.get('content', {}).get('parts', []):
            d = part.get('inlineData') or part.get('inline_data')
            if d and d.get('data'):
                return base64.b64decode(d['data'])
    raise RuntimeError('no image in response')


def gen_pollinations(name, prompt, w, h):
    url = (f'https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}'
           f'?width={w}&height={h}&nologo=true&model=flux&seed={42 + len(name)}')
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if len(data) < 5000:
        raise RuntimeError(f'suspiciously small response ({len(data)}B)')
    return data


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    backend = 'auto'
    if '--backend' in sys.argv:
        backend = sys.argv[sys.argv.index('--backend') + 1]
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('FOVEAI_REPERTOIRE_GEMINI_API_KEY')
    os.makedirs(OUT, exist_ok=True)

    for name in (args or list(ASSETS)):
        if name not in ASSETS:
            print(f'skip {name}'); continue
        prompt, w, h = ASSETS[name]
        path = os.path.join(OUT, f'{name}.png')
        print(f'{name}…', end=' ', flush=True)

        ok = False
        if backend in ('auto', 'gemini') and key:
            try:
                data = gen_gemini(name, prompt, w, h, key)
                ok = True; print('gemini', end=' ')
            except Exception as e:
                print(f'(gemini: {str(e)[:60]})', end=' ')
        if not ok and backend in ('auto', 'pollinations'):
            for attempt in range(3):
                try:
                    data = gen_pollinations(name, prompt, w, h)
                    ok = True; print('pollinations', end=' ')
                    break
                except Exception as e:
                    print(f'(p{attempt+1}: {str(e)[:50]})', end=' '); time.sleep(5)
        if ok:
            open(path, 'wb').write(data)
            strip_watermark(path)
            print(f'→ {path} ({len(data)//1024} KiB)')
        else:
            print('FAILED')


if __name__ == '__main__':
    main()
