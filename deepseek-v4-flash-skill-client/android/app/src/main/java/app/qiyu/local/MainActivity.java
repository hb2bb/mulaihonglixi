package app.qiyu.local;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.*;
import android.widget.TextView;
import android.widget.Toast;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.*;
import java.util.UUID;
import java.util.zip.*;

public class MainActivity extends Activity {
    private static final String SECRET = UUID.randomUUID().toString() + UUID.randomUUID().toString();
    private static final Object START_LOCK = new Object();
    private static int activePort = 0;
    private WebView web;
    private String origin;
    private ValueCallback<Uri[]> fileCallback;
    private String pendingBackup;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        KeyVault.init(this);
        TextView loading = new TextView(this);
        loading.setText("栖语\n正在启动本地聊天…"); loading.setGravity(17); setContentView(loading);
        new Thread(() -> {
            try {
                int port;
                synchronized (START_LOCK) {
                    if (activePort == 0) {
                    File runtime = new File(getFilesDir(), "runtime-v1");
                    unpack(runtime);
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                    activePort = Python.getInstance().getModule("android_bootstrap")
                        .callAttr("start", runtime.getAbsolutePath(), getFilesDir().getAbsolutePath(), SECRET).toInt();
                    }
                    port = activePort;
                }
                runOnUiThread(() -> { if (!isDestroyed()) showApp(port); });
            } catch (Exception error) {
                runOnUiThread(() -> loading.setText("本地引擎启动失败。请重新打开应用；已有数据保留。"));
            }
        }, "qiyu-start").start();
    }
    private void unpack(File root) throws IOException {
        root.mkdirs(); String prefix = root.getCanonicalPath() + File.separator;
        try (ZipInputStream zip = new ZipInputStream(getAssets().open("runtime.zip"))) {
            ZipEntry entry; byte[] buffer = new byte[16384];
            while ((entry = zip.getNextEntry()) != null) {
                File file = new File(root, entry.getName());
                if (!file.getCanonicalPath().startsWith(prefix)) throw new IOException("Invalid asset path");
                if (entry.isDirectory()) { file.mkdirs(); continue; }
                file.getParentFile().mkdirs();
                try (OutputStream out = new FileOutputStream(file)) {
                    int count; while ((count = zip.read(buffer)) != -1) out.write(buffer, 0, count);
                }
            }
        }
    }
    private boolean local(Uri url) {
        return url != null && "http".equals(url.getScheme()) && "127.0.0.1".equals(url.getHost()) &&
            origin != null && url.getPort() == Uri.parse(origin).getPort();
    }
    @SuppressWarnings("SetJavaScriptEnabled") private void showApp(int port) {
        origin = "http://127.0.0.1:" + port;
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(true);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return !local(request.getUrl()); }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (local(request.getUrl())) return null;
                return new WebResourceResponse("text/plain", "utf-8", new ByteArrayInputStream(new byte[0]));
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/json");
                startActivityForResult(intent, 10); return true;
            }
            @Override public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                new android.app.AlertDialog.Builder(MainActivity.this).setMessage(message)
                    .setPositiveButton("确认", (d,w) -> result.confirm()).setNegativeButton("取消", (d,w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel()).show(); return true;
            }
        });
        web.addJavascriptInterface(new BackupBridge(), "QiyuBackup");
        web.setOnApplyWindowInsetsListener((v,insets) -> {
            v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom()); return insets;
        });
        CookieManager cookies = CookieManager.getInstance(); cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);
        cookies.setCookie(origin, "qiyu_access=" + SECRET + "; Path=/; HttpOnly; SameSite=Strict", success -> web.loadUrl(origin + "/"));
        setContentView(web);
    }
    public class BackupBridge {
        @JavascriptInterface public void save(String json) {
            if (json == null || json.length() > 32000000) return;
            runOnUiThread(() -> {
                if (pendingBackup != null) return;
                pendingBackup = json;
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("application/json").putExtra(Intent.EXTRA_TITLE, "栖语备份.json");
                startActivityForResult(intent, 11);
            });
        }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request,result,data);
        if (request == 10 && fileCallback != null) {
            fileCallback.onReceiveValue(result == RESULT_OK && data != null && data.getData() != null ? new Uri[]{data.getData()} : null);
            fileCallback = null;
        }
        if (request == 11) {
            final String backup = pendingBackup; pendingBackup = null;
            if (result == RESULT_OK && data != null && data.getData() != null && backup != null) {
                final Uri destination = data.getData();
                new Thread(() -> {
                    try (OutputStream out = getContentResolver().openOutputStream(destination)) {
                        if (out == null) throw new IOException();
                        out.write(backup.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                        runOnUiThread(() -> Toast.makeText(this,"备份已保存",Toast.LENGTH_SHORT).show());
                    } catch (Exception error) {
                        runOnUiThread(() -> Toast.makeText(this,"备份未保存，请重试",Toast.LENGTH_LONG).show());
                    }
                }).start();
            }
        }
    }
    @Override public void onBackPressed() {
        if (web != null) web.evaluateJavascript("if(document.querySelector('dialog[open]'))document.querySelector('dialog[open]').close();", null);
        new android.app.AlertDialog.Builder(this).setMessage("退出栖语？聊天已保存在本机。")
            .setPositiveButton("退出", (d,w) -> finish()).setNegativeButton("继续聊天", null).show();
    }
    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) { web.removeJavascriptInterface("QiyuBackup"); web.destroy(); }
        super.onDestroy();
    }
}
