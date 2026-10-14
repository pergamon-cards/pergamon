pub mod commands;
pub mod py;
pub mod scripting;
pub mod settings;

use anyhow::Result;
use serenity::prelude::*;
use sqlx::postgres::{PgConnectOptions, PgPoolOptions, PgSslMode};

use tracing::{error, info};

use crate::settings::Settings;

#[derive(Debug)]
pub struct State {
    pub database: sqlx::PgPool,
}

#[poise::command(prefix_command)]
pub async fn register(ctx: poise::Context<'_, State, anyhow::Error>) -> anyhow::Result<()> {
    poise::builtins::register_application_commands_buttons(ctx).await?;
    Ok(())
}

async fn on_error(error: poise::FrameworkError<'_, State, anyhow::Error>) {
    match error {
        poise::FrameworkError::Setup { error, .. } => panic!("Failed to start bot: {error:?}"),
        poise::FrameworkError::Command { error, ctx, .. } => {
            error!("Error in command `{}`: {error:?}", ctx.command().name);
        }
        error => {
            if let Err(e) = poise::builtins::on_error(error).await {
                error!("Error while handling error: {e}")
            }
        }
    }
}

/// Connects to the database and runs the Discord client until it shuts down.
/// Settings must already be loaded with `Settings::new_global()`.
pub async fn run() -> Result<()> {
    // Configure the client with your Discord bot token in the environment.
    let discord_token = Settings::global().token.as_str();
    // let intents = GatewayIntents::GUILD_MESSAGES | GatewayIntents::DIRECT_MESSAGES | GatewayIntents::MESSAGE_CONTENT;
    let intents = GatewayIntents::non_privileged() | GatewayIntents::MESSAGE_CONTENT;

    // create db connection options
    let db_options = PgConnectOptions::new()
        .host(Settings::global().database.host.as_str())
        .port(Settings::global().database.port)
        .username(Settings::global().database.username.as_str())
        .password(Settings::global().database.password.as_str())
        .database(Settings::global().database.database.as_str())
        .ssl_mode(PgSslMode::Prefer);

    // create db connection pool
    let database = PgPoolOptions::new()
        .max_connections(Settings::global().database.max_connections)
        .connect_with(db_options)
        .await
        .inspect_err(|e| tracing::error!("{}", e.to_string()))?;

    let state = State { database };

    let framework = poise::Framework::builder()
        .setup(move |_ctx, _ready, _framework| Box::pin(async move { Ok(state) }))
        .options(poise::FrameworkOptions {
            commands: vec![commands::lookup(), register()],
            event_handler: |ctx, event, framework, data| Box::pin(event_handler(ctx, event, framework, data)),
            on_error: |error| Box::pin(on_error(error)),
            ..Default::default()
        })
        .build();

    let mut client = serenity::Client::builder(&discord_token, intents).framework(framework).await?;

    let shard_manager = client.shard_manager.clone();

    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.expect("unable to register ctrl+c handler");
        shard_manager.shutdown_all().await;
    });

    tracing::info!("starting serenity client");

    if let Err(why) = client.start().await {
        error!("serenity client error: {why:?}");
    }

    Ok(())
}

async fn event_handler(
    ctx: &serenity::all::Context,
    event: &serenity::all::FullEvent,
    _framework: poise::FrameworkContext<'_, State, anyhow::Error>,
    state: &State,
) -> anyhow::Result<()> {
    match event {
        serenity::all::FullEvent::Ready { data_about_bot, .. } => {
            info!("Logged in as {}", data_about_bot.user.name);
        }
        serenity::all::FullEvent::Message { new_message } => {
            // process message through all inline commands
            commands::lookup_inline(state, ctx.clone(), new_message.clone()).await;
        }
        _ => {}
    }
    Ok(())
}
