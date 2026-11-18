/*--------------------------------------------------
  ---------- FallingBit Super8 FilmScanner ---------
  --------------------------------------------------*/

// Scanner per pellicole Super8 / Normal8 basato su un proiettore Silma Bivox "D" Lux,
// comandato da un ESP32 con motore passo-passo NEMA 17 e driver TMC2208.
//
//  - la posizione del fotogramma è rilevata da un sensore HALL (magnete sulla ruota dello shutter);
//  - quando il fotogramma è fermo l'ESP32 simula il click sinistro di un mouse (tramite optoisolatore),
//    e il programma Super8Scan sul PC salva il fotogramma;
//  - un display OLED e tre led (quelli originali del proiettore) mostrano lo stato.
//
// Organizzazione dei file (Arduino IDE li unisce in ordine alfabetico dopo questo):
//   Super8FilmScanner.ino  questo file: pin, impostazioni, variabili, setup() e loop()
//   Caricamento.ino        caricamento della pellicola (manopola premuta)
//   ClickMouse.ino         pulsante che abilita/disabilita il click del mouse
//   Display.ino            tutte le schermate del display OLED
//   Lampada.ino            lampada accesa per inquadrare e mettere a fuoco
//   Manopola.ino           lettura della manopola dei comandi
//   Riavvolgimento.ino     riavvolgimento (motore al contrario)
//   Scansione.ino          scansione del film fotogramma per fotogramma
//   LogoFallingBit.h, LogoSuper8.h   immagini mostrate all'accensione
//
//--------------------------------------------------- CHANGELOG ---------------------------------------------------------
//
// Versione 2.27
// - Se il motore si ferma durante la scansione (successo su una giuntura a 7 giri/s) il firmware riparte da solo:
//   ferma il motore, aspetta un attimo, riparte piano per qualche giro e poi torna alla velocità normale. Dopo
//   3 tentativi falliti compare NO HALL come prima
// - Velocità di scansione ridotta a 6,5 giri/s (circa 4,8 fotogrammi/s) per avere più margine di coppia
//
// Versione 2.26
// - Scansione più veloce: motore a 7 giri/s (prima 5), cioè circa 5,1 fotogrammi/s invece di 3,7. Velocità scelta con il
//   firmware di prova: 7,0 giri/s ha retto 15 minuti, 7,5 giri/s va in stallo
// - Rampa di accelerazione di 1,5 s all'avvio della scansione (evita gli stalli in partenza)
// - L'attesa prima del click è proporzionale al tempo tra due passaggi del magnete (22 %): a velocità diverse il click
//   cade nella stessa fase del giro
// - Costanti passiAlSecondoScansione, rampaScansioneMs e frazioneStabilizzazione per regolare velocità e attesa
//
// Versione 2.25
// - Dopo uno stop la scansione non fa il click se il magnete è già davanti al sensore (evita il fotogramma doppio)
// - Se il sensore HALL non dà segnale per 3 secondi il motore si ferma e il display mostra NO HALL
// - Uscita dalla scansione, dal caricamento e dalla marcia indietro con antirimbalzo (30 ms): una vibrazione
//   dei contatti della manopola non ferma più il motore
// - Il pulsante del click agisce una sola volta a ogni pressione (prima, tenuto premuto, commutava di continuo)
// - L'impulso di click si spegne una sola volta
//
// Versione 2.24
// - Costante versoAvanti per invertire il verso del motore senza cambiare i collegamenti
//   (il valore 1 è l'opposto di quello usato fino alla 2.23, che era -1)
//
// Versione 2.23
// - Logo FallingBit
// - Codice commentato, nomi di variabili e funzioni più chiari, file rinominati (nessuna modifica di funzionamento)
//
// Versione 2.22
// - Ottimizzazione generale
//
// Versione 2.21
// - Ritardo prima di fare click (per stabilizzare la pellicola e la camera)
// - Fix antibump pulsante MOUSE
// - Aumentata velocitá motore
// - Bug fix
// - Aggiunte statistiche tempo
//
// Versione 2.20
// - Bug fix
//
// Versione 2.19
// - Aggiunto pulsante abilitazione/disabilitazione CLICK MOUSE
// - Segnalazione CLICK MOUSE tramite led GRAB
// - Disattivate statistiche in fase di SCAN per aumentare velocitá. Verranno mostrate sulla pagina principale
// - Bug fix
//
// Versione 2.18
// - Aggiunta informazioni display SCAN
// - Bug fix
// - Ottimizzazione generale
// - Riscritta routine ERROR
//
// Versione 2.17
// - Bug fix
//
// Versione 2.16
// - Passaggio a libreria MobaTools (per ottimizzare la scansione e la velocitá). Il motore viene comandato in background
// - Ripristino funzionalitá display (contatore frames)
// - Ottimizzazione generale del codice
//
// Versione 2.15
// - Ottimizzazione routine SCAN - miglioramento nella velocitá di acquisizione
//
// Versione 2.14
// - Bugfix
//
// Versione 2.13
// - Pulizia e ottimizzazione codice
// - Statistiche scansione
//
// Versione 2.00
// - Sostituito Arduino NANO con ESP32 WROOM
// - Sostituito modulo controller stepper con TMC2208
// - Riscritta completamente la parte di controllo motore stepper
//
//-------------------------------------------------------------------------------------------------------------------------

