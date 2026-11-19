# controllo.py
# Controllo dei fotogrammi acquisiti:
#  - riconoscimento dei fotogrammi bianchi (pellicola finita);
#  - ricerca dei fotogrammi "mossi" usando il foro della pellicola (a sinistra) come riferimento:
#    quando la pellicola è ferma e centrata il foro sta sempre nello stesso punto; se la pellicola scivola
#    il foro si sposta, si deforma o diventa una scia.
#
# Tutte le misure si fanno su immagini ridotte (1/4 o 1/8 in fase di lettura del JPG, quindi molto veloci).

import os
import re
import json
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor

NOME_FILE = "controllo_fotogrammi.json"
MODELLO_NOME = re.compile(r"fotogramma_(\d+)\.(jpg|png)")

# ----------------------------------------------------------------------------- lettura

_FLAG_GRIGIO = {2: cv2.IMREAD_REDUCED_GRAYSCALE_2, 4: cv2.IMREAD_REDUCED_GRAYSCALE_4, 8: cv2.IMREAD_REDUCED_GRAYSCALE_8}
_FLAG_COLORE = {2: cv2.IMREAD_REDUCED_COLOR_2, 4: cv2.IMREAD_REDUCED_COLOR_4, 8: cv2.IMREAD_REDUCED_COLOR_8}


def leggi(path, riduzione=4, colore=False):
    """Legge un fotogramma ridotto (nomi con accenti inclusi). None se illeggibile."""
    try:
        flag = (_FLAG_COLORE if colore else _FLAG_GRIGIO)[riduzione]
        return cv2.imdecode(np.fromfile(path, np.uint8), flag)
    except Exception:
        return None


def elenco_fotogrammi(cartella):
    """[(numero, nome file)] ordinati per numero."""
    out = []
    if os.path.isdir(cartella):
        for nome in os.listdir(cartella):
            m = MODELLO_NOME.fullmatch(nome)
            if m:
                out.append((int(m.group(1)), nome))
    out.sort()
    return out


# ----------------------------------------------------------------------------- fotogrammi bianchi

BIANCO_LUMINOSITA_MIN = 240   # media dei grigi (0-255) della zona centrale
BIANCO_DEVIAZIONE_MAX = 10    # deviazione standard: sotto questo valore l'immagine è uniforme


def e_bianco(im):
    """Un fotogramma è "bianco" (pellicola finita, solo luce della lampada) se la zona centrale è molto chiara
    e quasi uniforme. Si guarda solo il centro perché ai lati ci sono i bordi scuri e il foro."""
    if im is None:
        return False
    h, w = im.shape[:2]
    c = im[int(h * 0.2):int(h * 0.8), int(w * 0.25):int(w * 0.75)]
    return bool(c.mean() >= BIANCO_LUMINOSITA_MIN and c.std() <= BIANCO_DEVIAZIONE_MAX)


def fotogramma_bianco(path):
    return e_bianco(leggi(path, 8))


def bianchi_finali(cartella, nomi):
    """Quanti fotogrammi bianchi ci sono in fondo all'elenco (ordinato). Se sono tutti bianchi restituisce 0."""
    n = 0
    for nome in reversed(nomi):
        if fotogramma_bianco(os.path.join(cartella, nome)):
            n += 1
        else:
            break
    return 0 if n == len(nomi) else n


# ----------------------------------------------------------------------------- foro della pellicola

def _cerca_foro(med, H, Wr, largo):
    """Cerca il foro nell'immagine mediana "med" (alta H, la cui larghezza completa e Wr).
    largo=False: foro Super8, nella striscia di sinistra, alto circa un quarto del fotogramma e al centro.
    largo=True: foro Normal8, piu lontano dal bordo e in qualunque punto dell'altezza (nell'inquadratura se ne vedono
    anche due, uno sopra e uno sotto). Restituisce la zona come frazioni dell'immagine, oppure None."""
    otsu, _ = cv2.threshold(med, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    xmax = 0.45 if largo else 0.20
    centro_min, centro_max = (0.05, 0.95) if largo else (0.30, 0.70)
    # Si provano soglie via via piu alte: con certe pellicole il foro tocca il bordo chiaro dell'immagine e con la
    # soglia di Otsu i due si fondono; il foro e quasi bianco, quindi a una soglia piu alta si separa.
    for soglia in [otsu] + [t for t in (100, 130, 150, 170, 190, 210) if t > otsu]:
        n, _, st, _ = cv2.connectedComponentsWithStats((med > soglia).astype(np.uint8), 8)
        candidati = []
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in st[i])
            if y <= 1 or y + h >= H - 1:        # tocca il bordo alto o basso: non e un foro
                continue
            if x / Wr < 0.01 or (x + w) / Wr > xmax:   # il foro sta nella striscia di sinistra
                continue
            if area < 0.001 * H * Wr or not (0.5 <= h / max(w, 1) <= 8):
                continue
            if area < 0.6 * w * h:               # il foro e un rettangolo pieno
                continue
            if not (0.18 <= h / H <= 0.40) or not (centro_min <= (y + h / 2) / H <= centro_max):
                continue
            candidati.append((area if not largo else -abs((y + h / 2) / H - 0.5), area, x, y, w, h))
        if candidati:
            _, _, x, y, w, h = max(candidati)
            return {"x": x / Wr, "y": y / H, "w": w / Wr, "h": h / H}
    return None


