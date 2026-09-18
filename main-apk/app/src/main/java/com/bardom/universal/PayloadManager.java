package com.bardom.universal;

import android.content.Context;
import android.util.Log;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;

/**
 * PayloadManager — Encrypts and decrypts the payload blob.
 *
 * The payload contains the full functions/ tree (all HTML/CSS/JS/config/
 * strings) and is downloaded from GitHub on first install.
 *
 * Security model:
 *   - Payload is stored at app/files/payload.enc (encrypted, AES-256-GCM)
 *   - The encryption key is device-bound: derived from
 *     (device_id + android_id + app_signature_hash)
 *   - This means a payload encrypted on device A CANNOT be decrypted
 *     on device B — even if the attacker copies the file.
 *   - The payload is decrypted in MEMORY only, then injected into the
 *     WebView. It is never written to disk in plaintext.
 *
 * Why this defeats Apktool/Jadx:
 *   - The payload is NOT in the APK (it's downloaded at runtime)
 *   - Even if extracted from /data/data/, it's encrypted with a key
 *     that's only derivable on the original device
 *   - The .env / Firebase keys / bot tokens are on the BACKEND,
 *     not in the APK or payload
 */
public final class PayloadManager {

    private static final String TAG = "PayloadManager";
    private static final String PAYLOAD_FILE = "payload.enc";
    private static final String ALGO = "AES/GCM/NoPadding";
    private static final int GCM_TAG_LENGTH = 128;  // bits
    private static final int GCM_IV_LENGTH = 12;    // bytes
    private static final int SALT_LENGTH = 32;      // bytes

    private PayloadManager() {}

    /**
     * Derive the device-bound encryption key.
     *
     * key = SHA-256(device_id + android_id + app_signature)
     *
     * The app_signature is the SHA-256 of the APK signing certificate —
     * this means if the APK is re-signed with a different key, the
     * derived key changes and the payload cannot be decrypted.
     */
    private static SecretKey deriveKey(Context ctx) {
        try {
            String deviceId = LocalStorage.getDeviceId();
            String androidId = android.provider.Settings.Secure.getString(
                    ctx.getContentResolver(),
                    android.provider.Settings.Secure.ANDROID_ID);

            // Get the app signature hash
            String sigHash = SecurityShield.verifySignature(ctx)
                    ? getAppSignatureHash(ctx) : "unsigned";

            String combined = deviceId + "|" + androidId + "|" + sigHash;
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] keyBytes = md.digest(combined.getBytes(StandardCharsets.UTF_8));

            return new SecretKeySpec(keyBytes, "AES");
        } catch (Exception e) {
            Log.e(TAG, "deriveKey failed: " + e.getMessage());
            throw new RuntimeException("Key derivation failed", e);
        }
    }

    private static String getAppSignatureHash(Context ctx) {
        try {
            android.content.pm.PackageManager pm = ctx.getPackageManager();
            android.content.pm.Signature[] sigs = pm.getPackageInfo(
                    ctx.getPackageName(),
                    android.content.pm.PackageManager.GET_SIGNATURES).signatures;
            if (sigs == null || sigs.length == 0) return "unsigned";
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(sigs[0].toByteArray());
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            return "error";
        }
    }

    /**
     * Encrypt a payload and store it locally.
     *
     * Format:
     *   [salt (32 bytes)] [IV (12 bytes)] [ciphertext + GCM tag]
     *
     * The salt is random per-encryption (prevents identical plaintext
     * producing identical ciphertext).
     */
    public static boolean encryptAndStore(Context ctx, String plaintextJson) {
        try {
            File payloadFile = new File(ctx.getFilesDir(), PAYLOAD_FILE);
            SecretKey key = deriveKey(ctx);

            // Generate random salt + IV
            SecureRandom random = new SecureRandom();
            byte[] salt = new byte[SALT_LENGTH];
            byte[] iv = new byte[GCM_IV_LENGTH];
            random.nextBytes(salt);
            random.nextBytes(iv);

            // Derive the actual encryption key from the master key + salt
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(key.getEncoded());
            md.update(salt);
            byte[] finalKey = md.digest();
            SecretKey encKey = new SecretKeySpec(finalKey, "AES");

            // Encrypt
            Cipher cipher = Cipher.getInstance(ALGO);
            cipher.init(Cipher.ENCRYPT_MODE, encKey, new GCMParameterSpec(GCM_TAG_LENGTH, iv));
            byte[] ciphertext = cipher.doFinal(plaintextJson.getBytes(StandardCharsets.UTF_8));

            // Write: salt + iv + ciphertext
            try (FileOutputStream fos = new FileOutputStream(payloadFile)) {
                fos.write(salt);
                fos.write(iv);
                fos.write(ciphertext);
            }

            Log.i(TAG, "Payload encrypted: " + payloadFile.length() + " bytes");
            return true;
        } catch (Exception e) {
            Log.e(TAG, "encryptAndStore failed: " + e.getMessage());
            return false;
        }
    }

    /**
     * Decrypt the locally-stored payload and return as JSON string.
     * Called by the WebView's JS bridge to get the engine + functions.
     */
    public static String getDecryptedPayload(Context ctx) {
        try {
            File payloadFile = new File(ctx.getFilesDir(), PAYLOAD_FILE);
            if (!payloadFile.exists()) {
                Log.w(TAG, "Payload file not found");
                return "{}";
            }

            byte[] fileData = new byte[(int) payloadFile.length()];
            try (FileInputStream fis = new FileInputStream(payloadFile)) {
                fis.read(fileData);
            }

            // Extract salt (32) + IV (12) + ciphertext (rest)
            int offset = 0;
            byte[] salt = Arrays.copyOfRange(fileData, offset, offset + SALT_LENGTH);
            offset += SALT_LENGTH;
            byte[] iv = Arrays.copyOfRange(fileData, offset, offset + GCM_IV_LENGTH);
            offset += GCM_IV_LENGTH;
            byte[] ciphertext = Arrays.copyOfRange(fileData, offset, fileData.length);

            // Derive the same key
            SecretKey key = deriveKey(ctx);
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(key.getEncoded());
            md.update(salt);
            byte[] finalKey = md.digest();
            SecretKey encKey = new SecretKeySpec(finalKey, "AES");

            // Decrypt
            Cipher cipher = Cipher.getInstance(ALGO);
            cipher.init(Cipher.DECRYPT_MODE, encKey, new GCMParameterSpec(GCM_TAG_LENGTH, iv));
            byte[] plaintext = cipher.doFinal(ciphertext);

            String result = new String(plaintext, StandardCharsets.UTF_8);
            Log.i(TAG, "Payload decrypted: " + result.length() + " chars");
            return result;
        } catch (Exception e) {
            Log.e(TAG, "getDecryptedPayload failed: " + e.getMessage());
            return "{}";
        }
    }

    /**
     * Check if the payload file exists locally.
     */
    public static boolean payloadExists(Context ctx) {
        File f = new File(ctx.getFilesDir(), PAYLOAD_FILE);
        return f.exists() && f.length() > 100;
    }
}
