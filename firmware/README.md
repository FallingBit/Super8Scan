# Firmware (ESP32)

Cartella `Super8FilmScanner/`: sketch Arduino per l'**ESP32-WROOM-32** che comanda il proiettore modificato
(versione **2.27**, vedi il changelog in testa a `Super8FilmScanner.ino`). Si compila con l'**Arduino IDE**.

## File dello sketch

| File | Contenuto |
|---|---|
| `Super8FilmScanner.ino` | pin, impostazioni, variabili di stato, `setup()` e `loop()` |
| `Manopola.ino` | lettura della manopola |
| `Scansione.ino` | scansione fotogramma per fotogramma |
| `Caricamento.ino` | caricamento della pellicola |
| `Lampada.ino` | lampada accesa per inquadrare e mettere a fuoco |
| `Riavvolgimento.ino` | marcia indietro di qualche fotogramma |
| `ClickMouse.ino` | pulsante che abilita/disabilita il click |
| `Display.ino` | schermate del display OLED |
| `LogoFallingBit.h`, `LogoSuper8.h` | immagini 128×32 mostrate all'accensione |

Il logo FallingBit è stato generato con `tools/make_logo.py` (OpenCV + NumPy) a partire da un PNG: si può rifare
con qualsiasi altra immagine.

## Compilazione

- Core **esp32** (Espressif) installato dal Gestore schede.
- Scheda usata: **AZDelivery ESP32-WROOM-32** (DevKit C, marca AZDelivery, modulo ESP32-WROOM-32). In Arduino IDE si seleziona **ESP32 Dev Module**
  (vale per le schede con il modulo ESP32-WROOM-32).
- Impostazioni della scheda: *Upload Speed* 921600 (se il caricamento dà errori prova 460800 o 115200),
  *Flash Size* 4MB (32Mb), *Partition Scheme* Default 4MB with spiffs, le altre opzioni predefinite.
- Se il caricamento si ferma su «Connecting…», tieni premuto il pulsante **BOOT** della scheda finché inizia il
  trasferimento. Usa un cavo USB che trasmette anche i dati.
- Librerie (Gestore librerie):
  - `Adafruit GFX Library`
  - `Adafruit SSD1306`
  - `MobaTools` (comanda lo stepper in background, con rampa di accelerazione); licenza LGPL-2.1
- Seriale a 115200 baud (non indispensabile).

## Manopola

La manopola originale del proiettore (5 contatti) è letta con `INPUT_PULLUP`. Posizioni riconosciute
(`Manopola.ino`):

| Posizione | Funzione | Motore | Lampada |
|---|---|---|---|
| Centrale (riposo) | **STOP** | fermo | spenta |
| Centrale, **manopola premuta** | **Caricamento pellicola**: il motore gira finché la tieni premuta | gira | spenta |
| 1 scatto a destra | **Lampada**: per inquadrare e mettere a fuoco la camera | fermo | accesa |
| 2 scatti a destra | **SCAN**: acquisizione fotogramma per fotogramma | gira | accesa |
| 1 scatto a sinistra | Lampada accesa (preparazione alla marcia indietro) | fermo | accesa |
| 2 scatti a sinistra | **Marcia indietro** (motore al contrario, a metà velocità): per tornare indietro di qualche fotogramma, non è un riavvolgimento veloce | gira | accesa |
| 3 scatti a sinistra | STOP | fermo | spenta |

Se all'accensione la manopola non è in posizione di riposo, il display mostra **ERROR** e il led MOTOR lampeggia
finché non la riporti al centro.

## Come funziona la scansione

1. Il motore gira. Sulla ruota dello shutter è incollato un **magnete** nel punto in cui il fotogramma è pronto.
2. Il **sensore Hall** (analogico, ingresso 34) lo rileva: la lettura scende sotto **1300**
   (e deve risalire sopra **1500** prima di poter scattare di nuovo, per evitare doppi scatti).
   Il sensore è lineare: circa 1,6 V (metà dei 3,3 V) senza magnete e circa 1,2 V vicino al magnete. Le soglie sono
   valori grezzi dell'ADC a 12 bit (0–4095): 1300 e 1500 corrispondono a circa 1,05 V e 1,2 V (calcolo teorico: l'ADC
   dell'ESP32 non è perfettamente lineare), quindi lo scatto avviene solo se il magnete si avvicina abbastanza.
3. Il firmware attende **60 ms** (`attesaStabilizzazioneMs`) perché pellicola e camera si stabilizzino.
4. Dà un impulso di **30 ms** all'optoisolatore collegato al tasto sinistro di un mouse: il PC "sente" un click
   e il programma Super8Scan salva il fotogramma.
5. Il motore non si ferma: la meccanica originale tiene fermo il fotogramma per circa un quarto di giro.

Protezioni durante la scansione:
- **Dopo uno stop**: se il magnete è già davanti al sensore, il fotogramma è stato acquisito prima dello stop e la
  scansione riparte **senza fare il click**, così non si salva un fotogramma doppio.
- **Sensore senza segnale**: se per 3 secondi il magnete non passa davanti al sensore (sensore scollegato o guasto,
  motore bloccato) il motore si ferma, il display mostra **NO HALL** e il led MOTOR lampeggia, finché la manopola
  non viene spostata da SCAN.
