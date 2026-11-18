// ============================================================================
//  MANOPOLA DEI COMANDI
// ============================================================================

// Legge i 5 contatti della manopola e li restituisce come un numero a 5 bit:
// bit 4 = pinManopola1 ... bit 0 = pinManopola5 (1 = HIGH, contatto aperto).
// Il risultato si confronta con i CODICE_... definiti nel file principale.
int leggiCodiceManopola() {
  return (digitalRead(pinManopola1) << 4) | (digitalRead(pinManopola2) << 3) | (digitalRead(pinManopola3) << 2) | (digitalRead(pinManopola4) << 1) | digitalRead(pinManopola5);
}


// Aggiorna posizioneManopola leggendo la manopola (dopo l'attesa antirimbalzo) e controlla
// il pulsante che abilita/disabilita il click del mouse.
// Se i contatti danno una combinazione non riconosciuta (la manopola è tra due posizioni)
// posizioneManopola resta invariata.
void leggiManopola() {

  delay(antirimbalzoMs);

  switch (leggiCodiceManopola()) {
    case CODICE_RIPOSO:
      posizioneManopola = MANOPOLA_RIPOSO;  // tutto fermo, manopola in posizione centrale
      break;
    case CODICE_PREMUTA:
      posizioneManopola = MANOPOLA_CARICAMENTO;  // manopola premuta: caricamento pellicola
      break;
    case CODICE_LAMPADA:
      posizioneManopola = MANOPOLA_LAMPADA;  // 1 scatto a destra: lampada per inquadrare e mettere a fuoco
      break;
    case CODICE_SCAN:
      posizioneManopola = MANOPOLA_SCAN;  // 2 scatti a destra: scansione del film
      break;
    case CODICE_STOP_SINISTRA:
      posizioneManopola = MANOPOLA_STOP_SINISTRA;  // 3 scatti a sinistra: stop
      break;
    case CODICE_LAMPADA_RIAVVOLGI:
      posizioneManopola = MANOPOLA_LAMPADA_RIAVVOLGI;  // 1 scatto a sinistra: lampada (per il riavvolgimento)
      break;
    case CODICE_RIAVVOLGIMENTO:
      posizioneManopola = MANOPOLA_RIAVVOLGIMENTO;  // 2 scatti a sinistra: riavvolgimento
      break;
    default:
      break;  // combinazione non valida: nessuna modifica
  }

  aggiornaClickMouse();
}


// Dice se la manopola è stata lasciata: true quando i contatti sono rimasti diversi da "codice" per almeno
// antirimbalzoUscitaMs. Si usa nei cicli in cui il motore gira (scansione, caricamento, marcia indietro): una
// vibrazione dei contatti non deve fermare il motore. "inizioFuori" è una variabile del chiamante, partita da 0.
bool manopolaLasciata(int codice, unsigned long &inizioFuori) {
  if (leggiCodiceManopola() == codice) {
    inizioFuori = 0;
    return false;
  }
  if (inizioFuori == 0) {
    inizioFuori = millis();
    if (inizioFuori == 0) inizioFuori = 1;
    return false;
  }
  return (millis() - inizioFuori) >= antirimbalzoUscitaMs;
}
