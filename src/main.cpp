// ============================================================
// SMART BARANGAY SYSTEM - Gateway Node
// Adds HMAC-based message authentication + sequence numbering
// ============================================================

#include <Arduino.h>
#include <WiFi.h>
#include "mbedtls/md.h"

#define WIFI_SSID "Wokwi-GUEST"
#define WIFI_PASSWORD ""

// Shared secret - MUST match the one in Household main.cpp exactly
#define SHARED_SECRET "BarangayOtaviSecretKey2026"

unsigned long sequenceNumber = 0;

// ===== FUNCTION: Compute HMAC-SHA256, return first 16 hex chars (8 bytes) =====
String computeHMAC(const String &data) {
  byte hmacResult[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;

  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)SHARED_SECRET, strlen(SHARED_SECRET));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)data.c_str(), data.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  String hexResult = "";
  for (int i = 0; i < 8; i++) {
    char buf[3];
    sprintf(buf, "%02x", hmacResult[i]);
    hexResult += buf;
  }
  return hexResult;
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n========================================");
  Serial.println("  SMART BARANGAY ANNOUNCEMENT SYSTEM");
  Serial.println("  ROLE: GATEWAY NODE (with HMAC auth)");
  Serial.println("========================================\n");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    attempts++;
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ Gateway WiFi Connected!");
    Serial.print("   Gateway IP: ");
    Serial.println(WiFi.localIP());
  }
  Serial.println("Gateway ready. Type an announcement to relay...");
}

void loop() {
  if (Serial.available()) {
    String message = Serial.readStringUntil('\n');
    message.trim();

    if (message.length() > 0) {
      sequenceNumber++;

      // HMAC is computed over "sequence|message"
      String signedPayload = String(sequenceNumber) + "|" + message;
      String hmac = computeHMAC(signedPayload);

      // Full packet: sequence|hmac|message
      String packet = String(sequenceNumber) + "|" + hmac + "|" + message;

      Serial.print("ANNOUNCE:");
      Serial.println(packet);
    }
  }
  delay(100);
}