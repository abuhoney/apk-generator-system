package com.bardom.universal;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.ProgressBar;
import android.widget.TextView;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;

/**
 * SplashActivity — First-install progress bar.
 *
 * On first launch:
 *   1. Checks if encrypted payload exists locally
 *   2. If not, downloads from GitHub with a progress bar
 *   3. Decrypts + verifies with device-bound key
 *   4. Stores encrypted payload locally
 *   5. Launches MainActivity
 *
 * On subsequent launches:
 *   - Payload already exists → skip directly to MainActivity (fast)
 *   - AutoUpdater checks for updates in background (WorkManager)
 */
public class SplashActivity extends Activity {

    private static final String TAG = "SplashActivity";
    private ProgressBar progressBar;
    private TextView tvStage;
    private TextView tvPercent;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_splash);

        progressBar = findViewById(R.id.progressBar);
        tvStage = findViewById(R.id.tvStage);
        tvPercent = findViewById(R.id.tvPercent);

        // Check if payload is already downloaded
        if (LocalStorage.isPayloadInstalled()) {
            // Fast path: skip to MainActivity
            tvStage.setText("Ready");
            tvPercent.setText("100%");
            progressBar.setProgress(100);
            new Handler(Looper.getMainLooper()).postDelayed(this::launchMain, 500);
        } else {
            // First install: download payload with progress bar
            startPayloadDownload();
        }
    }

    private void startPayloadDownload() {
        // Enqueue the LibraryInstallerWorker to download payload from GitHub
        OneTimeWorkRequest downloadWork =
                new OneTimeWorkRequest.Builder(LibraryInstallerWorker.class)
                        .build();
        WorkManager.getInstance(this).enqueue(downloadWork);

        // Poll for progress (the worker writes progress to LocalStorage)
        Handler handler = new Handler(Looper.getMainLooper());
        handler.postDelayed(new Runnable() {
            @Override
            public void run() {
                int progress = LocalStorage.getPayloadProgress();
                String stage = LocalStorage.getPayloadStage();
                progressBar.setProgress(progress);
                tvStage.setText(stage != null ? stage : "Working...");
                tvPercent.setText(progress + "%");

                if (progress >= 100) {
                    launchMain();
                } else if (progress < 0) {
                    // Error occurred
                    tvStage.setText("Download failed. Retrying...");
                    LocalStorage.resetPayloadProgress();
                    startPayloadDownload();
                } else {
                    handler.postDelayed(this, 500);
                }
            }
        }, 500);
    }

    private void launchMain() {
        startActivity(new Intent(this, MainActivity.class));
        finish();
    }
}
