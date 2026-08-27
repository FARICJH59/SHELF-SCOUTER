# Shelf Scouter Android Edge v1

Phone-first edge client for SHELF-SCOUTER.

## Architecture

Camera -> Edge client -> `/scan` -> Gemma 4 -> structured product results.

The Android client owns camera capture, scan sessions, device identity, orientation metadata, and result presentation. Spatial/VIO tracking and HOARE policy orchestration are intentionally staged for the next phases.

## Backend

Set `BASE_URL` in `app/src/main/java/com/techfusion/shelfscouter/MainActivity.kt` to the reachable HTTPS endpoint exposing the existing Flask API.

The existing backend already exposes `/health`, `/scan`, `/search`, and scan-session endpoints.

## Security

Use HTTPS in production. Do not embed Google API keys in the Android app. The phone communicates with the Shelf Scouter service; model credentials remain server-side.
