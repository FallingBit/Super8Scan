// ============================================================================
//  PULSANTE DI ABILITAZIONE DEL CLICK DEL MOUSE
// ============================================================================

// Ogni pressione del pulsante (pinPulsanteClick) abilita o disabilita il click del mouse durante la scansione.
// Utile per le prove: con il click disabilitato la pellicola scorre ma il PC non salva fotogrammi.
// La commutazione avviene una sola volta a ogni pressione, anche se il pulsante resta premuto a lungo.
// Il led GRAB resta acceso fisso finché il click è disabilitato.
void aggiornaClickMouse() {

  bool premuto = (digitalRead(pinPulsanteClick) == LOW);

  if (premuto && !pulsanteClickPremuto) {
    delay(antirimbalzoMs);
    delay(30);
    if (digitalRead(pinPulsanteClick) == LOW) {  // ancora premuto: non era un rimbalzo
      clickMouseAbilitato = !clickMouseAbilitato;
      pulsanteClickPremuto = true;
    }
  } else if (!premuto) {
    pulsanteClickPremuto = false;  // rilasciato: la prossima pressione commuta di nuovo
  }

  if (!clickMouseAbilitato) {
    digitalWrite(pinLedScatto, HIGH);  // click disattivato: led GRAB fisso
  } else {
    digitalWrite(pinLedScatto, LOW);
  }
}
