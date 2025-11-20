mod commands;
mod scripting;

use serenity::prelude::*;
use std::env;
use std::sync::Arc;

use tracing::{Level, error, info};
use tracing_subscriber::FmtSubscriber;

#[derive(Debug)]
struct State {
    database: sqlx::SqlitePool,
    runtime: Arc<rune::runtime::RuntimeContext>,
    unit: Arc<rune::Unit>,
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

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let subscriber = FmtSubscriber::builder().with_max_level(Level::INFO).finish();

    tracing::subscriber::set_global_default(subscriber).expect("setting default subscriber failed");

    // Configure the client with your Discord bot token in the environment.
    let token = env::var("DISCORD_TOKEN")?;
    // let intents = GatewayIntents::GUILD_MESSAGES | GatewayIntents::DIRECT_MESSAGES | GatewayIntents::MESSAGE_CONTENT;
    let intents = GatewayIntents::non_privileged() | GatewayIntents::MESSAGE_CONTENT;

    let database = sqlx::sqlite::SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(sqlx::sqlite::SqliteConnectOptions::new().filename("data/cards.sqlite").create_if_missing(false))
        .await?;

    let (runtime, unit) = scripting::create_rune_runtime()?;

    let state = State { database, runtime, unit };

    let framework = poise::Framework::builder()
        .setup(move |_ctx, _ready, _framework| Box::pin(async move { Ok(state) }))
        .options(poise::FrameworkOptions {
            commands: vec![commands::lookup(), register()],
            event_handler: |ctx, event, framework, data| Box::pin(event_handler(ctx, event, framework, data)),
            on_error: |error| Box::pin(on_error(error)),
            ..Default::default()
        })
        .build();

    let mut client = serenity::Client::builder(&token, intents).framework(framework).await?;

    let shard_manager = client.shard_manager.clone();

    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.expect("Could not register ctrl+c handler");
        shard_manager.shutdown_all().await;
    });

    if let Err(why) = client.start().await {
        error!("Client error: {why:?}");
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
