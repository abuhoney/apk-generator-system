package com.bardom.universal;

import android.content.Context;
import android.util.Log;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import java.util.concurrent.TimeUnit;

/**
 * AutoUpdater — Checks GitHub for payload updates.
 *
 * Runs as a periodic WorkManager job (every 12 hours):
 *   1. Fetches payload.manifest.json from GitHub
 *   2. Compares version with local stored version
 *   3. If newer version exists:
 *      a. Downloads the new payload.enc
 *      b. Stores it locally (encrypted)
 *      c. Updates LocalStorage version
 *      d. On next app open, the WebView reloads with new functions
 *
 * This enables "auto-update without APK rebuild" — new functions,
 * new templates, new strings are pushed to GitHub and appear in the
 * app without ever recompiling the main APK.
 *
 * The update check is network-only (no backend needed) — it fetches
 * directly from GitHub raw URLs, so even if the backend is down,
 * updates still work.
 */
public class AutoUpdater {

    private static final String TAG = "AutoUpdater";
    private static final String WORK_NAME = "bardom_auto_update";
    private static final long CHECK_INTERVAL_HOURS = 12;

    private static final String GITHUB_RAW_BASE =
            "https://raw.githubusercontent.com/abuhoney/apk-generator-system/main/";
    private static final String MANIFEST_URL = GITHUB_RAW_BASE + "payload.manifest.json";
    private static final String PAYLOAD_URL = GITHUB_RAW_BASE + "payload.enc";

    /**
     * Schedule the periodic update check (called from MainActivity.onCreate).
     */
    public static void schedule(Context ctx) {
        Constraints constraints = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();

        PeriodicWorkRequest updateWork = new PeriodicWorkRequest.Builder(
                UpdateWorker.class,
                CHECK_INTERVAL_HOURS,
                TimeUnit.HOURS)
                .setConstraints(constraints)
                .build();

        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                updateWork);

        Log.i(TAG, "Auto-updater scheduled (every " + CHECK_INTERVAL_HOURS + "h)");
    }

    /**
     * Check for updates NOW (called from JS bridge when user taps "Check for updates").
     * Returns JSON with the result.
     */
    public static String checkNow(Context ctx) {
        try {
            Log.i(TAG, "Manual update check...");
            String manifest = simpleGet(MANIFEST_URL);
            if (manifest == null) {
                return "{\"ok\":false,\"error\":\"Cannot reach GitHub\"}";
            }

            String remoteVersion = extractVersion(manifest);
            String localVersion = LocalStorage.getPayloadVersion();

            if (remoteVersion.equals(localVersion)) {
                return "{\"ok\":true,\"updated\":false,\"version\":\"" + localVersion + "\"}";
            }

            // Download new payload
            byte[] payload = simpleGetBytes(PAYLOAD_URL);
            if (payload == null || payload.length < 100) {
                return "{\"ok\":false,\"error\":\"Payload download failed\"}";
            }

            // Store
            java.io.File payloadFile = new java.io.File(ctx.getFilesDir(), "payload.enc");
            try (java.io.FileOutputStream fos = new java.io.FileOutputStream(payloadFile)) {
                fos.write(payload);
            }

            LocalStorage.setPayloadVersion(remoteVersion);
            LocalStorage.setPayloadInstalled(true);

            Log.i(TAG, "Updated to v" + remoteVersion);
            return "{\"ok\":true,\"updated\":true,\"version\":\"" + remoteVersion + "\"}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    private static String simpleGet(String urlStr) {
        try {
            java.net.URL url = new java.net.URL(urlStr);
            java.net.HttpURLConnection con = (java.net.HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            con.setConnectTimeout(15000);
            con.setReadTimeout(30000);
            if (con.getResponseCode() != 200) return null;
            try (java.io.InputStream is = con.getInputStream()) {
                java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
                byte[] tmp = new byte[8192];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
                return buf.toString("UTF-8");
            }
        } catch (Exception e) {
            Log.e(TAG, "simpleGet: " + e.getMessage());
            return null;
        }
    }

    private static byte[] simpleGetBytes(String urlStr) {
        try {
            java.net.URL url = new java.net.URL(urlStr);
            java.net.HttpURLConnection con = (java.net.HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            con.setConnectTimeout(15000);
            con.setReadTimeout(120000);
            if (con.getResponseCode() != 200) return null;
            try (java.io.InputStream is = con.getInputStream()) {
                java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
                byte[] tmp = new byte[16384];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
                return buf.toByteArray();
            }
        } catch (Exception e) {
            return null;
        }
    }

    private static String extractVersion(String json) {
        int idx = json.indexOf("\"version\"");
        if (idx < 0) return "0.0.0";
        int colon = json.indexOf(":", idx);
        int startQuote = json.indexOf("\"", colon + 1);
        int endQuote = json.indexOf("\"", startQuote + 1);
        if (startQuote < 0 || endQuote < 0) return "0.0.0";
        return json.substring(startQuote + 1, endQuote);
    }
}
