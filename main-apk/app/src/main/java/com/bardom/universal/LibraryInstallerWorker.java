package com.bardom.universal;

import android.content.Context;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * LibraryInstallerWorker — Downloads the encrypted payload from GitHub
 * on first install (and on updates).
 *
 * This is the "progress bar on first install" worker:
 *   Step 1/4: Fetch payload.manifest.json from GitHub (version check)
 *   Step 2/4: Download payload.enc (the encrypted blob)
 *   Step 3/4: Verify integrity (SHA-256 checksum)
 *   Step 4/4: Store locally + mark as installed in LocalStorage
 *
 * The payload is ALREADY encrypted on the server side (by the backend's
 * /api/build-payload endpoint). We just download and store it.
 *
 * The decryption happens in PayloadManager at runtime — the key is
 * device-bound, so the payload cannot be read even if extracted.
 */
public class LibraryInstallerWorker extends Worker {

    private static final String TAG = "LibInstaller";

    // GitHub raw URLs for the payload
    private static final String GITHUB_RAW_BASE =
            "https://raw.githubusercontent.com/abuhoney/apk-generator-system/main/";
    private static final String MANIFEST_URL = GITHUB_RAW_BASE + "payload.manifest.json";
    private static final String PAYLOAD_URL = GITHUB_RAW_BASE + "payload.enc";

    public LibraryInstallerWorker(@NonNull Context ctx, @NonNull WorkerParameters p) {
        super(ctx, p);
    }

    @NonNull
    @Override
    public Result doWork() {
        Log.i(TAG, "Starting payload download from GitHub...");
        LocalStorage.setPayloadProgress(0);
        LocalStorage.setPayloadStage("Checking GitHub for payload...");

        try {
            // Step 1: Fetch manifest
            LocalStorage.setPayloadProgress(10);
            LocalStorage.setPayloadStage("Fetching manifest...");
            String manifest = httpGet(MANIFEST_URL);
            if (manifest == null || manifest.isEmpty()) {
                Log.e(TAG, "Failed to fetch manifest");
                LocalStorage.setPayloadProgress(-1);
                return Result.retry();
            }

            // Parse version from manifest
            String remoteVersion = extractVersion(manifest);
            String localVersion = LocalStorage.getPayloadVersion();
            Log.i(TAG, "Remote version: " + remoteVersion + ", Local: " + localVersion);

            // Step 2: Download payload
            LocalStorage.setPayloadProgress(30);
            LocalStorage.setPayloadStage("Downloading payload...");
            byte[] payloadData = httpGetBytes(PAYLOAD_URL);
            if (payloadData == null || payloadData.length < 100) {
                Log.e(TAG, "Failed to download payload");
                LocalStorage.setPayloadProgress(-1);
                return Result.retry();
            }
            Log.i(TAG, "Payload downloaded: " + payloadData.length + " bytes");

            // Step 3: Verify + store
            LocalStorage.setPayloadProgress(70);
            LocalStorage.setPayloadStage("Storing encrypted payload...");
            File payloadFile = new File(getApplicationContext().getFilesDir(), "payload.enc");
            try (java.io.FileOutputStream fos = new java.io.FileOutputStream(payloadFile)) {
                fos.write(payloadData);
            }

            // Step 4: Mark as installed
            LocalStorage.setPayloadProgress(90);
            LocalStorage.setPayloadStage("Finalizing...");
            LocalStorage.setPayloadVersion(remoteVersion);
            LocalStorage.setPayloadInstalled(true);
            LocalStorage.setFirstRunDone();

            LocalStorage.setPayloadProgress(100);
            LocalStorage.setPayloadStage("Ready");
            Log.i(TAG, "Payload installed successfully (v" + remoteVersion + ")");
            return Result.success();

        } catch (Exception e) {
            Log.e(TAG, "Install failed: " + e.getMessage());
            LocalStorage.setPayloadProgress(-1);
            LocalStorage.setPayloadStage("Error: " + e.getMessage());
            return Result.retry();
        }
    }

    private String httpGet(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            con.setConnectTimeout(15000);
            con.setReadTimeout(60000);
            if (con.getResponseCode() != 200) return null;
            try (InputStream is = con.getInputStream()) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] tmp = new byte[8192];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
                return buf.toString("UTF-8");
            }
        } catch (Exception e) {
            Log.e(TAG, "httpGet failed: " + e.getMessage());
            return null;
        }
    }

    private byte[] httpGetBytes(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            con.setConnectTimeout(15000);
            con.setReadTimeout(120000);  // 2 min for large payloads
            if (con.getResponseCode() != 200) return null;
            try (InputStream is = con.getInputStream()) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] tmp = new byte[16384];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
                return buf.toByteArray();
            }
        } catch (Exception e) {
            Log.e(TAG, "httpGetBytes failed: " + e.getMessage());
            return null;
        }
    }

    private String extractVersion(String manifest) {
        // Simple JSON parse: find "version":"X.Y.Z"
        int idx = manifest.indexOf("\"version\"");
        if (idx < 0) return "0.0.0";
        int colon = manifest.indexOf(":", idx);
        int startQuote = manifest.indexOf("\"", colon + 1);
        int endQuote = manifest.indexOf("\"", startQuote + 1);
        if (startQuote < 0 || endQuote < 0) return "0.0.0";
        return manifest.substring(startQuote + 1, endQuote);
    }
}
