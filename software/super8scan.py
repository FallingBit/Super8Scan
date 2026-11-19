# super8scan.py
# Acquisizione di fotogrammi Super8: ad ogni click sinistro del mouse salva un fotogramma
# preso dalla scheda di acquisizione, poi (a fine lavoro) crea il file MP4.
#
# Uso:
#   super8scan.py            apre la finestra dell'applicazione
#   super8scan.py --sim      come sopra ma con una telecamera simulata (prove senza scheda)
#   super8scan.py --browser  non apre la finestra: stampa l'indirizzo da aprire in un browser (sviluppo)

import sys
import os
import re
import json
import time
import queue
import secrets
import threading
import datetime
import subprocess
import ctypes
import ctypes.wintypes as wt
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import numpy as np
import cv2

import controllo
from controllo import fotogramma_bianco, bianchi_finali

APP_NAME = "Super8Scan"
VERSION = "1.1.3"
CREATE_NO_WINDOW = 0x08000000


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def settings_path():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "impostazioni.json")


DEFAULTS = {
    "device": 0,
    "backend": "dshow",          # dshow | msmf
    "resolution": "3840x2160",
    "fourcc": "MJPG",            # MJPG | YUY2 | auto
    "cam_fps": 30,
    "folder": os.path.join(os.path.expanduser("~"), "Videos", "Super8"),
    "project": "film1",
    "format": "jpg",             # jpg | png
    "jpg_quality": 98,
    "delay_ms": 120,             # attesa dopo il click prima di prendere il fotogramma
    "ffmpeg": "",
    "video_fps": 18,
    "video_fps_sel": "18",       # 16 (Normal8), 18 (Super8), 24 (Super8) oppure "custom"
    "video_codec": "h264",       # h264 | h265 | h264_nvenc | hevc_nvenc
    "video_mbps": 40,
    "video_scale": "orig",       # orig | 3840 | 2560 | 1920 | 1280
    "video_name": "",
    "video_folder": "",          # vuoto = cartella dei fotogrammi
    "video_flip_v": True,        # ribalta l'immagine in verticale (lo scanner la riprende capovolta)
    "video_trim_white": True,    # esclude dal video i fotogrammi bianchi in fondo alla scansione
    "video_scartati_modo": "salta",   # fotogrammi scartati dal controllo: "salta" oppure "ripeti" il precedente
    "controllo_sposta": 10,      # spostamento del foro (in % della sua altezza) oltre il quale il fotogramma e sospetto
    "giuntura_avviso": True,     # avvisa quando sta per arrivare la giuntura tra due bobine
    "giuntura_beep": True,       # segnale acustico quando si entra nella zona della giuntura
    "bobina_fotogrammi": 3600,   # fotogrammi di una bobina da 15 m (7,5 cm): le bobine grandi sono bobine piccole giuntate
    "giuntura_margine": 200,     # l'avviso va da (bobina - margine) a (bobina + margine), e si ripete a ogni bobina
}


