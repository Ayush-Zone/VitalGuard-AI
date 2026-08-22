#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

#include "wifiComm.h"


// =====================================================
// WIFI CONFIGURATION
// =====================================================

const char* WIFI_SSID = "Ayush's S21 FE";
const char* WIFI_PASSWORD = "12345678";

const char* UDP_IP = "10.134.119.215";
const uint16_t UDP_PORT = 5000;


// =====================================================
// UDP OBJECT
// =====================================================

WiFiUDP udp;


// =====================================================
// INITIALIZE WIFI
// =====================================================

void initWiFi() {

    Serial.println();
    Serial.println("Connecting to WiFi...");

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED) {

        delay(500);

        Serial.print(".");
    }

    Serial.println();
    Serial.println("WiFi connected!");

    Serial.print("ESP8266 IP: ");
    Serial.println(WiFi.localIP());

    udp.begin(UDP_PORT);

    Serial.print("UDP ready on port: ");
    Serial.println(UDP_PORT);
}


// =====================================================
// SEND UDP
// =====================================================

void sendUDP(const String &data) {

    if (WiFi.status() != WL_CONNECTED) {
        return;
    }

    udp.beginPacket(UDP_IP, UDP_PORT);

    udp.print(data);

    udp.endPacket();
}