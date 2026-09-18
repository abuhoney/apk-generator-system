package com.bardom.universal;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Environment;
import android.util.Log;
import androidx.core.content.FileProvider;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * ApkBuilderClient — Calls the backend to build real APKs.
 *
 * This is the ONLY part of the main APK that requires the backend:
 *   1. User selects a function and taps "Build APK"
 *   2. This client POSTs to the backend's /api/build-apk
 *   3. The backend runs the v3 pipeline (aapt2 + javac + d8 + apksigner)
 *   4. This client downloads the resulting APK
 *   5. Triggers the Android package installer
 *
 * The backend is only needed for building APKs — all other operations
 * (browsing functions, using calculator/notes/weather) work offline.
 */
public class ApkBuilderClient {

    private static final String TAG = "ApkBuilderClient";

    /**
     * Build an APK on the backend.
     * Returns JSON with the result: {ok, apk_path, apk_size, build_mode, ...}
     */
    public static String buildApk(String functionId, String optionsJson) {
        try {
            String backendUrl = BuildConfig.BACKEND_URL;
            String urlStr = backendUrl + "/api/build-apk";
            String body = "{\"function\":\"" + functionId + "\"";
            if (optionsJson != null && !optionsJson.isEmpty()) {
                // Merge options
                body = "{\"function\":\"" + functionId + "\",\"options\":" + optionsJson + "}";
            }
            body += "}";

            URL url = new URL(urlStr);
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("POST");
            con.setRequestProperty("Content-Type", "application/json");
            con.setDoOutput(true);
            con.setConnectTimeout(30000);
            con.setReadTimeout(300000);  // 5 min for APK builds
            try (java.io.OutputStream os = con.getOutputStream()) {
                os.write(body.getBytes("UTF-8"));
            }
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            try (InputStream is = con.getInputStream()) {
                byte[] tmp = new byte[8192];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
            }
            return buf.toString("UTF-8");
        } catch (Exception e) {
            Log.e(TAG, "buildApk: " + e.getMessage());
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    /**
     * Download an APK from the backend and trigger the installer.
     */
    public static void downloadAndInstall(Activity ctx, String url, String filename) {
        new Thread(() -> {
            try {
                File downloads = new File(Environment.getExternalStoragePublicDirectory(
                        Environment.DIRECTORY_DOWNLOADS), "BardomPro");
                if (!downloads.exists()) downloads.mkdirs();
                File apkFile = new File(downloads, filename);

                // Download
                URL u = new URL(url);
                HttpURLConnection con = (HttpURLConnection) u.openConnection();
                con.setRequestMethod("GET");
                con.setConnectTimeout(15000);
                con.setReadTimeout(120000);
                try (InputStream is = con.getInputStream();
                     FileOutputStream fos = new FileOutputStream(apkFile)) {
                    byte[] tmp = new byte[16384];
                    int n;
                    while ((n = is.read(tmp)) > 0) fos.write(tmp, 0, n);
                }

                Log.i(TAG, "APK downloaded: " + apkFile.length() + " bytes");

                // Trigger installer
                Intent intent = new Intent(Intent.ACTION_VIEW);
                Uri apkUri = FileProvider.getUriForFile(ctx,
                        ctx.getPackageName() + ".fileprovider", apkFile);
                intent.setDataAndType(apkUri, "application/vnd.android.package-archive");
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                ctx.startActivity(intent);
            } catch (Exception e) {
                Log.e(TAG, "downloadAndInstall: " + e.getMessage());
            }
        }).start();
    }
}
