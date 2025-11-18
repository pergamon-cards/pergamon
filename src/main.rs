use std::collections::HashSet;
use std::env;
use std::sync::Arc;
use std::time::Duration;

use regex::Regex;

use rune::alloc::prelude::TryClone;
use rune::runtime::{Vm, VmResult};
use rune::termcolor::{ColorChoice, StandardStream};
use rune::{Diagnostics, Source, Sources};

use serenity::all::{ComponentInteractionDataKind, CreateInteractionResponse, CreateInteractionResponseMessage};
use serenity::async_trait;
use serenity::builder::{CreateEmbed, CreateEmbedFooter, CreateMessage,
    CreateSelectMenu,
    CreateSelectMenuKind,
    CreateSelectMenuOption,};
use serenity::model::channel::Message;
use serenity::model::gateway::Ready;
use serenity::prelude::*;

use sqlx::Row;

struct State {
    database: sqlx::SqlitePool,
    runtime: Arc<rune::runtime::RuntimeContext>,
    unit: Arc<rune::Unit>,
}

fn rune_object_to_embed(obj: rune::runtime::Object) -> CreateEmbed {
    let mut ret = CreateEmbed::new();
    
    ret = match obj.get("title") {
        Some(title) => ret.title(title.clone().into_string().unwrap()),
        None => ret,
    };
    
    ret = match obj.get("url") {
        Some(url) => ret.url(url.clone().into_string().unwrap()),
        None => ret,
    };
    
    ret = match obj.get("thumbnail") {
        Some(thumbnail) => ret.thumbnail(thumbnail.clone().into_string().unwrap()),
        None => ret,
    };
    
    ret = match obj.get("field") {
        Some(field) => {
            let field_rt = field.clone().into_tuple().unwrap();
            let header = field_rt[0].clone().into_string().unwrap();
            let body = field_rt[1].clone().into_string().unwrap();
            ret.field(header, body, false)
        }
        None => ret,
    };
    
    ret = match obj.get("footer") {
        Some(footer) => {
            let footer = CreateEmbedFooter::new(footer.clone().into_string().unwrap());
            ret.footer(footer)
        }
        None => ret,
    };
    
    ret
}

