#!/bin/bash
# ----------------------------------------------------------------------
# SHELF-SCOUTER Full Plug-and-Play Demo with Quantum GPS
# - Docker backend with Gemma 4 AI
# - Mobile Expo client with auto-session
# - QGPS coordinates auto-included for high-precision mapping
# ----------------------------------------------------------------------

# -------------------------
# Configurable Environment
# -------------------------
GEMMA_MODEL=${GEMMA_MODEL:-"gemma-4-multimodal"}
GOOGLE_API_KEY=${GOOGLE_API_KEY:-"YOUR_GOOGLE_API_KEY_HERE"}
BACKEND_PORT=${BACKEND_PORT:-5000}
MOBILE_DIR="./mobile"
BACKEND_DIR="."
DOCKER_IMAGE="shelf-scouter-backend"
DEFAULT_QGPS='{"x":0.0,"y":0.0,"z":0.0,"floor":1,"accuracy_mm":15}'

# -------------------------
# Step 1: Build Backend Docker
# -------------------------
echo "🚀 Building backend Docker image..."
docker build -t $DOCKER_IMAGE $BACKEND_DIR

# -------------------------
# Step 2: Run Backend Container
# -------------------------
echo "🟢 Running backend container..."
docker rm -f shelf-scouter-api 2>/dev/null || true
docker run -d -p $BACKEND_PORT:5000 \
  --name shelf-scouter-api \
  -e GEMMA_MODEL="$GEMMA_MODEL" \
  -e GOOGLE_API_KEY="$GOOGLE_API_KEY" \
  -e FLASK_ENV="development" \
  $DOCKER_IMAGE

echo "⏳ Waiting for backend to initialize..."
sleep 5

BACKEND_URL="http://localhost:$BACKEND_PORT"
echo "🌐 Backend URL: $BACKEND_URL"

# -------------------------
# Step 3: Auto-create session with QGPS
# -------------------------
echo "📝 Creating test session with QGPS..."
SESSION_ID=$(curl -s -X POST "$BACKEND_URL/scan/session/start" \
  -H "Content-Type: application/json" \
  -d '{
        "gps":{"lat":38.8951,"lng":-77.0364,"accuracy":5},
        "qgps":'"$DEFAULT_QGPS"',
        "orientation":{"pitch":0,"yaw":0,"roll":0},
        "device_id":"phone-demo-qgps"
      }' | jq -r '.session_id')

if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" == "null" ]; then
  echo "❌ Failed to create session. Check backend logs."
  exit 1
fi

echo "✅ Session created! Session ID: $SESSION_ID"

# -------------------------
# Step 4: Start Mobile Expo Client
# -------------------------
if [ -d "$MOBILE_DIR" ]; then
  echo "📱 Starting Expo mobile client..."
  cd $MOBILE_DIR
  export REACT_NATIVE_BACKEND_URL="$BACKEND_URL"
  export REACT_NATIVE_SESSION_ID="$SESSION_ID"
  export REACT_NATIVE_DEFAULT_QGPS="$DEFAULT_QGPS"
  expo start --dev-client
else
  echo "⚠️ Mobile directory not found: $MOBILE_DIR"
  echo "Please ensure your mobile app is in the correct path."
fi

# -------------------------
# Step 5: Instructions
# -------------------------
echo "✅ Demo Setup Complete with QGPS!"
echo "1. Open Expo Go / Dev Client on your phone."
echo "2. The app will auto-start scanning using Session ID: $SESSION_ID"
echo "3. Frames include QGPS coordinates for high-precision shelf mapping."
echo "4. Export session mapping via: $BACKEND_URL/scan/session/$SESSION_ID/export"
