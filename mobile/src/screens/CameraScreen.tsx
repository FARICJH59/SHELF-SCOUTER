/**
 * CameraScreen – the main shelf-scanning interface.
 *
 * Features:
 *  - Smart Scan Mode: automatically captures the best 3–5 frames when the
 *    device is held steady and the scene is well-lit.
 *  - Frame quality analysis (stability via accelerometer, brightness heuristic)
 *  - Multi-frame buffering: collects up to MAX_FRAMES per session
 *  - QGPS layer: captures GPS + device orientation before the session starts
 *  - Upload flow: start session → upload frames → finalize
 *  - Overlay: real-time ScanFeedback component
 *  - Navigation: pushes to ResultsScreen when finalization completes
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Dimensions,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useNavigation } from "@react-navigation/native";
import type { StackNavigationProp } from "@react-navigation/stack";

import { ScanFeedback, ScanPhase } from "../components/ScanFeedback";
import { BoundingBoxOverlay } from "../components/BoundingBoxOverlay";
import { useFrameQuality, estimateBrightness } from "../hooks/useFrameQuality";
import { captureQGPS } from "../services/qgps";
import { startSession, uploadFrame, finalizeSession } from "../services/api";
import type { RootStackParamList, ScanResult } from "../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Minimum frames to capture per session. */
const MIN_FRAMES = 3;
/** Maximum frames to capture per session. */
const MAX_FRAMES = 5;
/** Minimum milliseconds between automatic captures. */
const CAPTURE_INTERVAL_MS = 600;
/** How long to wait for the device to stabilise before starting Smart Scan. */
const STABILISE_DELAY_MS = 1200;

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");

