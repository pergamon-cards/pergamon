use std::collections::HashSet;
use std::env;
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;

use regex::Regex;

use rune::alloc::prelude::TryClone;
use rune::runtime::{Vm, VmResult};
use rune::termcolor::{ColorChoice, StandardStream};
use rune::{Diagnostics, Source, Sources};

use serenity::async_trait;
use serenity::builder::{CreateButton, CreateEmbed, CreateEmbedFooter, CreateMessage};
use serenity::model::channel::Message;
use serenity::model::gateway::Ready;
use serenity::prelude::*;

use sqlx::Row;

use tracing::{error, info, Level};
use tracing_subscriber::FmtSubscriber;

#[derive(Debug)]
struct State {
    database: sqlx::SqlitePool,
    runtime: Arc<rune::runtime::RuntimeContext>,
    unit: Arc<rune::Unit>,
}

fn try_from_rune_object_to_embed(obj: rune::runtime::Object) -> anyhow::Result<CreateEmbed> {
    let mut ret = CreateEmbed::new();

    ret = match obj.get("title") {
        Some(title) => ret.title(title.clone().into_string()?),
        None => ret,
    };

    ret = match obj.get("url") {
        Some(url) => ret.url(url.clone().into_string()?),
        None => ret,
    };

    ret = match obj.get("thumbnail") {
        Some(thumbnail) => ret.thumbnail(thumbnail.clone().into_string()?),
        None => ret,
    };

    ret = match obj.get("field") {
        Some(field) => {
            let field_rt = field.clone().into_tuple()?;
            let header = field_rt[0].clone().into_string()?;
            let body = field_rt[1].clone().into_string()?;
            ret.field(header, body, false)
        }
        None => ret,
    };

    ret = match obj.get("footer") {
        Some(footer) => {
            let footer = CreateEmbedFooter::new(footer.clone().into_string()?);
            ret.footer(footer)
        }
        None => ret,
    };

    Ok(ret)
}

#[async_trait]
impl EventHandler for State {
    #[tracing::instrument(level = "info")]
    async fn message(&self, ctx: serenity::all::Context, msg: Message) {
        // build here for debug only, shouldn't be here
        let re = Regex::new(r"\[\[(?<title_query>.*)\]\]").expect("Error building regex");
        let Some(q) = re.captures(&msg.content) else {
            return;
        };

        let tq = &q["title_query"];
        let pattern = format!("{tq}%");

        let mut results = match sqlx::query("SELECT game, title, card FROM cards WHERE title LIKE ? ORDER BY rowid LIMIT 10")
            .bind(pattern)
            .fetch_all(&self.database)
            .await
        {
            Ok(res) => res,
            Err(e) => {
                error!("Error querying sqlite: {e}");
                return;
            }
        };

        let entry = if results.len() == 1 {
            Some(results.remove(0))
        } else if results.len() == 0 {
            None
        } else {
            let unique_card_titles = results
                .iter()
                .map(|r| r.get::<String, _>("title"))
                .collect::<HashSet<_>>();
                
            let selected_card = 
                if unique_card_titles.len() == 1 {
                    results[0].get::<String, _>("title")
                } else {
                    let card_selection_buttons = unique_card_titles
                        .iter()
                        .map(|t| CreateButton::new(t).label(t))
                        .collect::<Vec<_>>();
                    
                    let card_selection_msg_init = CreateMessage::new().content("Please select the card you're looking for");
                    let card_selection_msg = card_selection_buttons.into_iter().fold(card_selection_msg_init, |acc, b| acc.button(b));
                    
                    let m = match msg.channel_id.send_message(&ctx, card_selection_msg).await {
                        Ok(res) => res,
                        Err(e) => {
                            error!("Error sending card selection message: {e}");
                            return;
                        }
                    };
                    
                    let interaction = match m
                        .await_component_interaction(&ctx.shard).timeout(Duration::from_secs(60 * 3))
                        .await
                    {
                        Some(x) => x,
                        None => {
                            match m.reply(&ctx, "Timed out").await {
                                Ok(res) => res,
                                Err(e) => {
                                    error!("Error sending message reply: {e}");
                                    return;
                                }
                            };
                            return;
                        }
                    };
                    
                    m.delete(&ctx).await.unwrap();
                    
                    interaction.data.custom_id
                };

            let entry = match sqlx::query("SELECT game, title, card FROM cards WHERE title LIKE ? ORDER BY rowid LIMIT 1")
                .bind(selected_card)
                .fetch_one(&self.database)
                .await
            {
                Ok(res) => res,
                Err(e) => {
                    println!("Error querying sqlite: {e}");
                    return;
                }
            };

            Some(entry)
        };

        if let Some(row) = entry {
            let card = row.get::<String, _>("card"); // get json data as string (for rune reasons)
            let game = row.get::<String, _>("game");

            // build rune vm
            let vm = Vm::new(self.runtime.clone(), self.unit.clone());

            // create execution struct, i.e. rune function call
            let execution = match vm.try_clone().unwrap().send_execute([&game, "embed"], (card,)) {
                Ok(exe) => exe,
                Err(e) => {
                    error!("Error creating execution: {e}");
                    return;
                }
            };

            // run in separate thread
            let _ = tokio::spawn(async move {
                // run rune function
                let output = match execution.async_complete().await {
                    VmResult::Ok(out) => out,
                    VmResult::Err(e) => {
                        error!("{e}");
                        return;
                    }
                };

                // convert rune value into module struct
                let output: rune::runtime::Object = match rune::from_value(output) {
                    Ok(out) => out,
                    Err(e) => {
                        error!("Error converting from rune value to rune object: {e}");
                        return;
                    }
                };

                // convert module struct into serenity discord embed
                let embed = match try_from_rune_object_to_embed(output) {
                    Ok(em) => em,
                    Err(e) => {
                        error!("Error creating embed from script: {e}");
                        return;
                    }
                };

                // create discord message with embed and send
                let builder = CreateMessage::new().embed(embed);
                let _msg = match msg.channel_id.send_message(&ctx.http, builder).await {
                    Ok(msg) => msg,
                    Err(e) => {
                        error!("Error sending message to Discord: {e}");
                        return;
                    }
                };
            });
        } else {
            let builder = CreateMessage::new().content(&format!("{tq} not found"));
            let _msg = match msg.channel_id.send_message(&ctx.http, builder).await {
                Ok(msg) => msg,
                Err(e) => {
                    error!("Error sending message to Discord: {e}");
                    return;
                }
            };
        }
    }

