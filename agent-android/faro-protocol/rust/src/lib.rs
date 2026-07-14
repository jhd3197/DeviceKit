//! JNI embedding of the Faro agent daemon for Android.
//!
//! This is `Faro/src-tauri/src/agent_host.rs` minus Tauri: the same
//! `faro-agentd` stack (identity, pin store, Noise handshake, ops) hosted
//! in-process, driven from Kotlin (`com.faro.protocol.FaroNative`). Kotlin
//! owns the Android side — foreground service, multicast lock, UI — and polls
//! `nativeStatus()`; every entry point returns a `HostStatus`-shaped JSON
//! string (camelCase, same shape Faro's Settings UI consumes) or
//! `{"error": "..."}`.

use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, OnceLock};
use std::time::Duration;

use anyhow::{bail, Context, Result};
use faro_agent_proto::identity::Identity;
use faro_agentd::{config_path, discovery::Advertisement, identity_path, ops, Config, Daemon};
use jni::objects::{JClass, JString};
use jni::sys::{jboolean, jint, jstring};
use jni::JNIEnv;
use tokio::net::TcpListener;
use tokio::sync::Mutex;

const PAIRING_WINDOW: Duration = Duration::from_secs(10 * 60);
const DEFAULT_PORT: u16 = 8722;

struct Running {
    daemon: Daemon,
    port: u16,
    advert: Option<Advertisement>,
    accept_task: tokio::task::JoinHandle<()>,
}

struct Inner {
    dir: PathBuf,
    running: Option<Running>,
}

struct Host {
    rt: tokio::runtime::Runtime,
    inner: Mutex<Inner>,
    /// Bumped on every pairing open/close so a stale expiry timer can tell it
    /// lost the race and must not touch newer state.
    window_seq: AtomicU64,
}

static HOST: OnceLock<Arc<Host>> = OnceLock::new();

fn host() -> Result<Arc<Host>> {
    HOST.get().cloned().context("FaroNative.nativeInit was never called")
}

impl Host {
    async fn start(&self, port: u16) -> Result<()> {
        let mut inner = self.inner.lock().await;
        if inner.running.is_some() {
            return Ok(());
        }
        let dir = inner.dir.clone();
        std::fs::create_dir_all(&dir).ok();
        let identity = Identity::load_or_create(&identity_path(&dir))?;
        let config = Config::load(&config_path(&dir))?;
        let fingerprint = identity.fingerprint();
        let info = ops::system_info();

        let listener = match TcpListener::bind(("0.0.0.0", port)).await {
            Ok(l) => l,
            Err(e) if e.kind() == std::io::ErrorKind::AddrInUse => {
                bail!("port {port} is already in use")
            }
            Err(e) => return Err(e).with_context(|| format!("bind 0.0.0.0:{port}")),
        };

        let daemon = Daemon::new(identity, config, dir).with_on_paired(|name, _key| {
            log::info!("faro-agent: paired with controller '{name}'");
        });

        let advert = match Advertisement::publish(port, &fingerprint, &info.os, false) {
            Ok(ad) => Some(ad),
            Err(e) => {
                log::warn!("faro-agent: mDNS unavailable: {e:#} — reachable by IP only");
                None
            }
        };

        let serve_daemon = daemon.clone();
        let accept_task = tokio::spawn(async move {
            if let Err(e) = faro_agentd::serve(listener, serve_daemon).await {
                log::warn!("faro-agent: stopped serving: {e:#}");
            }
        });

        inner.running = Some(Running { daemon, port, advert, accept_task });
        Ok(())
    }

    async fn stop(&self) {
        if let Some(r) = self.inner.lock().await.running.take() {
            r.accept_task.abort();
            // Dropping `advert` unregisters the mDNS record; dropping the
            // listener (inside the aborted task) frees the port.
        }
        self.window_seq.fetch_add(1, Ordering::SeqCst);
    }

