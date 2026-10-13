use config::{Config, ConfigError, Environment, File};
use once_cell::sync::OnceCell;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Settings {
    // pub server: Server,
    pub token: String,
    pub database: Database,
}

// #[derive(Debug, Deserialize)]
// pub struct Server {
//     pub host: String,
//     pub port: u16,
// }

#[derive(Debug, Deserialize)]
pub struct Database {
    pub host: String,
    pub port: u16,
    pub username: String,
    pub password: String,
    pub database: String,
    pub max_connections: u32,
}

static SETTINGS: OnceCell<Settings> = OnceCell::new();

impl Settings {
    pub fn new() -> Result<Self, ConfigError> {
        let run_env = std::env::var("PERGAMON_RUN_ENV").unwrap_or_else(|_| "dev".into());

        tracing::info!("loading settings for {run_env} environment");

        let settings = Config::builder()
            .add_source(File::with_name(&format!("config/{run_env}")))
            .add_source(Environment::with_prefix("PERGAMON"))
            .build()?;

        settings.try_deserialize()
    }

    pub fn new_global() -> Result<(), ConfigError> {
        let s = Settings::new()?;

        Ok(SETTINGS.set(s).unwrap())
    }

    pub fn global() -> &'static Self {
        match SETTINGS.get() {
            Some(settings) => settings,
            None => {
                tracing::error!("settings should be initialized before being accessed");
                panic!();
            }
        }
    }
}
