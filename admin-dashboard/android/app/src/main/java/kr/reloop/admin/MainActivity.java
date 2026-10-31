package kr.reloop.admin;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import android.window.OnBackInvokedDispatcher;

/**
 * The Reloop dashboard in a WebView. The dashboard and its data stay on the PC server; the phone
 * reaches it at 127.0.0.1:8765 through `adb reverse` (USB), or at an address set on the connect screen.
 */
public class MainActivity extends Activity {
    private static final String DEFAULT_SERVER = "http://127.0.0.1:8765";
    private static final int PICK_FILES = 1;
    private WebView web;
    private LinearLayout connect;
    private EditText address;
    private TextView reason;
    private ValueCallback<Uri[]> pickFiles;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.WHITE);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        connect = connectScreen();
        root.addView(connect, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        keepClearOfSystemBars(root);

        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                if (sameServer(url)) return false;
                // anything outside the dashboard opens in the phone's browser
                try { startActivity(new Intent(Intent.ACTION_VIEW, url)); } catch (ActivityNotFoundException ignored) { }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showConnect("서버에 연결할 수 없습니다. (" + error.getDescription() + ")");
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                // floor plan upload and backup restore
                if (pickFiles != null) pickFiles.onReceiveValue(null);
                pickFiles = callback;
                try {
                    startActivityForResult(params.createIntent(), PICK_FILES);
                } catch (ActivityNotFoundException e) {
                    pickFiles = null;
                    return false;
                }
                return true;
            }
        });
        web.setDownloadListener((url, userAgent, disposition, mimeType, length) -> download(url, userAgent, disposition, mimeType));
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::goBack);
        }
        if (state == null || web.restoreState(state) == null) open();
    }

    private String server() {
        return getSharedPreferences("reloop", MODE_PRIVATE).getString("server", DEFAULT_SERVER);
    }

    private boolean sameServer(Uri url) {
        Uri base = Uri.parse(server());
        return url.getScheme() != null && url.getScheme().equals(base.getScheme())
                && url.getHost() != null && url.getHost().equals(base.getHost()) && url.getPort() == base.getPort();
    }

    private void open() {
        connect.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
        web.loadUrl(server() + "/");
    }

    private void showConnect(String message) {
        reason.setText(message);
        address.setText(server());
        web.setVisibility(View.INVISIBLE);
        connect.setVisibility(View.VISIBLE);
    }

    // Shown when the server cannot be reached: the address can be changed before trying again.
    private LinearLayout connectScreen() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_VERTICAL);
        box.setBackgroundColor(Color.rgb(0xf5, 0xf6, 0xf2));
        int pad = dp(28);
        box.setPadding(pad, pad, pad, pad);
        box.setVisibility(View.GONE);
        TextView title = text("리루프 서버 연결", 22, Color.rgb(0x1f, 0x2e, 0x27));
        title.setTypeface(title.getTypeface(), android.graphics.Typeface.BOLD);
        box.addView(title);
        reason = text("", 14, Color.rgb(0xb0, 0x30, 0x1f));
        reason.setPadding(0, dp(10), 0, dp(18));
        box.addView(reason);
        box.addView(text("서버 주소", 13, Color.rgb(0x43, 0x53, 0x4a)));
        address = new EditText(this);
        address.setSingleLine(true);
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        box.addView(address);
        Button retry = new Button(this);
        retry.setText("연결");
        retry.setOnClickListener(v -> {
            String value = address.getText().toString().trim().replaceAll("/+$", "");
            if (!value.startsWith("http://") && !value.startsWith("https://")) value = "http://" + value;
            getSharedPreferences("reloop", MODE_PRIVATE).edit().putString("server", value).apply();
            open();
        });
        box.addView(retry);
        TextView help = text("USB로 연결했다면 PC에서 adb reverse tcp:8765 tcp:8765 를 실행한 뒤 "
                + DEFAULT_SERVER + " 로 연결하세요. 같은 네트워크라면 PC의 IP 주소와 포트를 입력하세요.", 13, Color.rgb(0x5f, 0x6c, 0x64));
        help.setPadding(0, dp(18), 0, 0);
        box.addView(help);
        return box;
    }

    private TextView text(String value, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        view.setTextColor(color);
        return view;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    // Android 15 and later draw apps edge to edge: pad the content clear of the bars and the keyboard.
    private void keepClearOfSystemBars(View root) {
        if (Build.VERSION.SDK_INT >= 30) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime() | WindowInsets.Type.displayCutout());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return WindowInsets.CONSUMED;
            });
            WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                int dark = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                controller.setSystemBarsAppearance(dark, dark);
            }
        }
    }

    private void download(String url, String userAgent, String disposition, String mimeType) {
        if (!URLUtil.isNetworkUrl(url)) {
            // CSV exports are made in the page (blob:), which the download service cannot fetch
            Toast.makeText(this, "이 파일은 앱에서 내려받을 수 없습니다. PC 브라우저에서 내려받아 주세요.", Toast.LENGTH_LONG).show();
            return;
        }
        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
        String cookies = CookieManager.getInstance().getCookie(url);
        if (cookies != null) request.addRequestHeader("Cookie", cookies);
        request.addRequestHeader("User-Agent", userAgent);
        request.setMimeType(mimeType);
        request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, URLUtil.guessFileName(url, disposition, mimeType));
        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
        Toast.makeText(this, "다운로드 폴더에 저장합니다.", Toast.LENGTH_SHORT).show();
    }

    private void goBack() {
        if (connect.getVisibility() != View.VISIBLE && web.canGoBack()) web.goBack();
        else finish();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        goBack();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == PICK_FILES && pickFiles != null) {
            pickFiles.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            pickFiles = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        web.saveState(state);
    }
}
