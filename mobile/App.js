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
  const [status, setStatus] = useState('Starting SHELF-SCOUTER…');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    startSession();
  }, []);

  async function startSession() {
    try {
      const response = await fetch(`${BACKEND_URL}/scan/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: `phone-${Date.now()}`,
          qgps: { x: 0, y: 0, z: 0, floor: 1, accuracy_mm: 15 },
          orientation: { pitch: 0, yaw: 0, roll: 0 }
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      setSessionId(data.session_id);
      setStatus('Ready — scan the requested item.');
    } catch (error) {
      setStatus(`Backend unavailable: ${error.message}`);
    }
  }

  async function scan() {
    if (!cameraRef.current || busy) return;
    setBusy(true);
    setStatus('Scanning…');
    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.55 });
      const response = await fetch(`${BACKEND_URL}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: photo.base64, query: query.trim() || undefined })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      setResult(data);
      const matches = data.matches || data.products || [];
      setStatus(query && data.found === false ? 'Item not found in this view.' : `Found ${matches.length} candidate item(s).`);
    } catch (error) {
      setStatus(`Scan failed: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  if (!permission) return <SafeAreaView style={styles.center}><ActivityIndicator /></SafeAreaView>;
  if (!permission.granted) {
    return <SafeAreaView style={styles.center}>
      <Text style={styles.title}>SHELF-SCOUTER</Text>
      <Text style={styles.body}>Camera access is required to locate grocery items.</Text>
      <Button title="Allow camera" onPress={requestPermission} />
    </SafeAreaView>;
  }

  return <SafeAreaView style={styles.container}>
    <View style={styles.header}>
      <Text style={styles.title}>SHELF-SCOUTER</Text>
      <Text style={styles.status}>{status}</Text>
    </View>
    <View style={styles.cameraWrap}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back" barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128'] }} />
      <View style={styles.target}><Text style={styles.targetText}>CENTER PRODUCT / SHELF</Text></View>
    </View>
    <View style={styles.controls}>
      <TextInput value={query} onChangeText={setQuery} placeholder="Requested item (e.g. Honey Nut Cheerios 18.8 oz)" placeholderTextColor="#9aa0a6" style={styles.input} />
      <Button title={busy ? 'Scanning…' : 'SCAN / FIND ITEM'} onPress={scan} disabled={busy} />
      {sessionId && <Text style={styles.session}>Session: {sessionId.slice(0, 8)}</Text>}
      {result && <View style={styles.result}>
        <Text style={styles.resultTitle}>{result.found === false ? 'NOT FOUND' : query ? 'MATCH RESULTS' : 'SHELF RESULTS'}</Text>
        {(result.matches || result.products || []).slice(0, 5).map((p, i) => (
          <Text key={`${p.name}-${i}`} style={styles.item}>• {p.name}{p.quantity ? ` ×${p.quantity}` : ''}{p.shelf_position ? ` — ${p.shelf_position}` : ''}</Text>
        ))}
      </View>}
    </View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 16 },
  header: { padding: 12, backgroundColor: '#111' },
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
  result: { backgroundColor: '#222', borderRadius: 8, padding: 10 },
  resultTitle: { color: '#fff', fontWeight: '800', marginBottom: 5 },
  item: { color: '#eee', marginVertical: 2 }
});
