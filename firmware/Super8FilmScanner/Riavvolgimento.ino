// ============================================================================
//  RIAVVOLGIMENTO
// ============================================================================

// Con la manopola a 2 scatti a sinistra il motore gira al contrario, a metà velocità, con la lampada accesa.
// Si ferma quando la manopola viene spostata.
void riavvolgimento() {

  displayIntestazione();
  testoGrande = "REVERSE";
  displayTestoGrande();

  if (lampadaAccesa == 0) {
    digitalWrite(pinReleLampada, HIGH);  // accendo lampada e led
    digitalWrite(pinLedLampada, HIGH);
    lampadaAccesa = 1;
  }

  digitalWrite(pinMotoreAbilita, LOW);  // motore alimentato
  digitalWrite(pinLedMotore, HIGH);     // led MOTOR acceso

  motore.setSpeed(velocitaMax / 2);
  motore.setRampLen(passiPerGiro / 2);  // la rampa di accelerazione dura mezzo giro

  motore.rotate(-versoAvanti);  // avvio il motore in senso inverso

  // Resto qui finché la manopola è nella posizione di riavvolgimento
  unsigned long inizioFuori = 0;
  while (!manopolaLasciata(CODICE_RIAVVOLGIMENTO, inizioFuori)) {
  }

  motore.rotate(0);                      // fermo il motore
  digitalWrite(pinMotoreAbilita, HIGH);  // motore libero
  digitalWrite(pinLedMotore, LOW);       // led MOTOR spento
}
