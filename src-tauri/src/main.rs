#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{BufRead, BufReader, Write}, process::{Child, ChildStdin, ChildStdout, Command, Stdio}, sync::Mutex};
use std::os::windows::process::CommandExt;
use tauri::{Manager, State, menu::{Menu, MenuItem}, tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState}};
use serde_json::{json, Value};
use tauri_plugin_window_state::{AppHandleExt, StateFlags};

fn window_state_flags() -> StateFlags {
    StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED
}

struct Bridge { child: Child, input: ChildStdin, output: BufReader<ChildStdout> }
impl Drop for Bridge { fn drop(&mut self) { let _ = self.child.kill(); let _ = self.child.wait(); } }
struct Backend(Mutex<Option<Bridge>>);

#[tauri::command]
fn open_auth_url(url: String) -> Result<(),String> {
    if !url.starts_with("https://accounts.feishu.cn/open-apis/authen/v1/authorize?") || url.contains(['\r','\n','"']) {
        return Err("只允许打开飞书授权链接".into());
    }
    Command::new("rundll32.exe").arg("url.dll,FileProtocolHandler").arg(url).creation_flags(0x08000000).spawn().map_err(|e|e.to_string())?;
    Ok(())
}

#[tauri::command]
async fn rpc(app: tauri::AppHandle, _backend: State<'_, Backend>, method: String, params: Option<Value>) -> Result<Value,String> {
    let request = json!({"method":method,"params":params.unwrap_or(json!({}))});
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<Backend>();
        let mut guard = state.0.lock().map_err(|_| "任务服务锁定失败")?;
        if guard.is_none() {
            let resource = app.path().resource_dir().map_err(|e|e.to_string())?;
            let path = resource.join("sidecar").join("larkpm-backend.exe");
            let mut cmd = if cfg!(debug_assertions) {
                let mut c = Command::new("python");
                c.args(["-X", "utf8", "-u"]).arg(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../backend/service.py")); c
            } else if path.exists() { Command::new(path) }
            else { return Err("缺少 sidecar/larkpm-backend.exe，请完整解压便携包".into()); };
            let mut child = cmd.creation_flags(0x08000000).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn().map_err(|e|format!("启动任务服务失败：{e}"))?;
            let input = child.stdin.take().ok_or("无法创建输入管道")?;
            let output = BufReader::new(child.stdout.take().ok_or("无法创建输出管道")?);
            *guard = Some(Bridge { child,input,output });
        }
        let bridge = guard.as_mut().unwrap();
        let exchange = (|| -> Result<Value,String> {
            writeln!(bridge.input,"{}",request).map_err(|e|e.to_string())?;
            bridge.input.flush().map_err(|e|e.to_string())?;
            let mut line = String::new();
            bridge.output.read_line(&mut line).map_err(|e|e.to_string())?;
            if line.is_empty() { return Err("任务服务已退出，请重试".into()); }
            serde_json::from_str(&line).map_err(|e|e.to_string())
        })();
        match exchange {
            Ok(response) => if let Some(error) = response.get("error").and_then(Value::as_str) { Err(error.to_owned()) } else { Ok(response["result"].clone()) },
            Err(error) => { *guard = None; Err(error) }
        }
    }).await.map_err(|e|e.to_string())?
}

fn show(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") { let _=w.show(); let _=w.unminimize(); let _=w.set_focus(); }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app,_,_|show(app)))
        .plugin(tauri_plugin_window_state::Builder::default().with_state_flags(window_state_flags()).build())
        .manage(Backend(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![rpc,open_auth_url])
        .setup(|app| {
            if cfg!(debug_assertions) {
                if let Some(window) = app.get_webview_window("main") { window.set_title("LarkPM · 开发验收窗口")?; }
            }
            let open = MenuItem::with_id(app,"open","打开 LarkPM",true,None::<&str>)?;
            let quit = MenuItem::with_id(app,"quit","退出",true,None::<&str>)?;
            let menu = Menu::with_items(app,&[&open,&quit])?;
            let mut pixels = vec![0u8;32*32*4];
            for y in 0..32 { for x in 0..32 { let i=(y*32+x)*4; pixels[i..i+4].copy_from_slice(if (7..12).contains(&x) || ((20..25).contains(&y) && (7..25).contains(&x)) { &[240,249,248,255] } else { &[28,112,106,255] }); } }
            TrayIconBuilder::new().icon(tauri::image::Image::new_owned(pixels,32,32)).tooltip("LarkPM · 需求工作台")
                .menu(&menu).show_menu_on_left_click(false)
                .on_menu_event(|app,event|match event.id.as_ref() { "open"=>show(app), "quit"=>app.exit(0), _=>{} })
                .on_tray_icon_event(|tray,event|if let TrayIconEvent::Click {button:MouseButton::Left,button_state:MouseButtonState::Up,..}=event { show(tray.app_handle()); }).build(app)?;
            Ok(())
        })
        .on_window_event(|window,event|if let tauri::WindowEvent::CloseRequested {api,..}=event { api.prevent_close(); let _=window.app_handle().save_window_state(window_state_flags()); let _=window.hide(); })
        .build(tauri::generate_context!()).expect("无法初始化 LarkPM")
        .run(|app,event|if let tauri::RunEvent::Exit = event { if let Ok(mut backend)=app.state::<Backend>().0.lock() { *backend=None; } });
}