    async fn ready(&self, _: serenity::all::Context, ready: Ready) {
        info!("{} is connected!", ready.user.name);
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .finish();
    
    tracing::subscriber::set_global_default(subscriber)
        .expect("setting default subscriber failed");
        
    // Configure the client with your Discord bot token in the environment.
    let token = env::var("DISCORD_TOKEN")?;

    let database = sqlx::sqlite::SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(sqlx::sqlite::SqliteConnectOptions::new().filename("data/cards.sqlite").create_if_missing(false))
        .await?;

    let (runtime, unit) = create_rune_runtime()?;

    let state = State { database, runtime, unit };

    let intents = GatewayIntents::GUILD_MESSAGES | GatewayIntents::DIRECT_MESSAGES | GatewayIntents::MESSAGE_CONTENT;
    let mut client = Client::builder(&token, intents).event_handler(state).await?;
    
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

#[tracing::instrument(level = "info", err)]
fn create_rune_runtime() -> rune::support::Result<(Arc<rune::runtime::RuntimeContext>, Arc<rune::Unit>)> {
    let mut context = rune::Context::with_default_modules().context("Failed to create context")?;
    context
        .install(rune_modules::json::module(true).context("Failed to load json module")?)
        .context("Failed to install context")?;
    let runtime = Arc::new(context.runtime().context("Failed to create runtime")?);

    let mut sources = Sources::new();

    for entry in std::fs::read_dir("games").context("Script directory doesn't exist")? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().unwrap() == "rn" {
            sources.insert(Source::from_path(&path)?).context(format!("Failed to insert source at {}", path.display()))?;
            info!("Loaded game script at {}", path.display());
        }
    }

    let mut diagnostics = Diagnostics::new();

    let unit = rune::prepare(&mut sources)
        .with_context(&context)
        .with_diagnostics(&mut diagnostics)
        .build()
        .context("Failed to prepare rune")?;

    if !diagnostics.is_empty() {
        let mut writer = StandardStream::stderr(ColorChoice::Always);
        diagnostics.emit(&mut writer, &sources)?;
    }

    let unit = Arc::new(unit);

    Ok((runtime, unit))
}
