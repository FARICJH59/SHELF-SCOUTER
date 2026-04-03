/**
 * QGPS service – captures GPS coordinates and device orientation.
 *
 * GPS uses expo-location; orientation uses expo-sensors (DeviceMotion).
 */

import * as Location from "expo-location";
import { DeviceMotion } from "expo-sensors";
import type { GPSCoordinates, DeviceOrientation, QGPSMetadata } from "../types";

/** Request location permission and return the current GPS fix. */
export async function getCurrentGPS(): Promise<GPSCoordinates> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== "granted") {
    throw new Error("Location permission not granted");
  }

  const location = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.High,
  });

  return {
    latitude: location.coords.latitude,
    longitude: location.coords.longitude,
    accuracy: location.coords.accuracy ?? 0,
  };
}

/** Return the current device orientation (pitch / yaw / roll in degrees). */
export async function getCurrentOrientation(): Promise<DeviceOrientation> {
  const isAvailable = await DeviceMotion.isAvailableAsync();
  if (!isAvailable) {
    // Graceful degradation – return zeroes when sensor is absent (e.g. emulator).
    return { pitch: 0, yaw: 0, roll: 0 };
  }

  return new Promise((resolve) => {
    const subscription = DeviceMotion.addListener((data) => {
      subscription.remove();
      const { beta = 0, gamma = 0, alpha = 0 } = data.rotation ?? {};
      // beta  = pitch (tilt forward/back, degrees)
      // gamma = roll  (tilt left/right, degrees)
      // alpha = yaw   (compass heading, degrees)
      resolve({
        pitch: beta * (180 / Math.PI),
        yaw: alpha * (180 / Math.PI),
        roll: gamma * (180 / Math.PI),
      });
    });
    DeviceMotion.setUpdateInterval(100);
  });
}

/** Capture GPS + orientation together. */
export async function captureQGPS(): Promise<QGPSMetadata> {
  const [gps, orientation] = await Promise.all([
    getCurrentGPS(),
    getCurrentOrientation(),
  ]);
  return { gps, orientation };
}