    async fn status(&self) -> Result<serde_json::Value> {
        let inner = self.inner.lock().await;
        let dir = inner.dir.clone();
        let identity = Identity::load_or_create(&identity_path(&dir))?;
        let info = ops::system_info();

        let (running, port, config, pairing) = match &inner.running {
            Some(r) => {
                let cfg = r.daemon.config.lock().await.clone();
                let pairing =
                    match (r.daemon.pairing_code().await, r.daemon.pairing_remaining().await) {
                        (Some(code), Some(left)) => Some(serde_json::json!({
                            "code": code,
                            "remainingSecs": left.as_secs(),
                        })),
                        _ => None,
                    };
                (true, r.port, cfg, pairing)
            }
            None => (false, DEFAULT_PORT, Config::load(&config_path(&dir))?, None),
        };

        Ok(serde_json::json!({
            "running": running,
            "port": port,
            "hostname": info.hostname,
            "os": info.os,
            "fingerprint": identity.fingerprint(),
            "allowExec": config.policy.allow_exec,
            "allowWrite": config.policy.allow_write,
            "peers": config.peers.iter().map(|p| serde_json::json!({
                "name": p.name,
                "publicKey": p.public_key,
                "fingerprint": faro_agent_proto::decode_public(&p.public_key)
                    .map(|k| faro_agent_proto::fingerprint_of(&k))
                    .unwrap_or_else(|_| "?".into()),
                "pairedAt": p.paired_at,
            })).collect::<Vec<_>>(),
            "pairing": pairing,
        }))
    }

    async fn open_pairing(self: &Arc<Self>) -> Result<()> {
        let code = faro_agent_proto::generate_code();
        {
            let mut inner = self.inner.lock().await;
            let Some(r) = inner.running.as_mut() else {
                bail!("enable the agent first");
            };
            r.daemon.open_pairing(code, PAIRING_WINDOW).await;
            if let Some(ad) = r.advert.as_mut() {
                let _ = ad.set_pairable(true);
            }
        }
        // Drop the advertised flag when this window expires — unless a newer
        // window (or a stop) superseded it in the meantime.
        let seq = self.window_seq.fetch_add(1, Ordering::SeqCst) + 1;
        let timer_host = Arc::clone(self);
        tokio::spawn(async move {
            tokio::time::sleep(PAIRING_WINDOW).await;
            if timer_host.window_seq.load(Ordering::SeqCst) != seq {
                return;
            }
            let mut inner = timer_host.inner.lock().await;
            if let Some(r) = inner.running.as_mut() {
                r.daemon.close_pairing().await;
                if let Some(ad) = r.advert.as_mut() {
                    let _ = ad.set_pairable(false);
                }
            }
        });
        Ok(())
    }

    async fn close_pairing(&self) {
        self.window_seq.fetch_add(1, Ordering::SeqCst);
        let mut inner = self.inner.lock().await;
        if let Some(r) = inner.running.as_mut() {
            r.daemon.close_pairing().await;
            if let Some(ad) = r.advert.as_mut() {
                let _ = ad.set_pairable(false);
            }
        }
    }

    /// Mutate the persisted config, applying to the live daemon when running
    /// (same live/disk split as agent_host.rs set_policy/revoke_peer).
    async fn edit_config(&self, f: impl FnOnce(&mut Config)) -> Result<()> {
        let inner = self.inner.lock().await;
        let path = config_path(&inner.dir);
        match &inner.running {
            Some(r) => {
                let mut cfg = r.daemon.config.lock().await;
                f(&mut cfg);
                cfg.save(&path)?;
            }
            None => {
                let mut cfg = Config::load(&path)?;
                f(&mut cfg);
                cfg.save(&path)?;
            }
        }
        Ok(())
    }

    /// Re-publish the mDNS record so a device-name change shows up live.
    async fn republish(&self) {
        let mut inner = self.inner.lock().await;
        let id_path = identity_path(&inner.dir);
        if let Some(r) = inner.running.as_mut() {
            let pairable = r.daemon.pairing_code().await.is_some();
            let identity = Identity::load_or_create(&id_path).ok();
            let fp = identity.map(|i| i.fingerprint()).unwrap_or_default();
            let os = ops::system_info().os;
            r.advert = Advertisement::publish(r.port, &fp, &os, pairable).ok();
        }
    }
}

// ---------- JNI plumbing ----------

fn jstr(env: &mut JNIEnv, s: &JString) -> Result<String> {
    Ok(env.get_string(s).context("read Java string")?.into())
}

