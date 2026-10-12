package com.aro.led;

import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import com.getcapacitor.BridgeActivity;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends BridgeActivity {

    // Release ESTABLE. BETA seria ".../releases?per_page=1".
    private static final String GITHUB_API_URL =
            "https://api.github.com/repos/JesPezz/AroLED/releases/latest";
    private static final String APK_ASSET = "AroLED.apk";

    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            getBridge().getWebView().addJavascriptInterface(new VersionBridge(), "AndroidApp");
        } catch (Exception ignored) {
        }
        checkForUpdate();
    }

    // Puente para que la web muestre la version de la app.
    private class VersionBridge {
        @JavascriptInterface
        public String getVersionName() {
            return currentVersionName();
        }

        @JavascriptInterface
        public int getVersionCode() {
            try {
                PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
                return pi.versionCode;
            } catch (Exception e) {
                return 0;
            }
        }
    }

    private String currentVersionName() {
        try {
            PackageInfo pi = getPackageManager().getPackageInfo(getPackageName(), 0);
            return pi.versionName;
        } catch (Exception e) {
            return "0";
        }
    }

    // "v2.0" -> 200, "1.3" -> 103 (compara numericamente, sin degradar).
    private static int verKey(String v) {
        if (v == null) return 0;
        v = v.trim();
        if (v.startsWith("v") || v.startsWith("V")) v = v.substring(1);
        int dash = v.indexOf('-');
        if (dash >= 0) v = v.substring(0, dash);
        int plus = v.indexOf('+');
        if (plus >= 0) v = v.substring(0, plus);
        String[] parts = v.split("\\.");
        int[] nums = new int[]{0, 0};
        for (int i = 0; i < parts.length && i < 2; i++) {
            String p = parts[i].replaceAll("[^0-9].*$", "");
            nums[i] = p.isEmpty() ? 0 : Integer.parseInt(p);
        }
        return nums[0] * 100 + nums[1];
    }

    private void checkForUpdate() {
        new Thread(() -> {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(GITHUB_API_URL).openConnection();
                c.setConnectTimeout(8000);
                c.setReadTimeout(8000);
                c.setRequestProperty("User-Agent", "AroLED");
                c.setRequestProperty("Accept", "application/vnd.github+json");
                if (c.getResponseCode() != 200) return;
                StringBuilder sb = new StringBuilder();
                try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream()))) {
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line);
                }
                JSONObject j = new JSONObject(sb.toString());
                final String tag = j.optString("tag_name", "");
                final String notes = j.optString("name", "");
                String apkUrl = null;
                JSONArray assets = j.optJSONArray("assets");
                if (assets != null) {
                    for (int i = 0; i < assets.length(); i++) {
                        JSONObject a = assets.getJSONObject(i);
                        if (APK_ASSET.equals(a.optString("name"))) {
                            apkUrl = a.optString("browser_download_url");
                        }
                    }
                }
                if (apkUrl == null || apkUrl.isEmpty()) return;
                final String url = apkUrl;
                if (verKey(tag) > verKey(currentVersionName())) {
                    final String version = tag;
                    ui.post(() -> promptUpdate(version, url, notes));
                }
            } catch (Exception ignored) {
            }
        }).start();
    }

    private void promptUpdate(String version, String apkUrl, String notes) {
        String msg = "Version " + version + (notes.isEmpty() ? "" : "\n\n" + notes);
        new AlertDialog.Builder(this)
                .setTitle("Actualizar AroLED")
                .setMessage(msg)
                .setCancelable(true)
                .setPositiveButton("Actualizar", (d, w) -> downloadAndInstall(apkUrl))
                .setNegativeButton("Luego", null)
                .show();
    }

    private void downloadAndInstall(String apkUrl) {
        Toast.makeText(this, "Descargando actualizacion...", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                File dir = new File(getCacheDir(), "updates");
                if (!dir.exists()) dir.mkdirs();
                File apk = new File(dir, "aro-update.apk");
                HttpURLConnection c = (HttpURLConnection) new URL(apkUrl).openConnection();
                c.setInstanceFollowRedirects(true);
                c.setConnectTimeout(10000);
                c.setReadTimeout(30000);
                c.setRequestProperty("User-Agent", "AroLED");
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(apk)) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                }
                ui.post(() -> installApk(apk));
            } catch (Exception e) {
                ui.post(() -> Toast.makeText(this, "Fallo la descarga: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }).start();
    }

    private void installApk(File apk) {
        try {
            Uri uri = FileProvider.getUriForFile(this, getPackageName() + ".fileprovider", apk);
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(uri, "application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        } catch (Exception e) {
            Toast.makeText(this, "No se pudo abrir el instalador: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }
}