#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <MobaTools.h>

#include "LogoFallingBit.h"
#include "LogoSuper8.h"


String versioneFirmware = "v2.27";  // mostrata sul display


// ============================================================================
//  DISPLAY OLED (SSD1306, collegato all'I2C predefinito dell'ESP32)
// ============================================================================
const int LARGHEZZA_DISPLAY = 128;  // pixel
const int ALTEZZA_DISPLAY = 32;     // pixel
#define RESET_DISPLAY -1            // -1 = il display non ha un pin di reset dedicato
#define INDIRIZZO_DISPLAY 0x3C      // indirizzo I2C (0x3C per i 128x32, 0x3D per alcuni 128x64)
Adafruit_SSD1306 display(LARGHEZZA_DISPLAY, ALTEZZA_DISPLAY, &Wire, RESET_DISPLAY);

#define LOGO_ALTEZZA 32  // dimensioni delle immagini in LogoFallingBit.h e LogoSuper8.h
#define LOGO_LARGHEZZA 128

#if (SSD1306_LCDHEIGHT != 32)
#error("Height incorrect, please fix Adafruit_SSD1306.h!");
#endif


// ============================================================================
//  MOTORE PASSO-PASSO con driver TMC2208
// ============================================================================
const int pinMotoreDirezione = 33;  // DIR: verso di rotazione
const int pinMotoreStep = 25;       // STEP: un impulso = un passo
const int pinMotoreAbilita = 26;    // EN: LOW = motore alimentato, HIGH = motore libero

// MS1 / MS2 del TMC2208 scelgono i microstep. Con MS1=HIGH e MS2=LOW il driver lavora a 1/2 di passo.
const int pinMicrostepMS1 = 13;
const int pinMicrostepMS2 = 15;

const int passiPerGiro = 200;  // passi interi per giro del motore NEMA 17

// Velocità in decimi di giro al minuto (unità di MobaTools::setSpeed). 6000 è il massimo usato.
const int velocitaMax = 6000;

MoToStepper motore(passiPerGiro, STEPDIR);  // il motore viene comandato in background da MobaTools

// Verso di rotazione del motore in caricamento e scansione: 1 oppure -1 (la marcia indietro usa il verso opposto).
// Se il motore gira al contrario del previsto, cambia il segno qui, senza toccare i fili.
const int versoAvanti = 1;

// Velocità della SCANSIONE: frequenza degli impulsi STEP. A 1/2 di passo (400 passi per giro) 2600 passi/s sono
// 6,5 giri/s del motore (circa 4,8 fotogrammi/s). Misure con il firmware di prova: 7,0 giri/s regge ma con poco
// margine (si è fermato su una giuntura), 7,5 va in stallo.
const long passiAlSecondoScansione = 2600;
const long rampaScansioneMs = 1500;  // durata dell'accelerazione all'avvio

