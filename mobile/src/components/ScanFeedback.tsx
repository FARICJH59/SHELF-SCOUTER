/**
 * ScanFeedback – real-time status overlay during Smart Scan mode.
 *
 * Displays animated messages ("Hold steady…", "Capturing…", etc.) and a
 * progress bar showing how many of the required frames have been captured.
 */

import React from "react";
import {
  View,
  Text,
  StyleSheet,
  Animated,
  ActivityIndicator,
} from "react-native";
import type { FrameQuality } from "../types";

export type ScanPhase =
  | "waiting"    // waiting for the user to hold steady
  | "capturing"  // actively capturing frames
  | "processing" // sending frames to backend
  | "done";      // scan complete

interface ScanFeedbackProps {
  phase: ScanPhase;
  quality: FrameQuality;
  capturedFrames: number;
  totalFrames: number;
}

const PHASE_MESSAGES: Record<ScanPhase, string> = {
  waiting: "Hold steady…",
  capturing: "Capturing…",
  processing: "Analysing shelf…",
  done: "Scan complete!",
};

const QUALITY_COLOR = (quality: FrameQuality): string => {
  if (quality.isGood) return "#22c55e"; // green
  if (quality.stability < 0.5) return "#f97316"; // orange – too shaky
  return "#eab308"; // yellow – borderline
};

export const ScanFeedback: React.FC<ScanFeedbackProps> = ({
  phase,
  quality,
  capturedFrames,
  totalFrames,
}) => {
  const progress = totalFrames > 0 ? capturedFrames / totalFrames : 0;
  const fillWidth = `${Math.round(progress * 100)}%` as `${number}%`;

  return (
    <View style={styles.container} pointerEvents="none">
      {/* Status message */}
      <View style={styles.messageBadge}>
        {phase === "processing" && (
          <ActivityIndicator size="small" color="#ffffff" style={styles.spinner} />
        )}
        <Text style={styles.messageText}>{PHASE_MESSAGES[phase]}</Text>
      </View>

      {/* Quality indicator */}
      <View style={styles.qualityRow}>
        <View
          style={[styles.qualityDot, { backgroundColor: QUALITY_COLOR(quality) }]}
        />
        <Text style={styles.qualityText}>
          {quality.isGood
            ? "Ready"
            : quality.stability < 0.5
            ? "Too shaky"
            : "Adjusting…"}
        </Text>
      </View>

      {/* Frame progress bar */}
      {totalFrames > 0 && (
        <View style={styles.progressBar}>
          <View
            style={[
              styles.progressFill,
              { width: fillWidth },
            ]}
          />
        </View>
      )}

      {/* Frame count */}
      {totalFrames > 0 && (
        <Text style={styles.frameCount}>
          {capturedFrames} / {totalFrames} frames
        </Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    bottom: 120,
    left: 20,
    right: 20,
    alignItems: "center",
    gap: 8,
  },
  messageBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(0,0,0,0.65)",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    gap: 6,
  },
  spinner: {
    marginRight: 4,
  },
  messageText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "600",
    letterSpacing: 0.4,
  },
  qualityRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  qualityDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  qualityText: {
    color: "#e2e8f0",
    fontSize: 13,
  },
  progressBar: {
    width: "80%",
    height: 6,
    backgroundColor: "rgba(255,255,255,0.25)",
    borderRadius: 3,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    backgroundColor: "#22c55e",
    borderRadius: 3,
  },
  frameCount: {
    color: "#94a3b8",
    fontSize: 12,
  },
});
