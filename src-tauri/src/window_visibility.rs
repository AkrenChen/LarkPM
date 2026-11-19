use tauri::Manager;

fn show_command(visible: bool, minimized: bool) -> i32 {
    if !visible { 0 } else if minimized { 9 } else { 5 }
}

pub fn set_visible(app: &tauri::AppHandle, visible: bool) {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(windows)]
        {
            let target = window.clone();
            let _ = window.run_on_main_thread(move || {
                #[link(name = "user32")]
                extern "system" {
                    fn ShowWindow(window: isize, command: i32) -> i32;
                    fn IsIconic(window: isize) -> i32;
                    fn SetForegroundWindow(window: isize) -> i32;
                }
                if let Ok(handle) = target.hwnd() {
                    // Tao's visibility change reapplies maximized styles and redraws the frame twice.
                    unsafe {
                        let handle = handle.0 as isize;
                        ShowWindow(handle, show_command(visible, IsIconic(handle) != 0));
                        if visible { SetForegroundWindow(handle); }
                    }
                }
            });
        }
        #[cfg(not(windows))]
        if visible {
            if window.is_minimized().unwrap_or(false) { let _ = window.unminimize(); }
            let _ = window.show();
            let _ = window.set_focus();
        } else { let _ = window.hide(); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn showing_hidden_normal_or_maximized_window_does_not_restore_it() {
        assert_eq!(show_command(true, false), 5);
        assert_eq!(show_command(true, true), 9);
        assert_eq!(show_command(false, false), 0);
    }
}
