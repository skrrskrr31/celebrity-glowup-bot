"""
CELEBRITY GLOW-UP BOT — Fully Automated
Pulls before/after photos from Wikipedia, creates a YouTube Short, uploads automatically.
Test mode: python 1_eski_yeni_video_bot.py --test
"""

import os, sys, random, json, re, io
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from moviepy.editor import (
    ImageClip, concatenate_videoclips,
    CompositeAudioClip, AudioFileClip
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import yt_dlp
from groq import Groq

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

TEST_MODE = "--test" in sys.argv

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
SECRET_PATH  = os.path.join(script_dir, "secret.json")
TOKEN_PATH   = os.path.join(script_dir, "token.json")
USED_FILE    = os.path.join(script_dir, "used_celebs.json")
OUTPUT_VIDEO = os.path.join(script_dir, "shorts_video.mp4")
MUSIC_BASE   = os.path.join(script_dir, "music")
W, H         = 1080, 1920

HEADERS = {"User-Agent": "GlowUpBot/2.0 (educational)"}

# ─────────────────────────────────────────────────────────────
# CELEBRITY LIST  (Wikipedia page title, display name)
# All verified to have year-tagged photos with 10+ year gap
# ─────────────────────────────────────────────────────────────
CELEBRITIES = [
    {"wiki": "Beyoncé",           "name": "Beyoncé"},
    {"wiki": "Madonna",           "name": "Madonna"},
    {"wiki": "Lady Gaga",         "name": "Lady Gaga"},
    {"wiki": "Jennifer Lopez",    "name": "Jennifer Lopez"},
    {"wiki": "Katy Perry",        "name": "Katy Perry"},
    {"wiki": "Taylor Swift",      "name": "Taylor Swift"},
    {"wiki": "Britney Spears",    "name": "Britney Spears"},
    {"wiki": "Miley Cyrus",       "name": "Miley Cyrus"},
    {"wiki": "Selena Gomez",      "name": "Selena Gomez"},
    {"wiki": "Ariana Grande",     "name": "Ariana Grande"},
    {"wiki": "Rihanna",           "name": "Rihanna"},
    {"wiki": "Adele",             "name": "Adele"},
    {"wiki": "Demi Lovato",       "name": "Demi Lovato"},
    {"wiki": "Ed Sheeran",        "name": "Ed Sheeran"},
    {"wiki": "Eminem",            "name": "Eminem"},
    {"wiki": "Johnny Depp",       "name": "Johnny Depp"},
    {"wiki": "Chris Brown",       "name": "Chris Brown"},
    {"wiki": "Kanye West",        "name": "Kanye West"},
    {"wiki": "Tom Hanks",         "name": "Tom Hanks"},
    {"wiki": "Shakira",           "name": "Shakira"},
    {"wiki": "Nicki Minaj",       "name": "Nicki Minaj"},
    {"wiki": "Paris Hilton",      "name": "Paris Hilton"},
    {"wiki": "Pamela Anderson",   "name": "Pamela Anderson"},
    {"wiki": "Kim Kardashian",    "name": "Kim Kardashian"},
    {"wiki": "Caitlyn Jenner",    "name": "Caitlyn Jenner"},
    {"wiki": "Lizzo",             "name": "Lizzo"},
    {"wiki": "Megan Fox",         "name": "Megan Fox"},
    {"wiki": "Sam Smith",         "name": "Sam Smith"},
    {"wiki": "Drew Barrymore",    "name": "Drew Barrymore"},
    {"wiki": "Jennifer Aniston",  "name": "Jennifer Aniston"},
    {"wiki": "Hadise",            "name": "Hadise"},
    {"wiki": "Ajda Pekkan",       "name": "Ajda Pekkan"},
    {"wiki": "Sertab Erener",     "name": "Sertab Erener"},
]

# ─────────────────────────────────────────────────────────────
# FONT
# ─────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    paths = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "C:\\Windows\\Fonts\\arialbd.ttf",
         "C:\\Windows\\Fonts\\impact.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "C:\\Windows\\Fonts\\arial.ttf"]
    )
    for p in paths:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default(size=size)