def calibra(cartella, nomi, campioni=60, frazione=0.30):
    """Trova il foro: mediana di una sessantina di fotogrammi sparsi (il contenuto delle scene si cancella,
    il foro resta). Restituisce la zona del foro come frazioni dell'immagine, oppure None se non lo trova
    (per esempio se il foro tocca il bordo alto e basso, come in certe pellicole Normal8).
    Prima si cerca un foro Super8; se non c'e si cerca un foro Normal8 (vedi _cerca_foro)."""
    idx = np.linspace(0, len(nomi) - 1, min(campioni, len(nomi))).astype(int)
    strisce = []
    forma = None
    for i in idx:
        im = leggi(os.path.join(cartella, nomi[i]), 4)
        if im is None or e_bianco(im):
            continue
        forma = im.shape
        strisce.append(im[:, :int(im.shape[1] * 0.5)])
    if len(strisce) < 5:
        return None
    med = np.median(np.stack(strisce), axis=0).astype(np.uint8)
    H, Wr = forma
    roi = _cerca_foro(med[:, :int(Wr * frazione)], H, Wr, False)
    if roi is None:
        roi = _cerca_foro(med, H, Wr, True)
    return roi


def misura(im, roi):
    """Misure del foro in un fotogramma ridotto. Restituisce (alto, basso, centro, nitidezza, contrasto) con le
    posizioni in frazioni dell'altezza dell'immagine; alto = -1 se il foro non si riconosce."""
    H, W = im.shape
    x0, w = roi["x"] * W, roi["w"] * W
    y0, h = roi["y"] * H, roi["h"] * H
    ya, yb = int(max(0, y0 - 0.6 * h)), int(min(H, y0 + 1.6 * h))
    xa, xb = int(max(0, x0 + 0.17 * w)), int(min(W, x0 + 0.83 * w))
    if xb - xa < 2 or yb - ya < 8:
        return (-1.0, -1.0, -1.0, 0.0, 0.0)
    p = im[ya:yb, xa:xb].astype(np.float32).mean(axis=1)     # profilo verticale della luminosità
    basso_, alto_ = np.percentile(p, 10), np.percentile(p, 90)
    contrasto = float(alto_ - basso_)
    if contrasto < 8:
        return (-1.0, -1.0, -1.0, 0.0, contrasto)
    sopra = p > (basso_ + alto_) / 2
    # tratto chiaro più lungo
    migliore = (0, 0, 0)
    inizio = None
    for i, v in enumerate(list(sopra) + [False]):
        if v and inizio is None:
            inizio = i
        if not v and inizio is not None:
            if i - inizio > migliore[0]:
                migliore = (i - inizio, inizio, i)
            inizio = None
    _, a, b = migliore
    if b <= a:
        return (-1.0, -1.0, -1.0, 0.0, contrasto)
    d = np.abs(p[3:] - p[:-3])
    def bordo(y):
        s, e = max(0, y - 6), min(len(d), y + 6)
        return float(d[s:e].max()) if e > s else 0.0
    nitidezza = min(bordo(a), bordo(b)) / contrasto
    return ((ya + a) / H, (ya + b) / H, (ya + (a + b) / 2) / H, float(nitidezza), contrasto)


