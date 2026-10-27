package com.hakom.warehouse;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.FrameLayout;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;

/** One owner of system/cutout/IME space; children (including WebView) receive consumed insets. */
final class SafeArea {
    private SafeArea() {}
    static void setContent(Activity activity, View content) {
        Window window=activity.getWindow();
        WindowCompat.setDecorFitsSystemWindows(window,false);
        window.clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(Color.TRANSPARENT);
        if(Build.VERSION.SDK_INT>=29){window.setStatusBarContrastEnforced(false);window.setNavigationBarContrastEnforced(false);}
        FrameLayout container=new FrameLayout(activity);
        container.setBackgroundColor(Color.rgb(244,247,248));
        container.addView(content,new FrameLayout.LayoutParams(-1,-1));
        activity.setContentView(container);
        WindowCompat.getInsetsController(window,container).show(WindowInsetsCompat.Type.systemBars());
        WindowCompat.getInsetsController(window,container).setAppearanceLightStatusBars(true);
        WindowCompat.getInsetsController(window,container).setAppearanceLightNavigationBars(true);
        ViewCompat.setOnApplyWindowInsetsListener(container,(view,insets)->{
            Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout()|WindowInsetsCompat.Type.ime());
            view.setPadding(safe.left,safe.top,safe.right,safe.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
        container.post(()->ViewCompat.requestApplyInsets(container));
    }
}
