package com.bardom.generator;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.view.KeyEvent;
import android.view.WindowManager;
import android.graphics.Color;

/**
 * MainActivity — WebView host for the BardomPro APK Generator dashboard.
 *
 * Points at BACKEND_URL (default: https://bardomai.onrender.com).
 * Falls back to a bundled offline page if the backend is unreachable.
 *
 * Build:
 *   cd android
 *   ./gradlew assembleRelease
 *
 * The resulting APK installs the dashboard directly on the device —
 * the user can then trigger builds, download APKs, push to GitHub,
 * and deploy to Render — all from the phone.
 */
public class MainActivity extends Activity {
    private WebView webView;
    private static final String BACKEND_URL =
        "https://bardomai.onrender.com";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.parseColor("#0d1117"));
        getWindow().setNavigationBarColor(Color.parseColor("#0d1117"));
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, int errorCode,
                                        String description, String failingUrl) {
                view.loadDataWithBaseURL("file:///android_asset/",
                    "<html><body style='background:#0d1117;color:#c9d1d9;" +
                    "font-family:sans-serif;padding:24px;text-align:center'>" +
                    "<h2 style='color:#58a6ff'>Offline</h2>" +
                    "<p>Cannot reach the backend. Please check your " +
                    "internet connection and try again.</p>" +
                    "<p style='color:#8b949e;font-size:12px'>" +
                    failingUrl + "</p></body></html>",
                    "text/html", "utf-8", null);
            }

            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        request.grant(request.getResources());
                    }
                });
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        request.grant(request.getResources());
                    }
                });
            }
        });

        // Load backend dashboard
        webView.loadUrl(BACKEND_URL);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView != null && webView.canGoBack()) {
            webView.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.onPause();
        }
        super.onPause();
    }
}
