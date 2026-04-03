/**
 * Shelf Scouter API client.
 *
 * Wraps the Flask backend endpoints used by the mobile app:
 *   - /scan/session/start
 *   - /scan/session/<id>/frame
 *   - /scan/session/<id>/finalize
 *   - /search
 *   - /health
 */

import Constants from "expo-constants";
import type {
  QGPSMetadata,
  SessionStartResponse,
  FrameUploadResponse,
  ScanResult,
} from "../types";

const API_BASE_URL: string =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  "http://localhost:5000";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function fetchJSON<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API error ${response.status}: ${body}`);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

export async function checkHealth(): Promise<{ status: string; model: string }> {
  return fetchJSON("/health");
}

// ---------------------------------------------------------------------------
// Session management
// ---------------------------------------------------------------------------

/**
 * Start a new multi-frame scanning session with QGPS metadata.
 */
export async function startSession(
  qgps: QGPSMetadata
): Promise<SessionStartResponse> {
  return fetchJSON<SessionStartResponse>("/scan/session/start", {
    method: "POST",
    body: JSON.stringify(qgps),
  });
}

/**
 * Upload a single frame (base-64 encoded image) to an open session.
 *
 * @param sessionId  Session identifier from startSession().
 * @param imageBase64  Base-64 encoded JPEG string (no data-URL prefix).
 * @param frameIndex   0-based index of this frame within the session.
 * @param query        Optional product search query to focus the scan.
 */
export async function uploadFrame(
  sessionId: string,
  imageBase64: string,
  frameIndex: number,
  query?: string
): Promise<FrameUploadResponse> {
  return fetchJSON<FrameUploadResponse>(`/scan/session/${sessionId}/frame`, {
    method: "POST",
    body: JSON.stringify({
      image: imageBase64,
      frame_index: frameIndex,
      ...(query ? { query } : {}),
    }),
  });
}

/**
 * Finalise a session and trigger multi-frame fusion.
 *
 * @returns The merged scan result with all products from all frames.
 */
export async function finalizeSession(sessionId: string): Promise<ScanResult> {
  return fetchJSON<ScanResult>(`/scan/session/${sessionId}/finalize`, {
    method: "POST",
  });
}

/**
 * Search for a specific product across a shelf image (single-frame).
 *
 * @param imageBase64  Base-64 encoded image.
 * @param query        Product search query.
 */
export async function searchProduct(
  imageBase64: string,
  query: string
): Promise<ScanResult & { matches: ScanResult["products"]; found: boolean; query: string }> {
  return fetchJSON("/search", {
    method: "POST",
    body: JSON.stringify({ image: imageBase64, query }),
  });
}