- **Manopola**: il motore si ferma solo se i contatti restano fuori posizione per almeno 30 ms, così una
  vibrazione non interrompe la scansione.

Mettendo la manopola in STOP si ferma tutto; riportandola in SCAN la scansione riprende dallo stesso punto,
anche il giorno dopo.

Un **pulsante** (ingresso 19) abilita/disabilita i click del mouse a ogni pressione, utile per le prove: con i click disabilitati
il led GRAB resta acceso fisso. Il pulsante si legge solo fuori dalla scansione (manopola a riposo o su lampada):
la scelta vale poi per la scansione successiva.

## Velocità del motore e ripartenza dopo uno stallo

Il motore gira a una frequenza di passi fissa (`passiAlSecondoScansione`), a 1/2 di passo. Il rapporto tra la puleggia del
motore e la meccanica è circa 1,36:1, quindi un giro del motore ogni 1,36 fotogrammi. Misure con un firmware di prova
(sensore HALL, pellicola in carico, 24 V, Vref 0,577 V cioè circa 0,4 A):

| Giri/s del motore | Passi/s | Fotogrammi/s | Esito |
|---|---|---|---|
| 5,0 (firmware 2.25) | 2000 | 3,7 | funziona |
| 6,5 | 2600 | 4,8 | funziona, usato dalla 2.27 |
| 7,0 | 2800 | 5,1 | regge 15 minuti ma si è fermato su una giuntura |
| 7,5 | 3000 | 5,5 | stallo dopo circa 30 s |
| 8,0 | 3200 | 5,9 | stallo dopo circa 3 s |

Il motore è un 17HS13-0404S (0,4 A per fase, 30 Ω, 37 mH): la corrente non riesce a salire in fretta e la coppia cala
con la velocità. Per questo non conviene salire oltre. Sulle giunture, più spesse, il motore può fermarsi: la 2.27 se ne
accorge (il magnete non passa per 1,5 s), lo ferma, aspetta 0,3 s e riparte piano a 3 giri/s, poi torna alla velocità
normale dopo 3 passaggi. Dopo 3 tentativi falliti compare NO HALL. Ogni ripartenza è scritta sulla seriale.

## Parametri da regolare (in `Super8FilmScanner.ino`)

| Costante | Valore | Significato |
|---|---|---|
| `passiAlSecondoScansione` | 2600 | velocità del motore in scansione, in passi al secondo (a 1/2 passo: 6,5 giri/s ≈ 4,8 fotogrammi/s). 7,0 giri/s regge con poco margine (si è fermato su una giuntura), 7,5 va in stallo |
| `rampaScansioneMs` | 1500 ms | durata dell'accelerazione all'avvio della scansione |
| `velocitaMax` | 6000 | velocità, in decimi di giro al minuto, di caricamento (e riavvolgimento, dimezzata) |
| `frazioneStabilizzazione` | 0,22 | attesa dopo il segnale Hall prima del click, come frazione del periodo tra due passaggi del magnete |
| `attesaStabilizzazioneMs` | 43 ms | la stessa attesa per il primo fotogramma, quando il periodo non è ancora noto |
| `sogliaHallScatto` / `sogliaHallRiarmo` | 1300 / 1500 | scatto / riarmo (dipendono da sensore e magnete) |
| `durataClickMs` | 30 ms | durata del "click" simulato |
| `antirimbalzoMs` | 50 ms | antirimbalzo della manopola |
| `antirimbalzoUscitaMs` | 30 ms | tempo in cui la manopola deve restare fuori posizione prima di fermare il motore |
| `timeoutStalloMs` | 1500 ms | tempo senza passaggi del magnete dopo il quale il firmware considera il motore fermo e prova a ripartire da solo |
| `tentativiRipartenza` | 3 | ripartenze consecutive prima di mostrare NO HALL (ogni ripartenza ha `timeoutRipartenzaMs` = 2000 ms, parte piano a `passiAlSecondoRipartenza` = 1200 passi/s e torna alla velocità normale dopo `passaggiRipartenza` = 3 passaggi) |
| `versoAvanti` | 1 | verso di rotazione del motore (1 o -1); cambia il segno se il motore gira al contrario |

Microstep: `MS1 = HIGH`, `MS2 = LOW` → **1/2 di passo** sul TMC2208.

## Collegamenti dell'ESP32

| GPIO | Funzione |
|---|---|
| 25 / 33 / 26 | STEP / DIR / ENABLE (attivo basso) del TMC2208 |
| 13 / 15 | MS1 / MS2 del TMC2208 (microstep) |
| 5, 17, 16, 4, 2 | contatti della manopola (con pull-up interne) |
| 19 | pulsante abilitazione click del mouse |
| 18 | optoisolatore → tasto sinistro del mouse |
| 23 | relé della lampada (pannello LED) |
| 34 | sensore Hall (ingresso analogico) |
| 27 / 14 / 12 | led MOTOR / LAMP / GRAB del pannello originale |
| I2C (SDA/SCL predefiniti ESP32) | display OLED SSD1306 128×32, indirizzo 0x3C |

Nota: alcuni di questi pin (2, 4, 5, 12, 15) sono *strapping pin* dell'ESP32 e influenzano l'avvio:
se cambi i collegamenti tienine conto.
