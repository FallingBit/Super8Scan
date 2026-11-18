// ============================================================================
//  SCANSIONE DEL FILM FOTOGRAMMA PER FOTOGRAMMA
// ============================================================================

// Il motore gira di continuo. A ogni giro la meccanica del proiettore fa avanzare la pellicola di un fotogramma
// e lo tiene fermo per circa un quarto di giro. Un magnete sulla ruota dello shutter segnala al sensore HALL
// il momento in cui il fotogramma è pronto: il firmware attende (una frazione del periodo) che la pellicola si stabilizzi e poi
// fa "click" (impulso sull'optoisolatore del mouse), così il PC salva il fotogramma.
// La funzione ritorna quando la manopola viene spostata dalla posizione SCAN, oppure se il sensore HALL
// non dà più segnale. Se il motore si ferma (stallo) il firmware prova a ripartire da solo (vedi timeoutStalloMs).
void scansione() {

  displayIntestazione();
  testoGrande = "SCAN";
  displayTestoGrande();

  if (lampadaAccesa == 0) {
    digitalWrite(pinReleLampada, HIGH);  // accendo lampada e led
    digitalWrite(pinLedLampada, HIGH);
    lampadaAccesa = 1;
  }

  long int fotogrammiQuestaScansione = 0;

  digitalWrite(pinMotoreAbilita, LOW);  // motore alimentato
  digitalWrite(pinLedMotore, HIGH);     // led MOTOR acceso

  // Velocità in passi ogni 10 secondi; la rampa è lunga passi/s * durata / 2 (la velocità media è metà)
  motore.setSpeedSteps(passiAlSecondoScansione * 10, passiAlSecondoScansione * rampaScansioneMs / 2000);

  int letturaHall = analogRead(pinSensoreHall);

  // Se la scansione riprende dopo uno stop e il magnete è già davanti al sensore, quel fotogramma è stato
  // acquisito prima dello stop (il click parte sempre prima che il firmware possa vedere lo stop):
  // si parte come se il magnete fosse già stato rilevato, così non si salva un fotogramma doppio.
  bool magnetePresente = (letturaHall <= sogliaHallScatto);

  bool clickInCorso = false;                       // true tra l'inizio e la fine dell'impulso di click
  unsigned long istanteClick = millis();           // istante dell'ultimo click
  unsigned long istanteUltimoPassaggio = millis();  // istante dell'ultimo passaggio del magnete
  unsigned long inizioFuori = 0;                   // per l'antirimbalzo dell'uscita dalla manopola
  unsigned long periodoMs = 0;                     // tempo tra gli ultimi due passaggi del magnete (0 = non ancora noto)
  unsigned long istantePassaggioPrecedente = 0;    // istante del passaggio precedente (0 = nessuno)
  unsigned long istanteRipartenza = 0;             // istante dell'ultima ripartenza dopo uno stallo
  int tentativi = 0;                               // ripartenze consecutive senza passaggi del magnete
  int passaggiDaRipartenza = 0;                    // passaggi del magnete dall'ultima ripartenza
  bool inRipartenza = false;                       // true finché si va piano dopo uno stallo
  bool segnaleMancante = false;
  inizioScansioneMs = millis();

  motore.rotate(versoAvanti);  // avvio il motore

  // Si resta nel ciclo finché la manopola è su SCAN. Il ciclo e volutamente privo di aggiornamenti del display
  // per non rallentare la scansione.
  while (!manopolaLasciata(CODICE_SCAN, inizioFuori)) {

    letturaHall = analogRead(pinSensoreHall);

    // Magnete lontano: il sensore si riarma per il fotogramma successivo
    if (letturaHall >= sogliaHallRiarmo) {
      magnetePresente = false;
    }

    // Magnete vicino (fotogramma pronto) e sensore armato: passaggio del magnete
    if ((letturaHall <= sogliaHallScatto) && (!magnetePresente)) {
      magnetePresente = true;
      istanteUltimoPassaggio = millis();
      if (istantePassaggioPrecedente != 0) periodoMs = istanteUltimoPassaggio - istantePassaggioPrecedente;
      istantePassaggioPrecedente = istanteUltimoPassaggio;

      // Dopo uno stallo: superati alcuni passaggi si torna alla velocità normale
      if (inRipartenza) {
        passaggiDaRipartenza++;
        if (passaggiDaRipartenza >= passaggiRipartenza) {
          motore.setSpeedSteps(passiAlSecondoScansione * 10, passiAlSecondoScansione * rampaScansioneMs / 2000);
          inRipartenza = false;
          tentativi = 0;
        }
      }

      if (clickMouseAbilitato) {
        // Aspetto che la pellicola si stabilizzi: una frazione del periodo (se noto e plausibile)
        if (periodoMs > 0 && periodoMs < 1000) delay((unsigned long)(periodoMs * frazioneStabilizzazione));
        else delay(attesaStabilizzazioneMs);
        istanteClick = millis();
        digitalWrite(pinClickMouse, HIGH);  // click del mouse e led GRAB
        digitalWrite(pinLedScatto, HIGH);
        clickInCorso = true;
        fotogrammiQuestaScansione++;
        fotogrammiTotali++;
      }
    }

    // Termine dell'impulso di click
    if (clickInCorso && ((millis() - istanteClick) >= durataClickMs)) {
      digitalWrite(pinClickMouse, LOW);  // rilascio il tasto e spengo il led GRAB
      digitalWrite(pinLedScatto, LOW);
      clickInCorso = false;
    }

    // Il magnete non passa più davanti al sensore: il motore si è fermato (per esempio su una giuntura) oppure
    // il sensore è scollegato o guasto. Si prova a ripartire; dopo troppi tentativi si ferma tutto (NO HALL).
    unsigned long ultimoSegno = max(istanteUltimoPassaggio, istanteRipartenza);
    unsigned long limite = (istanteRipartenza > istanteUltimoPassaggio) ? timeoutRipartenzaMs : timeoutStalloMs;
    if ((millis() - ultimoSegno) > limite) {
      if (tentativi >= tentativiRipartenza) {
        segnaleMancante = true;
        break;
      }
      tentativi++;
      Serial.printf("Stallo: ripartenza %d di %d\n", tentativi, tentativiRipartenza);
      motore.stop();                       // fermo subito il motore
      delay(pausaRipartenzaMs);
      motore.setSpeedSteps(passiAlSecondoRipartenza * 10, passiAlSecondoRipartenza * rampaRipartenzaMs / 2000);
      motore.rotate(versoAvanti);          // riparto piano
      istanteRipartenza = millis();
      periodoMs = 0;
      istantePassaggioPrecedente = 0;
      passaggiDaRipartenza = 0;
      inRipartenza = true;
    }
  }

  motore.rotate(0);                      // fermo il motore
  digitalWrite(pinClickMouse, LOW);      // nessun click rimasto acceso
  if (clickMouseAbilitato) digitalWrite(pinLedScatto, LOW);
  digitalWrite(pinMotoreAbilita, HIGH);  // motore libero
  digitalWrite(pinLedMotore, LOW);       // led MOTOR spento

  // Statistiche della scansione appena terminata (mostrate poi sul display)
  durataUltimaScansioneMs = millis() - inizioScansioneMs;
  if (segnaleMancante) durataUltimaScansioneMs -= (millis() - max(istanteUltimoPassaggio, istanteRipartenza));  // il tempo di attesa non è scansione
  durataTotaleScansioniMs = durataTotaleScansioniMs + durataUltimaScansioneMs;
  if (fotogrammiQuestaScansione != 0) fotogrammiUltimaScansione = fotogrammiQuestaScansione;

  if (segnaleMancante) segnaleHallMancante();
}


// Mostra l'errore "NO HALL" con il led MOTOR lampeggiante e resta in attesa finché la manopola
// non viene spostata dalla posizione SCAN.
void segnaleHallMancante() {

  displayIntestazione();
  testoGrande = "NO HALL";
  displayTestoGrande();

  unsigned long inizioFuori = 0;
  unsigned long ultimoLampeggio = millis();

  while (!manopolaLasciata(CODICE_SCAN, inizioFuori)) {
    if ((millis() - ultimoLampeggio) >= 150) {
      digitalWrite(pinLedMotore, !digitalRead(pinLedMotore));  // lampeggio
      ultimoLampeggio = millis();
    }
  }

  digitalWrite(pinLedMotore, LOW);
}