// Attesa tra il segnale del sensore HALL e il click: lascia stabilizzare pellicola e camera. È una frazione del
// tempo trascorso tra gli ultimi due passaggi del magnete (60 ms su 272 ms = 0,22), così a ogni velocità il click
// cade nella stessa fase del giro. Per il primo fotogramma si usa attesaStabilizzazioneMs.
const float frazioneStabilizzazione = 0.22;
const int attesaStabilizzazioneMs = 43;


// ============================================================================
//  MANOPOLA DEI COMANDI (5 contatti, letti con pull-up interne: contatto chiuso = LOW)
// ============================================================================
const int pinManopola1 = 5;
const int pinManopola2 = 17;
const int pinManopola3 = 16;
const int pinManopola4 = 4;
const int pinManopola5 = 2;

// Combinazioni dei 5 contatti (bit 4 = pinManopola1 ... bit 0 = pinManopola5) per ogni posizione.
const int CODICE_RIPOSO = 0b10101;             // centro
const int CODICE_PREMUTA = 0b10100;            // centro, manopola premuta
const int CODICE_LAMPADA = 0b11111;            // 1 scatto a destra
const int CODICE_SCAN = 0b11011;               // 2 scatti a destra
const int CODICE_STOP_SINISTRA = 0b01101;      // 3 scatti a sinistra
const int CODICE_LAMPADA_RIAVVOLGI = 0b00101;  // 1 scatto a sinistra
const int CODICE_RIAVVOLGIMENTO = 0b00001;     // 2 scatti a sinistra

// Funzioni associate alle posizioni, usate in posizioneManopola
const int MANOPOLA_RIPOSO = 0;              // tutto fermo
const int MANOPOLA_CARICAMENTO = 1;         // manopola premuta: carica la pellicola
const int MANOPOLA_LAMPADA = 2;             // lampada accesa per inquadrare e mettere a fuoco
const int MANOPOLA_SCAN = 3;                // scansione del film
const int MANOPOLA_STOP_SINISTRA = 4;       // stop (3 scatti a sinistra)
const int MANOPOLA_LAMPADA_RIAVVOLGI = 5;   // lampada accesa (1 scatto a sinistra)
const int MANOPOLA_RIAVVOLGIMENTO = 6;      // riavvolgimento

const int antirimbalzoMs = 50;  // attesa per scartare i rimbalzi dei contatti della manopola
const int antirimbalzoUscitaMs = 30;  // la manopola deve restare fuori posizione per questo tempo prima di fermare il motore


// ============================================================================
//  LED, LAMPADA, MOUSE
// ============================================================================
const int pinLedMotore = 27;      // led in alto (rosso): motore in funzione
const int pinLedLampada = 14;     // led centrale (giallo/verde): lampada accesa
const int pinLedScatto = 12;      // led in basso (azzurro): click del mouse ("GRAB")
const int pinReleLampada = 23;    // relé che alimenta il pannello LED
const int pinClickMouse = 18;     // optoisolatore collegato al tasto sinistro del mouse
const int pinPulsanteClick = 19;  // pulsante che abilita/disabilita il click durante la scansione

bool clickMouseAbilitato = true;  // se false la scansione muove la pellicola ma non fa click
bool pulsanteClickPremuto = false;  // true mentre il pulsante è tenuto premuto (il click si commuta una volta sola)

const int durataClickMs = 30;  // durata dell'impulso che simula il click


// ============================================================================
//  SENSORE HALL
// ============================================================================
const int pinSensoreHall = 34;  // ingresso analogico (ADC1)

// Il magnete sulla ruota dello shutter fa SCENDERE la lettura. Si usano due soglie diverse (isteresi):
// il click parte sotto la soglia di scatto, e si può scattare di nuovo solo dopo che la lettura
// è risalita sopra la soglia di riarmo.
const int sogliaHallScatto = 1300;
const int sogliaHallRiarmo = 1500;

