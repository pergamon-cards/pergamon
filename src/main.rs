mod commands;
mod py;
mod scripting;

use anyhow::Context as _;
use serenity::prelude::*;
use std::env;
// use std::sync::Arc;

use tracing::{error, info};

#[derive(Debug)]
struct State {
    database: sqlx::PgPool,
    // runtime: Arc<rune::runtime::RuntimeContext>,
    // unit: Arc<rune::Unit>,
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

#[shuttle_runtime::main]
async fn main(
    #[shuttle_shared_db::Postgres] database: sqlx::PgPool,
    #[shuttle_runtime::Secrets] secrets: shuttle_runtime::SecretStore,
) -> shuttle_serenity::ShuttleSerenity {
    // Configure the client with your Discord bot token in the environment.
    let discord_token = secrets.get("DISCORD_TOKEN").context("discord token not found")?;
    // let intents = GatewayIntents::GUILD_MESSAGES | GatewayIntents::DIRECT_MESSAGES | GatewayIntents::MESSAGE_CONTENT;
    let intents = GatewayIntents::non_privileged() | GatewayIntents::MESSAGE_CONTENT;

    // let (runtime, unit) = scripting::create_rune_runtime()?;

    let state = State { database, /*runtime, unit*/ };

    let framework = poise::Framework::builder()
        .setup(move |_ctx, _ready, _framework| Box::pin(async move { Ok(state) }))
        .options(poise::FrameworkOptions {
            commands: vec![commands::lookup(), register()],
            event_handler: |ctx, event, framework, data| Box::pin(event_handler(ctx, event, framework, data)),
            on_error: |error| Box::pin(on_error(error)),
            ..Default::default()
        })
        .build();

    let mut client = serenity::Client::builder(&discord_token, intents)
        .framework(framework)
        .await
        .map_err(shuttle_runtime::CustomError::new)?;

    let shard_manager = client.shard_manager.clone();

    tokio::spawn(async move {
        tokio::signal::ctrl_c().await.expect("unable to register ctrl+c handler");
        shard_manager.shutdown_all().await;
    });

    if let Err(why) = client.start().await {
        error!("serenity client error: {why:?}");
    }

    Ok(client.into())
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
