package com.bardom.universal;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import androidx.core.content.FileProvider;
import com.bardom.universal.functions.FunctionsEngine;
import com.bardom.universal.net.FirebaseRestClient;
import com.bardom.universal.net.GitHubClient;
import com.bardom.universal.net.TelegramBotClient;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.HashMap;
import java.util.Map;

/**
 * MainActivity — The WebView host for the universal APK generator engine.
 *
 * This is the heart of the offline-first main APK:
 *   1. Loads assets/engine/index.html (tiny bootstrap, 2 KB)
 *   2. index.html calls loader.js which decrypts the local payload
 *   3. The decrypted engine HTML is injected into the WebView
 *   4. The engine UI appears — user can:
 *      - Browse functions (offline)
 *      - Use functions (offline — calculator, notes, weather)
 *      - Build APKs (online — via backend)
 *      - Push to GitHub (online — via backend)
 *      - Send Telegram messages (online — via backend)
 *
 * The JS bridge (EngineBridge) exposes native Android capabilities to the
 * WebView: file downloads, APK installation, Firebase, Telegram, etc.
 */
public class MainActivity extends Activity {

    private static final String TAG = "MainActivity";
    private WebView webView;
    private ProgressBar progressBar;
    private TextView tvStatus;
    private FirebaseRestClient fbRest;
    private TelegramBotClient tg;
    private GitHubClient github;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);
        tvStatus = findViewById(R.id.tvStatus);

        // Initialize network clients (credentials from BuildConfig, injected at build time)
        fbRest = new FirebaseRestClient(BuildConfig.FIREBASE_DB_URL);
        tg = new TelegramBotClient(BuildConfig.TELEGRAM_BOT_TOKEN);
        github = new GitHubClient(BuildConfig.GITHUB_TOKEN, BuildConfig.GITHUB_REPO);

        setupWebView();
        loadEngine();

        // Schedule the auto-updater (checks GitHub every 12 hours for payload updates)
        AutoUpdater.schedule(this);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);  // Always load fresh engine
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);  // Security: no mixed content

        // Add the JS bridge — this is how the WebView calls native Android
        webView.addJavascriptInterface(new EngineBridge(), "Android");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                progressBar.setVisibility(ProgressBar.GONE);
                tvStatus.setVisibility(TextView.GONE);
                // Engine loaded — call the bootstrap function
                view.evaluateJavascript("window.__bootstrapEngine && __bootstrapEngine()", null);
            }

            @Override
            public void onReceivedError(WebView view, int errorCode,
                                        String description, String failingUrl) {
                Log.e(TAG, "WebView error: " + description);
                view.loadDataWithBaseURL("file:///android_asset/",
                    "<html><body style='background:#0d1117;color:#c9d1d9;" +
                    "font-family:sans-serif;padding:24px;text-align:center'>" +
                    "<h2 style='color:#f85149'>Engine load failed</h2>" +
                    "<p>" + description + "</p>" +
                    "<p style='color:#8b949e;font-size:12px'>" + failingUrl + "</p>" +
                    "</body></html>",
                    "text/html", "utf-8", null);
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
            }

            @Override
            public void onConsoleMessage(String message, int lineNumber, String sourceID) {
                Log.d(TAG, "JS: " + message + " (" + sourceID + ":" + lineNumber + ")");
            }
        });
    }

    /**
     * Load the engine bootstrap from assets.
     * The bootstrap (index.html) calls loader.js which decrypts the
     * local payload and injects the full engine UI.
     */
    private void loadEngine() {
        // Check if payload is installed
        if (!LocalStorage.isPayloadInstalled()) {
            // Payload not downloaded yet — redirect to SplashActivity
            startActivity(new Intent(this, SplashActivity.class));
            finish();
            return;
        }
        webView.loadUrl("file:///android_asset/engine/index.html");
    }

    // ---------------------------------------------------------------- //
    // JS Bridge — native methods exposed to the WebView
    // ---------------------------------------------------------------- //
    public class EngineBridge {

        // ----- Payload / Engine ----- //

        @JavascriptInterface
        public String getPayloadVersion() {
            return LocalStorage.getPayloadVersion();
        }

        @JavascriptInterface
        public String getDecryptedPayload() {
            // Decrypt the local payload and return as JSON string
            return PayloadManager.getDecryptedPayload(MainActivity.this);
        }

        @JavascriptInterface
        public boolean isOfflineMode() {
            return true;  // Main APK is always offline-first
        }

        @JavascriptInterface
        public String getBackendUrl() {
            return BuildConfig.BACKEND_URL;
        }

        // ----- Functions ----- //

        @JavascriptInterface
        public String listFunctions() {
            // Returns JSON array of all available functions (from decrypted payload)
            return FunctionsEngine.getInstance().listFunctionsJson();
        }

        @JavascriptInterface
        public String getFunction(String functionId) {
            return FunctionsEngine.getInstance().getFunctionJson(functionId);
        }

        @JavascriptInterface
        public String executeFunction(String functionId, String paramsJson) {
            return FunctionsEngine.getInstance().execute(functionId, paramsJson);
        }

        // ----- APK Build (online — via backend) ----- //

        @JavascriptInterface
        public String buildApk(String functionId, String optionsJson) {
            // Calls the backend to build a real APK
            return ApkBuilderClient.buildApk(functionId, optionsJson);
        }

        @JavascriptInterface
        public void downloadApk(String url, String filename) {
            // Download an APK from the backend and trigger install
            ApkBuilderClient.downloadAndInstall(MainActivity.this, url, filename);
        }

        // ----- GitHub ----- //

        @JavascriptInterface
        public String githubPush() {
            return github.pushProject();
        }

        @JavascriptInterface
        public String checkForUpdates() {
            return AutoUpdater.checkNow(MainActivity.this);
        }

        // ----- Firebase ----- //

        @JavascriptInterface
        public String firebaseGet(String path) {
            return fbRest.get(path);
        }

        @JavascriptInterface
        public String firebasePut(String path, String body) {
            return fbRest.put(path, body);
        }

        @JavascriptInterface
        public String firebasePatch(String path, String body) {
            return fbRest.patch(path, body);
        }

        // ----- Telegram ----- //

        @JavascriptInterface
        public String telegramSend(String chatId, String text) {
            return tg.sendMessage(chatId, text);
        }

        @JavascriptInterface
        public String telegramSendApk(String chatId, String apkPath, String caption) {
            return tg.sendDocument(chatId, apkPath, caption);
        }

        // ----- User / Points ----- //

        @JavascriptInterface
        public String getUserSession() {
            return LocalStorage.getUserSession().toString();
        }

        @JavascriptInterface
        public int getPoints() {
            return LocalStorage.getPoints();
        }

        @JavascriptInterface
        public void saveUserSession(String json) {
            try {
                LocalStorage.saveUserSession(new JSONObject(json));
            } catch (Exception e) {
                Log.e(TAG, "saveUserSession: " + e.getMessage());
            }
        }

        // ----- Utility ----- //

        @JavascriptInterface
        public String getDeviceId() {
            return LocalStorage.getDeviceId();
        }

        @JavascriptInterface
        public void toast(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
        }

        @JavascriptInterface
        public void log(String message) {
            Log.i(TAG, "[JS] " + message);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
    }

    @Override
    protected void onPause() {
        if (webView != null) webView.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