def _mediana_locale(v, valido, finestra=31):
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        a, b = max(0, i - finestra // 2), min(len(v), i + finestra // 2 + 1)
        seg = v[a:b][valido[a:b]]
        if len(seg) >= 5:
            out[i] = np.median(seg)
    return out


def valuta(feat, sposta=0.10, altezza=0.15, contrasto=0.15, nitidezza=0.35):
    """Decide quali fotogrammi sono sospetti. feat = lista di [numero, alto, basso, centro, nitidezza,
    contrasto, bianco]. Le soglie di spostamento e altezza sono frazioni dell'altezza del foro.
    Restituisce [{"n", "motivo", "valore"}] con motivo "sfocato", "deformato" oppure "spostato"."""
    if not feat:
        return []
    a = np.array(feat, dtype=float)
    n, alto, basso, centro, nit, con, bianco = (a[:, i] for i in range(7))
    altez = basso - alto
    valido = (alto >= 0) & (bianco == 0)
    if valido.sum() < 5:
        return []
    con_glob = np.median(con[valido])
    valido &= con >= contrasto * con_glob
    h0 = np.median(altez[valido])
    rc, rh, rn = _mediana_locale(centro, valido), _mediana_locale(altez, valido), _mediana_locale(nit, valido)
    sospetti = []
    for i in range(len(n)):
        if bianco[i]:
            continue
        num = int(n[i])
        if not valido[i]:
            sospetti.append({"n": num, "motivo": "sfocato", "valore": 0.0})
        elif not np.isnan(rn[i]) and nit[i] < nitidezza * rn[i]:
            sospetti.append({"n": num, "motivo": "sfocato", "valore": float(nit[i] / rn[i])})
        elif not np.isnan(rh[i]) and abs(altez[i] - rh[i]) > altezza * h0:
            sospetti.append({"n": num, "motivo": "deformato", "valore": float((altez[i] - rh[i]) / h0)})
        elif not np.isnan(rc[i]) and abs(centro[i] - rc[i]) > sposta * h0:
            sospetti.append({"n": num, "motivo": "spostato", "valore": float((centro[i] - rc[i]) / h0)})
    return sospetti


def analizza(cartella, progresso=None, lavoratori=6):
    """Analizza tutti i fotogrammi della cartella. Restituisce {"roi", "feat"} oppure {"errore": testo}.
    progresso(frazione) viene chiamata durante il lavoro."""
    elenco = elenco_fotogrammi(cartella)
    if len(elenco) < 10:
        return {"errore": "Servono almeno 10 fotogrammi per l'analisi."}
    nomi = [nome for _, nome in elenco]
    roi = calibra(cartella, nomi)
    if roi is None:
        return {"errore": "Il foro della pellicola non è stato riconosciuto nella zona a sinistra del fotogramma (succede, per esempio, con certe pellicole commerciali esposte oltre i bordi)."}

    def lavora(voce):
        num, nome = voce
        im = leggi(os.path.join(cartella, nome), 4)
        if im is None:
            return [num, -1, -1, -1, 0, 0, 0]
        if e_bianco(im):
            return [num, -1, -1, -1, 0, 0, 1]
        alto, basso, centro, nit, con = misura(im, roi)
        return [num, alto, basso, centro, nit, con, 0]

    feat = []
    with ThreadPoolExecutor(lavoratori) as pool:
        for k, r in enumerate(pool.map(lavora, elenco)):
            feat.append(r)
            if progresso and k % 20 == 0:
                progresso((k + 1) / len(elenco))
    if progresso:
        progresso(1.0)
    return {"roi": roi, "feat": feat}


# ----------------------------------------------------------------------------- file dei risultati

def percorso_file(cartella):
    return os.path.join(cartella, NOME_FILE)


def salva(cartella, dati):
    tmp = percorso_file(cartella) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f)
    os.replace(tmp, percorso_file(cartella))


def carica(cartella):
    try:
        with open(percorso_file(cartella), encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("versione") == 1 else None
    except Exception:
        return None


def miniatura(cartella, nome, tipo="intero"):
    """JPG piccolo da mostrare nell'elenco: "intero" (480 px), "grande" (960 px) o "foro" (striscia a sinistra)."""
    path = os.path.join(cartella, nome)
    if tipo == "grande":
        im = leggi(path, 4, colore=True)
    else:
        im = leggi(path, 8 if tipo == "intero" else 4, colore=True)
    if im is None:
        return b""
    if tipo == "foro":
        im = im[:, :int(im.shape[1] * 0.30)]
        im = cv2.resize(im, (int(im.shape[1] * 270 / im.shape[0]), 270))
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 72])
    return buf.tobytes() if ok else b""
