#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    error::Error,
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};
use tauri::{Manager, RunEvent};

const BACKEND_PORTS: std::ops::RangeInclusive<u16> = 8001..=8010;

struct BackendProcess {
    port: u16,
    child: Mutex<Option<Child>>,
}

fn backend_is_compatible(port: u16) -> bool {
    let address: SocketAddr = match format!("127.0.0.1:{port}").parse() {
        Ok(address) => address,
        Err(_) => return false,
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    if stream
        .write_all(b"GET /openapi.json HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }

    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return false;
    };
    if !headers
        .lines()
        .next()
        .is_some_and(|status| status.contains(" 200 "))
    {
        return false;
    }

    let Ok(spec) = serde_json::from_str::<serde_json::Value>(body) else {
        return false;
    };
    let paths = &spec["paths"];
    spec["info"]["version"] == "0.1.6"
        && paths["/api/news/search"].get("get").is_some()
        && paths["/api/assets/search"].get("get").is_some()
        && paths["/api/forecast"].get("post").is_some()
        && paths["/api/assets/{ticker}"].get("put").is_some()
        && paths["/api/assets/{ticker}"].get("delete").is_some()
}

fn select_backend_port() -> Result<(u16, bool), Box<dyn Error>> {
    for port in BACKEND_PORTS {
        if backend_is_compatible(port) {
            return Ok((port, true));
        }
        if let Ok(listener) = TcpListener::bind(("127.0.0.1", port)) {
            drop(listener);
            return Ok((port, false));
        }
    }
    Err("No available localhost port for the Stock Predictor backend".into())
}

fn python_executable() -> String {
    if let Ok(python) = std::env::var("STOCK_PREDICTOR_PYTHON") {
        if !python.trim().is_empty() {
            return python;
        }
    }

    #[cfg(target_os = "macos")]
    for candidate in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"] {
        if PathBuf::from(candidate).is_file() {
            return candidate.to_string();
        }
    }

    #[cfg(not(target_os = "macos"))]
    for candidate in ["python3", "python"] {
        if Command::new(candidate).arg("--version").output().is_ok() {
            return candidate.to_string();
        }
    }

    "python3".to_string()
}

fn start_backend(app: &tauri::AppHandle) -> Result<(u16, Option<Child>), Box<dyn Error>> {
    let (port, already_running) = select_backend_port()?;
    if already_running {
        return Ok((port, None));
    }

    let backend_root = if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend")
    } else {
        app.path().resource_dir()?.join("backend")
    };
    let script = backend_root.join("start_server.py");
    if !script.is_file() {
        return Err(format!("Bundled backend entry point not found: {}", script.display()).into());
    }

    let app_data_dir = app.path().app_data_dir()?;
    fs::create_dir_all(&app_data_dir)?;
    let source_db = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../backend/stock_predictor_server/data/stock_predictor.db");
    let db_path = if source_db.is_file() {
        source_db
    } else {
        app_data_dir.join("stock_predictor.db")
    };
    let log_path = app_data_dir.join("backend.log");
    let stdout = OpenOptions::new().create(true).append(true).open(&log_path)?;
    let stderr = stdout.try_clone()?;

    let mut child = Command::new(python_executable())
        .arg(&script)
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .current_dir(&backend_root)
        .env("STOCK_PREDICTOR_DB", db_path)
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .spawn()?;

    for _ in 0..80 {
        if backend_is_compatible(port) {
            return Ok((port, Some(child)));
        }
        if let Some(status) = child.try_wait()? {
            return Err(format!(
                "Backend exited before becoming ready ({status}); inspect {}",
                log_path.display()
            )
            .into());
        }
        thread::sleep(Duration::from_millis(250));
    }

    let _ = child.kill();
    let _ = child.wait();
    Err(format!(
        "Backend did not become ready; inspect {}",
        log_path.display()
    )
    .into())
}

#[tauri::command]
fn backend_url(state: tauri::State<'_, BackendProcess>) -> Result<String, String> {
    if state.port == 0 {
        return Err("The backend did not start. Check backend.log in the app data directory.".into());
    }
    Ok(format!("http://127.0.0.1:{}", state.port))
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            let (port, child) = match start_backend(app.handle()) {
                Ok(backend) => backend,
                Err(error) => {
                    eprintln!("Could not start Stock Predictor backend: {error}");
                    (0, None)
                }
            };
            app.manage(BackendProcess {
                port,
                child: Mutex::new(child),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Tauri application");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit) {
            if let Some(state) = handle.try_state::<BackendProcess>() {
                if let Ok(mut process) = state.child.lock() {
                    if let Some(mut child) = process.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        }
    });
}
