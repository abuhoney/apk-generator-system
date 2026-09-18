// loader.js — Payload decryption + injection helper
// Called by index.html's bootstrap function
//
// The actual decryption happens in the Android Java layer (PayloadManager)
// because AES-256-GCM with a device-bound key requires native code.
// This JS file just orchestrates the flow:
//   1. Call Android.getDecryptedPayload() (returns JSON string)
//   2. Parse the JSON
//   3. Inject the engine HTML into the document

(function() {
    'use strict';

    /**
     * Fetch the decrypted payload from the Android layer.
     * The Android layer decrypts it with a device-bound AES-256-GCM key.
     * This means: even if an attacker extracts the payload.enc file from
     * /data/data/, they cannot decrypt it on a different device.
     */
    window.__getPayload = function() {
        if (!window.Android || !Android.getDecryptedPayload) {
            return null;
        }
        try {
            var json = Android.getDecryptedPayload();
            return JSON.parse(json);
        } catch (e) {
            console.error('Payload parse error:', e);
            return null;
        }
    };

    /**
     * Get a specific function's data from the payload.
     */
    window.__getFunction = function(functionId) {
        var payload = window.__bardomPayload || window.__getPayload();
        if (!payload || !payload.functions) return null;
        return payload.functions[functionId] || null;
    };

    /**
     * List all function IDs.
     */
    window.__listFunctions = function() {
        var payload = window.__bardomPayload || window.__getPayload();
        if (!payload || !payload.functions) return [];
        return Object.keys(payload.functions);
    };

    /**
     * Render a function's template into a target element.
     */
    window.__renderFunction = function(functionId, targetEl) {
        var fn = window.__getFunction(functionId);
        if (!fn || !fn.template_html) {
            targetEl.innerHTML = '<p>Function not found: ' + functionId + '</p>';
            return;
        }
        // Create a blob URL for the function's HTML
        var blob = new Blob([fn.template_html], { type: 'text/html' });
        var url = URL.createObjectURL(blob);
        if (targetEl.tagName === 'IFRAME') {
            targetEl.src = url;
        } else {
            targetEl.innerHTML = '<iframe src="' + url + '" style="width:100%;height:100%;border:0"></iframe>';
        }
    };

    /**
     * Build an APK for a function (calls the backend).
     */
    window.__buildApk = function(functionId, options) {
        if (!window.Android || !Android.buildApk) {
            return Promise.resolve({ ok: false, error: 'Android bridge not available' });
        }
        var opts = options ? JSON.stringify(options) : '';
        var result = Android.buildApk(functionId, opts);
        try {
            return Promise.resolve(JSON.parse(result));
        } catch (e) {
            return Promise.resolve({ ok: false, error: 'Parse error: ' + e.message });
        }
    };

    /**
     * Check for payload updates (calls GitHub directly, no backend).
     */
    window.__checkUpdates = function() {
        if (!window.Android || !Android.checkForUpdates) {
            return Promise.resolve({ ok: false, error: 'Android bridge not available' });
        }
        var result = Android.checkForUpdates();
        try {
            return Promise.resolve(JSON.parse(result));
        } catch (e) {
            return Promise.resolve({ ok: false, error: 'Parse error: ' + e.message });
        }
    };

    console.log('loader.js ready — payload bridge initialized');
})();
