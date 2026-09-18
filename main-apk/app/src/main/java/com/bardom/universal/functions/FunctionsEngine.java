package com.bardom.universal.functions;

import android.content.Context;
import android.util.Log;
import com.bardom.universal.PayloadManager;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Iterator;

/**
 * FunctionsEngine — Dynamic functions engine (offline-first).
 *
 * Reads the function definitions from the decrypted payload (which was
 * downloaded from GitHub and stored encrypted locally). This means:
 *
 *   - New functions appear instantly when the payload updates
 *   - No backend call needed to list/use functions
 *   - Admin can add functions to the payload manifest → they appear
 *     on all devices after the next auto-update (12h interval)
 *
 * Function types supported (from bardom-platform pattern):
 *   - add_points      — grants points
 *   - remove_points   — deducts points
 *   - purchase         — buy with stars
 *   - reward_link      — create a reward link
 *   - message          — send message to another user
 *   - custom           — custom JS callback (runs in WebView)
 *
 * Each function's HTML/CSS/JS is in the payload, so when the user
 * opens a function, its UI renders offline.
 */
public class FunctionsEngine {

    private static final String TAG = "FunctionsEngine";
    private static FunctionsEngine instance;

    private Context ctx;
    private JSONObject payloadCache;
    private long lastCacheTime = 0;
    private static final long CACHE_TTL_MS = 5 * 60 * 1000;  // 5 min

    private FunctionsEngine() {}

    public static synchronized FunctionsEngine getInstance() {
        if (instance == null) instance = new FunctionsEngine();
        return instance;
    }

    public void init(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        // Pre-load the payload cache
        loadPayload();
    }

    private synchronized void loadPayload() {
        if (ctx == null) return;
        long now = System.currentTimeMillis();
        if (payloadCache != null && (now - lastCacheTime) < CACHE_TTL_MS) return;
        try {
            String payloadJson = PayloadManager.getDecryptedPayload(ctx);
            payloadCache = new JSONObject(payloadJson);
            lastCacheTime = now;
            Log.i(TAG, "Payload loaded: " + payloadCache.length() + " top-level keys");
        } catch (Exception e) {
            Log.e(TAG, "loadPayload failed: " + e.getMessage());
            payloadCache = new JSONObject();
        }
    }

    /**
     * List all available functions as a JSON array string.
     * Each entry: {id, name, version, description, icon_color, ...}
     */
    public String listFunctionsJson() {
        loadPayload();
        try {
            JSONObject functions = payloadCache.optJSONObject("functions");
            if (functions == null) return "[]";
            JSONArray arr = new JSONArray();
            Iterator<String> it = functions.keys();
            while (it.hasNext()) {
                String id = it.next();
                JSONObject fn = functions.optJSONObject(id);
                if (fn == null) continue;
                JSONObject manifest = fn.optJSONObject("manifest");
                if (manifest == null) {
                    manifest = new JSONObject().put("name", id).put("version", "1.0.0");
                }
                JSONObject entry = new JSONObject();
                entry.put("id", id);
                entry.put("name", manifest.optString("name", id));
                entry.put("version", manifest.optString("version", "1.0.0"));
                entry.put("description", manifest.optString("description", ""));
                entry.put("icon_color", manifest.optString("icon_color", "#58a6ff"));
                entry.put("has_template", fn.has("template_html"));
                entry.put("has_handler", fn.has("handler_py"));
                arr.put(entry);
            }
            return arr.toString();
        } catch (Exception e) {
            Log.e(TAG, "listFunctionsJson: " + e.getMessage());
            return "[]";
        }
    }

    /**
     * Get a single function's full data as JSON string.
     * Includes template_html, config_json, strings_json, css, js.
     */
    public String getFunctionJson(String functionId) {
        loadPayload();
        try {
            JSONObject functions = payloadCache.optJSONObject("functions");
            if (functions == null) return "{}";
            JSONObject fn = functions.optJSONObject(functionId);
            if (fn == null) return "{}";
            return fn.toString();
        } catch (Exception e) {
            return "{}";
        }
    }

    /**
     * Execute a function (for dynamic functions like add_points, purchase, etc.)
     * For static functions (calculator, notes), execution happens in the WebView's JS.
     */
    public String execute(String functionId, String paramsJson) {
        loadPayload();
        try {
            JSONObject functions = payloadCache.optJSONObject("functions");
            if (functions == null) return "{\"ok\":false,\"error\":\"No functions\"}";
            JSONObject fn = functions.optJSONObject(functionId);
            if (fn == null) return "{\"ok\":false,\"error\":\"Function not found\"}";

            JSONObject manifest = fn.optJSONObject("manifest");
            if (manifest == null) return "{\"ok\":false,\"error\":\"No manifest\"}";

            String type = manifest.optString("type", "static");
            switch (type) {
                case "add_points":
                    return executeAddPoints(paramsJson);
                case "remove_points":
                    return executeRemovePoints(paramsJson);
                case "custom":
                    return "{\"ok\":true,\"message\":\"Custom function — execute in WebView\"}";
                default:
                    return "{\"ok\":true,\"message\":\"Static function — open in WebView\"}";
            }
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    private String executeAddPoints(String paramsJson) {
        try {
            JSONObject params = new JSONObject(paramsJson);
            int amount = params.optInt("amount", 0);
            com.bardom.universal.LocalStorage.addPoints(amount);
            return "{\"ok\":true,\"points\":" + com.bardom.universal.LocalStorage.getPoints() + "}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }

    private String executeRemovePoints(String paramsJson) {
        try {
            JSONObject params = new JSONObject(paramsJson);
            int amount = params.optInt("amount", 0);
            int current = com.bardom.universal.LocalStorage.getPoints();
            if (current < amount) {
                return "{\"ok\":false,\"error\":\"Insufficient points\"}";
            }
            com.bardom.universal.LocalStorage.addPoints(-amount);
            return "{\"ok\":true,\"points\":" + com.bardom.universal.LocalStorage.getPoints() + "}";
        } catch (Exception e) {
            return "{\"ok\":false,\"error\":\"" + e.getMessage() + "\"}";
        }
    }
}
