use anyhow::Result;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use pergamon::settings::Settings;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "pergamon=debug,tower_http=debug".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    Settings::new_global().inspect_err(|e| tracing::error!("{}", e.to_string()))?;

    pergamon::run().await
}