def formatta_durata(sec):
    """Durata in forma leggibile: 45 s, 4 min 03 s, 1 h 05 min."""
    sec = max(0, int(round(sec)))
    if sec < 60:
        return "%d s" % sec
    if sec < 3600:
        return "%d min %02d s" % (sec // 60, sec % 60)
    return "%d h %02d min" % (sec // 3600, (sec % 3600) // 60)


def stima_codifica(campioni, totale):
    """Velocita (fotogrammi/s) e tempo residuo (s) della codifica, dagli ultimi campioni [(istante, fotogrammi), ...].
    Ritorna (None, None) finche i dati non bastano per una stima ragionevole."""
    if len(campioni) < 2:
        return None, None
    (t0, f0), (t1, f1) = campioni[0], campioni[-1]
    if t1 - t0 < 1.0 or f1 <= f0:
        return None, None
    fps = (f1 - f0) / (t1 - t0)
    return fps, max(0.0, (totale - f1) / fps)


def avviso_giuntura(n, bobina, margine):
    """Dice se il fotogramma n e vicino a una giuntura tra bobine da "bobina" fotogrammi.
    Ritorna None fuori dalle zone di avviso, altrimenti un dizionario con il fotogramma atteso della giuntura
    ("obiettivo") e i fotogrammi mancanti ("restano", negativo se e gia stato superato)."""
    bobina = max(100, int(bobina))
    margine = max(0, min(int(margine), bobina // 2 - 1))
    k = int(round(n / bobina))
    if k < 1 or abs(n - k * bobina) > margine:
        return None
    return {"obiettivo": k * bobina, "restano": k * bobina - n}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    # impostazioni di versioni precedenti: ricava la voce della frequenza dal valore salvato
    try:
        with open(settings_path(), encoding="utf-8") as f:
            salvate = json.load(f)
    except Exception:
        salvate = {}
    if "video_fps_sel" not in salvate:
        s["video_fps_sel"] = str(int(s["video_fps"])) if int(s["video_fps"]) in (16, 18, 24) else "custom"
    return s


def save_settings(s):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1, ensure_ascii=False)
    except Exception:
        pass


# --------------------------------------------------------------------------- FFmpeg

def find_ffmpeg(custom=""):
    cands = []
    if custom:
        cands.append(custom)
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    cands += [os.path.join(exe_dir, "ffmpeg.exe"), os.path.join(exe_dir, "ffmpeg", "bin", "ffmpeg.exe"),
              os.path.join(exe_dir, "ffmpeg", "ffmpeg.exe")]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cands.append(os.path.join(d.strip('"'), "ffmpeg.exe"))
    cands.append(r"D:\Programmazione\_strumenti\ffmpeg\bin\ffmpeg.exe")
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ""


def ffmpeg_encoders(ff):
    try:
        out = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True,
                             creationflags=CREATE_NO_WINDOW, timeout=20).stdout
    except Exception:
        return []
    return [e for e in ("libx264", "libx265", "h264_nvenc", "hevc_nvenc") if re.search(r"\b" + e + r"\b", out)]


def list_devices(ff):
    """Nomi delle periferiche video DirectShow (nello stesso ordine degli indici di OpenCV)."""
    names = []
    if ff:
        try:
            r = subprocess.run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               creationflags=CREATE_NO_WINDOW, timeout=20)
            txt = r.stderr
            tagged = re.findall(r'"([^"]+)"\s+\(video\)', txt)
            if tagged:
                names = tagged
            else:  # vecchio formato a sezioni
                sec = None
                for line in txt.splitlines():
                    if "DirectShow video devices" in line:
                        sec = "v"
                    elif "DirectShow audio devices" in line:
                        sec = "a"
                    elif sec == "v" and "Alternative name" not in line:
                        m = re.search(r'"([^"]+)"', line)
                        if m:
                            names.append(m.group(1))
        except Exception:
            pass
    return names


# --------------------------------------------------------------------------- Sorgente simulata

class SimCap:
    """Telecamera finta 4K per provare tutto senza la scheda di acquisizione."""

    def __init__(self, w=3840, h=2160, fps=30):
        self.w, self.h, self.fps = w, h, fps
        self.n = 0
        self.t0 = time.perf_counter()
        y = np.linspace(40, 200, h, dtype=np.uint8)[:, None]
        x = np.linspace(0, 255, w, dtype=np.uint8)[None, :]
        self.bg = np.dstack([np.broadcast_to(x, (h, w)), np.broadcast_to(y, (h, w)),
                             np.full((h, w), 90, np.uint8)]).copy()

    def isOpened(self):
        return True

    def set(self, *a):
        return True

    def get(self, prop):
        return {cv2.CAP_PROP_FRAME_WIDTH: self.w, cv2.CAP_PROP_FRAME_HEIGHT: self.h,
                cv2.CAP_PROP_FPS: self.fps}.get(prop, 0)

    def read(self):
        target = self.t0 + (self.n + 1) / self.fps
        wait = target - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        self.n += 1
        f = self.bg.copy()
        x = (self.n * 37) % (self.w - 300)
        cv2.rectangle(f, (x, 0), (x + 300, self.h), (255, 255, 255), -1)
        cv2.putText(f, "SIM %06d" % self.n, (200, 600), cv2.FONT_HERSHEY_SIMPLEX, 12, (0, 0, 0), 30)
        return True, f

    def release(self):
        pass


# --------------------------------------------------------------------------- Acquisizione continua

class Grabber:
    """Legge senza sosta la scheda e tiene l'ultimo fotogramma (con numero d'ordine e istante)."""

    def __init__(self):
        self.cap = None
        self.cond = threading.Condition()
        self.frame = None
        self.seq = 0
        self.t = 0.0
        self.running = False
        self.thread = None
        self.width = self.height = 0
        self.fps_real = 0.0
        self.error = ""
        self.preview_jpg = b""
        self.preview_seq = 0
        self._prev_thread = None

    def open(self, sim, index, backend, resolution, fourcc, fps):
        self.close()
        self.error = ""
        if sim:
            cap = SimCap()
        else:
            api = cv2.CAP_DSHOW if backend == "dshow" else cv2.CAP_MSMF
            cap = cv2.VideoCapture(int(index), api)
            if not cap.isOpened():
                cap.release()
                raise RuntimeError("Impossibile aprire la periferica video. È già usata da un altro programma?")
            if fourcc and fourcc != "auto":
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
            w, h = (int(v) for v in resolution.split("x"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            cap.set(cv2.CAP_PROP_FPS, int(fps))
        self.cap = cap
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.running = True
        self.frame = None
        self.seq = 0
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self._prev_thread = threading.Thread(target=self._preview_loop, daemon=True)
        self._prev_thread.start()
        # aspetta il primo fotogramma
        with self.cond:
            if not self.cond.wait_for(lambda: self.seq > 0, timeout=6):
                self.running = False
                msg = "La periferica non invia immagini."
                self.cap.release()
                self.cap = None
                raise RuntimeError(msg)
        self.width, self.height = self.frame.shape[1], self.frame.shape[0]

    def _loop(self):
        times = []
        misses = 0
        while self.running:
            ok, f = self.cap.read()
            now = time.perf_counter()
            if not ok or f is None:
                misses += 1
                if misses > 100:
                    self.error = "Il segnale video si è interrotto."
                    break
                time.sleep(0.01)
                continue
            misses = 0
            times.append(now)
            times = times[-30:]
            if len(times) > 5:
                self.fps_real = (len(times) - 1) / (times[-1] - times[0])
            with self.cond:
                self.frame = f
                self.seq += 1
                self.t = now
                self.cond.notify_all()
        self.running = False
        with self.cond:
            self.cond.notify_all()

    def _preview_loop(self):
        last = 0
        while self.running:
            time.sleep(0.08)
            with self.cond:
                f, s = self.frame, self.seq
            if f is None or s == last:
                continue
            last = s
            h, w = f.shape[:2]
            pw = 960
            small = cv2.resize(f, (pw, max(1, h * pw // w)), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 72])
            if ok:
                with self.cond:
                    self.preview_jpg = buf.tobytes()
                    self.preview_seq += 1
                    self.cond.notify_all()

    def wait_frame(self, t_min, seq_min, timeout=3.0):
        """Primo fotogramma arrivato dopo t_min e con numero >= seq_min."""
        end = time.perf_counter() + timeout
        with self.cond:
            while self.running:
                if self.seq >= seq_min and self.t >= t_min and self.frame is not None:
                    return self.frame, self.seq, self.t
                rest = end - time.perf_counter()
                if rest <= 0:
                    return None, 0, 0.0
                self.cond.wait(rest)
        return None, 0, 0.0

    def close(self):
        self.running = False
        for th in (self.thread, self._prev_thread):
            if th and th.is_alive():
                th.join(timeout=3)
        self.thread = self._prev_thread = None
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None
        self.frame = None
        self.preview_jpg = b""
        self.fps_real = 0.0


# --------------------------------------------------------------------------- Click globale del mouse

class MouseHook:
    """Hook di basso livello: vede ogni click sinistro, anche se la finestra non ha il focus."""
    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201

    def __init__(self, callback):
        self.callback = callback
        self.thread = None
        self.tid = 0
        self.hook = None
        self.ready = threading.Event()
        self._proc = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(3)

    def _run(self):
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
        u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
        u32.SetWindowsHookExW.restype = wt.HHOOK
        u32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
        u32.CallNextHookEx.restype = ctypes.c_ssize_t
        u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
        k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
        k32.GetModuleHandleW.restype = wt.HMODULE
        self.tid = k32.GetCurrentThreadId()

        def proc(n, wparam, lparam):
            if n >= 0 and wparam == self.WM_LBUTTONDOWN:
                try:
                    self.callback(time.perf_counter())
                except Exception:
                    pass
            return u32.CallNextHookEx(self.hook, n, wparam, lparam)

        self._proc = HOOKPROC(proc)
        self.hook = u32.SetWindowsHookExW(self.WH_MOUSE_LL, self._proc, k32.GetModuleHandleW(None), 0)
        self.ready.set()
        if not self.hook:
            return
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        u32.UnhookWindowsHookEx(self.hook)

    def stop(self):
        if self.tid:
            ctypes.windll.user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)  # WM_QUIT


# --------------------------------------------------------------------------- Logica dell'applicazione

class App:
    def __init__(self, sim=False):
        self.sim = sim
        self.s = load_settings()
        self.grab = Grabber()
        self.hook = MouseHook(self._on_click)
        self.lock = threading.Lock()
        self.armed = False
        self.ignore_zone = False       # il mouse è sopra il pulsante Stop: il click non conta
        self.cam_error = ""
        self.cam_name = ""
        self.out_dir = ""
        self.next_index = 1
        self.saved = 0
        self.failed = 0
        self.skipped = 0
        self.late = 0
        self.pending_writes = 0
        self.session_start = 0.0
        self.session_count = 0
        self.last_click_t = 0.0
        self.last_seq = 0
        self.last_thumb = b""
        self.last_lag_ms = 0
        self.jobs = queue.Queue()
        self.writers = ThreadPoolExecutor(max_workers=3)
        self.worker = None
        self.video = {"running": False, "progress": 0.0, "msg": "", "done": False, "error": "", "path": ""}
        self.video_proc = None
        self.controllo = {"running": False, "progress": 0.0, "error": ""}
        self.sessione_inizio = None      # datetime dell'avvio dell'acquisizione
        self.sessione_t0 = 0.0           # istante di avvio (monotonic)
        self.sessione_fotogrammi0 = 0    # fotogrammi gia presenti all'avvio
        self.last_log = ""              # ultimo log scritto
        self.controllo_extra = None
        self._ctl = None     # risultati del controllo fotogrammi della cartella attuale
        self._ctl_nuovo = False     # true dopo un'analisi appena finita: l'interfaccia puo preselezionare il formato
        self.window = None
        self.ffmpeg = find_ffmpeg(self.s.get("ffmpeg", ""))
        self.encoders = ffmpeg_encoders(self.ffmpeg) if self.ffmpeg else []
        self.devices = []
        self.hook.start()

    # ---- impostazioni
    def update_settings(self, d):
        for k, v in (d or {}).items():
            if k in DEFAULTS:
                self.s[k] = v
        save_settings(self.s)

    # ---- periferica
    def refresh_devices(self):
        self.devices = list_devices(self.ffmpeg)
        if not self.devices and not self.sim:
            self.devices = []
        return self.devices

    def open_camera(self):
        if self.armed:
            raise RuntimeError("Ferma prima l'acquisizione.")
        try:
            self.grab.open(self.sim, self.s["device"], self.s["backend"], self.s["resolution"],
                           self.s["fourcc"], self.s["cam_fps"])
            self.cam_error = ""
        except Exception as e:
            self.cam_error = str(e)
            raise
        names = self.devices
        i = int(self.s["device"])
        self.cam_name = "Telecamera simulata" if self.sim else (names[i] if i < len(names) else f"Periferica {i}")

    def close_camera(self):
        if self.armed:
            self.stop_capture()
        self.grab.close()

    # ---- acquisizione
    def _scan_folder(self, d):
        top = 0
        n = 0
        if os.path.isdir(d):
            for name in os.listdir(d):
                m = re.fullmatch(r"fotogramma_(\d+)\.(jpg|png)", name)
                if m:
                    n += 1
                    top = max(top, int(m.group(1)))
        return top, n

    def start_capture(self):
        if not self.grab.running:
            raise RuntimeError("Apri prima la telecamera.")
        if self.armed:
            return
        proj = re.sub(r'[\\/:*?"<>|]', "_", self.s["project"].strip()) or "film"
        d = os.path.join(self.s["folder"], proj)
        os.makedirs(d, exist_ok=True)
        top, n = self._scan_folder(d)
        self.out_dir = d
        self.next_index = top + 1
        self.saved = n
        self.failed = self.skipped = self.late = 0
        self.session_count = 0
        self.session_start = 0.0
        self.last_seq = self.grab.seq
        self.last_click_t = 0.0
        self.jobs = queue.Queue()
        self.sessione_inizio = datetime.datetime.now()
        self.sessione_t0 = time.monotonic()
        self.sessione_fotogrammi0 = n
        self.armed = True
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def stop_capture(self):
        if self.armed and self.sessione_inizio is not None:
            durata = time.monotonic() - self.sessione_t0
            inizio, self.sessione_inizio = self.sessione_inizio, None
        else:
            durata, inizio = 0.0, None
        self.armed = False
        self.jobs.put(None)
        if self.worker:
            self.worker.join(timeout=5)
        self.worker = None
        # aspetta che le scritture in corso finiscano
        end = time.time() + 30
        while self.pending_writes > 0 and time.time() < end:
            time.sleep(0.05)
        if inizio is not None:
            self._scrivi_log(inizio, durata)

    def _scrivi_log(self, inizio, durata):
        """Scrive il log della lavorazione nella cartella di lavoro: <film>-<ggmmaaaa>-<hhmm>.txt"""
        fotogrammi = self.saved - self.sessione_fotogrammi0
        if fotogrammi <= 0:
            return                      # nessun fotogramma acquisito: niente da registrare
        try:
            film = os.path.basename(self.out_dir)
            fine = inizio + datetime.timedelta(seconds=durata)
            ore, resto = divmod(int(round(durata)), 3600)
            minuti, secondi = divmod(resto, 60)
            righe = [
                "LOG DI LAVORAZIONE - Super8Scan %s" % VERSION,
                "",
                "Cartella di lavoro: %s" % os.path.basename(os.path.normpath(self.s["folder"])),
                "Film: %s" % film,
                "Data e ora di lavorazione: %s" % inizio.strftime("%d/%m/%Y %H:%M"),
                "Fine acquisizione: %s" % fine.strftime("%d/%m/%Y %H:%M"),
                "Durata della scansione: %d h %02d min %02d s" % (ore, minuti, secondi),
                "Fotogrammi acquisiti in questa lavorazione: %d" % fotogrammi,
                "Fotogrammi totali del film: %d" % self.saved,
                "Fotogrammi non salvati: %d" % self.failed,
                "Cartella dei fotogrammi: %s" % self.out_dir,
            ]
            base = "%s-%s" % (film, inizio.strftime("%d%m%Y-%H%M"))
            percorso = os.path.join(self.s["folder"], base + ".txt")
            k = 2
            while os.path.exists(percorso):
                percorso = os.path.join(self.s["folder"], "%s-%d.txt" % (base, k))
                k += 1
            with open(percorso, "w", encoding="utf-8-sig") as f:
                f.write("\r\n".join(righe) + "\r\n")
            self.last_log = percorso
        except Exception as e:
            self.last_log = ""
            self.cam_error = "Log non scritto: %s" % e

    def _on_click(self, t):
        """Chiamata dall'hook (o dal pulsante di prova): non deve mai bloccarsi."""
        if not self.armed or self.ignore_zone:
            return
        if t - self.last_click_t < 0.03:      # rimbalzo del contatto
            self.skipped += 1
            return
        self.last_click_t = t
        with self.lock:
            idx = self.next_index
            self.next_index += 1
        self.jobs.put((idx, t))

    def manual_capture(self):
        if self.armed:
            self._on_click(time.perf_counter())

    def _worker(self):
        delay = max(0, int(self.s["delay_ms"])) / 1000.0
        while True:
            job = self.jobs.get()
            if job is None:
                return
            idx, t_click = job
            frame, seq, tf = self.grab.wait_frame(t_click + delay, self.last_seq + 1)
            if frame is None:
                self.failed += 1
                continue
            self.last_seq = seq
            lag = tf - t_click
            self.last_lag_ms = int(lag * 1000)
            if lag > delay + 0.25:
                self.late += 1
            # limite di memoria: se la scrittura è troppo indietro aspetta
            while self.pending_writes > 24 and self.armed:
                time.sleep(0.01)
            with self.lock:
                self.pending_writes += 1
            if self.session_start == 0.0:
                self.session_start = time.perf_counter()
            self.session_count += 1
            self.writers.submit(self._write, idx, frame)

    def _write(self, idx, frame):
        try:
            fmt = self.s["format"]
            if fmt == "png":
                params = [cv2.IMWRITE_PNG_COMPRESSION, 1]
            else:
                params = [cv2.IMWRITE_JPEG_QUALITY, int(self.s["jpg_quality"])]
                try:
                    params += [cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444]
                except AttributeError:
                    pass
            ok, buf = cv2.imencode("." + fmt, frame, params)
            if not ok:
                raise RuntimeError("codifica fallita")
            name = "fotogramma_%06d.%s" % (idx, fmt)
            tmp = os.path.join(self.out_dir, name + ".tmp")
            with open(tmp, "wb") as f:
                f.write(buf)
            os.replace(tmp, os.path.join(self.out_dir, name))
            self.saved += 1
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (320, max(1, h * 320 // w)), interpolation=cv2.INTER_AREA)
            ok2, b2 = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok2:
                self.last_thumb = b2.tobytes()
        except Exception:
            self.failed += 1
        finally:
            with self.lock:
                self.pending_writes -= 1

    # ---- stato
    def state(self):
        fps = 0.0
        if self.session_count > 1 and self.armed:
            el = time.perf_counter() - self.session_start
            fps = self.session_count / el if el > 0 else 0
        return {
            "cam_open": self.grab.running,
            "cam_error": self.cam_error or self.grab.error,
            "cam_name": self.cam_name,
            "cam_w": self.grab.width, "cam_h": self.grab.height,
            "cam_fps": round(self.grab.fps_real, 1),
            "armed": self.armed,
            "saved": self.saved, "failed": self.failed, "skipped": self.skipped, "late": self.late,
            "pending": self.pending_writes, "queued": self.jobs.qsize(),
            "lag_ms": self.last_lag_ms, "avg_fps": round(fps, 2),
            "next_index": self.next_index,
            "out_dir": self.out_dir,
            "last_log": os.path.basename(self.last_log),
            "thumb_seq": self.saved,
            "video": self.video,
            "controllo": {"running": self.controllo["running"], "progress": self.controllo["progress"], "error": self.controllo["error"]},
            "giuntura": self._giuntura(),
        }

    def _giuntura(self):
        """Avviso di giuntura in arrivo (solo durante l'acquisizione)."""
        if not (self.armed and self.s.get("giuntura_avviso")):
            return None
        try:
            return avviso_giuntura(self.next_index - 1, self.s["bobina_fotogrammi"], self.s["giuntura_margine"])
        except (TypeError, ValueError):
            return None

    def info(self):
        return {
            "settings": self.s,
            "devices": self.devices,
            "ffmpeg": self.ffmpeg,
            "encoders": self.encoders,
            "sim": self.sim,
            "version": VERSION,
        }

    def set_ffmpeg(self, path):
        if path and os.path.isfile(path):
            self.s["ffmpeg"] = path
            save_settings(self.s)
        self.ffmpeg = find_ffmpeg(self.s.get("ffmpeg", ""))
        self.encoders = ffmpeg_encoders(self.ffmpeg) if self.ffmpeg else []
        return {"ffmpeg": self.ffmpeg, "encoders": self.encoders}

    # ---- cartelle e finestre di scelta
    def pick_folder(self, start=""):
        if self.window is None:
            raise RuntimeError("Scelta cartella disponibile solo nella finestra dell'applicazione.")
        import webview
        r = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=start or self.s["folder"])
        return r[0] if r else ""

    def pick_file(self, start=""):
        if self.window is None:
            raise RuntimeError("Scelta file disponibile solo nella finestra dell'applicazione.")
        import webview
        r = self.window.create_file_dialog(webview.OPEN_DIALOG, file_types=("Programma (*.exe)",))
        return r[0] if r else ""

    def open_folder(self, path):
        if path and os.path.isdir(path):
            os.startfile(path)

    def folder_info(self):
        proj = re.sub(r'[\\/:*?"<>|]', "_", self.s["project"].strip()) or "film"
        d = os.path.join(self.s["folder"], proj)
        top, n = self._scan_folder(d)
        tail = 0
        if n and self.s.get("video_trim_white"):
            nomi = sorted(f for f in os.listdir(d) if re.fullmatch(r"fotogramma_\d+\.(jpg|png)", f))
            tail = bianchi_finali(d, nomi)
        c = self._ctl_cartella() if n else None
        return {"dir": d, "frames": n, "last": top, "blank_tail": tail,
                "discarded": len(c["scartati"]) if c else 0}

    # ---- controllo dei fotogrammi (foro della pellicola)
    def _cartella_progetto(self):
        proj = re.sub(r'[\\/:*?"<>|]', "_", self.s["project"].strip()) or "film"
        return os.path.join(self.s["folder"], proj)

    def _ctl_cartella(self):
        """Risultati del controllo per il progetto attuale (dalla memoria o dal file); None se non ce ne sono."""
        d = self._cartella_progetto()
        if self._ctl is not None and self._ctl["dir"] == d:
            return self._ctl
        dati = controllo.carica(d)
        if not dati:
            return None
        self._ctl = {"dir": d, "roi": dati["roi"], "feat": dati["feat"], "sposta": dati.get("sposta", 10),
                     "scartati": set(dati.get("scartati", []))}
        self._ctl["sospetti"] = controllo.valuta(dati["feat"], sposta=self._ctl["sposta"] / 100.0)
        return self._ctl

    def _ctl_salva(self):
        c = self._ctl
        controllo.salva(c["dir"], {"versione": 1, "roi": c["roi"], "feat": c["feat"], "sposta": c["sposta"],
                                   "scartati": sorted(c["scartati"])})

    def controllo_avvia(self):
        if self.controllo["running"]:
            return
        if self.armed:
            raise RuntimeError("Ferma prima l'acquisizione.")
        d = self._cartella_progetto()
        if not os.path.isdir(d):
            raise RuntimeError("La cartella del film non esiste.")
        self.controllo.update(running=True, progress=0.0, error="")
        threading.Thread(target=self._controllo_job, args=(d,), daemon=True).start()

    def _controllo_job(self, d):
        try:
            r = controllo.analizza(d, progresso=lambda f: self.controllo.__setitem__("progress", f))
            if "errore" in r:
                self.controllo["error"] = r["errore"]
                return
            sposta = float(self.s["controllo_sposta"])
            sosp = controllo.valuta(r["feat"], sposta=sposta / 100.0)
            self._ctl = {"dir": d, "roi": r["roi"], "feat": r["feat"], "sposta": sposta,
                         "sospetti": sosp, "scartati": set(x["n"] for x in sosp)}
            self._ctl_salva()
            self._ctl_nuovo = True
        except Exception as e:
            self.controllo["error"] = str(e)
        finally:
            self.controllo["running"] = False

    def controllo_valuta(self, sposta):
        c = self._ctl_cartella()
        if not c:
            raise RuntimeError("Prima analizza i fotogrammi.")
        sposta = max(2.0, min(40.0, float(sposta)))
        self.s["controllo_sposta"] = sposta
        save_settings(self.s)
        vecchi = set(x["n"] for x in c["sospetti"])
        nuovi = controllo.valuta(c["feat"], sposta=sposta / 100.0)
        nn = set(x["n"] for x in nuovi)
        # le scelte gia fatte restano; i nuovi sospetti partono come "da scartare"
        c["scartati"] = (c["scartati"] & nn) | (nn - vecchi)
        c["sospetti"], c["sposta"] = nuovi, sposta
        self._ctl_salva()

    def controllo_scarta(self, numeri, valore):
        c = self._ctl_cartella()
        if not c:
            return
        for n in numeri:
            if valore:
                c["scartati"].add(int(n))
            else:
                c["scartati"].discard(int(n))
        self._ctl_salva()

    def controllo_stato(self):
        c = None if self.controllo["running"] else self._ctl_cartella()
        out = dict(self.controllo)
        out["pronto"] = bool(c)
        if c:
            out["sposta"] = c["sposta"]
            out["scartati"] = len(c["scartati"])
            out["sospetti"] = [dict(x, scartato=x["n"] in c["scartati"]) for x in c["sospetti"]]
            out["fotogrammi"] = len(c["feat"])
            out["formato"] = c["roi"].get("formato", "super8")     # riconosciuto dal foro: "super8" o "normal8"
            out["formato_nuovo"] = self._ctl_nuovo
            self._ctl_nuovo = False
        return out

    def miniatura(self, n, tipo):
        d = self._cartella_progetto()
        for num, nome in controllo.elenco_fotogrammi(d):
            if num == int(n):
                return controllo.miniatura(d, nome, tipo)
        return b""

    # ---- video
    def build_video(self):
        if self.video["running"]:
            return
        if not self.ffmpeg:
            raise RuntimeError("FFmpeg non trovato. Indica dove si trova ffmpeg.exe.")
        proj = re.sub(r'[\\/:*?"<>|]', "_", self.s["project"].strip()) or "film"
        d = os.path.join(self.s["folder"], proj)
        files = []
        if os.path.isdir(d):
            for name in os.listdir(d):
                m = re.fullmatch(r"fotogramma_(\d+)\.(jpg|png)", name)
                if m:
                    files.append((int(m.group(1)), name))
        if not files:
            raise RuntimeError("Nella cartella del progetto non ci sono fotogrammi.")
        files.sort()
        self.video = {"running": True, "progress": 0.0, "msg": "Preparazione…", "done": False, "error": "", "path": ""}
        threading.Thread(target=self._video_job, args=(d, [n for _, n in files]), daemon=True).start()

    def cancel_video(self):
        p = self.video_proc
        if p and p.poll() is None:
            p.kill()
            self.video["msg"] = "Annullato"

    def _video_job(self, d, names):
        s = self.s
        try:
            fps = float(int(s["video_fps"]))
            if fps <= 0:
                raise RuntimeError("Fotogrammi al secondo non validi.")
            out_name = (s.get("video_name") or "").strip() or (os.path.basename(d) + ".mp4")
            out_name = re.sub(r'[\\/:*?"<>|]', "_", out_name)
            if not out_name.lower().endswith(".mp4"):
                out_name += ".mp4"
            out_dir = (s.get("video_folder") or "").strip() or d
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, out_name)
            scartati = set()
            c = self._ctl_cartella()
            if c and c["dir"] == d:
                scartati = c["scartati"]
            n_scartati = 0
            if scartati:
                finali = []
                for nome in names:
                    num = int(re.search(r"(\d+)", nome).group(1))
                    if num in scartati:
                        n_scartati += 1
                        if s.get("video_scartati_modo") == "ripeti" and finali:
                            finali.append(finali[-1])
                        continue
                    finali.append(nome)
                names = finali
            lst = os.path.join(d, "_elenco_ffmpeg.txt")
            dur = "%.9f" % (1.0 / fps)
            esclusi = 0
            if s.get("video_trim_white"):
                self.video["msg"] = "Controllo dei fotogrammi bianchi…"
                esclusi = bianchi_finali(d, names)
                if esclusi:
                    names = names[:-esclusi]
            with open(lst, "w", encoding="utf-8") as f:
                for n in names:
                    p = os.path.join(d, n).replace("\\", "/").replace("'", "'\\''")
                    f.write("file '%s'\nduration %s\n" % (p, dur))
            codec = s["video_codec"]
            if codec not in ("h264", "h264_medium", "h265", "h264_nvenc", "hevc_nvenc"):
                codec = "h264"
            enc = {"h264": "libx264", "h264_medium": "libx264", "h265": "libx265"}.get(codec, codec)
            if enc not in self.encoders:
                raise RuntimeError("Il codificatore %s non è disponibile in questo FFmpeg." % enc)
            br = float(s["video_mbps"])
            args = [self.ffmpeg, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", lst]
            vf = []
            if s.get("video_flip_v"):
                vf.append("vflip")
            if s["video_scale"] != "orig":
                vf.append("scale=%d:-2:flags=lanczos" % int(s["video_scale"]))
            vf.append("format=yuv420p")
            args += ["-vf", ",".join(vf), "-r", "%g" % fps, "-fps_mode", "cfr", "-c:v", enc,
                     "-b:v", "%dk" % int(br * 1000), "-maxrate", "%dk" % int(br * 1000 * 1.5),
                     "-bufsize", "%dk" % int(br * 1000 * 2)]
            if enc == "libx264":
                args += ["-preset", "medium" if codec == "h264_medium" else "slow"]
            elif enc == "libx265":
                args += ["-preset", "medium", "-tag:v", "hvc1"]
            elif "nvenc" in enc:
                args += ["-preset", "p6", "-rc", "vbr", "-tag:v", "hvc1"] if enc == "hevc_nvenc" else \
                        ["-preset", "p6", "-rc", "vbr"]
            args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", out]
            total = len(names)
            self.video["msg"] = "Codifica di %d fotogrammi…" % total
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
            self.video_proc = p
            t_inizio = time.monotonic()
            campioni = []            # (istante, fotogrammi): finestra degli ultimi secondi per la stima
            err_lines = []
            threading.Thread(target=lambda: err_lines.extend(p.stderr.readlines()), daemon=True).start()
            for line in p.stdout:
                line = line.strip()
                if line.startswith("frame="):
                    try:
                        fr = int(line.split("=")[1])
                        self.video["progress"] = min(1.0, fr / total)
                        adesso = time.monotonic()
                        campioni.append((adesso, fr))
                        while len(campioni) > 2 and adesso - campioni[0][0] > 20:
                            campioni.pop(0)
                        fps_cod, residuo = stima_codifica(campioni, total)
                        msg = "Codifica: fotogramma %d di %d" % (fr, total)
                        if fps_cod:
                            msg += " · %s fotogrammi/s · tempo residuo circa %s" % (
                                ("%.1f" % fps_cod).replace(".", ","), formatta_durata(residuo))
                        self.video["msg"] = msg
                    except ValueError:
                        pass
            p.wait()
            try:
                os.remove(lst)
            except OSError:
                pass
            if p.returncode != 0:
                if self.video["msg"] == "Annullato":
                    self.video["error"] = "Annullato"
                    if os.path.exists(out):
                        os.remove(out)
                else:
                    self.video["error"] = "FFmpeg ha restituito un errore: " + "".join(err_lines[-6:]).strip()
            else:
                self.video["progress"] = 1.0
                self.video["done"] = True
                self.video["path"] = out
                self.video["msg"] = "Video creato (%.1f MB) in %s" % (os.path.getsize(out) / 1e6,
                                                                    formatta_durata(time.monotonic() - t_inizio))
                if esclusi:
                    self.video["msg"] += " · %d fotogrammi bianchi finali esclusi" % esclusi
                if n_scartati:
                    self.video["msg"] += " · %d fotogrammi scartati dal controllo" % n_scartati
        except Exception as e:
            self.video["error"] = str(e)
        finally:
            self.video["running"] = False
            self.video_proc = None

    def shutdown(self):
        try:
            self.close_camera()
        except Exception:
            pass
        self.hook.stop()


# --------------------------------------------------------------------------- Server locale (interfaccia + anteprima)

class Handler(BaseHTTPRequestHandler):
    app = None
    token = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _tok_ok(self, q=None):
        return self.headers.get("X-Token") == self.token or (q is not None and q.get("t") == self.token)

    def _query(self):
        q = {}
        if "?" in self.path:
            for kv in self.path.split("?", 1)[1].split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    q[k] = v
        return q

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        q = self._query()
        if path == "/":
            with open(resource_path("ui", "index.html"), encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", self.token)
            return self._send(200, html, "text/html; charset=utf-8")
        if not self._tok_ok(q):
            return self._send(403, "{}")
        g = self.app.grab
        if path == "/thumb":
            try:
                b = self.app.miniatura(q.get("n", "0"), q.get("k", "intero"))
            except Exception:
                b = b""
            return self._send(200 if b else 404, b or b"", "image/jpeg")
        if path == "/last.jpg":
            b = self.app.last_thumb
            return self._send(200 if b else 404, b or b"", "image/jpeg")
        if path == "/preview":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            last = -1
            try:
                while True:
                    with g.cond:
                        g.cond.wait_for(lambda: g.preview_seq != last or not g.running, timeout=1.0)
                        if not g.running:
                            break
                        b, last = g.preview_jpg, g.preview_seq
                    if not b:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(b))
                    self.wfile.write(b + b"\r\n")
                    self.wfile.flush()
            except (ConnectionError, OSError):
                pass
            self.close_connection = True
            return
        self._send(404, "{}")

    def do_POST(self):
        if not self._tok_ok():
            return self._send(403, "{}")
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            data = {}
        name = self.path.split("?")[0].rsplit("/", 1)[-1]
        a = self.app
        try:
            if name == "info":
                res = a.info()
            elif name == "state":
                res = a.state()
            elif name == "settings":
                a.update_settings(data)
                res = {}
            elif name == "devices":
                res = a.refresh_devices()
            elif name == "open_camera":
                a.update_settings(data)
                a.open_camera()
                res = {}
            elif name == "close_camera":
                a.close_camera()
                res = {}
            elif name == "start":
                a.update_settings(data)
                a.start_capture()
                res = {}
            elif name == "stop":
                a.stop_capture()
                res = {}
            elif name == "ignore":
                a.ignore_zone = bool(data.get("v"))
                res = {}
            elif name == "manual":
                a.manual_capture()
                res = {}
            elif name == "pick_folder":
                res = a.pick_folder(data.get("start", ""))
            elif name == "pick_file":
                res = a.pick_file()
            elif name == "set_ffmpeg":
                res = a.set_ffmpeg(data.get("path", ""))
            elif name == "open_folder":
                a.open_folder(data.get("path", ""))
                res = {}
            elif name == "folder_info":
                a.update_settings(data)
                res = a.folder_info()
            elif name == "controllo_avvia":
                a.update_settings(data)
                a.controllo_avvia()
                res = {}
            elif name == "controllo_stato":
                res = a.controllo_stato()
            elif name == "controllo_valuta":
                a.controllo_valuta(data.get("sposta", 10))
                res = a.controllo_stato()
            elif name == "controllo_scarta":
                a.controllo_scarta(data.get("numeri", []), bool(data.get("valore")))
                res = {}
            elif name == "build_video":
                a.update_settings(data)
                a.build_video()
                res = {}
            elif name == "cancel_video":
                a.cancel_video()
                res = {}
            else:
                return self._send(404, "{}")
            self._send(200, json.dumps({"ok": True, "data": res}))
        except Exception as e:
            self._send(200, json.dumps({"ok": False, "error": str(e)}))


def start_server(app, port=0):
    Handler.app = app
    Handler.token = secrets.token_urlsafe(16)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, Handler.token


def main():
    sim = "--sim" in sys.argv
    browser = "--browser" in sys.argv
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass
    app = App(sim=sim)
    srv, token = start_server(app, 8791 if browser else 0)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    if browser:
        print(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        import webview
        icon = resource_path("res", "icona.ico")
        win = webview.create_window("Super8Scan", url, width=1280, height=820, min_size=(1000, 700))
        app.window = win
        webview.start(icon=icon if os.path.isfile(icon) else None)
    app.shutdown()


if __name__ == "__main__":
    main()
