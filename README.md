# Super8Scan

Progetto completo di uno **scanner per pellicole Super8 e Normal8** fatto in casa, a cura di **FallingBit**:
hardware, firmware e software.

Un proiettore modificato fa avanzare la pellicola un fotogramma alla volta; quando l'immagine è ferma simula il click
di un mouse. Un programma per Windows salva a ogni click il fotogramma ripreso da una scheda di acquisizione HDMI/USB
in 4K, controlla la qualità dei fotogrammi e alla fine crea il video MP4.

![Il proiettore modificato](docs/foto/Silma%20bivox%20D%20LUX.webp)

## Il sistema

Un proiettore Super8/Normal8 **Silma Bivox "D" Lux** modificato è comandato da un **ESP32**. La lampada è sostituita
da un pannello LED a 4000 K e la camera (scheda di acquisizione HDMI/USB 4K) riprende direttamente nell'obiettivo,
senza telo, con tutto il fotogramma e il foro della pellicola. Il cuore del sistema:

- **Motore passo-passo** NEMA 17 con driver TMC2208, collegato alla meccanica originale del proiettore;
- **Sensore Hall** e un magnete sulla ruota dello shutter, per sapere quando il fotogramma è fermo;
- **Optoisolatore** (PC817) collegato al tasto sinistro di un mouse USB: l'ESP32 "fa click" al momento giusto;
- **Display OLED** e led del pannello originale per le informazioni;
- alimentazione a **24 V** (motore), 12 V (illuminazione) e 5 V (logica).

### Funzioni della manopola

Con la manopola originale del proiettore si scelgono le funzioni:

| Posizione della manopola | Funzione |
|---|---|
| **Centro (riposo)** | **STOP**: tutto fermo, lampada spenta |
| Centro, **manopola premuta** | **Caricamento della pellicola**: il motore gira finché la tieni premuta e fa avanzare la pellicola nella meccanica, senza lampada e senza click |
| **1 scatto a destra** | **Lampada accesa**, motore fermo: serve a posizionare la camera davanti all'obiettivo, inquadrare e mettere a fuoco |
| **2 scatti a destra** | **Scansione**: il motore gira, un sensore Hall rileva il fotogramma fermo e l'ESP32 simula il click di un mouse; Super8Scan salva il fotogramma a ogni click |
| **1 scatto a sinistra** | Lampada accesa, motore fermo (preparazione alla marcia indietro) |
| **2 scatti a sinistra** | **Marcia indietro**: il motore gira al contrario, a metà velocità, con la lampada accesa. Serve a tornare indietro di **qualche fotogramma**, per esempio per ripetere la scansione di un tratto |
| **3 scatti a sinistra** | STOP (lampada spenta) |

Non c'è il riavvolgimento veloce: per riavvolgere la bobina si completa la scansione, si fa uscire tutta la pellicola
dal proiettore e la si riavvolge a parte.

Fermando il proiettore si ferma anche l'acquisizione, che può essere ripresa dallo stesso punto anche il giorno dopo.
Prima di cominciare, il puntatore del mouse va posizionato sulla finestra di Super8Scan.

## Contenuto del repository

| Cartella | Contenuto | Stato |
|---|---|---|
| [`software/`](software) | **Super8Scan** per Windows (Python): acquisizione a ogni click, controllo dei fotogrammi, creazione MP4, log delle lavorazioni | 1.0.0 |
| [`firmware/`](firmware) | Firmware Arduino per l'ESP32: manopola, motore, lampada, click, display | v2.24 |
| [`hardware/`](hardware) | Descrizione del proiettore modificato, componenti, alimentazione, schema a blocchi; progetto KiCad, gerber del **PCB rev. 2.1** | rev. 2.1 |
| [`docs/`](docs) | Foto del prototipo e immagine del PCB | |

## Cosa serve

- **Un proiettore** Super8 (o Normal8) da modificare. Quello usato è un Silma Bivox "D" Lux, ma ogni proiettore con
  meccanica a griffa e shutter a ruota si può adattare. Vedi [`hardware/`](hardware) per l'elenco dei componenti e le
  modifiche.
- **Una scheda di acquisizione** USB con ingresso HDMI (4K UHD) e una camera con uscita HDMI.
- **Un PC con Windows** e Python per il software (vedi sotto).
- Per il firmware: Arduino IDE, una scheda ESP32 (WROOM-32) e le librerie indicate in [`firmware/`](firmware).

