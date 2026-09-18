package com.bardom.universal.net;

import android.util.Log;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * FirebaseRestClient — Direct REST API client for Firebase Realtime DB.
 *
 * No firebase_admin SDK dependency — just plain HTTPS REST calls.
 * This keeps the APK small and avoids Google Play Services version conflicts.
 *
 * Used for:
 *   - User registration / session
 *   - Points system (add/remove)
 *   - Build queue (APK build status)
 *   - Inbox (user-to-user messages)
 *   - Announcements
 *   - FCM token registration
 */
public class FirebaseRestClient {

    private static final String TAG = "FirebaseRestClient";
    private final String dbUrl;

    public FirebaseRestClient(String dbUrl) {
        this.dbUrl = dbUrl != null ? dbUrl.replaceAll("/$", "") : "";
    }

    public String get(String path) {
        try {
            URL url = new URL(dbUrl + path + ".json");
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            con.setConnectTimeout(15000);
            con.setReadTimeout(30000);
            if (con.getResponseCode() != 200) {
                Log.e(TAG, "GET " + path + " HTTP " + con.getResponseCode());
                return null;
            }
            return readStream(con.getInputStream());
        } catch (Exception e) {
            Log.e(TAG, "get " + path + ": " + e.getMessage());
            return null;
        }
    }

    public String put(String path, String body) {
        try {
            URL url = new URL(dbUrl + path + ".json");
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("PUT");
            con.setRequestProperty("Content-Type", "application/json");
            con.setDoOutput(true);
            con.setConnectTimeout(15000);
            con.setReadTimeout(30000);
            try (OutputStream os = con.getOutputStream()) {
                os.write(body.getBytes("UTF-8"));
            }
            if (con.getResponseCode() != 200) {
                Log.e(TAG, "PUT " + path + " HTTP " + con.getResponseCode());
                return null;
            }
            return readStream(con.getInputStream());
        } catch (Exception e) {
            Log.e(TAG, "put " + path + ": " + e.getMessage());
            return null;
        }
    }

    public String patch(String path, String body) {
        try {
            URL url = new URL(dbUrl + path + ".json");
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("PATCH");
            con.setRequestProperty("Content-Type", "application/json");
            con.setDoOutput(true);
            con.setConnectTimeout(15000);
            con.setReadTimeout(30000);
            try (OutputStream os = con.getOutputStream()) {
                os.write(body.getBytes("UTF-8"));
            }
            if (con.getResponseCode() != 200) {
                Log.e(TAG, "PATCH " + path + " HTTP " + con.getResponseCode());
                return null;
            }
            return readStream(con.getInputStream());
        } catch (Exception e) {
            Log.e(TAG, "patch " + path + ": " + e.getMessage());
            return null;
        }
    }

    public String delete(String path) {
        try {
            URL url = new URL(dbUrl + path + ".json");
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("DELETE");
            con.setConnectTimeout(15000);
            con.setReadTimeout(30000);
            if (con.getResponseCode() != 200) return null;
            return readStream(con.getInputStream());
        } catch (Exception e) {
            Log.e(TAG, "delete " + path + ": " + e.getMessage());
            return null;
        }
    }

    private String readStream(InputStream is) throws Exception {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] tmp = new byte[8192];
        int n;
        while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
        return buf.toString("UTF-8");
    }
}