// Se durante la scansione il magnete non passa davanti al sensore per timeoutStalloMs, il motore si è fermato
// (per esempio su una giuntura) oppure il sensore non funziona. Il firmware prova a ripartire: ferma il motore,
// aspetta pausaRipartenzaMs e riparte piano (passiAlSecondoRipartenza). Dopo passaggiRipartenza passaggi del magnete
// torna alla velocità normale. Se entro timeoutRipartenzaMs il magnete non passa, ritenta, fino a tentativiRipartenza
// volte; poi il motore si ferma e il display mostra NO HALL (sensore scollegato o guasto, o motore bloccato).
const unsigned long timeoutStalloMs = 1500;  // più dei 0,7 s che servono al primo passaggio durante la rampa di avvio
const unsigned long timeoutRipartenzaMs = 2000;
const unsigned long pausaRipartenzaMs = 300;
const int tentativiRipartenza = 3;
const long passiAlSecondoRipartenza = 1200;  // 3 giri/s
const long rampaRipartenzaMs = 500;
const int passaggiRipartenza = 3;


// ============================================================================
//  VARIABILI DI STATO
// ============================================================================
int posizioneManopola = MANOPOLA_RIPOSO;  // posizione attuale della manopola (vedi MANOPOLA_...)
int lampadaAccesa = 0;                    // 1 = lampada accesa
int controlloAvvio = 1;                   // 1 finché, dopo l'accensione, la manopola non è tornata a riposo

// Contatori dei fotogrammi
long int fotogrammiUltimaScansione = 0;  // fotogrammi dell'ultima scansione
long int fotogrammiTotali = 0;           // fotogrammi di tutte le scansioni da quando è acceso

// Durate in millisecondi
unsigned long inizioScansioneMs = 0;
unsigned long durataUltimaScansioneMs = 0;
unsigned long durataTotaleScansioniMs = 0;

// Rotazione delle pagine informative del display (vedi aggiornaPagineInformative)
const int PAGINA_BASE_PRONTO = 0;   // pagina base "READY"
const int PAGINA_BASE_LAMPADA = 1;  // pagina base "LAMP"
unsigned long istantePagina = 0;    // istante dell'ultimo cambio pagina
int prossimaPagina = 0;             // 0 = pagina base, 1 = contatori, 2 = tempi
const int durataPaginaMs = 3000;    // ogni quanto cambia pagina

String intestazioneDisplay = " Super 8 FilmScanner ";  // prima riga del display (testo invertito)
String testoGrande = "";                                // testo in corpo 2 mostrato da displayTestoGrande()


// *********************************** SETUP ***************************************
void setup() {

  Serial.begin(115200);

  delay(500);  // aspetto che si stabilizzi l'alimentazione per proseguire

  // Uscite
  pinMode(pinLedMotore, OUTPUT);
  pinMode(pinLedLampada, OUTPUT);
  pinMode(pinLedScatto, OUTPUT);
  pinMode(pinReleLampada, OUTPUT);
  pinMode(pinMotoreAbilita, OUTPUT);
  pinMode(pinMotoreDirezione, OUTPUT);
  pinMode(pinMotoreStep, OUTPUT);
  pinMode(pinClickMouse, OUTPUT);
  pinMode(pinMicrostepMS1, OUTPUT);
  pinMode(pinMicrostepMS2, OUTPUT);

  // Ingressi (pull-up interne: il contatto chiuso porta il pin a LOW)
  pinMode(pinManopola1, INPUT_PULLUP);
  pinMode(pinManopola2, INPUT_PULLUP);
  pinMode(pinManopola3, INPUT_PULLUP);
  pinMode(pinManopola4, INPUT_PULLUP);
  pinMode(pinManopola5, INPUT_PULLUP);
  pinMode(pinPulsanteClick, INPUT_PULLUP);

  // Microstep del TMC2208: MS1=HIGH, MS2=LOW -> 1/2 di passo
  digitalWrite(pinMicrostepMS1, HIGH);
  digitalWrite(pinMicrostepMS2, LOW);

  // Stato iniziale: tutto spento
  digitalWrite(pinLedMotore, LOW);
  digitalWrite(pinLedLampada, LOW);
  digitalWrite(pinLedScatto, LOW);
  digitalWrite(pinReleLampada, LOW);     // lampada spenta
  digitalWrite(pinMotoreAbilita, HIGH);  // motore libero
  digitalWrite(pinClickMouse, LOW);      // nessun click

  motore.attach(pinMotoreStep, pinMotoreDirezione);

  digitalWrite(pinLedScatto, HIGH);  // accendo il led GRAB per indicare che tutto funziona

  delay(1500);                       // aspetto che si stabilizzi l'alimentazione per avviare il display
  digitalWrite(pinLedScatto, LOW);   // spengo il led e avvio le animazioni iniziali
  displayInizializza();
  displayAnimazioneIniziale();
}


