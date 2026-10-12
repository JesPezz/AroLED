package com.aro.led;

import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import com.getcapacitor.BridgeActivity;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends BridgeActivity {

    private static final String UPDATE_JSON_URL = "http://192.168.1.107:8800/ota/aro-led.json";

    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        checkForUpdate();
    }

    private int currentVersionCode() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    private void checkForUpdate() {
        new Thread(() -> {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(UPDATE_JSON_URL).openConnection();
                c.setConnectTimeout(6000);
                c.setReadTimeout(6000);
                if (c.getResponseCode() != 200) return;
                StringBuilder sb = new StringBuilder();
                try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream()))) {
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line);
                }
                JSONObject j = new JSONObject(sb.toString());
                final int remoteCode = j.getInt("versionCode");
                final String apkUrl = j.getString("url");
                final String notes = j.optString("notes", "");
                if (remoteCode > currentVersionCode()) {
                    ui.post(() -> promptUpdate(remoteCode, apkUrl, notes));
                }
            } catch (Exception ignored) {
            }
        }).start();
    }

    private void promptUpdate(int remoteCode, String apkUrl, String notes) {
        String msg = "Nueva version disponible" + (notes.isEmpty() ? "" : "\n\n" + notes);
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
                c.setConnectTimeout(10000);
                c.setReadTimeout(30000);
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