#[async_trait]
impl EventHandler for State {
    async fn message(&self, ctx: Context, msg: Message) {
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
            .await {
                Ok(res) => res,
                Err(e) => {
                    println!("Error querying sqlite: {e}");
                    return
                }
            };
            
        let entry = if results.len() == 1 {
            Some(results.remove(0))
        } else if results.len() == 0 {
            None
        } else {
            let menu_options = results
                .iter()
                .map(|r| r.get::<String,_>("title"))
                .collect::<HashSet<_>>()
                .iter()
                .map(|t| CreateSelectMenuOption::new(t, t))
                .collect();
            let m = msg
                .channel_id
                .send_message(
                    &ctx,
                    CreateMessage::new().content("Please select the card you're looking for").select_menu(
                        CreateSelectMenu::new("card_select", CreateSelectMenuKind::String {
                            options: menu_options,
                        })
                        .custom_id("card_select")
                        .placeholder("No card selected"),
                    ),
                )
                .await
                .unwrap();
                
            let interaction = match m
                .await_component_interaction(&ctx.shard)
                .timeout(Duration::from_secs(60 * 3))
                .await
            {
                Some(x) => x,
                None => {
                    m.reply(&ctx, "Timed out").await.unwrap();
                    return;
                },
            };
            
            let selected_card = match &interaction.data.kind {
                ComponentInteractionDataKind::StringSelect {
                    values,
                } => &values[0],
                _ => panic!("unexpected interaction data kind"),
            };
            
            interaction
                .create_response(
                    &ctx,
                    CreateInteractionResponse::UpdateMessage(
                        CreateInteractionResponseMessage::default()
                            .content(format!("You chose: **{selected_card}**")),
                    ),
                )
                .await
                .unwrap();
            
            println!("selected option: {selected_card}");
            
            m.delete(&ctx).await.unwrap();
            
            let entry = match sqlx::query("SELECT game, title, card FROM cards WHERE title LIKE ? ORDER BY rowid LIMIT 1")
                .bind(selected_card)
                .fetch_one(&self.database)
                .await {
                    Ok(res) => res,
                    Err(e) => {
                        println!("Error querying sqlite: {e}");
                        return
                    }
                };

            // temp
            // results.first()
            Some(entry)
        };
        
        if let Some(row) = entry {
            let card = row.get::<String,_>("card"); // get json data as string (for rune reasons)
            let game = row.get::<String,_>("game");
            
            // build rune vm
            let vm = Vm::new(self.runtime.clone(), self.unit.clone());
            
            // create execution struct, i.e. rune function call
            let execution = match vm.try_clone().unwrap().send_execute([format!("{game}_embed").as_str()], (card,)) {
                Ok(exe) => exe,
                Err(e) => {
                    println!("Error creating execution: {e}");
                    return
                }
            };
            
            // run in separate thread
            let _ = tokio::spawn(async move {
                // run rune function
                let output = match execution.async_complete().await {
                    VmResult::Ok(out) => out,
                    VmResult::Err(e) => {
                        println!("{e}");
                        return
                    }
                };
                
                // convert rune value into module struct
                let output: rune::runtime::Object = match rune::from_value(output) {
                    Ok(out) => out,
                    Err(e) => {
                        println!("Error converting from rune value to rune object: {e}");
                        return
                    }
                };
                
                // convert module struct into serenity discord embed
                let embed = rune_object_to_embed(output);
                
                // create discord message with embed and send
                let builder = CreateMessage::new().embed(embed);
                let _msg = match msg.channel_id.send_message(&ctx.http, builder).await {
                    Ok(msg) => msg,
                    Err(e) => {
                        println!("Error sending message to Discord: {e}");
                        return
                    }
                };
            });
        } else {
            let builder = CreateMessage::new().content(&format!("{tq} not found"));
            let _msg = match msg.channel_id.send_message(&ctx.http, builder).await {
                Ok(msg) => msg,
                Err(e) => {
                    println!("Error sending message to Discord: {e}");
                    return
                }
            };
        }
    }

    async fn ready(&self, _: Context, ready: Ready) {
        println!("{} is connected!", ready.user.name);
    }
}

#[tokio::main]
async fn main() {
    // Configure the client with your Discord bot token in the environment.
    let token = env::var("DISCORD_TOKEN").expect("Expected a token in the environment");

    let database = sqlx::sqlite::SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(
            sqlx::sqlite::SqliteConnectOptions::new()
                .filename("data/cards.sqlite")
                .create_if_missing(false),
        )
        .await
        .expect("Unable to connect to database");
    
    let (runtime, unit) = create_rune_runtime().unwrap();

    let state = State { database, runtime, unit };

    let intents = GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::DIRECT_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT;
    let mut client = Client::builder(&token, intents)
        .event_handler(state)
        .await
        .expect("Unable to create client");

    if let Err(why) = client.start().await {
        println!("Client error: {why:?}");
    }
}

fn create_rune_runtime() -> rune::support::Result<(Arc<rune::runtime::RuntimeContext>, Arc<rune::Unit>)> {
    let mut context = rune::Context::with_default_modules()?;
    context.install(rune_modules::json::module(true)?)?;
    let runtime = Arc::new(context.runtime()?);
    
    let mut sources = Sources::new();
    sources.insert(Source::from_path("games/agricola.rn").unwrap()).unwrap();
    sources.insert(Source::from_path("games/netrunner.rn").unwrap()).unwrap();
    
    let mut diagnostics = Diagnostics::new();
    
    let result = rune::prepare(&mut sources)
        .with_context(&context)
        .with_diagnostics(&mut diagnostics)
        .build();
    
    if !diagnostics.is_empty() {
        let mut writer = StandardStream::stderr(ColorChoice::Always);
        diagnostics.emit(&mut writer, &sources)?;
    }
    
    let unit = result?;
    let unit = Arc::new(unit);
    
    Ok((runtime, unit))
}