# ─────────────────────────────────────────────────────────────
# USED TRACKING
# ─────────────────────────────────────────────────────────────
def load_used():
    if os.path.exists(USED_FILE):
        with open(USED_FILE, encoding='utf-8') as f:
            return json.load(f)
    return []

def save_used(lst):
    with open(USED_FILE, 'w', encoding='utf-8') as f:
        json.dump(lst[-50:], f, ensure_ascii=False)

def pick_celebrity():
    used = load_used()
    pool = [c for c in CELEBRITIES if c["name"] not in used]
    if not pool:
        pool = CELEBRITIES
        used = []
    chosen = random.choice(pool)
    used.append(chosen["name"])
    save_used(used)
    return chosen


# ─────────────────────────────────────────────────────────────
# WIKIPEDIA PHOTOS
# ─────────────────────────────────────────────────────────────
def extract_year(fn):
    m = re.search(r'(19[6-9]\d|20[0-2]\d)', fn)
    return int(m.group(1)) if m else None

def get_wiki_images(wiki_title):
    r = requests.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "titles": wiki_title, "prop": "images",
        "format": "json", "imlimit": 50
    }, headers=HEADERS, timeout=15)
    for p in r.json().get("query", {}).get("pages", {}).values():
        return [i["title"] for i in p.get("images", [])
                if not any(k in i["title"].lower() for k in
                           ["flag","logo","svg","commons","arrow","edit","icon",
                            "map","sign","ribbon","stub","wikimedia","silhouette"])]
    return []

def get_image_url(file_title):
    r = requests.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "titles": file_title, "prop": "imageinfo",
        "iiprop": "url", "iiurlwidth": 900, "format": "json"
    }, headers=HEADERS, timeout=15)
    for p in r.json().get("query", {}).get("pages", {}).values():
        ii = p.get("imageinfo", [])
        if ii:
            return ii[0].get("thumburl") or ii[0].get("url")
    return None

def find_before_after_photos(wiki_title):
    imgs = get_wiki_images(wiki_title)
    print(f"  Found {len(imgs)} photos on Wikipedia")

    year_imgs = sorted(
        [(f, extract_year(f)) for f in imgs if extract_year(f)],
        key=lambda x: x[1]
    )

    if len(year_imgs) >= 2:
        before_file, before_year = year_imgs[0]
        after_file,  after_year  = year_imgs[-1]
        print(f"  Year gap: {before_year} vs {after_year}")
    elif len(imgs) >= 2:
        before_file, after_file = imgs[0], imgs[-1]
        before_year, after_year = "Before", "After"
        print("  No year tags — using first/last photo")
    else:
        return None, None, None, None

    before_url = get_image_url(before_file)
    after_url  = get_image_url(after_file)
    return before_url, after_url, str(before_year), str(after_year)

