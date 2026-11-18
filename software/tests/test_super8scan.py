# Prove con telecamera simulata. Non toccano le impostazioni vere (APPDATA su cartella temporanea).
import os, sys, time, tempfile, hashlib, subprocess, json, ctypes, shutil
tmp = tempfile.mkdtemp(prefix="s8test_")
os.environ["APPDATA"] = os.path.join(tmp, "appdata")
os.makedirs(os.environ["APPDATA"])
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import super8scan as m

def check(c, msg):
    print(("OK   " if c else "FAIL ") + msg)
    if not c: check.fails += 1
check.fails = 0

a = m.App(sim=True)
a.hook.callback = lambda t: None   # i click veri dell'utente durante la prova non devono contare
a.s.update(folder=os.path.join(tmp, "out"), project="prova", delay_ms=100, format="jpg", jpg_quality=98)
a.open_camera()
check(a.grab.width == 3840 and a.grab.height == 2160, "sorgente 4K aperta")
a.start_capture()
N = 40
t0 = time.perf_counter()
for i in range(N):                         # 5 click al secondo
    a._on_click(time.perf_counter())
    time.sleep(0.2)
time.sleep(1.0)
a.stop_capture()
d = a.out_dir
files = sorted(f for f in os.listdir(d) if f.endswith(".jpg"))
check(len(files) == N, f"salvati {len(files)} fotogrammi su {N}")
check(a.failed == 0 and a.late == 0, f"nessun errore (failed={a.failed}, late={a.late})")
import glob, re
logs = sorted(glob.glob(os.path.join(a.s["folder"], "*.txt")))
check(len(logs) == 1 and re.fullmatch(r"prova-\d{8}-\d{4}\.txt", os.path.basename(logs[0])) is not None, "log scritto con il nome film-ggmmaaaa-hhmm: " + str([os.path.basename(x) for x in logs]))
testo = open(logs[0], encoding="utf-8-sig").read() if logs else ""
check("Film: prova" in testo and ("acquisiti in questa lavorazione: %d" % N) in testo and "Durata della scansione:" in testo and "Data e ora di lavorazione:" in testo, "il log contiene film, fotogrammi, durata e data")
print(testo)
hs = {hashlib.md5(open(os.path.join(d, f), "rb").read()).hexdigest() for f in files}
check(len(hs) == N, "tutti i fotogrammi sono diversi")
check(files[0] == "fotogramma_000001.jpg" and files[-1] == "fotogramma_%06d.jpg" % N, "numerazione continua")
print("   dimensione media", sum(os.path.getsize(os.path.join(d, f)) for f in files) // N // 1024, "KB; fps medi", a.state()["avg_fps"])

# click molto ravvicinati: devono dare fotogrammi diversi comunque
a.start_capture()
check(a.next_index == N + 1, "riparte dal numero successivo")
for i in range(5):
    a._on_click(time.perf_counter()); time.sleep(0.05)
time.sleep(1.0); a.stop_capture()
files = sorted(f for f in os.listdir(d) if f.endswith(".jpg"))
check(len(files) == N + 5, f"click ravvicinati: {len(files) - N}/5")
# zona da ignorare
a.start_capture(); a.ignore_zone = True; a._on_click(time.perf_counter()); a.ignore_zone = False
time.sleep(0.5); a.stop_capture()
check(len([f for f in os.listdir(d) if f.endswith(".jpg")]) == N + 5, "click sul pulsante Ferma ignorato")

# hook reale: finestra tkinter mia, click iniettato dentro la finestra
import tkinter as tk
a.hook.callback = a._on_click
a.start_capture()
root = tk.Tk(); root.geometry("200x200+300+300"); root.attributes("-topmost", True); root.update()
ctypes.windll.user32.SetCursorPos(400, 400)
for _ in range(10): root.update(); time.sleep(0.02)
before = a.jobs.qsize() + a.session_count
ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.01); ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
for _ in range(15): root.update(); time.sleep(0.05)
root.destroy()
time.sleep(0.5); a.stop_capture()
check(len([f for f in os.listdir(d) if f.endswith(".jpg")]) >= N + 6, "hook del mouse vede il click sinistro")

# fotogrammi bianchi in fondo (pellicola finita): vanno esclusi dal video
import numpy as np, cv2
for k in range(1, 7):
    ok, buf = cv2.imencode(".jpg", np.full((540, 960, 3), 255, np.uint8))
    open(os.path.join(d, "fotogramma_%06d.jpg" % (N + 6 + k)), "wb").write(buf.tobytes())
