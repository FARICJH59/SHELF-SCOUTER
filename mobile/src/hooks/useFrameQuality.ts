/**
 * useFrameQuality – analyses each camera frame for stability and brightness.
 *
 * Stability is estimated from successive accelerometer readings via expo-sensors.
 * Brightness is computed from the raw pixel buffer mean luminance.
 *
 * Returns a FrameQuality object that the CameraScreen uses to decide whether
 * to capture the current frame.
 */

import { useEffect, useRef, useState } from "react";
import { Accelerometer } from "expo-sensors";
import type { FrameQuality } from "../types";

/** Moving-average window size for accelerometer stability. */
const WINDOW = 10;

const STABILITY_THRESHOLD = 0.7;
const BRIGHTNESS_LOW = 0.15;
const BRIGHTNESS_HIGH = 0.92;

export function useFrameQuality(brightness: number = 0.5): FrameQuality {
  const accelHistory = useRef<number[]>([]);
  const [stability, setStability] = useState(1.0);

  useEffect(() => {
    const sub = Accelerometer.addListener(({ x, y, z }) => {
      const magnitude = Math.sqrt(x * x + y * y + z * z);
      accelHistory.current.push(magnitude);
      if (accelHistory.current.length > WINDOW) {
        accelHistory.current.shift();
      }

      if (accelHistory.current.length >= 2) {
        const values = accelHistory.current;
        const mean = values.reduce((a, b) => a + b, 0) / values.length;
        const variance =
          values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / values.length;
        // Map variance to a stability score: lower variance → higher stability.
        // Variance is typically near 0 when still and ~0.1+ when moving.
        const rawStability = Math.max(0, 1 - variance * 20);
        setStability(rawStability);
      }
    });

    Accelerometer.setUpdateInterval(100);
    return () => sub.remove();
  }, []);

  const isGood =
    stability >= STABILITY_THRESHOLD &&
    brightness >= BRIGHTNESS_LOW &&
    brightness <= BRIGHTNESS_HIGH;

  return { stability, brightness, isGood };
}

/**
 * Estimate the mean brightness of a base-64 encoded JPEG.
 *
 * Samples the raw JPEG byte values as a heuristic (not pixel-accurate but
 * fast and dependency-free on the JS side).
 *
 * @param base64  Base-64 encoded JPEG string.
 * @returns Brightness estimate in [0, 1].
 */
export function estimateBrightness(base64: string): number {
  // Decode a sample of bytes from the middle of the image data.
  const sample = base64.slice(
    Math.floor(base64.length * 0.3),
    Math.floor(base64.length * 0.7)
  );
  try {
    const bytes = atob(sample);
    let sum = 0;
    for (let i = 0; i < bytes.length; i++) {
      sum += bytes.charCodeAt(i);
    }
    return sum / (bytes.length * 255);
  } catch {
    return 0.5;
  }
}