## Software Super8Scan

1. Collega la scheda di acquisizione e premi **Apri telecamera** (4K UHD, MJPG o YUY2).
2. Scegli cartella e nome del film, formato (JPG qualità 85–100, oppure PNG senza perdita) e l'attesa dopo il click.
3. **Avvia acquisizione**: ogni click sinistro del mouse, in qualsiasi punto dello schermo, salva un fotogramma
   (`fotogramma_000001.jpg`, ...). Il pulsante *Ferma* non conta. Se la cartella contiene già fotogrammi, la
   numerazione prosegue.
4. **Controllo dei fotogrammi**: il programma misura la posizione del **foro** della pellicola (a sinistra) in tutti i
   fotogrammi. Se è spostato, deformato o sfocato (scia), il fotogramma è sospetto: li vedi in un elenco con le
   miniature e decidi tu quali scartare. Gli scartati non si cancellano: nel video si possono saltare oppure
   sostituire con il fotogramma precedente. Funziona se il foro è ben visibile; con certe pellicole commerciali
   esposte oltre i bordi il foro non si distingue e il controllo non è disponibile.
5. **Crea video MP4**: scegli i fotogrammi/s (Normal8 16, Super8 18, Super8 24 oppure un valore a piacere con *Custom*; il
   programma ricorda l'ultimo usato), il bitrate, il codec (x264 *slow* per la massima qualità, x264 *medium* più veloce, H.265, oppure la scheda
   NVIDIA), la risoluzione, il nome e la cartella di destinazione.
   Due opzioni, attive di default: **ribalta l'immagine in verticale** (lo scanner la riprende capovolta) ed
   **escludi i fotogrammi bianchi in fondo** (la parte finale della scansione, quando la pellicola è finita e
   passa solo la luce). I fotogrammi bianchi non vengono cancellati dalla cartella: sono solo saltati nel video.

**Log della lavorazione**: a ogni *Ferma* il programma scrive nella cartella di lavoro un file di testo
`<film>-<ggmmaaaa>-<hhmm>.txt` (per esempio `1986-17112026-1810.txt`) con il nome del film, la data e l'ora, la
durata della scansione (da *Avvia* a *Ferma*) e il numero di fotogrammi acquisiti. Serve come storico delle lavorazioni.

Lo scatto non prende il fotogramma presente nel momento del click, ma il primo arrivato dopo una breve attesa
(regolabile): le schede di acquisizione tengono qualche immagine in coda.

### Installazione ed esecuzione

