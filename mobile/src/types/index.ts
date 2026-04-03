/**
 * Shared TypeScript types for Shelf Scouter mobile client.
 */

// ---------------------------------------------------------------------------
// Product detection
// ---------------------------------------------------------------------------

export type ConfidenceLevel = "high" | "medium" | "low";
export type ShelfPosition = "top" | "middle" | "bottom" | "unknown";

export interface Product {
  name: string;
  category: string;
  quantity?: number;
  shelf_position?: ShelfPosition;
  label_text?: string;
  confidence: ConfidenceLevel;
  /** Bounding box in normalised [0, 1] coordinates (optional). */
  bbox?: BoundingBox;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

// ---------------------------------------------------------------------------
// Scan results
// ---------------------------------------------------------------------------

export interface ScanResult {
  products: Product[];
  shelf_summary: string;
  total_unique_products: number;
  frames_processed?: number;
  model?: string;
  store_id?: string | null;
  aisle?: string | null;
  shelf?: string | null;
  session_id?: string;
}

// ---------------------------------------------------------------------------
// QGPS metadata
// ---------------------------------------------------------------------------

export interface GPSCoordinates {
  latitude: number;
  longitude: number;
  accuracy: number;
}

export interface DeviceOrientation {
  pitch: number;
  yaw: number;
  roll: number;
}

export interface QGPSMetadata {
  gps: GPSCoordinates;
  orientation: DeviceOrientation;
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export interface SessionStartResponse {
  session_id: string;
  store_id: string | null;
  aisle: string | null;
  shelf: string | null;
  timestamp: string;
}

export interface FrameUploadResponse {
  session_id: string;
  frame_index: number;
  frame_count: number;
  result: ScanResult;
}

// ---------------------------------------------------------------------------
// Frame quality
// ---------------------------------------------------------------------------

export interface FrameQuality {
  /** Stability score 0–1 (1 = perfectly still). */
  stability: number;
  /** Brightness score 0–1 (0 = too dark, 1 = ideal, values above 0.9 = overexposed). */
  brightness: number;
  /** Whether this frame is good enough to capture. */
  isGood: boolean;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

export type RootStackParamList = {
  Camera: undefined;
  Results: { result: ScanResult };
};