type CameraNavProp = StackNavigationProp<RootStackParamList, "Camera">;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CameraScreen: React.FC = () => {
  const navigation = useNavigation<CameraNavProp>();
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  // Smart Scan state
  const [phase, setPhase] = useState<ScanPhase>("waiting");
  const [capturedFrames, setCapturedFrames] = useState(0);
  const [liveProducts, setLiveProducts] = useState<ScanResult["products"]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Frame quality from accelerometer, combined with current brightness estimate
  const [brightness, setBrightness] = useState(0.5);
  const quality = useFrameQuality(brightness);

  // Refs to avoid stale closure issues inside intervals
  const capturedCountRef = useRef(0);
  const sessionIdRef = useRef<string | null>(null);
  const isCapturingRef = useRef(false);
  const lastCaptureTimeRef = useRef(0);

  // ---------------------------------------------------------------------------
  // Permission handling
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!cameraPermission?.granted) {
      requestCameraPermission();
    }
  }, [cameraPermission, requestCameraPermission]);

  // ---------------------------------------------------------------------------
  // Start the scanning session (once, when the screen mounts and GPS is ready)
  // ---------------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    const initSession = async () => {
      try {
        const qgps = await captureQGPS();
        if (cancelled) return;
        const session = await startSession(qgps);
        if (cancelled) return;
        setSessionId(session.session_id);
        sessionIdRef.current = session.session_id;
      } catch (err) {
        if (!cancelled) {
          Alert.alert(
            "Setup error",
            "Could not initialise scanning session. Check your connection and location permissions.",
            [{ text: "OK" }]
          );
        }
      }
    };

    initSession();
    return () => {
      cancelled = true;
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Smart Scan: auto-capture loop
  // ---------------------------------------------------------------------------

  const captureFrame = useCallback(async () => {
    if (!cameraRef.current || !sessionIdRef.current) return;
    if (isCapturingRef.current) return;

    const now = Date.now();
    if (now - lastCaptureTimeRef.current < CAPTURE_INTERVAL_MS) return;
    lastCaptureTimeRef.current = now;

    isCapturingRef.current = true;
    setPhase("capturing");

    try {
      const photo = await cameraRef.current.takePictureAsync({
        base64: true,
        quality: 0.7,
        skipProcessing: true,
      });

      if (!photo?.base64) return;

      // Update brightness heuristic
      const b = estimateBrightness(photo.base64);
      setBrightness(b);

      // Skip if brightness is out of range
      if (b < 0.15 || b > 0.92) {
        setPhase("waiting");
        return;
      }

      const frameIndex = capturedCountRef.current;
      const response = await uploadFrame(
        sessionIdRef.current,
        photo.base64,
        frameIndex
      );

      capturedCountRef.current += 1;
      setCapturedFrames(capturedCountRef.current);

      // Show products from the latest frame as live feedback
      setLiveProducts(response.result.products ?? []);

      if (capturedCountRef.current >= MAX_FRAMES) {
        await finalize();
      } else {
        setPhase("waiting");
      }
    } catch (err) {
      setPhase("waiting");
    } finally {
      isCapturingRef.current = false;
    }
  }, []);

  // Auto-capture loop: fires every 400 ms, captures only when quality is good
  useEffect(() => {
    if (phase === "processing" || phase === "done") return;
    if (!sessionId) return;

    const interval = setInterval(async () => {
      if (
        quality.isGood &&
        phase !== "processing" &&
        capturedCountRef.current < MAX_FRAMES
      ) {
        await captureFrame();
      }
    }, 400);

    return () => clearInterval(interval);
  }, [phase, sessionId, quality.isGood, captureFrame]);

  // ---------------------------------------------------------------------------
  // Finalize
  // ---------------------------------------------------------------------------

  const finalize = useCallback(async () => {
    if (!sessionIdRef.current) return;

    setPhase("processing");

    try {
      const result = await finalizeSession(sessionIdRef.current);
      setPhase("done");
      navigation.navigate("Results", { result });
    } catch (err) {
      setPhase("waiting");
      Alert.alert("Error", "Failed to process scan. Please try again.");
    }
  }, [navigation]);

  // Manual capture trigger (tap the shutter button)
  const handleManualCapture = useCallback(async () => {
    if (capturedCountRef.current >= MIN_FRAMES) {
      await finalize();
    } else {
      await captureFrame();
    }
  }, [captureFrame, finalize]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!cameraPermission) {
    return <View style={styles.container} />;
  }

  if (!cameraPermission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.permissionText}>
          Camera access is required to scan shelves.
        </Text>
        <TouchableOpacity style={styles.button} onPress={requestCameraPermission}>
          <Text style={styles.buttonText}>Grant Camera Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        facing="back"
        ratio="16:9"
      />

      {/* Bounding box overlay (from latest frame analysis) */}
      <BoundingBoxOverlay
        products={liveProducts}
        width={SCREEN_WIDTH}
        height={SCREEN_HEIGHT}
      />

      {/* Real-time scan feedback */}
      <ScanFeedback
        phase={phase}
        quality={quality}
        capturedFrames={capturedFrames}
        totalFrames={MAX_FRAMES}
      />

      {/* Session not started yet */}
      {!sessionId && (
        <View style={styles.initBadge}>
          <Text style={styles.initText}>Locating store…</Text>
        </View>
      )}

      {/* Manual shutter button */}
      <TouchableOpacity
        style={[
          styles.shutterButton,
          capturedFrames >= MIN_FRAMES && styles.shutterButtonReady,
        ]}
        onPress={handleManualCapture}
        disabled={phase === "processing" || !sessionId}
        accessibilityLabel={
          capturedFrames >= MIN_FRAMES
            ? "Finish scan"
            : "Capture frame"
        }
      >
        <View style={styles.shutterInner} />
      </TouchableOpacity>

      {/* Frame counter badge */}
      <View style={styles.frameBadge}>
        <Text style={styles.frameBadgeText}>
          {capturedFrames}/{MAX_FRAMES}
        </Text>
      </View>
    </View>
  );
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000",
  },
  center: {
    flex: 1,
    backgroundColor: "#0f172a",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  permissionText: {
    color: "#e2e8f0",
    fontSize: 16,
    textAlign: "center",
    marginBottom: 20,
  },
  button: {
    backgroundColor: "#3b82f6",
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 12,
  },
  buttonText: {
    color: "#fff",
    fontWeight: "600",
    fontSize: 15,
  },
  shutterButton: {
    position: "absolute",
    bottom: 44,
    alignSelf: "center",
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 4,
    borderColor: "#ffffff",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "transparent",
  },
  shutterButtonReady: {
    borderColor: "#22c55e",
  },
  shutterInner: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: "#ffffff",
  },
  initBadge: {
    position: "absolute",
    top: 60,
    alignSelf: "center",
    backgroundColor: "rgba(0,0,0,0.6)",
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 14,
  },
  initText: {
    color: "#94a3b8",
    fontSize: 13,
  },
  frameBadge: {
    position: "absolute",
    top: 60,
    right: 20,
    backgroundColor: "rgba(0,0,0,0.55)",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
  },
  frameBadgeText: {
    color: "#e2e8f0",
    fontSize: 13,
    fontWeight: "600",
  },
});
