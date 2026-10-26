use std::collections::HashMap;

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

        let env: HashMap<String, String> = std::env::vars().collect();

        Self::from_sources(&format!("config/{run_env}"), env)
    }

    /// Loads the config file at `path` (extension optional), then overlays `PERGAMON_*` entries of `env`.
    /// Reads neither the process environment nor the global settings.
    pub fn from_sources(path: &str, env: HashMap<String, String>) -> Result<Self, ConfigError> {
        Config::builder()
            .add_source(File::with_name(path))
            .add_source(Environment::with_prefix("PERGAMON").source(Some(env)))
            .build()?
            .try_deserialize()
    }

    pub fn new_global() -> Result<(), ConfigError> {
        let s = Settings::new()?;

        SETTINGS.set(s).unwrap();

        Ok(())
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

#[cfg(test)]
mod tests {
    use super::*;

    const FILE: &str = r#"
token = "file-token"

[database]
host = "localhost"
port = 5432
username = "postgres"
password = "secret"
database = "pergamon"
max_connections = 5
"#;

    /// Writes `contents` to a unique temp file and returns its path without the extension.
    fn config_file(name: &str, contents: &str) -> String {
        let path = std::env::temp_dir().join(format!("pergamon-settings-{}-{name}", std::process::id()));
        std::fs::write(path.with_extension("toml"), contents).unwrap();
        path.to_str().unwrap().to_string()
    }

    fn env(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    #[test]
    fn loads_the_file() {
        let path = config_file("loads", FILE);

        let settings = Settings::from_sources(&path, HashMap::new()).unwrap();

        assert_eq!(settings.token, "file-token");
        assert_eq!(settings.database.host, "localhost");
        assert_eq!(settings.database.port, 5432);
        assert_eq!(settings.database.max_connections, 5);
    }

    #[test]
    fn env_overrides_the_token() {
        let path = config_file("env-token", FILE);

        let settings = Settings::from_sources(&path, env(&[("PERGAMON_TOKEN", "env-token")])).unwrap();

        assert_eq!(settings.token, "env-token");
    }

    #[test]
    fn ignores_env_without_the_prefix() {
        let path = config_file("env-prefix", FILE);

        let settings = Settings::from_sources(&path, env(&[("TOKEN", "other")])).unwrap();

        assert_eq!(settings.token, "file-token");
    }

    #[test]
    fn nested_env_override_needs_a_separator() {
        let path = config_file("env-nested", FILE);

        // with the default (no) separator, the key does not reach [database]
        let settings = Settings::from_sources(&path, env(&[("PERGAMON_DATABASE__HOST", "db.example.com")])).unwrap();

        assert_eq!(settings.database.host, "localhost");
    }

    #[test]
    fn missing_required_key_is_an_error() {
        let path = config_file("missing-key", &FILE.replace("token = \"file-token\"", ""));

        let err = Settings::from_sources(&path, HashMap::new()).unwrap_err();

        assert!(err.to_string().contains("token"), "{err}");
    }

    #[test]
    fn missing_file_is_an_error() {
        assert!(Settings::from_sources("/nonexistent/pergamon", HashMap::new()).is_err());
    }
}
