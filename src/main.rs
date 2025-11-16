use std::env;
use std::sync::Arc;

use regex::Regex;

use rune::alloc::prelude::TryClone;
use rune::runtime::{Vm, VmResult};
use rune::termcolor::{ColorChoice, StandardStream};
use rune::{Diagnostics, Source, Sources};

use serenity::async_trait;
use serenity::builder::{CreateEmbed, CreateEmbedFooter, CreateMessage};
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
        let re = Regex::new(r"\[\[(?<title_query>.*)\]\]").unwrap();
        let Some(q) = re.captures(&msg.content) else {
            return;
        };

        let tq = &q["title_query"];

        let entry = sqlx::query(
            "SELECT game, title, card FROM cards WHERE title = ? ORDER BY rowid LIMIT 1",
        )
        .bind(tq)
        .fetch_optional(&self.database) // < Just one data will be sent to entry
        .await
        .unwrap();
        
        if let Some(row) = entry {
            // get json data as string (for rune reasons)
            let card = row.get::<String,_>("card");
            
            // build rune vm
            let vm = Vm::new(self.runtime.clone(), self.unit.clone());
            
            // create execution struct, i.e. rune function call
            let execution = vm.try_clone().unwrap().send_execute(["netrunner_embed"], (card,)).unwrap();
            
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
                let output: rune::runtime::Object = rune::from_value(output).unwrap();
                
                // convert module struct into serenity discord embed
                let embed = rune_object_to_embed(output);
                
                // create discord message with embed and send
                let builder = CreateMessage::new().embed(embed);
                let _msg = msg.channel_id.send_message(&ctx.http, builder).await.unwrap();
            });
        } else {
            let builder = CreateMessage::new().content(&format!("{tq} not found"));
            let _msg = msg.channel_id.send_message(&ctx.http, builder).await.unwrap();
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
        .expect("Couldn't connect to database");
    
    let (runtime, unit) = create_rune_runtime().unwrap();

    let state = State { database, runtime, unit };

    let intents = GatewayIntents::GUILD_MESSAGES
        | GatewayIntents::DIRECT_MESSAGES
        | GatewayIntents::MESSAGE_CONTENT;
    let mut client = Client::builder(&token, intents)
        .event_handler(state)
        .await
        .expect("Err creating client");

    if let Err(why) = client.start().await {
        println!("Client error: {why:?}");
    }
}

fn create_rune_runtime() -> rune::support::Result<(Arc<rune::runtime::RuntimeContext>, Arc<rune::Unit>)> {
    let mut context = rune::Context::with_default_modules()?;
    context.install(rune_modules::json::module(true)?)?;
    let runtime = Arc::new(context.runtime()?);
    
    let mut sources = Sources::new();
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
