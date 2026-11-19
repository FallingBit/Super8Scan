# Super8Scan: cronologia delle versioni

Questa è la cronologia del **software per PC** (cartella `software/`). Il firmware dell'ESP32 ha una sua numerazione
(attualmente 2.27) con il changelog in testa a `firmware/Super8FilmScanner/Super8FilmScanner.ino`.

## 1.1.2 (19/11/2026)

### Novità
- **Formato del video scelto dai fori**: dopo l'analisi dei fotogrammi, se il foro è Normal8 la sezione *Video MP4* passa
  a Normal8 (16 fps); se è Super8 passa a Super8 (18 fps), a meno che fosse già scelto 18 o 24 fps. Un messaggio sotto il controllo lo
  segnala, e la scelta si può cambiare a mano.

## 1.1.1 (19/11/2026)

### Novità
- **Controllo dei fotogrammi con pellicola Normal8**: se non trova un foro Super8, il controllo cerca un foro Normal8
  (più lontano dal bordo, in qualunque punto dell'altezza, anche con due fori visibili nell'inquadratura). Il
  riconoscimento del foro Super8 non cambia. Provato su immagini del LEAD bianco di una pellicola Normal8.

## 1.1.0 (18/11/2026)

### Novità
- **Avviso di giuntura**: una bobina da 15 m ha circa 3600 fotogrammi e le bobine più grandi sono bobine piccole
  giuntate. Intorno a 3600, 7200, 10800… (da 200 fotogrammi prima a 200 dopo) l'anteprima ha una cornice gialla
  lampeggiante, compare «Giuntura in arrivo: tra circa N fotogrammi» e suona un segnale acustico (facoltativo).
  Si regolano fotogrammi per bobina e margine, e si può disattivare. Il conteggio usa il numero del fotogramma nella
  cartella, quindi vale anche quando la scansione riprende dopo uno stop.
- **Creazione del video**: durante la codifica compaiono la velocità (fotogrammi al secondo) e il tempo residuo
  stimato; a fine lavoro il messaggio indica anche quanto è durata la codifica.

## 1.0.0 (17/11/2026)

Prima versione, sviluppata e provata con lo scanner reale. Comprende tutto quanto segue.

### Acquisizione
- Salvataggio di un fotogramma a **ogni click sinistro del mouse** (simulato dallo scanner tramite l'optoisolatore),
  da una scheda di acquisizione HDMI → USB 4K, in JPG (qualità 85–100) o PNG. Lo scatto prende il primo fotogramma
  arrivato dopo una breve attesa regolabile, perché le schede tengono qualche immagine in coda.
- Il pulsante *Ferma* non conta come click. Scatto manuale con la barra spaziatrice.
- La numerazione (`fotogramma_000001.jpg`, …) prosegue se la cartella contiene già fotogrammi.
- **Log della lavorazione**: a ogni *Ferma* viene scritto un file `<film>-<ggmmaaaa>-<hhmm>.txt` nella cartella di
  lavoro, con nome del film, data e ora, durata e numero di fotogrammi acquisiti (utile per la fatturazione).
- Telecamera simulata (`--sim`) per le prove senza scheda; modalità `--browser` per lo sviluppo.

### Controllo dei fotogrammi
- Analisi della posizione, della forma e della nitidezza del **foro della pellicola** (a sinistra) in tutti i
  fotogrammi, per trovare quelli acquisiti con la pellicola in movimento.
- Riconoscimento del foro con più soglie e controlli di forma e posizione, così funziona anche con pellicole in cui il
  foro è poco evidente; avviso se i fotogrammi sospetti sono oltre il 10% (probabile foro riconosciuto male).
- Elenco dei sospetti con miniature e ingrandimento, soglia regolabile; scegli tu quali scartare. Gli scartati non si
  cancellano: nel video si possono saltare oppure sostituire con il fotogramma precedente.

### Creazione del video MP4 (con FFmpeg esterno, non incluso)
- Fotogrammi al secondo: Normal8 16, Super8 18, Super8 24 o valore libero (Custom); l'ultima scelta viene ricordata.
- Bitrate, risoluzione (originale, 4K, 2560, Full HD, HD), nome e cartella del file.
- Codec: x264 *slow* (qualità massima), x264 *medium* (più veloce), H.265, oppure la scheda NVIDIA (H.264 e H.265).
- **Ribaltamento verticale** (lo scanner riprende l'immagine capovolta) ed **esclusione dei fotogrammi bianchi finali**,
  entrambi attivi di default; i fotogrammi bianchi non vengono cancellati, solo saltati nel video.

### Altro
- Interfaccia in una finestra (pywebview) con anteprima in tempo reale; eseguibile Windows creato con `build.py`.
- Test automatici con telecamera simulata in `tests/`.
