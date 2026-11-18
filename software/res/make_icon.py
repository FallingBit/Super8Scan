# Crea res/icona.ico (pellicola Super8 stilizzata) con OpenCV + struttura ICO a mano
import cv2, numpy as np, struct, os
S = 256
img = np.zeros((S, S, 4), np.uint8)
cv2.rectangle(img, (8, 8), (S - 9, S - 9), (30, 33, 39, 255), -1)
for y in range(20, S - 20, 44):
    for x in (18, S - 34):
        cv2.rectangle(img, (x, y), (x + 16, y + 24), (120, 126, 140, 255), -1)
cv2.rectangle(img, (62, 40), (S - 63, S - 41), (61, 163, 232, 255), -1)   # BGR del colore ambra
cv2.rectangle(img, (74, 54), (S - 75, S - 55), (21, 23, 27, 255), -1)
cv2.putText(img, "8", (88, 190), cv2.FONT_HERSHEY_DUPLEX, 5.2, (61, 163, 232, 255), 10)
ok, png = cv2.imencode(".png", img)
data = png.tobytes()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icona.ico")
with open(out, "wb") as f:
    f.write(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(data), 22) + data)