fi = a.folder_info()
check(fi["blank_tail"] == 6, "rilevati 6 fotogrammi bianchi finali (%s)" % fi["blank_tail"])
# un fotogramma chiaro ma con contenuto non è bianco
ok, buf = cv2.imencode(".jpg", (np.random.rand(540, 960, 3) * 60 + 170).astype(np.uint8))
open(os.path.join(d, "chiaro.jpg"), "wb").write(buf.tobytes())
check(not m.fotogramma_bianco(os.path.join(d, "chiaro.jpg")), "un fotogramma chiaro con contenuto non è bianco")
os.remove(os.path.join(d, "chiaro.jpg"))

# video
ff = a.ffmpeg
check(bool(ff), "ffmpeg trovato: " + ff)
a.s.update(video_fps=18, video_mbps=20, video_codec="h264", video_scale="orig", video_name="")
a.build_video()
while a.video["running"]: time.sleep(0.2)
check(a.video["done"], "video creato " + (a.video["error"] or a.video["msg"]))
out = a.video["path"]
pr = json.loads(subprocess.run([os.path.join(os.path.dirname(ff), "ffprobe.exe"), "-v", "error", "-count_frames", "-select_streams", "v",
    "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_read_frames,bit_rate", "-of", "json", out], capture_output=True, text=True).stdout)["streams"][0]
print("  ", pr)
check(int(pr["nb_read_frames"]) == N + 6, "il video ha tutti i fotogrammi")
check(pr["r_frame_rate"] == "18/1", "18 fps")
check(pr["width"] == 3840, "4K")
# ribaltamento verticale: nella sorgente simulata il verde cresce dall'alto (40) al basso (200)
png = os.path.join(tmp, "primo.png")
subprocess.run([ff, "-y", "-v", "error", "-i", out, "-frames:v", "1", png], check=True)
fr = cv2.imread(png)
check(fr[:40, :, 1].mean() > 150 and fr[-40:, :, 1].mean() < 100, "immagine ribaltata in verticale")
check(a.video["msg"].endswith("6 fotogrammi bianchi finali esclusi"), "messaggio: " + a.video["msg"])
a.s.update(video_flip_v=False, video_trim_white=False, video_name="senza.mp4")
a.build_video()
while a.video["running"]: time.sleep(0.2)
pr2 = json.loads(subprocess.run([os.path.join(os.path.dirname(ff), "ffprobe.exe"), "-v", "error", "-count_frames", "-select_streams", "v",
    "-show_entries", "stream=nb_read_frames", "-of", "json", a.video["path"]], capture_output=True, text=True).stdout)["streams"][0]
check(int(pr2["nb_read_frames"]) == N + 12, "senza esclusione: tutti i fotogrammi (%s)" % pr2["nb_read_frames"])
a.s.update(video_flip_v=True, video_trim_white=True, video_name="")
a.s.update(video_scale="1920", video_codec="h265", video_fps=24, video_name="piccolo.mp4", video_folder=os.path.join(tmp, "altra", "cartella"))
a.build_video()
while a.video["running"]: time.sleep(0.2)
check(os.path.isfile(os.path.join(tmp, "altra", "cartella", "piccolo.mp4")), "video nella cartella scelta")
check(a.video["done"], "secondo video (1920, h265, 24 fps) " + (a.video["error"] or a.video["msg"]))
# --- controllo dei fotogrammi (foro) con immagini sintetiche 1920x1080
import controllo
rng = np.random.default_rng(1)
cart = os.path.join(tmp, "ctl", "film")
os.makedirs(cart)
def fotogramma(i, dy=0, sfoca=False, bianco=False):
    if bianco:
        return np.full((1080, 1920, 3), 255, np.uint8)
    im = (rng.random((1080, 1920, 3)) * 120 + 60).astype(np.uint8)
    im[:, :260] = 5                                          # margine scuro a sinistra e fino all'immagine
    y0 = 420 + int(rng.integers(-3, 4)) + dy
    im[y0:y0 + 240, 140:220] = 250                             # foro
    if sfoca:
        im[:, 120:240] = cv2.blur(im[:, 120:240], (1, 181))
    return im
spec = {40: dict(dy=70), 60: dict(sfoca=True)}
for i in range(1, 101):
    cv2.imwrite(os.path.join(cart, "fotogramma_%06d.jpg" % i), fotogramma(i, **spec.get(i, {})), [cv2.IMWRITE_JPEG_QUALITY, 90])
for i in range(101, 106):
    cv2.imwrite(os.path.join(cart, "fotogramma_%06d.jpg" % i), fotogramma(i, bianco=True))
