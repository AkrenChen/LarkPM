use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf, sync::Mutex};
use tauri::Manager;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct DesktopPreferences {
    pub shortcut: String,
    pub show_taskbar: bool,
}

impl Default for DesktopPreferences {
    fn default() -> Self { Self { shortcut: String::new(), show_taskbar: true } }
}

impl DesktopPreferences {
    fn validate(&mut self) -> Result<(), String> {
        self.shortcut = self.shortcut.trim().to_owned();
        if self.shortcut.is_empty() { return Ok(()); }
        if self.shortcut.len() > 100 || !self.shortcut.split('+').any(|part| matches!(part.to_ascii_lowercase().as_str(), "ctrl" | "control" | "alt" | "super" | "meta" | "command" | "commandorcontrol")) {
            return Err("快捷键需包含 Ctrl、Alt 或 Win，避免占用普通输入按键".into());
        }
        self.shortcut = self.shortcut.parse::<Shortcut>().map_err(|_| "快捷键格式无效")?.to_string();
        Ok(())
    }
}

#[derive(Default)]
pub struct DesktopState(pub Mutex<(DesktopPreferences, Option<String>)>);

fn path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let folder = std::env::var_os("LARKPM_WINDOW_CONFIG_DIR").map(PathBuf::from)
        .map(Ok).unwrap_or_else(|| app.path().app_config_dir().map_err(|e| e.to_string()))?;
    Ok(folder.join("desktop-preferences.json"))
}

pub fn initialize(app: &tauri::AppHandle) {
    let state = app.state::<DesktopState>();
    let mut current = state.0.lock().unwrap();
    let loaded = (|| -> Result<DesktopPreferences, String> {
        let file = path(app)?;
        if !file.exists() { return Ok(DesktopPreferences::default()); }
        let mut settings: DesktopPreferences = serde_json::from_slice(&fs::read(file).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        settings.validate()?;
        Ok(settings)
    })();
    match loaded {
        Ok(settings) => current.0 = settings,
        Err(error) => current.1 = Some(format!("窗口设置读取失败：{error}")),
    }
    if !current.0.shortcut.is_empty() {
        if let Err(error) = app.global_shortcut().register(current.0.shortcut.as_str()) {
            current.1 = Some(format!("唤起快捷键不可用，请在设置中更换：{error}"));
        }
    }
    if let Some(window) = app.get_webview_window("main") {
        if let Err(error) = window.set_skip_taskbar(!current.0.show_taskbar) {
            current.1 = Some(format!("任务栏设置应用失败：{error}"));
        }
    }
}

#[tauri::command]
pub fn desktop_preferences_get(state: tauri::State<'_, DesktopState>) -> Result<serde_json::Value, String> {
    let current = state.0.lock().map_err(|_| "窗口设置锁定失败")?;
    Ok(serde_json::json!({"settings": current.0, "error": current.1}))
}

#[tauri::command]
pub fn desktop_preferences_save(app: tauri::AppHandle, state: tauri::State<'_, DesktopState>, mut settings: DesktopPreferences) -> Result<DesktopPreferences, String> {
    settings.validate()?;
    let mut current = state.0.lock().map_err(|_| "窗口设置锁定失败")?;
    let changed = settings.shortcut != current.0.shortcut;
    let register_new = !settings.shortcut.is_empty() && (changed || !app.global_shortcut().is_registered(settings.shortcut.as_str()));
    if register_new { app.global_shortcut().register(settings.shortcut.as_str()).map_err(|e| format!("快捷键不可用，可能已被占用：{e}"))?; }
    let result = (|| -> Result<(), String> {
        let window = app.get_webview_window("main").ok_or("主窗口不可用")?;
        window.set_skip_taskbar(!settings.show_taskbar).map_err(|e| e.to_string())?;
        let file = path(&app)?;
        fs::create_dir_all(file.parent().unwrap()).map_err(|e| e.to_string())?;
        let temporary = file.with_extension("tmp");
        fs::write(&temporary, serde_json::to_vec_pretty(&settings).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        fs::rename(&temporary, &file).map_err(|e| e.to_string())?;
        Ok(())
    })();
    if let Err(error) = result {
        if register_new { let _ = app.global_shortcut().unregister(settings.shortcut.as_str()); }
        if let Some(window) = app.get_webview_window("main") { let _ = window.set_skip_taskbar(!current.0.show_taskbar); }
        return Err(format!("窗口设置保存失败：{error}"));
    }
    if changed && !current.0.shortcut.is_empty() { let _ = app.global_shortcut().unregister(current.0.shortcut.as_str()); }
    *current = (settings.clone(), None);
    Ok(settings)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn defaults_keep_taskbar_and_do_not_steal_a_shortcut() {
        let value: DesktopPreferences = serde_json::from_str("{}").unwrap();
        assert!(value.show_taskbar);
        assert!(value.shortcut.is_empty());
    }
    #[test]
    fn shortcut_validation_and_persistence() {
        let mut value = DesktopPreferences { shortcut: "Ctrl+Alt+K".into(), show_taskbar: false };
        value.validate().unwrap();
        let mut loaded: DesktopPreferences = serde_json::from_str(&serde_json::to_string(&value).unwrap()).unwrap();
        loaded.validate().unwrap();
        assert_eq!(value, loaded);
        for shortcut in ["S", "Shift+S", "Ctrl+NotAKey"] {
            let mut invalid = DesktopPreferences { shortcut: shortcut.into(), ..Default::default() };
            assert!(invalid.validate().is_err());
        }
    }
}
