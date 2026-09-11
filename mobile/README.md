# SHELF-SCOUTER Phone Pick Assistant

Development milestone: 2026-09-09.

This client turns the Android phone into the first edge device for SHELF-SCOUTER: camera → barcode/vision → requested-item matching → verify → pick confirmation.

## Run on the phone

From Termux on the phone:

```bash
cd ~/SHELF-SCOUTER
export GOOGLE_API_KEY='YOUR_KEY'
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
python run_mobile_gateway.py
```

In a second Termux session:

```bash
cd ~/SHELF-SCOUTER/mobile
npm install
EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:5000 npx expo start
```

Install/open Expo Go on the Android phone and open the development project. The phone client uses `expo-camera` for camera and barcode capture.

## Backend on another computer

Set the computer's LAN address instead:

```bash
EXPO_PUBLIC_BACKEND_URL=http://YOUR_COMPUTER_LAN_IP:5000 npx expo start
```

Do not use `localhost` for a backend running on another device.

## Picking workflow

1. Enter the requested grocery item.
2. Point the phone at the shelf.
3. Optionally capture a barcode automatically.
4. Capture a frame.
5. Gemma returns structured products.
6. The gateway produces a conservative `VERIFY_AND_PICK` match.
7. Shopper confirms the pick.
8. The session records the frame and pick for later retailer/order integration.

## Scalable API surface

`mobile_gateway.py` wraps the existing backend without replacing it:

- `POST /v1/sessions`
- `POST /v1/sessions/{id}/frames`
- `POST /v1/sessions/{id}/resolve`
- `POST /v1/sessions/{id}/pick`
- `GET /v1/sessions/{id}`
- `GET /v1/health`

`retailer_adapters.py` defines the normalized boundary for authorized retailer connectors. The current `catalog` adapter is deliberately local-only; no retailer credentials are embedded.

## Enterprise direction

Phone → SHELF-SCOUTER → retailer catalog/order adapter → HOARE admission/policy → Triton/model router → vision model/LoRA → structured pick result.

Retailer credentials, customer/order data, and production actions remain server-side. Instacart and Walmart integrations should be enabled only through their authorized developer/onboarding paths.