// ************************** PROGRAMMA PRINCIPALE *********************************
void loop() {

  int inAttesa = 1;
  int erroreMostrato = 0;
  unsigned long istanteLampeggio = millis();

  // --- Controllo all'accensione: la manopola deve essere a riposo, altrimenti il proiettore
  //     potrebbe partire da solo. Finché non lo è: scritta ERROR e led MOTOR lampeggiante.
  if (controlloAvvio == 1) {
    while (inAttesa) {

      leggiManopola();

      if ((controlloAvvio == 1) && (posizioneManopola != MANOPOLA_RIPOSO)) {

        if (erroreMostrato == 0) {
          displayIntestazione();
          testoGrande = "ERROR";
          displayTestoGrande();
          erroreMostrato = 1;
          digitalWrite(pinLedMotore, HIGH);
        }
        if ((millis() - istanteLampeggio) >= 150) {
          digitalWrite(pinLedMotore, !digitalRead(pinLedMotore));  // lampeggio
          istanteLampeggio = millis();
        }
      }
      if (posizioneManopola == MANOPOLA_RIPOSO) {
        controlloAvvio = 0;
        inAttesa = 0;
        digitalWrite(pinLedMotore, LOW);  // spengo tutti i led
        digitalWrite(pinLedLampada, LOW);
        digitalWrite(pinLedScatto, LOW);
      }
    }
  }

  if (posizioneManopola == MANOPOLA_RIPOSO) displayPronto();  // preparo lo schermo

  // --- Attesa di un comando: finché la manopola è a riposo mostro le pagine informative
  istantePagina = millis();
  prossimaPagina = 1;
  inAttesa = 1;
  while (inAttesa) {

    leggiManopola();

    // Se la manopola torna a riposo o in STOP (a sinistra) spengo la lampada
    if ((posizioneManopola == MANOPOLA_RIPOSO) && (lampadaAccesa == 1)) {
      digitalWrite(pinReleLampada, LOW);
      digitalWrite(pinLedLampada, LOW);
      lampadaAccesa = 0;
    }

    if ((posizioneManopola == MANOPOLA_STOP_SINISTRA) && (lampadaAccesa == 1)) {
      digitalWrite(pinReleLampada, LOW);
      digitalWrite(pinLedLampada, LOW);
      lampadaAccesa = 0;
    }

    if (posizioneManopola != MANOPOLA_RIPOSO) {
      inAttesa = 0;  // è arrivato un comando
    }

    aggiornaPagineInformative(PAGINA_BASE_PRONTO);
  }

  // --- Eseguo il comando scelto con la manopola (ognuna di queste funzioni ritorna
  //     quando la manopola viene spostata)
  if (posizioneManopola == MANOPOLA_CARICAMENTO) caricamento();
  if (posizioneManopola == MANOPOLA_LAMPADA || posizioneManopola == MANOPOLA_LAMPADA_RIAVVOLGI) lampada();
  if (posizioneManopola == MANOPOLA_SCAN) scansione();
  if (posizioneManopola == MANOPOLA_RIAVVOLGIMENTO) riavvolgimento();
}


// Cambia la pagina del display ogni durataPaginaMs: contatori -> tempi -> pagina base.
// La pagina base dipende dalla modalità: "READY" a riposo (PAGINA_BASE_PRONTO), "LAMP" con la lampada accesa
// (PAGINA_BASE_LAMPADA).
void aggiornaPagineInformative(int paginaBase) {
  if ((millis() - istantePagina) > durataPaginaMs) {
    if (prossimaPagina == 1) {
      displayStatistiche();
      prossimaPagina = 2;
    } else if (prossimaPagina == 2) {
      displayStatisticheTempi();
      prossimaPagina = 0;
    } else {
      if (paginaBase == PAGINA_BASE_LAMPADA) displayLampada();
      else displayPronto();
      prossimaPagina = 1;
    }
    istantePagina = millis();
  }
}