a.s.update(folder=os.path.join(tmp, "ctl"), project="film", video_scartati_modo="salta", video_name="", video_folder="", video_fps=18, video_scale="orig")
a.controllo_avvia()
while a.controllo["running"]: time.sleep(0.2)
st = a.controllo_stato()
check(not a.controllo["error"] and st["pronto"], "analisi completata " + a.controllo["error"])
nums = sorted(x["n"] for x in st["sospetti"])
check(nums == [40, 60], "sospetti trovati: %s (attesi 40 e 60)" % nums)
check(a.folder_info()["discarded"] == 2, "due fotogrammi da scartare nel riepilogo")
a.controllo_scarta([60], False)
check(a.controllo_stato()["scartati"] == 1, "scelta dell'utente: ne tengo uno")
check(os.path.isfile(controllo.percorso_file(cart)), "scelte salvate nella cartella del film")
a2 = m.App(sim=True)                                                    # riapre: le scelte sono ricordate
a2.s.update(folder=os.path.join(tmp, "ctl"), project="film")
check(a2.controllo_stato()["scartati"] == 1, "le scelte sopravvivono alla chiusura")
a2.shutdown()
a.build_video()
while a.video["running"]: time.sleep(0.2)
pr3 = json.loads(subprocess.run([os.path.join(os.path.dirname(ff), "ffprobe.exe"), "-v", "error", "-count_frames", "-select_streams", "v",
    "-show_entries", "stream=nb_read_frames", "-of", "json", a.video["path"]], capture_output=True, text=True).stdout)["streams"][0]
check(int(pr3["nb_read_frames"]) == 99, "video: 100 fotogrammi - 1 scartato, 5 bianchi esclusi (%s)" % pr3["nb_read_frames"])
a.s.update(video_scartati_modo="ripeti", video_name="ripeti.mp4")
a.build_video()
while a.video["running"]: time.sleep(0.2)
pr4 = json.loads(subprocess.run([os.path.join(os.path.dirname(ff), "ffprobe.exe"), "-v", "error", "-count_frames", "-select_streams", "v",
    "-show_entries", "stream=nb_read_frames", "-of", "json", a.video["path"]], capture_output=True, text=True).stdout)["streams"][0]
check(int(pr4["nb_read_frames"]) == 100, "modo ripeti: la durata resta uguale (%s)" % pr4["nb_read_frames"])
# foro attaccato al bordo dell'immagine (come nella scansione 04 - 1987): con la sola soglia di Otsu foro e immagine si fondono
cart3 = os.path.join(tmp, "ctl", "attaccato"); os.makedirs(cart3)
for i in range(1, 41):
    im = (rng.random((1080, 1920, 3)) * 60 + 70).astype(np.uint8)   # contenuto grigio medio, sempre sotto il foro
    im[:, :140] = 5
    im[:, 140:220] = 5
    y0 = 420 + int(rng.integers(-3, 4))
    im[y0:y0 + 270, 140:220] = 250                                    # il foro finisce dove comincia l'immagine
    im[:, 220:] = np.clip(im[:, 220:], 70, 130)
    cv2.imwrite(os.path.join(cart3, "fotogramma_%06d.jpg" % i), im, [cv2.IMWRITE_JPEG_QUALITY, 90])
roi3 = controllo.calibra(cart3, [n for _, n in controllo.elenco_fotogrammi(cart3)])
check(roi3 is not None and abs(roi3["x"] - 140 / 1920) < 0.01, "foro a contatto con l'immagine riconosciuto (%s)" % (roi3,))
# preset x264 "medium": si seleziona dal codec e produce un video valido con lo stesso numero di fotogrammi
a.s.update(video_codec="h264_medium", video_scartati_modo="ripeti", video_name="medium.mp4")
a.build_video()
while a.video["running"]: time.sleep(0.2)
pr5 = json.loads(subprocess.run([os.path.join(os.path.dirname(ff), "ffprobe.exe"), "-v", "error", "-count_frames", "-select_streams", "v",
    "-show_entries", "stream=codec_name,nb_read_frames", "-of", "json", a.video["path"]], capture_output=True, text=True).stdout)["streams"][0]
check(a.video["done"] and pr5["codec_name"] == "h264" and int(pr5["nb_read_frames"]) == 100, "x264 medium: video valido (%s)" % pr5)
a.s.update(video_codec="h264")
# film senza foro riconoscibile (immagini uniformi): messaggio chiaro
cart2 = os.path.join(tmp, "ctl", "senzaforo"); os.makedirs(cart2)
for i in range(1, 21):
    cv2.imwrite(os.path.join(cart2, "fotogramma_%06d.jpg" % i), (rng.random((540, 960, 3)) * 120 + 60).astype(np.uint8))
res = controllo.analizza(cart2)
check("errore" in res, "senza foro: nessuna analisi inventata (%s)" % res.get("errore", ""))

a.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("ERRORI:", check.fails)
sys.exit(1 if check.fails else 0)
