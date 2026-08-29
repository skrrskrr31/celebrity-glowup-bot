"""
CELEB NEWS BOT  (purdyblog pipeline -> English celebrity news)
Kaynak: pagesix.com/celebrity-news  -> Groq ozet/baslik/hook -> PIL kart -> Ken Burns video -> YouTube Short
"""

import os, sys, random, json
import io as _io
from PIL import Image, ImageDraw, ImageFont
from groq import Groq
from moviepy.editor import ImageClip, AudioFileClip

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
SECRET_PATH = os.path.join(script_dir, "secret.json")
TOKEN_PATH  = os.path.join(script_dir, "token.json")

def _write_env_json(env_name, path):
    """Secret duz JSON de olabilir base64 de -> ikisini de destekle."""
    import base64
    v = os.environ.get(env_name, "")
    if not v or os.path.exists(path):
        return
    v = v.strip()
    if not v.startswith("{"):
        try:
            v = base64.b64decode(v).decode("utf-8").strip()
        except Exception:
            pass
    open(path, "w", encoding="utf-8").write(v)

_write_env_json("SECRET_JSON", SECRET_PATH)
_write_env_json("TOKEN_JSON", TOKEN_PATH)

OUTPUT_VIDEO = os.path.join(script_dir, "celeb_news_shorts.mp4")

W, H = 1080, 1920
PAD  = 44
CHANNEL_NAME   = "Celeb Buzz"       # <-- YouTube kanal adinla ayni yap
CHANNEL_HANDLE = "@celebbuzz"       # <-- kanal handle'inla ayni yap
GROQ_MODEL     = "openai/gpt-oss-120b"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"}

USED_PATH = os.path.join(script_dir, "kullanilan_haberler.json")


# ─────────────────────────────────────────────────────────────
def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import urllib.request, urllib.parse
    try:
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=data), timeout=10)
    except Exception as e:
        print(f"[Telegram] {e}")


# ─────────────────────────────────────────────────────────────
# YARDIMCILAR
# ─────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
    ]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


def draw_verified(draw, x, y, size=30):
    draw.ellipse([x, y, x + size, y + size], fill=(29, 155, 240))
    p1 = (x + size * 0.22, y + size * 0.52)
    p2 = (x + size * 0.44, y + size * 0.72)
    p3 = (x + size * 0.78, y + size * 0.28)
    draw.line([p1, p2], fill="white", width=max(2, int(size * 0.13)))
    draw.line([p2, p3], fill="white", width=max(2, int(size * 0.13)))


