// ============================================================================
//  LAMPADA ACCESA PER INQUADRARE E METTERE A FUOCO
// ============================================================================

// Accende il pannello LED con il motore fermo: serve a posizionare la camera davanti al proiettore,
// centrare l'immagine e metterla a fuoco. Resta in questa modalità finché la manopola non viene spostata.
// Intanto il display alterna la pagina "LAMP" con i contatori e i tempi.
void lampada() {

  displayLampada();

  digitalWrite(pinReleLampada, HIGH);  // accendo la lampada e il led corrispondente
  digitalWrite(pinLedLampada, HIGH);
  lampadaAccesa = 1;

  istantePagina = millis();
  prossimaPagina = 1;

  while ((posizioneManopola == MANOPOLA_LAMPADA) || (posizioneManopola == MANOPOLA_LAMPADA_RIAVVOLGI)) {
    leggiManopola();  // attendo il prossimo comando
    aggiornaPagineInformative(PAGINA_BASE_LAMPADA);
  }
}
