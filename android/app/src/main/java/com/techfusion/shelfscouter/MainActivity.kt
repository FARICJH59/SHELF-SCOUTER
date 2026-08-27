package com.techfusion.shelfscouter

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    companion object {
        // Replace with the HTTPS address of the deployed SHELF-SCOUTER Flask API.
        private const val BASE_URL = "https://YOUR-SHELF-SCOUTER-HOST"
    }

    private lateinit var previewView: PreviewView
    private lateinit var status: TextView
    private lateinit var result: TextView
    private lateinit var captureButton: Button
    private var imageCapture: ImageCapture? = null
    private var sessionId: String? = null
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera() else status.text = "Camera permission required"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
        lifecycleScope.launchWhenCreated { createSession() }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(16, 16, 16, 16)
        }
        previewView = PreviewView(this).apply {
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
        root.addView(previewView, LinearLayout.LayoutParams(-1, 0, 1f))

        status = TextView(this).apply {
            text = "Initializing Shelf Scouter…"
            textSize = 16f
            setPadding(0, 12, 0, 8)
        }
        root.addView(status)

        captureButton = Button(this).apply {
            text = "SCAN SHELF"
            setOnClickListener { captureAndScan() }
        }
        root.addView(captureButton)

        result = TextView(this).apply {
            text = "No scan yet"
            textSize = 14f
            gravity = Gravity.START
            setPadding(0, 12, 0, 0)
        }
        root.addView(result)
        setContentView(root)
    }

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build().also {
                it.surfaceProvider = previewView.surfaceProvider
            }
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()
            provider.unbindAll()
            provider.bindToLifecycle(
                this,
                CameraSelector.DEFAULT_BACK_CAMERA,
                preview,
                imageCapture
            )
            status.text = "Camera ready"
        }, ContextCompat.getMainExecutor(this))
    }

    private fun captureAndScan() {
        val capture = imageCapture ?: run {
            status.text = "Camera not ready"
            return
        }
        captureButton.isEnabled = false
        status.text = "Capturing…"
        val file = java.io.File(cacheDir, "shelf-${UUID.randomUUID()}.jpg")
        val output = ImageCapture.OutputFileOptions.Builder(file).build()
        capture.takePicture(output, cameraExecutor, object : ImageCapture.OnImageSavedCallback {
            override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                val bytes = file.readBytes()
                file.delete()
                lifecycleScope.launchWhenResumed { uploadScan(bytes) }
            }

            override fun onError(exception: ImageCaptureException) {
                runOnUiThread {
                    status.text = "Capture failed: ${exception.message ?: "unknown error"}"
                    captureButton.isEnabled = true
                }
            }
        })
    }

    private suspend fun createSession() {
        try {
            val payload = JSONObject().apply {
                put("device_id", deviceId(this@MainActivity))
            }
            val response = postJson("$BASE_URL/scan/session/start", payload.toString())
            sessionId = JSONObject(response).optString("session_id").ifBlank { null }
            status.text = if (sessionId != null) "Scan session ready" else "Session unavailable"
        } catch (e: Exception) {
            status.text = "Offline: session will retry"
        }
    }

    private suspend fun uploadScan(imageBytes: ByteArray) {
        runOnUiThread { status.text = "Analyzing with Gemma 4…" }
        try {
            val compressed = compressForUpload(imageBytes)
            val encoded = Base64.getEncoder().encodeToString(compressed)
            val payload = JSONObject().apply {
                put("image", "data:image/jpeg;base64,$encoded")
            }
            val response = postJson("$BASE_URL/scan", payload.toString())
            val json = JSONObject(response)
            val products = json.optJSONArray("products")
            val summary = json.optString("shelf_summary", "No summary")
            val count = products?.length() ?: 0
            runOnUiThread {
                result.text = "Detected: $count unique product records\n$summary"
                status.text = "Scan complete"
                captureButton.isEnabled = true
            }
        } catch (e: Exception) {
            runOnUiThread {
                status.text = "Scan failed: ${e.message ?: "network error"}"
                captureButton.isEnabled = true
            }
        }
    }

    private fun compressForUpload(bytes: ByteArray): ByteArray {
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            ?: return bytes
        return ByteArrayOutputStream().use { out ->
            bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 82, out)
            out.toByteArray()
        }
    }

    private fun postJson(urlString: String, body: String): String {
        val connection = (URL(urlString).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 10_000
            readTimeout = 30_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
        }
        return connection.useAndRead(body)
    }

    private fun HttpURLConnection.useAndRead(body: String): String {
        outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val code = responseCode
        val stream = if (code in 200..299) inputStream else errorStream
        val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
        disconnect()
        if (code !in 200..299) error("HTTP $code: $text")
        return text
    }

    private fun deviceId(context: Context): String =
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"

    override fun onDestroy() {
        cameraExecutor.shutdown()
        super.onDestroy()
    }
}
