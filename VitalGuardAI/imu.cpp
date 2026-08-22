#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

#include "imu.h"

Adafruit_MPU6050 mpu;

// Calibration offsets
float accelOffsetX = 0;
float accelOffsetY = 0;
float accelOffsetZ = 0;

float gyroOffsetX = 0;
float gyroOffsetY = 0;
float gyroOffsetZ = 0;


// =====================================================
// CALIBRATION
// =====================================================

void calibrateMPU6050() {

    const int samples = 500;

    float axSum = 0;
    float aySum = 0;
    float azSum = 0;

    float gxSum = 0;
    float gySum = 0;
    float gzSum = 0;

    Serial.println();
    Serial.println("================================");
    Serial.println("MPU6050 CALIBRATION");
    Serial.println("Keep sensor COMPLETELY STILL");
    Serial.println("================================");

    delay(1000);

    for (int i = 0; i < samples; i++) {

        sensors_event_t a, g, temp;

        mpu.getEvent(&a, &g, &temp);

        axSum += a.acceleration.x;
        aySum += a.acceleration.y;
        azSum += a.acceleration.z;

        gxSum += g.gyro.x;
        gySum += g.gyro.y;
        gzSum += g.gyro.z;

        delay(4);
    }

    float axAvg = axSum / samples;
    float ayAvg = aySum / samples;
    float azAvg = azSum / samples;

    float gxAvg = gxSum / samples;
    float gyAvg = gySum / samples;
    float gzAvg = gzSum / samples;

    // Accelerometer
    accelOffsetX = axAvg;
    accelOffsetY = ayAvg;
    accelOffsetZ = azAvg - 9.80665;

    // Gyroscope
    gyroOffsetX = gxAvg;
    gyroOffsetY = gyAvg;
    gyroOffsetZ = gzAvg;

    Serial.println("Calibration complete!");

    // Serial.print("Accel Offset X: ");
    // Serial.println(accelOffsetX, 6);

    // Serial.print("Accel Offset Y: ");
    // Serial.println(accelOffsetY, 6);

    // Serial.print("Accel Offset Z: ");
    // Serial.println(accelOffsetZ, 6);

    // Serial.print("Gyro Offset X: ");
    // Serial.println(gyroOffsetX, 6);

    // Serial.print("Gyro Offset Y: ");
    // Serial.println(gyroOffsetY, 6);

    // Serial.print("Gyro Offset Z: ");
    // Serial.println(gyroOffsetZ, 6);

    // Serial.println();
}


// =====================================================
// INITIALIZE IMU
// =====================================================

void initIMU() {

    Wire.begin();

    if (!mpu.begin()) {

        Serial.println("Failed to find MPU6050!");

        while (1) {
            delay(10);
        }
    }

    Serial.println("MPU6050 Found!");

    // Accelerometer ±8G
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);

    // Gyroscope ±500 deg/s
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);

    // Low-pass filter
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

    delay(100);

    calibrateMPU6050();

    Serial.println("IMU ready.");
}


// =====================================================
// READ IMU
// =====================================================

String readIMU() {

    sensors_event_t a, g, temp;

    mpu.getEvent(&a, &g, &temp);

    // Apply calibration
    float ax = a.acceleration.x - accelOffsetX;
    float ay = a.acceleration.y - accelOffsetY;
    float az = a.acceleration.z - accelOffsetZ;

    float gx = g.gyro.x - gyroOffsetX;
    float gy = g.gyro.y - gyroOffsetY;
    float gz = g.gyro.z - gyroOffsetZ;

    // CSV
    String data = "";

    data += String(millis());
    data += ",";

    data += String(ax, 4);
    data += ",";

    data += String(ay, 4);
    data += ",";

    data += String(az, 4);
    data += ",";

    data += String(gx, 4);
    data += ",";

    data += String(gy, 4);
    data += ",";

    data += String(gz, 4);
    data += ",";

    data += String(temp.temperature, 2);

    return data;
}