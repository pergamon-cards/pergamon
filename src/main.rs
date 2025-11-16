mod games;

use std::env;

use regex::Regex;

use serenity::async_trait;
use serenity::builder::CreateMessage;
use serenity::model::channel::Message;
use serenity::model::gateway::Ready;
use serenity::prelude::*;

use sqlx::Row;

use crate::games::netrunner;

struct State {
	database: sqlx::SqlitePool,
}

#[async_trait]
impl EventHandler for State {
	async fn message(&self, ctx: Context, msg: Message) {
		// build here for debug only, shouldn't be here
		let re = Regex::new(r"\[\[(?<title_query>.*)\]\]").unwrap();
		let Some(q) = re.captures(&msg.content) else { return };
		
		let tq = &q["title_query"];
		
		let entry = sqlx::query("SELECT game, title, card FROM cards WHERE title = ? ORDER BY rowid LIMIT 1")
			.bind(tq)
			.fetch_optional(&self.database) // < Just one data will be sent to entry
			.await
			.unwrap();
		
		let builder = 
			if let Some(row) = entry {
				let card = row.get("card");
				netrunner::create_embed(&card)
			} else {
				CreateMessage::new().content(&format!("{tq} not found"))
			};
			
		let msg = msg.channel_id.send_message(&ctx.http, builder).await;
		
		if let Err(why) = msg {
			println!("Error sending message: {why:?}");
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
	
	let state = State { database };
	
	let intents = GatewayIntents::GUILD_MESSAGES
		| GatewayIntents::DIRECT_MESSAGES
		| GatewayIntents::MESSAGE_CONTENT;
	let mut client =
		Client::builder(&token, intents).event_handler(state).await.expect("Err creating client");

	if let Err(why) = client.start().await {
		println!("Client error: {why:?}");
	}
}
