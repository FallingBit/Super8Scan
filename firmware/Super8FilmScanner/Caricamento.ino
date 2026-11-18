// ============================================================================
//  CARICAMENTO DELLA PELLICOLA
// ============================================================================

// Con la manopola al centro e PREMUTA il motore gira (senza lampada e senza click) e fa avanzare
// la pellicola nella meccanica del proiettore. Si ferma appena la manopola viene rilasciata.
void caricamento() {

  displayIntestazione();
  testoGrande = "Load film";
  displayTestoGrande();

  digitalWrite(pinMotoreAbilita, LOW);  // motore alimentato
  digitalWrite(pinLedMotore, HIGH);     // led MOTOR acceso

  motore.setSpeed(velocitaMax);
  motore.setRampLen(passiPerGiro / 2);  // la rampa di accelerazione dura mezzo giro

  motore.rotate(versoAvanti);  // avvio il motore

  // Resto qui finché la manopola è premuta
  unsigned long inizioFuori = 0;
  while (!manopolaLasciata(CODICE_PREMUTA, inizioFuori)) {
  }
  posizioneManopola = MANOPOLA_RIPOSO;

  motore.rotate(0);                      // fermo il motore
  digitalWrite(pinMotoreAbilita, HIGH);  // motore libero
  digitalWrite(pinLedMotore, LOW);       // led MOTOR spento
}
