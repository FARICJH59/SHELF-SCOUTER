import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Button, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';

const DEFAULT_BACKEND = 'http://127.0.0.1:5000';
const BACKEND_URL = (process.env.EXPO_PUBLIC_BACKEND_URL || DEFAULT_BACKEND).replace(/\/$/, '');

export default function App() {
  const cameraRef = useRef(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [sessionId, setSessionId] = useState(null);
  const [query, setQuery] = useState('');
  const [barcode, setBarcode] = useState(null);
  const [status, setStatus] = useState('Starting SHELF-SCOUTER…');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { startSession(); }, []);

  async function startSession() {
    try {
      const response = await fetch(`${BACKEND_URL}/v1/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: `phone-${Date.now()}`, retailer: 'catalog' })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      setSessionId(data.session_id);
      setStatus('Ready — scan the requested item.');
    } catch (error) { setStatus(`Backend unavailable: ${error.message}`); }
  }

  async function scan() {
    if (!cameraRef.current || !sessionId || busy) return;
    setBusy(true); setStatus('Scanning shelf…');
    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.55 });
      const response = await fetch(`${BACKEND_URL}/v1/sessions/${sessionId}/frames`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: photo.base64, query: query.trim() || null, barcode })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      setResult(data);
      const match = data.pick_match;
      if (match?.found) setStatus('ITEM FOUND — verify before picking.');
      else setStatus('Not found in this view — keep scanning.');
    } catch (error) { setStatus(`Scan failed: ${error.message}`); }
    finally { setBusy(false); }
  }

  async function confirmPick() {
    const candidate = result?.pick_match?.candidate;
    if (!candidate || !sessionId) return;
    setBusy(true);
    try {
      const response = await fetch(`${BACKEND_URL}/v1/sessions/${sessionId}/pick`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product: candidate.name,
          quantity: Math.max(1, Number(candidate.quantity || 1)),
          source_frame_id: result.frame_id,
          sku: candidate.sku,
          gtin: candidate.gtin
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      setStatus(`PICK CONFIRMED — ${data.quantity} × ${data.product}`);
    } catch (error) { setStatus(`Pick failed: ${error.message}`); }
    finally { setBusy(false); }
  }

  if (!permission) return <SafeAreaView style={styles.center}><ActivityIndicator /></SafeAreaView>;
  if (!permission.granted) return <SafeAreaView style={styles.center}>
    <Text style={styles.title}>SHELF-SCOUTER</Text>
    <Text style={styles.body}>Camera access is required to locate grocery items.</Text>
    <Button title="Allow camera" onPress={requestPermission} />
  </SafeAreaView>;

  const candidate = result?.pick_match?.candidate;
  return <SafeAreaView style={styles.container}>
    <View style={styles.header}>
      <Text style={styles.title}>SHELF-SCOUTER PICK</Text>
      <Text style={styles.status}>{status}</Text>
    </View>
    <View style={styles.cameraWrap}>
      <CameraView
        ref={cameraRef}
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128'] }}
        onBarcodeScanned={barcode ? undefined : ({ data }) => setBarcode(data)}
      />
      <View style={styles.target}><Text style={styles.targetText}>{barcode ? `BARCODE ${barcode}` : 'CENTER PRODUCT / SHELF'}</Text></View>
    </View>
    <View style={styles.controls}>
      <TextInput value={query} onChangeText={setQuery} placeholder="Requested item" placeholderTextColor="#777" style={styles.input} />
      <Button title={busy ? 'Working…' : 'SCAN / FIND ITEM'} onPress={scan} disabled={busy || !sessionId} />
      {candidate && <View style={styles.result}>
        <Text style={styles.resultTitle}>VERIFY ITEM</Text>
        <Text style={styles.item}>{candidate.name}</Text>
        <Text style={styles.meta}>Position: {candidate.shelf_position || 'unknown'} · Qty visible: {candidate.quantity ?? 'unknown'}</Text>
        <Button title="CONFIRM PICK" onPress={confirmPick} disabled={busy} />
      </View>}
      {result?.pick_match && !candidate && <Text style={styles.notFound}>No confident match. Keep scanning.</Text>}
      {sessionId && <Text style={styles.session}>Session: {sessionId.slice(0, 8)} · Barcode: {barcode || 'not captured'}</Text>}
    </View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 16 },
  header: { padding: 12 },
  title: { color: '#fff', fontSize: 22, fontWeight: '800' },
  body: { textAlign: 'center', fontSize: 16 },
  status: { color: '#b8f7c5', marginTop: 4 },
  cameraWrap: { flex: 1, minHeight: 300, position: 'relative' },
  camera: { flex: 1 },
  target: { position: 'absolute', left: '10%', right: '10%', top: '32%', height: '30%', borderWidth: 2, borderColor: '#fff', borderRadius: 12, alignItems: 'center', justifyContent: 'flex-start' },
  targetText: { color: '#fff', backgroundColor: '#0009', padding: 5, fontSize: 11 },
  controls: { padding: 12, gap: 8, backgroundColor: '#171717' },
  input: { backgroundColor: '#fff', color: '#111', borderRadius: 8, padding: 12, fontSize: 15 },
  session: { color: '#999', fontSize: 11 },
  result: { backgroundColor: '#222', borderRadius: 8, padding: 10, gap: 6 },
  resultTitle: { color: '#fff', fontWeight: '800' },
  item: { color: '#fff', fontSize: 18, fontWeight: '700' },
  meta: { color: '#ccc' },
  notFound: { color: '#ffcf70' }
});
