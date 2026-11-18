// ============================================================================
//  SCHERMATE DEL DISPLAY OLED (128x32 pixel)
// ============================================================================

// Prima riga: titolo in testo invertito. Cancella lo schermo.
void displayIntestazione() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(BLACK, WHITE);  // testo invertito
  display.setCursor(0, 0);
  display.println(intestazioneDisplay);
}


// Scrive "testoGrande" in corpo 2 sulle due righe in basso e aggiorna lo schermo.
void displayTestoGrande() {
  display.setTextSize(2);
  display.setTextColor(WHITE, BLACK);
  display.setCursor(0, 16);
  display.println(testoGrande);
  display.display();
}


// Schermata "READY" con la versione del firmware
void displayPronto() {
  displayIntestazione();
  testoGrande = "READY";
  displayTestoGrande();
  display.setTextSize(1);
  display.setCursor(88, 24);
  display.print(versioneFirmware);
  display.display();
}


// Schermata "LAMP": lampada accesa per inquadrare e mettere a fuoco
void displayLampada() {
  displayIntestazione();
  testoGrande = "LAMP";
  displayTestoGrande();
  display.setTextSize(1);
  display.setCursor(64, 16);
  display.println("Set Frame");
  display.setCursor(64, 24);
  display.println("and Focus");
  display.display();
}


// Contatori: fotogrammi dell'ultima scansione e totale
void displayStatistiche() {
  displayIntestazione();
  display.setTextSize(1);
  display.setTextColor(WHITE, BLACK);
  display.setCursor(0, 14);
  display.print("LAST  : ");
  display.println(fotogrammiUltimaScansione);
  display.setCursor(0, 24);
  display.print("TOTAL : ");
  display.println(fotogrammiTotali);
  display.display();
}


// Scrive una durata nel formato ore:minuti:secondi (le ore ricominciano da 0 dopo 24)
void displayDurata(unsigned long durataMs) {
  unsigned long secondi = durataMs / 1000;
  unsigned long minuti = secondi / 60;
  unsigned long ore = minuti / 60;
  secondi %= 60;
  minuti %= 60;
  ore %= 24;
  display.print(ore);
  display.print(":");
  display.print(minuti);
  display.print(":");
  display.println(secondi);
}


// Tempi: durata dell'ultima scansione e totale
void displayStatisticheTempi() {
  displayIntestazione();
  display.setTextSize(1);
  display.setTextColor(WHITE, BLACK);
  display.setCursor(0, 14);
  display.print("LAST  : ");
  displayDurata(durataUltimaScansioneMs);
  display.setCursor(0, 24);
  display.print("TOTAL : ");
  displayDurata(durataTotaleScansioniMs);
  display.display();
}


// Avvio del display. Se non risponde (cablaggio o indirizzo I2C errato) il firmware si blocca qui.
void displayInizializza() {
  if (!display.begin(SSD1306_SWITCHCAPVCC, INDIRIZZO_DISPLAY)) {
    Serial.println(F("SSD1306 allocation failed"));
    for (;;)
      ;  // non si prosegue
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(WHITE, BLACK);
  display.setCursor(0, 0);
  display.println("Initializing...");
  display.display();
  delay(150);
  display.println("Please wait...");
  display.display();
  delay(150);
  display.setCursor(0, 24);
  display.print("Firmware ");
  display.println(versioneFirmware);
  display.display();
  delay(850);
}


// Animazione all'accensione: logo FallingBit con i tre led che si accendono in sequenza,
// poi il logo "Super 8".
void displayAnimazioneIniziale() {
  display.clearDisplay();
  display.display();
  delay(150);
  display.drawBitmap(0, 0, LOGO_FALLINGBIT, LOGO_LARGHEZZA, LOGO_ALTEZZA, 1);
  display.display();
  digitalWrite(pinLedMotore, HIGH);
  delay(150);
  digitalWrite(pinLedLampada, HIGH);
  delay(150);
  digitalWrite(pinLedScatto, HIGH);
  delay(150);
  digitalWrite(pinLedScatto, LOW);
  digitalWrite(pinLedMotore, LOW);
  digitalWrite(pinLedLampada, LOW);
  delay(150);
  display.clearDisplay();
  display.drawBitmap(0, 0, LOGO_SUPER8, LOGO_LARGHEZZA, LOGO_ALTEZZA, 1);
  display.display();
  delay(850);
}