fn to_jstring(env: &JNIEnv, s: String) -> jstring {
    env.new_string(s).map(|s| s.into_raw()).unwrap_or(std::ptr::null_mut())
}

/// Run `f` on the host runtime and return the resulting status (or error) JSON.
fn with_host_status(
    env: &JNIEnv,
    f: impl FnOnce(&Arc<Host>) -> Result<()>,
) -> jstring {
    let out = (|| -> Result<serde_json::Value> {
        let host = host()?;
        f(&host)?;
        host.rt.block_on(host.status())
    })()
    .unwrap_or_else(|e| serde_json::json!({ "error": format!("{e:#}") }));
    to_jstring(env, out.to_string())
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeInit(
    mut env: JNIEnv,
    _class: JClass,
    config_dir: JString,
    device_name: JString,
) {
    android_logger::init_once(
        android_logger::Config::default()
            .with_max_level(log::LevelFilter::Info)
            .with_tag("faro-agent"),
    );
    let Ok(dir) = jstr(&mut env, &config_dir) else { return };
    if let Ok(name) = jstr(&mut env, &device_name) {
        if !name.trim().is_empty() {
            std::env::set_var("FARO_AGENT_NAME", name.trim());
        }
    }
    // dirs::home_dir() reads $HOME on Android; give SystemInfo a sensible root.
    if std::env::var_os("HOME").is_none() {
        std::env::set_var("HOME", "/storage/emulated/0");
    }
    let _ = HOST.set(Arc::new(Host {
        rt: tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .expect("tokio runtime"),
        inner: Mutex::new(Inner { dir: PathBuf::from(dir), running: None }),
        window_seq: AtomicU64::new(0),
    }));
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeSetEnabled(
    env: JNIEnv,
    _class: JClass,
    enabled: jboolean,
    port: jint,
) -> jstring {
    with_host_status(&env, |host| {
        host.rt.block_on(async {
            if enabled != 0 {
                let port = if port > 0 { port as u16 } else { DEFAULT_PORT };
                host.start(port).await
            } else {
                host.stop().await;
                Ok(())
            }
        })
    })
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeStatus(
    env: JNIEnv,
    _class: JClass,
) -> jstring {
    with_host_status(&env, |_| Ok(()))
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeOpenPairing(
    env: JNIEnv,
    _class: JClass,
) -> jstring {
    with_host_status(&env, |host| host.rt.block_on(host.open_pairing()))
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeClosePairing(
    env: JNIEnv,
    _class: JClass,
) -> jstring {
    with_host_status(&env, |host| {
        host.rt.block_on(host.close_pairing());
        Ok(())
    })
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeSetPolicy(
    env: JNIEnv,
    _class: JClass,
    allow_exec: jboolean,
    allow_write: jboolean,
) -> jstring {
    with_host_status(&env, |host| {
        host.rt.block_on(host.edit_config(|cfg| {
            cfg.policy.allow_exec = allow_exec != 0;
            cfg.policy.allow_write = allow_write != 0;
        }))
    })
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeRevokePeer(
    mut env: JNIEnv,
    _class: JClass,
    public_key: JString,
) -> jstring {
    let key = match jstr(&mut env, &public_key) {
        Ok(k) => k,
        Err(e) => return to_jstring(&env, serde_json::json!({"error": e.to_string()}).to_string()),
    };
    with_host_status(&env, |host| {
        host.rt.block_on(host.edit_config(|cfg| {
            cfg.peers.retain(|p| p.public_key != key);
        }))
    })
}

#[no_mangle]
pub extern "system" fn Java_com_faro_protocol_FaroNative_nativeSetDeviceName(
    mut env: JNIEnv,
    _class: JClass,
    device_name: JString,
) -> jstring {
    let name = match jstr(&mut env, &device_name) {
        Ok(n) => n,
        Err(e) => return to_jstring(&env, serde_json::json!({"error": e.to_string()}).to_string()),
    };
    with_host_status(&env, |host| {
        if name.trim().is_empty() {
            std::env::remove_var("FARO_AGENT_NAME");
        } else {
            std::env::set_var("FARO_AGENT_NAME", name.trim());
        }
        host.rt.block_on(host.republish());
        Ok(())
    })
}
