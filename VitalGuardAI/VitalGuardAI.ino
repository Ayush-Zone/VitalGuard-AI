#include "imu.h"
#include "wifiComm.h"

void setup() {
    Serial.begin(115200);

    initIMU();
    initWiFi();
}

void loop() {
    String data = readIMU();

    if (data.length() > 0) {
        sendUDP(data);
        Serial.println(data);
    }

    delay(20);   // ~50 Hz
}