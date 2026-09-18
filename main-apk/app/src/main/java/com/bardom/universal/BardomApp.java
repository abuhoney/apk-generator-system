package com.bardom.universal;

import android.app.Application;
import android.util.Log;
import androidx.work.Configuration;
import androidx.work.WorkManager;
import com.bardom.universal.functions.FunctionsEngine;

/**
 * BardomApp — Application entry point.
 *
 * Initializes:
 *   - WorkManager (for background tasks: AutoUpdater, LibraryInstaller)
 *   - LocalStorage (encrypted SharedPreferences)
 *   - FunctionsEngine (dynamic functions cache)
 *
 * The app is offline-first: all initialization happens locally.
 * Network calls only happen in background workers (AutoUpdater) or
 * when the user explicitly requests a backend operation (APK build).
 */
public class BardomApp extends Application implements Configuration.Provider {

    private static final String TAG = "BardomApp";
    private static BardomApp instance;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;

        Log.i(TAG, "BardomPro Universal APK Generator v6.0.0 starting...");

        // Initialize encrypted local storage
        LocalStorage.init(this);

        // Initialize WorkManager with our configuration
        WorkManager.initialize(this, getWorkManagerConfiguration());

        // Initialize the FunctionsEngine (reads from local cache)
        FunctionsEngine.getInstance().init(this);

        // Verify security on startup (anti-decompile)
        SecurityShield.verifyOnStartup(this);

        Log.i(TAG, "Initialization complete. Offline-first mode active.");
    }

    public static BardomApp getInstance() {
        return instance;
    }

    @Override
    public Configuration getWorkManagerConfiguration() {
        return new Configuration.Builder()
                .setMinimumLoggingLevel(Log.INFO)
                .build();
    }
}