def draw_button(draw, x, y, w, h, text, bg, fg, font, radius=14):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=bg)
    b = draw.textbbox((0, 0), text, font=font)
    draw.text((x + (w - (b[2] - b[0])) // 2, y + (h - (b[3] - b[1])) // 2 - b[1]), text, font=font, fill=fg)


def draw_like_button(img, draw, x, y, w, h, color=(48, 48, 48), radius=23):
    from PIL import Image as _Image
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=color)
    icon_path = os.path.join(script_dir, "like_icon.png")
    try:
        s = int(h * 0.68)
        icon = _Image.open(icon_path).convert("RGBA").resize((s, s), _Image.Resampling.LANCZOS)
        img.paste(icon, (x + (w - s) // 2, y + (h - s) // 2), icon)
    except Exception:
        pass


def paste_circular_logo(img, logo_path, x, y, size):
    try:
        logo = Image.open(logo_path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        logo.putalpha(mask)
        img.paste(logo, (x, y), logo)
    except Exception:
        ImageDraw.Draw(img).ellipse([x, y, x + size, y + size], fill=(60, 60, 60))
        ImageDraw.Draw(img).text((x + size // 4, y + size // 8), CHANNEL_NAME[:1].upper(),
                                 font=load_font(size // 2, bold=True), fill="white")


def norm_txt(s):
    """Kart fontunun (DejaVu) desteklemedigi ozel karakterleri sadelestir."""
    if not s:
        return s
    repl = {
        "‑": "-", "‐": "-", "–": "-", "‒": "-",
        "—": " - ", "‘": "'", "’": "'", "‚": "'",
        "“": '"', "”": '"', "„": '"', "…": "...",
        " ": " ", "​": "", " ": " ", " ": " ",
        "﻿": "", "•": "-", "­": "",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s


def wrap_text(draw, text, font, max_width):
    lines = []
    for para in text.split('\n'):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for word in para.split():
            test = (cur + " " + word).strip()
            if draw.textbbox((0, 0), test, font=font)[2] > max_width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)
    return lines


def extract_person(headline):
    """Basliktan kisi adi: ardisik buyuk harfle baslayan 2+ kelime."""
    import re
    names, cur = [], []
    for word in headline.split():
        clean = re.sub(r'[^\w]', '', word)
        if clean and clean[0].isupper() and not word.startswith('#'):
            cur.append(clean)
        else:
            if len(cur) >= 2 and any(len(w) > 2 for w in cur):
                names.append(' '.join(cur))
            cur = []
    if len(cur) >= 2 and any(len(w) > 2 for w in cur):
        names.append(' '.join(cur))
    return names[0] if names else ""


# ─────────────────────────────────────────────────────────────
# KART GORSELI
# ─────────────────────────────────────────────────────────────
def create_card(body_text, foto_paths, hook_text="", cta_text=""):
    body_text = norm_txt(body_text)
    hook_text = norm_txt(hook_text)
    cta_text = norm_txt(cta_text)
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    f_name = load_font(46, bold=True)
    f_handle = load_font(34)
    f_text = load_font(43)
    f_btn = load_font(30, bold=True)

    logo_size, line_h = 88, 62
    text_maxw = W - PAD * 2
    photo_h = 520
    gap2 = 14
    hook_h = 78 if hook_text else 0
    cta_h = 72 if cta_text else 0
    header_h = logo_size + 28

    lines = wrap_text(draw, body_text, f_text, text_maxw)
    text_h = sum(line_h // 2 if ln == "" else line_h for ln in lines) + 20
    foto_h_actual = photo_h if foto_paths else 0

    total_h = header_h + hook_h + text_h + foto_h_actual + cta_h
    start_y = max(PAD, (H - total_h) // 2)

    # header
    lx, ly = PAD, start_y
    paste_circular_logo(img, os.path.join(script_dir, "logo.jpg"), lx, ly, logo_size)
    tx = lx + logo_size + 20
    ty_name = ly + 10
    draw.text((tx, ty_name), CHANNEL_NAME, font=f_name, fill="white")
    nw = draw.textbbox((0, 0), CHANNEL_NAME, font=f_name)[2]
    draw_verified(draw, tx + nw + 10, ty_name + 6, size=32)
    ty_handle = ty_name + draw.textbbox((0, 0), CHANNEL_NAME, font=f_name)[3] + 6
    draw.text((tx, ty_handle), CHANNEL_HANDLE, font=f_handle, fill=(140, 140, 140))

    tick_end_x = tx + nw + 10 + 32
    btn_h = 46
    btn_sub_w, btn_lik_w, btn_gap = 205, 62, 12
    btn_x_sub = tick_end_x + 16
    btn_x_lik = btn_x_sub + btn_sub_w + btn_gap
    btn_y = ty_name + 4
    draw_button(draw, btn_x_sub, btn_y, btn_sub_w, btn_h, "SUBSCRIBE", (255, 0, 0), "white", f_btn, radius=23)
    draw_like_button(img, draw, btn_x_lik, btn_y, btn_lik_w, btn_h, color=(48, 48, 48), radius=23)

    # hook banner
    hook_y = start_y + header_h
    if hook_text:
        draw.rectangle([0, hook_y, W, hook_y + hook_h], fill=(200, 0, 0))
        f_hook = load_font(52, bold=True)
        hb = draw.textbbox((0, 0), hook_text, font=f_hook)
        draw.text(((W - (hb[2] - hb[0])) // 2, hook_y + (hook_h - (hb[3] - hb[1])) // 2 - hb[1]),
                  hook_text, font=f_hook, fill=(255, 215, 0))

    # body text
    text_y = hook_y + hook_h + (14 if hook_text else 0)
    for ln in lines:
        if ln == "":
            text_y += line_h // 2
            continue
        draw.text((PAD, text_y), ln, font=f_text, fill="white")
        text_y += line_h

    # photo(s)
    photos_top = text_y + 20
    if len(foto_paths) == 1:
        try:
            foto = Image.open(foto_paths[0]).convert("RGB")
            fw, fh = foto.size
            tw, th = W - PAD * 2, photo_h
            r = min(tw / fw, th / fh)
            nw2, nh2 = int(fw * r), int(fh * r)
            foto = foto.resize((nw2, nh2), Image.Resampling.LANCZOS)
            img.paste(foto, (PAD + (tw - nw2) // 2, photos_top + (th - nh2) // 2))
        except Exception as e:
            print(f"[WARN] foto: {e}")
    elif len(foto_paths) >= 2:
        each_w = (W - PAD * 2 - gap2) // 2
        for idx in range(2):
            try:
                foto = Image.open(foto_paths[idx]).convert("RGB")
                fw, fh = foto.size
                r = min(each_w / fw, photo_h / fh)
                nw2, nh2 = int(fw * r), int(fh * r)
                slot = Image.new("RGB", (each_w, photo_h), (0, 0, 0))
                slot.paste(foto.resize((nw2, nh2), Image.Resampling.LANCZOS),
                           ((each_w - nw2) // 2, (photo_h - nh2) // 2))
                img.paste(slot, (PAD + idx * (each_w + gap2), photos_top))
            except Exception as e:
                print(f"[WARN] foto{idx+1}: {e}")

    # CTA bubble
    if cta_text:
        cta_y = photos_top + foto_h_actual + 18
        rgba = img.convert("RGBA")
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rounded_rectangle([PAD, cta_y, W - PAD, cta_y + cta_h], radius=20, fill=(20, 20, 20, 210))
        img = Image.alpha_composite(rgba, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        f_cta = load_font(38, bold=True)
        cb = draw.textbbox((0, 0), cta_text, font=f_cta)
        draw.text(((W - (cb[2] - cb[0])) // 2, cta_y + (cta_h - (cb[3] - cb[1])) // 2 - cb[1]),
                  cta_text, font=f_cta, fill=(255, 215, 0))

    return img


# ─────────────────────────────────────────────────────────────
# HABER CEKICI  (Page Six)
# ─────────────────────────────────────────────────────────────
def fetch_news():
    import re, requests

    LIST_URLS = [
        "https://pagesix.com/celebrity-news/",
        "https://pagesix.com/entertainment/",
    ]
    ART_RE = re.compile(r"https://pagesix\.com/\d{4}/\d{2}/\d{2}/(?:celebrity-news|entertainment|hollywood|tv|movies|music)/[a-z0-9\-]+/?")

    links = []
    seen = set()
    for lu in LIST_URLS:
        try:
            html = requests.get(lu, headers=HEADERS, timeout=15).text
        except Exception as e:
            print(f"[WARN] liste {lu}: {e}")
            continue
        for m in ART_RE.findall(html):
            u = m.rstrip("/") + "/"
            if u not in seen:
                seen.add(u)
                links.append(u)

    if not links:
        print("[ERROR] Page Six'ten link cekilemedi.")
        return None, None, None

    # gecmis
    hist = []
    if os.path.exists(USED_PATH):
        try:
            hist = json.load(open(USED_PATH, encoding="utf-8"))
        except Exception:
            hist = []
    hist_urls = {h.get("url", "") for h in hist if isinstance(h, dict)}
    hist_people = {h.get("person", "").lower() for h in hist if isinstance(h, dict) and h.get("person")}
    hist_titles = [h.get("title", "").lower() for h in hist if isinstance(h, dict)]

    def slug_title(u):
        return u.rstrip("/").split("/")[-1].replace("-", " ")

    def title_overlap(a, b, thr=0.4):
        ka = {w for w in a.lower().split() if len(w) > 3}
        kb = {w for w in b.lower().split() if len(w) > 3}
        if not ka or not kb:
            return False
        return len(ka & kb) / min(len(ka), len(kb)) >= thr

    fresh = []
    for u in links:
        if u in hist_urls:
            continue
        st = slug_title(u)
        p = extract_person(" ".join(w.capitalize() for w in st.split()))
        if p and p.lower() in hist_people:
            print(f"[SKIP] '{p}' son videolarda var.")
            continue
        if any(title_overlap(st, ht) for ht in hist_titles):
            continue
        fresh.append(u)

    if not fresh:
        fresh = [u for u in links if u not in hist_urls] or links

    url = random.choice(fresh[:6])
    print(f"[OK] Haber: {url}")

    try:
        h = requests.get(url, headers=HEADERS, timeout=15).text
    except Exception as e:
        print(f"[ERROR] makale: {e}")
        return None, None, None

    def meta(prop):
        m = re.search(rf'<meta property="{prop}" content="([^"]+)"', h)
        return (m.group(1).replace("&#8217;", "'").replace("&#8216;", "'").replace("&#8220;", '"')
                .replace("&#8221;", '"').replace("&#8212;", "-").replace("&amp;", "&").replace("&#038;", "&")
                .replace("&#8230;", "...").strip()) if m else ""

    og_title = meta("og:title")
    og_desc = meta("og:description")
    og_img = meta("og:image")

    # govde metni
    paras = re.findall(r"<p[^>]*>(.*?)</p>", h, re.S)
    body = []
    for p in paras:
        t = re.sub(r"<[^>]+>", "", p)
        t = (t.replace("&#8217;", "'").replace("&#8216;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
             .replace("&#8212;", "-").replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8230;", "...")).strip()
        low = t.lower()
        if len(t) < 55:
            continue
        if any(k in low for k in ["primary menu", "sections", "add page six", "cookie", "newsletter",
                                  "sign up", "subscribe to", "©", "all rights reserved", "read more:"]):
            continue
        body.append(t)
        if len(body) >= 5:
            break

    full_text = og_title + "\n" + og_desc + "\n" + "\n".join(body)
    if len(full_text.strip()) < 40:
        print("[ERROR] Metin cekilemedi.")
        return None, None, None

    # foto indir
    foto_path = None
    if og_img:
        try:
            r = requests.get(og_img.split("?")[0], headers=HEADERS, timeout=15)
            r.raise_for_status()
            foto_path = os.path.join(script_dir, "orijinal_gonderi.jpg")
            open(foto_path, "wb").write(r.content)
            Image.open(foto_path).verify()
            print("[OK] Foto indirildi.")
        except Exception as e:
            print(f"[WARN] Foto: {e}")
            foto_path = None

    # gecmise kaydet
    person = extract_person(og_title or slug_title(url))
    hist_norm = [h if isinstance(h, dict) else {"url": h, "title": "", "person": ""} for h in hist]
    hist_norm.append({"url": url, "title": og_title[:120], "person": person})
    json.dump(hist_norm[-30:], open(USED_PATH, "w", encoding="utf-8"), ensure_ascii=False)

    return full_text, foto_path, person


# ─────────────────────────────────────────────────────────────
# GROQ
# ─────────────────────────────────────────────────────────────
def _groq(prompt, fallback=""):
    try:
        c = Groq(api_key=GROQ_API_KEY)
        r = c.chat.completions.create(model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content.strip()
    except Exception as e:
        print(f"[WARN] Groq: {e}")
        return fallback


def summarize(text):
    print("Ozet...")
    out = _groq(
        f"Summarize this celebrity news in 2-3 short sentences, max 220 characters total. "
        f"Match the tone (respectful if serious, upbeat if fun), natural language, no forced clickbait. "
        f"Output ONLY the summary:\n\n{text[:1200]}",
        fallback=text[:200].rsplit(" ", 1)[0] + "...")
    print(f"[OK] {out[:80]}")
    return out


def gen_title(text, person=""):
    print("Baslik...")
    hint = f"The story is about {person}; include their name early. " if person else ""
    tag = ("#" + person.replace(" ", "").lower()) if person else ""
    out = _groq(
        f"You are a top YouTube Shorts editor. Read this celebrity news:\n\"{text[:600]}\"\n\n"
        f"Write ONE curiosity-driven, emotionally engaging YouTube Shorts title. "
        f"Reflect the story accurately but make the viewer curious. {hint}"
        f"Add 2-3 hashtags: always #shorts, plus 1-2 topic tags{(' and ' + tag) if tag else ''}. "
        f"Max 80 characters. OUTPUT ONLY THE TITLE:",
        fallback="")
    out = out.replace('"', '').strip()
    if not out:
        out = random.choice([
            "Everyone Is Talking About This 😳 #shorts #celebrity",
            "Nobody Saw This Coming 😮 #shorts #hollywood",
            "This Just Happened In Hollywood 👀 #shorts #celebritynews",
        ])
    print(f"[OK] {out}")
    return out


def gen_hook(text):
    print("Hook...")
    out = _groq(
        f"Read this celebrity news:\n\"{text[:400]}\"\n\n"
        f"Write a SHORT scroll-stopping hook banner. Reflect the tone: shocking -> \"SHE SAID WHAT?!\", "
        f"sad -> \"FANS ARE HEARTBROKEN\", fun -> \"YOU WON'T BELIEVE THIS\". "
        f"Max 4 words. ALL CAPS. Output only the text.",
        fallback="")
    out = out.strip().strip('"').upper()
    return out or random.choice(["YOU WON'T BELIEVE THIS", "EVERYONE'S TALKING", "THIS IS WILD", "NOBODY EXPECTED THIS"])


def gen_cta(text):
    print("CTA...")
    out = _groq(
        f"Read this celebrity news:\n\"{text[:400]}\"\n\n"
        f"Write a very short question that makes viewers want to comment. Max 6 words. English. "
        f"Examples: \"What do you think?\", \"Team who?\", \"Did this surprise you?\". Output only the question.",
        fallback="")
    out = out.strip().strip('"')
    return out or random.choice(["What do you think?", "Were you surprised?", "Team who?", "Your thoughts?"])


def pick_music(text):
    print("Muzik...")
    md = os.path.join(script_dir, "muzikler")
    up = os.path.join(md, "upbeat")
    somber = os.path.join(md, "somber")
    up_f = [os.path.join(up, f) for f in os.listdir(up)] if os.path.isdir(up) else []
    so_f = [os.path.join(somber, f) for f in os.listdir(somber)] if os.path.isdir(somber) else []
    allf = [f for f in up_f + so_f if f.lower().endswith(".mp3")]
    if not allf:
        return None, 0.15
    tone = _groq(
        f"What's the overall tone of this celebrity news?\n\"{text[:300]}\"\nAnswer one word: UPBEAT or SOMBER",
        fallback="UPBEAT").upper()
    if "SOMBER" in tone and [f for f in so_f if f.lower().endswith(".mp3")]:
        pick = random.choice([f for f in so_f if f.lower().endswith(".mp3")])
    elif [f for f in up_f if f.lower().endswith(".mp3")]:
        pick = random.choice([f for f in up_f if f.lower().endswith(".mp3")])
    else:
        pick = random.choice(allf)
    print(f"[OK] {os.path.basename(pick)}")
    return pick, 0.18


# ─────────────────────────────────────────────────────────────
# VIDEO
# ─────────────────────────────────────────────────────────────
def create_video(img, music=None, volume=0.18):
    print("Video...")
    import numpy as np
    temp = "_temp_card.jpg"
    img.save(temp, quality=95)
    duration = 10
    arr = np.array(img)
    vw, vh = arr.shape[1], arr.shape[0]

    def zoom(gf, t):
        f = 1.0 + 0.07 * (t / duration)
        cw, ch = int(vw / f), int(vh / f)
        x0, y0 = (vw - cw) // 2, (vh - ch) // 2
        return np.array(Image.fromarray(arr[y0:y0 + ch, x0:x0 + cw]).resize((vw, vh), Image.Resampling.BILINEAR))

    clip = ImageClip(temp, duration=duration).fl(zoom)
    if music and os.path.exists(music):
        try:
            a = AudioFileClip(music)
            s = random.randint(0, max(0, int(a.duration) - duration - 2))
            end = min(s + duration, a.duration)
            aud = a.subclip(s, end).volumex(volume).audio_fadeout(0.6)
            clip = clip.set_audio(aud)
        except Exception as e:
            print(f"[WARN] muzik: {e}")
    clip.write_videofile(OUTPUT_VIDEO, fps=24, codec="libx264", logger=None)
    try:
        os.remove(temp)
    except Exception:
        pass
    print(f"[OK] {OUTPUT_VIDEO}")


# ─────────────────────────────────────────────────────────────
# YOUTUBE
# ─────────────────────────────────────────────────────────────
def upload_to_youtube(title, description, person=""):
    print("\nYouTube...")
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(SECRET_PATH):
        print("[ERROR] secret.json yok.")
        return None

    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES) if os.path.exists(TOKEN_PATH) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            creds = InstalledAppFlow.from_client_secrets_file(SECRET_PATH, SCOPES).run_local_server(port=0)
        open(TOKEN_PATH, 'w').write(creds.to_json())

    yt = build('youtube', 'v3', credentials=creds)
    tags = (([person, person.replace(' ', '')] if person else []) +
            ['shorts', 'celebrity', 'celebrity news', 'hollywood', 'entertainment', 'gossip', 'viral'])
    body = {
        'snippet': {'title': title[:100], 'description': description, 'tags': tags, 'categoryId': '24'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': False},
    }
    try:
        media = MediaFileUpload(OUTPUT_VIDEO, mimetype='video/mp4', resumable=True)
        req = yt.videos().insert(part='snippet,status', body=body, media_body=media)
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
        vid = resp['id']
        print(f"[OK] https://youtube.com/shorts/{vid}")
        return vid
    except Exception as e:
        print(f"[ERROR] upload: {e}")
        return None


def save_run_log(status, video_id=None, title=None, error=None):
    from datetime import datetime
    p = os.path.join(script_dir, "run_log.json")
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception:
        data = {"bot": "celeb_news", "runs": []}
    e = {"ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "status": status}
    if video_id:
        e["video_id"] = video_id
    if title:
        e["title"] = title[:80]
    if error:
        e["error"] = str(error)[:200]
    data.setdefault("runs", []).append(e)
    data["runs"] = data["runs"][-20:]
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    TEST = "--test" in sys.argv
    print("=== CELEB NEWS BOT" + (" [TEST]" if TEST else "") + " ===\n")

    text, foto, person = fetch_news()
    if not text:
        print("[ERROR] Haber cekilemedi.")
        save_run_log("error", error="fetch_news failed")
        sys.exit(1)

    foto_paths = [foto] if foto else []
    summary = summarize(text)
    title = gen_title(text, person)
    hook = gen_hook(text)
    cta = gen_cta(text)
    music, volume = pick_music(text)

    first = summary.split('.')[0].strip()
    prefix = (person + " - ") if person and person.lower() not in first.lower() else ""
    description = (f"{prefix}{first}.\n\n{text[:3500]}\n\n"
                   f"#shorts #celebrity #celebritynews #hollywood #entertainment #gossip #viral"
                   f"{(' #' + person.replace(' ', '').lower()) if person else ''}")

    img = create_card(summary, foto_paths, hook_text=hook, cta_text=cta)
    create_video(img, music, volume=volume)

    if TEST:
        print(f"\n[TEST] video: {OUTPUT_VIDEO}")
    else:
        vid = upload_to_youtube(title, description, person=person)
        if vid:
            save_run_log("ok", video_id=vid, title=title)
            send_telegram(f"✅ <b>celeb_news</b> yayınlandı!\n🎬 {title}\n🔗 https://youtube.com/shorts/{vid}")
        else:
            save_run_log("error", error="upload failed")
            send_telegram("❌ <b>celeb_news</b> yükleme başarısız!")

    print("\n=== Tamamlandi ===")
