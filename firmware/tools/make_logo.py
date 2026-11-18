# Converte un logo PNG (bianco su sfondo trasparente) in una bitmap 128x32 per il display OLED SSD1306.
# Uso:  python make_logo.py logo.png LogoFallingBit.h NOME_COSTANTE
# Richiede opencv-python e numpy.
import sys
import cv2
import numpy as np

LARGHEZZA, ALTEZZA = 128, 32

def main(png, uscita, nome):
    img = cv2.imread(png, cv2.IMREAD_UNCHANGED)
    # Il logo è nel canale alfa (bianco su trasparente); se manca si usa la luminosità
    alfa = img[:, :, 3] if img.ndim == 3 and img.shape[2] == 4 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ys, xs = np.where(alfa > 40)
    logo = alfa[ys.min():ys.max() + 1, xs.min():xs.max() + 1]           # ritaglia i margini
    scala = min((LARGHEZZA - 4) / logo.shape[1], (ALTEZZA - 4) / logo.shape[0])
    logo = cv2.resize(logo, (round(logo.shape[1] * scala), round(logo.shape[0] * scala)), interpolation=cv2.INTER_AREA)
    tela = np.zeros((ALTEZZA, LARGHEZZA), np.uint8)
    y0, x0 = (ALTEZZA - logo.shape[0]) // 2, (LARGHEZZA - logo.shape[1]) // 2
    tela[y0:y0 + logo.shape[0], x0:x0 + logo.shape[1]] = logo
    bit = tela >= 110                                                   # 1 = pixel acceso
    righe = []
    for riga in bit:
        byte = [sum(int(riga[x * 8 + k]) << (7 - k) for k in range(8)) for x in range(LARGHEZZA // 8)]
        righe.append("  " + ", ".join("0x%02X" % b for b in byte) + ",")
    with open(uscita, "w", encoding="utf-8") as f:
        f.write("// Generato da tools/make_logo.py - bitmap %dx%d per display OLED SSD1306\n" % (LARGHEZZA, ALTEZZA))
        f.write("static const unsigned char PROGMEM %s[] = {\n%s\n};\n" % (nome, "\n".join(righe)))
    for riga in bit:                                                    # anteprima in testo
        print("".join("#" if p else "." for p in riga))

if __name__ == "__main__":
    main(*sys.argv[1:4])
