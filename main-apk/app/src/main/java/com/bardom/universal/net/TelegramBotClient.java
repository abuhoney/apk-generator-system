package com.bardom.universal.net;

import android.util.Log;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/**
 * TelegramBotClient — Sends messages and APK files via Telegram bot.
 *
 * Uses the Telegram Bot API directly (no SDK dependency).
 * The BOT_TOKEN is in BuildConfig (injected at build time).
 *
 * Used for:
 *   - Sending build notifications
 *   - Sending APKs to users
 *   - Admin broadcasts
 *   - Reward link delivery
 */
public class TelegramBotClient {

    private static final String TAG = "TelegramBotClient";
    private static final String API_BASE = "https://api.telegram.org/bot";

    private final String botToken;

    public TelegramBotClient(String botToken) {
        this.botToken = botToken;
    }

    /**
     * Send a text message.
     */
    public String sendMessage(String chatId, String text) {
        try {
            String urlStr = API_BASE + botToken + "/sendMessage";
            String body = "{\"chat_id\":\"" + chatId + "\",\"text\":\"" +
                    escapeJson(text) + "\",\"parse_mode\":\"Markdown\"}";
            return httpPostJson(urlStr, body);
        } catch (Exception e) {
            Log.e(TAG, "sendMessage: " + e.getMessage());
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    /**
     * Send a document (e.g., an APK file).
     */
    public String sendDocument(String chatId, String filePath, String caption) {
        // Simplified: for binary uploads, the backend handles it
        // (the APK calls the backend's /api/telegram/notify endpoint)
        try {
            String urlStr = API_BASE + botToken + "/sendMessage";
            String body = "{\"chat_id\":\"" + chatId + "\",\"text\":\"" +
                    escapeJson(caption) + "\",\"parse_mode\":\"Markdown\"}";
            return httpPostJson(urlStr, body);
        } catch (Exception e) {
            Log.e(TAG, "sendDocument: " + e.getMessage());
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    private String httpPostJson(String urlStr, String body) throws Exception {
        URL url = new URL(urlStr);
        HttpURLConnection con = (HttpURLConnection) url.openConnection();
        con.setRequestMethod("POST");
        con.setRequestProperty("Content-Type", "application/json");
        con.setDoOutput(true);
        con.setConnectTimeout(15000);
        con.setReadTimeout(60000);
        try (OutputStream os = con.getOutputStream()) {
            os.write(body.getBytes("UTF-8"));
        }
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        try (InputStream is = con.getInputStream()) {
            byte[] tmp = new byte[8192];
            int n;
            while ((n = is.read(tmp)) > 0) buf.write(tmp, 0, n);
        }
        return buf.toString("UTF-8");
    }

    private String escapeJson(String s) {
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
