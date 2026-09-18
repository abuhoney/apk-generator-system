package com.bardom.universal;

import android.content.Context;
import android.util.Log;
import androidx.work.Constraints;
import androidx.work.NetworkType;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

/**
 * UpdateWorker — The actual WorkManager worker for the AutoUpdater.
 *
 * Checks GitHub for a newer payload version, downloads it if available,
 * and stores it locally. Runs every 12 hours (scheduled by AutoUpdater).
 */
public class UpdateWorker extends Worker {

    private static final String TAG = "UpdateWorker";

    public UpdateWorker(Context ctx, WorkerParameters params) {
        super(ctx, params);
    }

    @Override
    public Result doWork() {
        Log.i(TAG, "Checking for payload updates...");
        String result = AutoUpdater.checkNow(getApplicationContext());
        Log.i(TAG, "Update result: " + result);
        return Result.success();
    }
}
