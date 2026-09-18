package com.bardom.universal.net;

import android.util.Log;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * GitHubClient — Fetches payload + updates from GitHub.
 *
 * Uses the GitHub REST API to:
 *   - Download payload.enc (the encrypted functions tree)
 *   - Download payload.manifest.json (version info)
 *   - Push project updates (via the backend, not directly — the token
 *     is never stored in the APK)
 *
 * The GITHUB_TOKEN is in BuildConfig (injected at build time) but is
 * read-only scope — it can fetch public repos but cannot push.
 * Pushing is done via the backend (which has the write token).
 */
public class GitHubClient {

    private static final String TAG = "GitHubClient";
    private static final String API_BASE = "https://api.github.com";
    private static final String RAW_BASE = "https://raw.githubusercontent.com";

    private final String token;
    private final String repo;  // e.g. "abuhoney/apk-generator-system"

    public GitHubClient(String token, String repo) {
        this.token = token;
        this.repo = repo;
    }

    /**
     * Fetch the payload manifest (version info) from GitHub.
     */
    public String fetchManifest() {
        String[] parts = repo.split("/");
        String url = RAW_BASE + "/" + parts[0] + "/" + parts[1] + "/main/payload.manifest.json";
        return httpGet(url);
    }

    /**
     * Fetch the encrypted payload blob from GitHub.
     */
    public byte[] fetchPayload() {
        String[] parts = repo.split("/");
        String url = RAW_BASE + "/" + parts[0] + "/" + parts[1] + "/main/payload.enc";
        return httpGetBytes(url);
    }

    /**
     * Push the project to GitHub (via the backend — the token is not
     * stored in the APK for security).
     */
    public String pushProject() {
        // This is a stub — the actual push is done by the backend
        // The APK calls the backend's /api/github/push endpoint
        return "{\"ok\":false,\"error\":\"Use backend /api/github/push — token not in APK\"}";
    }

    // ===================== HTTP helpers ===================== //

    private String httpGet(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            if (token != null && !token.isEmpty()) {
                con.setRequestProperty("Authorization", "token " + token);
            }
            con.setConnectTimeout(15000);
            con.setReadTimeout(30000);
            if (con.getResponseCode() != 200) return null;
            try (InputStream is = con.getInputStream()) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] tmp = new byte[8192];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
                return buf.toString("UTF-8");
            }
        } catch (Exception e) {
            Log.e(TAG, "httpGet: " + e.getMessage());
            return null;
        }
    }

    private byte[] httpGetBytes(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("GET");
            if (token != null && !token.isEmpty()) {
                con.setRequestProperty("Authorization", "token " + token);
            }
            con.setConnectTimeout(15000);
            con.setReadTimeout(120000);
            if (con.getResponseCode() != 200) return null;
            try (InputStream is = con.getInputStream()) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] tmp = new byte[16384];
                int n;
                while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
                return buf.toByteArray();
            }
        } catch (Exception e) {
            Log.e(TAG, "httpGetBytes: " + e.getMessage());
            return null;
        }
    }
}