Nel repository ci sono **solo i sorgenti**: non vengono pubblicati programmi o firmware già compilati (vedi
[Licenza](#licenza)). Per usare il software lo si esegue o lo si compila dai sorgenti:

```
cd software
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe super8scan.py          # con la scheda di acquisizione
.venv\Scripts\python.exe super8scan.py --sim    # telecamera simulata, per provare senza scheda
.venv\Scripts\python.exe tests\test_super8scan.py
.venv\Scripts\python.exe build.py               # crea dist\Super8Scan.exe (per uso personale)
```

Il firmware si compila e si carica con Arduino IDE: vedi [`firmware/README.md`](firmware/README.md) per la scheda, le
impostazioni e le librerie.

### FFmpeg (necessario per creare il video)

FFmpeg **non è incluso**. Scaricalo (per esempio la build *essentials* di <https://www.gyan.dev/ffmpeg/builds/>)
e metti `ffmpeg.exe` nella stessa cartella di `Super8Scan.exe`. In alternativa il programma lo cerca nel `PATH`,
oppure puoi indicarlo con il link «indica…» in fondo al pannello.

## Un esempio di flusso di lavoro

Così lavora l'autore; è solo un'indicazione, ognuno può adattarla.

1. **Preparazione della pellicola**: pulirla e controllare le giunture, rifacendole se serve (l'autore usa una
   giuntatrice a nastro 3M 702, vedi la [foto](docs/README.md#giuntatrice)).
2. **LEAD bianco**: se manca, aggiungerlo all'inizio, così non si perde la parte iniziale della pellicola, che serve
   per il caricamento.
3. **Caricamento**: caricare la pellicola fino ai primi fotogrammi e solo allora accendere la lampada. Con pochi led
   il calore è trascurabile e non c'è rischio di bruciare la pellicola.
4. **Fotocamera**: obiettivo macro che permette di riempire il fotogramma e mettere a fuoco; tutto in manuale, niente
   automatismi. Il bilanciamento del bianco si fa **prima** di inserire la pellicola, con la lampada accesa e il suo
   diffusore: così si eliminano le dominanti di colore della luce e il bianco è corretto.
5. **Collegamenti**: avviare Super8Scan, collegare il cavetto USB del proiettore (simulazione del click) e il cavo
   USB 3 della scheda di acquisizione (con successo una Elgato Cam Link 4K, HDMI → USB).
6. **Acquisizione** dei fotogrammi.
7. **Controllo fotogrammi**: analisi e scarto di quelli danneggiati o fuori sincronismo.
8. **Video MP4** in 4K ad alto bitrate.
9. **Postproduzione** (facoltativa) in DaVinci Resolve: correzioni, musica o audio, poi esportazione per la consegna.
10. **Pellicole con pista sonora magnetica**: serve un secondo passaggio con un proiettore sonoro modificato per
    prelevare il segnale direttamente dalle testine audio, l'unico modo per recuperare il sonoro originale. La
    traccia si sistema poi in DaVinci Resolve sotto il video, in sincrono.

## Stato e cose da fare

- Il sistema funziona: scansione, controllo dei fotogrammi e creazione del video sono state provate su pellicole vere.
- Il firmware 2.25 (click doppio evitato dopo uno stop, errore NO HALL se manca il segnale del sensore, antirimbalzo
  della manopola, pulsante del click a rilevamento del fronte) è stato provato sul campo con pellicole vere: funziona.
- Il formato del foro per il **Normal8** non è ancora gestito nel controllo dei fotogrammi.
- Il sensore Hall usato non è identificato con certezza (vedi [`hardware/README.md`](hardware/README.md)): conta che
  abbia le caratteristiche indicate.

## Avvertenze ed esclusione di responsabilità

Super8Scan è un **progetto hobbistico**, nato per uso personale e condiviso così com'è, senza alcuna garanzia, per chi
fosse interessato a studiarlo o a costruirne uno simile. Non è un prodotto commerciale e non è certificato.

- **Nessuna garanzia sui risultati.** Chi riproduce il progetto, in tutto o in parte (hardware, firmware o software),
  può non ottenere i risultati descritti: dipende dal proiettore, dalla pellicola, dai componenti, dalla scheda di
  acquisizione e dal modo in cui il lavoro viene eseguito. Il progetto è stato provato soltanto sul prototipo
  dell'autore.
- **Rischi elettrici e meccanici.** Il progetto prevede modifiche a un proiettore e l'uso di un alimentatore
  alimentato dalla **tensione di rete (220 V)**, di parti in movimento. Chi lo
  riproduce lo fa **a proprio rischio** e sotto la propria responsabilità, e deve avere le competenze necessarie
  oppure farsi aiutare da una persona competente (vedi anche la sezione «Sicurezza» in
  [`hardware/README.md`](hardware/README.md)).
- **Pellicole e dati.** Le pellicole, soprattutto se vecchie o rare, possono rovinarsi durante il caricamento o la
  scansione; i file prodotti possono contenere errori. Conserva sempre gli originali e controlla i risultati.
- **Esclusione di responsabilità.** L'autore (FallingBit) **declina ogni responsabilità**, nei limiti consentiti dalla
  legge, per danni a persone, cose, apparecchi, pellicole o dati, e per qualunque insuccesso o risultato non
  soddisfacente derivante dalla costruzione o dall'uso di quanto pubblicato in questo repository. Il codice è
  distribuito alle condizioni della licenza MIT, che esclude ogni garanzia (vedi [LICENSE](LICENSE)).

## Licenza

Il codice è libero: puoi copiarlo, modificarlo e distribuirlo, **citando l'autore originale, FallingBit**
(licenza MIT, vedi [LICENSE](LICENSE)).

Le librerie di terze parti sono elencate in [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt). Alcune hanno licenze
non permissive (per esempio la libreria del firmware MobaTools, LGPL-2.1, e le librerie di OpenCV che includono
FFmpeg con licenza LGPL). Per questo il repository contiene **solo i sorgenti**, senza eseguibili né firmware già
compilati, e il progetto non è destinato alla vendita.
