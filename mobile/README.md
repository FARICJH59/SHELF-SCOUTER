# SHELF-SCOUTER Phone Pick Assistant

Development milestone: 2026-09-09.

This client turns the Android phone into the first edge device for SHELF-SCOUTER: camera → product recognition → requested-item matching → pick confirmation.

## Run on the phone

From Termux on the development machine/phone:

```bash
cd ~/SHELF-SCOUTER/mobile
npm install
EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:5000 npx expo start
```

Install/open Expo Go on the Android phone and open the development project. `expo-camera` is supported in Expo Go; the current Expo documentation recommends installing it with `npx expo install expo-camera` when aligning versions. If the generated project reports a dependency mismatch, run `npx expo install` so Expo resolves compatible package versions for the installed SDK.

### Backend on the same phone

Run the existing service from Termux:

```bash
cd ~/SHELF-SCOUTER
export GOOGLE_API_KEY='YOUR_KEY'
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
python app.py
```

The mobile app defaults to `http://127.0.0.1:5000`, so no LAN address is required when the backend and app are on the same Android device.

### Backend on another computer

Set the computer's LAN address instead:

```bash
EXPO_PUBLIC_BACKEND_URL=http://YOUR_COMPUTER_LAN_IP:5000 npx expo start
```

Do not use `localhost` for a backend running on another device.

## Scalable API surface

`mobile_gateway.py` wraps the existing backend without replacing it:

- `POST /v1/sessions`
- `POST /v1/sessions/{id}/frames`
- `POST /v1/sessions/{id}/pick`
- `GET /v1/sessions/{id}`
- `GET /v1/health`

The gateway is intentionally retailer-neutral. Future adapters can map an order/SKU from Instacart, Walmart, or another authorized retailer integration into the same session/pick model.

## Production direction

Phone → SHELF-SCOUTER → retailer catalog/order adapter → HOARE admission/policy → Triton/model router → vision model/LoRA → structured pick result.

Retailer credentials, customer/order data, and production actions must remain server-side and must not be embedded in the phone application.