def download_image(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGB")


# ─────────────────────────────────────────────────────────────
# VIDEO FRAMES
# ─────────────────────────────────────────────────────────────
def make_photo_frame(pil_img, label, year, celeb_name, label_color):
    """Full-screen photo with blurred background + BEFORE/AFTER overlay."""
    # Blurred background
    bg = pil_img.copy()
    iw, ih = bg.size
    bg_r = W / H
    ir   = iw / ih
    if ir > bg_r:
        nw = int(bg_r * ih)
        bg = bg.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / bg_r)
        bg = bg.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    bg = bg.resize((W, H), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=28))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 155))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    # Foreground photo — crop to portrait if landscape
    fw, fh = pil_img.size
    if fw > fh:  # landscape → crop center portrait
        new_w = int(fh * (W / H))
        if new_w > fw:
            new_w = fw
        pil_img = pil_img.crop(((fw - new_w) // 2, 0, (fw - new_w) // 2 + new_w, fh))
        fw, fh = pil_img.size

    max_w, max_h = 960, 1340
    scale = min(max_w / fw, max_h / fh)
    nw, nh = int(fw * scale), int(fh * scale)
    fg = pil_img.resize((nw, nh), Image.Resampling.LANCZOS)
    px = (W - nw) // 2
    py = (H - nh) // 2 - 50
    bg.paste(fg, (px, py))

    draw = ImageDraw.Draw(bg)

    # Celebrity name — top
    f_name = load_font(66, bold=True)
    nb = draw.textbbox((0, 0), celeb_name, font=f_name)
    nx = (W - (nb[2] - nb[0])) // 2
    draw.text((nx + 3, 55), celeb_name, font=f_name, fill=(0, 0, 0))
    draw.text((nx, 52),     celeb_name, font=f_name, fill=(255, 255, 255))

    # BEFORE / AFTER label — bottom
    f_label = load_font(108, bold=True)
    f_year  = load_font(58,  bold=False)

    lb = draw.textbbox((0, 0), label, font=f_label)
    lx = (W - (lb[2] - lb[0])) // 2
    label_y = H - 235
    draw.text((lx + 5, label_y + 5), label, font=f_label, fill=(0, 0, 0))
    draw.text((lx, label_y),         label, font=f_label, fill=label_color)

    yb = draw.textbbox((0, 0), year, font=f_year)
    yx = (W - (yb[2] - yb[0])) // 2
    draw.text((yx + 2, label_y + 115), year, font=f_year, fill=(0, 0, 0))
    draw.text((yx,     label_y + 113), year, font=f_year, fill=(210, 210, 210))

    return bg


def make_intro_frame(celeb_name):
    img  = Image.new("RGB", (W, H), (8, 8, 18))
    draw = ImageDraw.Draw(img)

    # Starfield
    for _ in range(70):
        sx, sy = random.randint(0, W), random.randint(0, H)
        r = random.randint(1, 3)
        a = random.randint(60, 180)
        draw.ellipse([sx-r, sy-r, sx+r, sy+r], fill=(a, a, a))

    f_tag  = load_font(46, bold=False)
    f_big  = load_font(88, bold=True)
    f_sub  = load_font(58, bold=True)

    # Top tag
    tag = "CELEBRITY GLOW UP"
    tb  = draw.textbbox((0, 0), tag, font=f_tag)
    draw.text(((W - (tb[2]-tb[0])) // 2, 145), tag, font=f_tag, fill=(160, 160, 160))

    # Name
    nb = draw.textbbox((0, 0), celeb_name, font=f_big)
    nx = (W - (nb[2]-nb[0])) // 2
    draw.text((nx + 4, H//2 - 85), celeb_name, font=f_big, fill=(0, 0, 0))
    draw.text((nx,     H//2 - 89), celeb_name, font=f_big, fill=(255, 215, 0))

    # Subtitle
    sub = "THEN vs NOW"
    sb  = draw.textbbox((0, 0), sub, font=f_sub)
    sx2 = (W - (sb[2]-sb[0])) // 2
    draw.text((sx2 + 3, H//2 + 42), sub, font=f_sub, fill=(0, 0, 0))
    draw.text((sx2,     H//2 + 39), sub, font=f_sub, fill=(255, 255, 255))

    draw.line([(120, H//2 + 112), (W-120, H//2 + 112)], fill=(255, 215, 0), width=3)

    # Bottom hashtags
    ht = "#shorts  #glowup  #celebrity"
    hb = draw.textbbox((0, 0), ht, font=f_tag)
    draw.text(((W-(hb[2]-hb[0]))//2, H-130), ht, font=f_tag, fill=(100, 100, 100))

    return img


def make_outro_frame(celeb_name, before_year, after_year):
    img  = Image.new("RGB", (W, H), (8, 8, 18))
    draw = ImageDraw.Draw(img)

    # Starfield
    for _ in range(70):
        sx, sy = random.randint(0, W), random.randint(0, H)
        r = random.randint(1, 3)
        a = random.randint(60, 180)
        draw.ellipse([sx-r, sy-r, sx+r, sy+r], fill=(a, a, a))

    f_big = load_font(82, bold=True)
    f_med = load_font(52, bold=False)
    f_sm  = load_font(46, bold=True)
    f_btn = load_font(38, bold=True)
    f_tag = load_font(42, bold=False)

    # Big blue tick circle
    cx_o, cy_o, r_o = W // 2, 560, 170
    draw.ellipse([cx_o-r_o, cy_o-r_o, cx_o+r_o, cy_o+r_o], fill=(29, 155, 240))
    ts  = int(r_o * 1.25)
    ttx = cx_o - ts // 2
    tty = cy_o - ts // 2
    tp1 = (int(ttx + ts*0.17), int(tty + ts*0.52))
    tp2 = (int(ttx + ts*0.42), int(tty + ts*0.74))
    tp3 = (int(ttx + ts*0.81), int(tty + ts*0.26))
    lw  = max(6, int(ts * 0.09))
    draw.line([tp1, tp2, tp3], fill="white", width=lw)
    rj = lw // 2
    draw.ellipse([tp2[0]-rj, tp2[1]-rj, tp2[0]+rj, tp2[1]+rj], fill="white")

    # Year comparison badge
    badge = f"{before_year}  →  {after_year}"
    bbx   = draw.textbbox((0, 0), badge, font=f_tag)
    bw    = bbx[2] - bbx[0]
    bx    = (W - bw) // 2
    draw.rounded_rectangle([bx-24, 766, bx+bw+24, 820], radius=14, fill=(30, 30, 50))
    draw.text((bx, 769), badge, font=f_tag, fill=(180, 180, 180))

    # Question
    q1 = "Can you believe"
    q2 = "the difference?!"
    q1b = draw.textbbox((0, 0), q1, font=f_big)
    q2b = draw.textbbox((0, 0), q2, font=f_big)
    draw.text(((W-(q1b[2]-q1b[0]))//2 + 3, 852), q1, font=f_big, fill=(0,0,0))
    draw.text(((W-(q1b[2]-q1b[0]))//2,     849), q1, font=f_big, fill=(255, 215, 0))
    draw.text(((W-(q2b[2]-q2b[0]))//2 + 3, 958), q2, font=f_big, fill=(0,0,0))
    draw.text(((W-(q2b[2]-q2b[0]))//2,     955), q2, font=f_big, fill=(255, 255, 255))

    # Comment call
    cc  = "Comment your reaction below!"
    ccb = draw.textbbox((0, 0), cc, font=f_med)
    draw.text(((W-(ccb[2]-ccb[0]))//2, 1072), cc, font=f_med, fill=(190, 190, 190))

    # Subscribe box
    box_y = 1175
    draw.rounded_rectangle([80, box_y, W-80, box_y+295], radius=30,
                            fill=(18, 18, 36), outline=(55, 55, 95), width=2)

    s1  = "New video every day!"
    s2  = "Subscribe + Like!"
    s1b = draw.textbbox((0, 0), s1, font=f_med)
    s2b = draw.textbbox((0, 0), s2, font=f_sm)
    draw.text(((W-(s1b[2]-s1b[0]))//2, box_y+36),  s1, font=f_med, fill=(200, 200, 200))
    draw.text(((W-(s2b[2]-s2b[0]))//2, box_y+112), s2, font=f_sm,  fill=(255, 75, 75))

    btn_y = box_y + 193
    draw.rounded_rectangle([150, btn_y, 490, btn_y+70], radius=16, fill=(200, 0, 0))
    draw.rounded_rectangle([560, btn_y, 880, btn_y+70], radius=16, fill=(29, 155, 240))

    sub_t = "SUBSCRIBE"
    lk_t  = "LIKE"
    sbb = draw.textbbox((0, 0), sub_t, font=f_btn)
    lkb = draw.textbbox((0, 0), lk_t,  font=f_btn)
    draw.text((150 + (340-(sbb[2]-sbb[0]))//2, btn_y+16), sub_t, font=f_btn, fill="white")
    draw.text((560 + (320-(lkb[2]-lkb[0]))//2, btn_y+16), lk_t,  font=f_btn, fill="white")

    # Celeb name footer
    ncb = draw.textbbox((0, 0), celeb_name, font=f_tag)
    draw.text(((W-(ncb[2]-ncb[0]))//2, H-145), celeb_name, font=f_tag, fill=(80, 80, 80))

    return img


# ─────────────────────────────────────────────────────────────
# CREATE VIDEO
# ─────────────────────────────────────────────────────────────
def create_video(before_pil, after_pil, before_year, after_year, celeb_name, music_file=None):
    print("  Building frames...")
    intro  = make_intro_frame(celeb_name)
    before = make_photo_frame(before_pil, "BEFORE", before_year, celeb_name, (255, 200, 55))
    after  = make_photo_frame(after_pil,  "AFTER",  after_year,  celeb_name, (55, 220, 110))
    outro  = make_outro_frame(celeb_name, before_year, after_year)

    clips = [
        ImageClip(np.array(intro),  duration=1.5).fadein(0.3),
        ImageClip(np.array(before), duration=3.5),
        ImageClip(np.array(after),  duration=3.5),
        ImageClip(np.array(outro),  duration=3.0).fadeout(0.4),
    ]
    final = concatenate_videoclips(clips, method="compose")

    if music_file and os.path.exists(music_file):
        try:
            music  = AudioFileClip(music_file)
            start  = 12 if music.duration > 25 else (4 if music.duration > 12 else 0)
            music  = music.subclip(start, min(start + final.duration, music.duration))
            music  = music.volumex(0.22).audio_fadein(0.4).audio_fadeout(0.6)
            final  = final.set_audio(music)
            print("  Music added.")
        except Exception as e:
            print(f"  [WARN] Music error: {e}")

    final.write_videofile(OUTPUT_VIDEO, fps=30, codec="libx264", audio_codec="aac", logger=None)
    print(f"  [OK] Video: {OUTPUT_VIDEO}")


# ─────────────────────────────────────────────────────────────
# MUSIC DOWNLOAD
# ─────────────────────────────────────────────────────────────
def download_music(celeb_name):
    print(f"  Downloading music ({celeb_name})...")
    queries = [
        f"ytsearch1:{celeb_name} greatest hits official",
        f"ytsearch1:{celeb_name} best song",
        f"ytsearch1:top pop hits 2024",
    ]
    for ext in [".m4a", ".webm", ".mp4", ".mp3"]:
        p = MUSIC_BASE + ext
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    opts = {"format": "bestaudio/best", "outtmpl": f"{MUSIC_BASE}.%(ext)s",
            "noplaylist": True, "quiet": True}
    for q in queries:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([q])
            for ext in [".m4a", ".webm", ".mp4", ".mp3"]:
                if os.path.exists(MUSIC_BASE + ext):
                    print(f"  Music OK: {MUSIC_BASE + ext}")
                    return MUSIC_BASE + ext
        except Exception as e:
            print(f"  [WARN] Music attempt failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────
# YOUTUBE UPLOAD
# ─────────────────────────────────────────────────────────────
def upload_to_youtube(celeb_name, before_year, after_year):
    print("\nUploading to YouTube...")

    import base64 as _b64
    token_env = os.environ.get("TOKEN_JSON", "")
    if token_env:
        try:    td = _b64.b64decode(token_env).decode()
        except: td = token_env
        with open(TOKEN_PATH, "w") as f:
            f.write(td)

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    creds  = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    hooks = [
        f"{celeb_name} then vs now — can you believe this?!",
        f"{celeb_name}'s glow up is INSANE 😱",
        f"{celeb_name} {before_year} vs {after_year} — spot the difference!",
        f"Nobody talks about {celeb_name}'s transformation...",
        f"{celeb_name} barely looks the same 🤯",
    ]
    hook = random.choice(hooks)
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp   = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content":
                f'YouTube Shorts clickbait title for a celebrity glow-up/transformation video. '
                f'Celebrity: "{celeb_name}", years: {before_year} vs {after_year}. '
                f'Hook idea: "{hook}". Max 65 chars, end with #Shorts, scroll-stopping. '
                f'ONLY THE TITLE, no quotes:'}]
        )
        title = resp.choices[0].message.content.strip().replace('"', '').strip()
        if not title: raise ValueError("empty")
    except Exception as e:
        print(f"  [WARN] Groq: {e}")
        title = hook + " #Shorts"

    desc = (
        f"{celeb_name} transformation: {before_year} vs {after_year}!\n\n"
        f"What do you think? Comment your reaction below!\n"
        f"Subscribe for a new glow-up every day!\n\n"
        f"#{celeb_name.replace(' ','')} #glowup #transformation #celebrity "
        f"#thenandnow #shorts #viral"
    )
    tags = ["glow up", "transformation", "then and now", "celebrity", "shorts",
            "before and after", celeb_name.replace(" ", ""), "viral", "celebrity transformation"]

    print(f"  Title: {title}")
    yt   = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title[:100], "description": desc,
                    "tags": tags, "categoryId": "24"},
        "status":  {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    try:
        media = MediaFileUpload(OUTPUT_VIDEO, mimetype="video/mp4", resumable=True)
        req   = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = req.next_chunk()
            if status: print(f"  {int(status.progress()*100)}%")
        vid = response["id"]
        print(f"\n[OK] Published! https://youtube.com/shorts/{vid}")
        return vid
    except Exception as e:
        print(f"  [ERROR] YouTube: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== CELEBRITY GLOW-UP BOT ===\n")

    # --celeb "Name" to force a specific celebrity
    force_name = None
    for i, arg in enumerate(sys.argv):
        if arg == "--celeb" and i + 1 < len(sys.argv):
            force_name = sys.argv[i + 1]

    if force_name:
        match = next((c for c in CELEBRITIES if c["name"].lower() == force_name.lower()), None)
        celeb = match or {"wiki": force_name, "name": force_name}
        print(f"[Force] {celeb['name']}")
    else:
        celeb = pick_celebrity()

    print(f"Celebrity: {celeb['name']}  (Wikipedia: {celeb['wiki']})")

    # Find photos
    print("\nSearching Wikipedia for photos...")
    before_url, after_url, before_year, after_year = find_before_after_photos(celeb["wiki"])

    if not before_url or not after_url:
        print("[ERROR] Not enough photos. Trying another celebrity...")
        for _ in range(8):
            celeb = random.choice(CELEBRITIES)
            before_url, after_url, before_year, after_year = find_before_after_photos(celeb["wiki"])
            if before_url and after_url:
                print(f"  Switched to: {celeb['name']}")
                break
        if not before_url:
            print("[FATAL] Could not find photos for any celebrity.")
            sys.exit(1)

    print(f"\nDownloading photos...")
    before_pil = download_image(before_url)
    after_pil  = download_image(after_url)
    print(f"  Before: {before_pil.size}  After: {after_pil.size}")

    # Music
    music_file = download_music(celeb["name"])

    # Build video
    print("\nBuilding video...")
    create_video(before_pil, after_pil, before_year, after_year, celeb["name"], music_file)

    if TEST_MODE:
        print("\n[TEST] Skipping YouTube upload.")
        print(f"[TEST] Video: {OUTPUT_VIDEO}")
    else:
        upload_to_youtube(celeb["name"], before_year, after_year)

    # Cleanup music
    for ext in [".m4a", ".webm", ".mp4", ".mp3"]:
        p = MUSIC_BASE + ext
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    print("\n=== Done! ===")
