mod games;

use std::collections::HashMap;
use std::env;

use regex::Regex;

use serenity::async_trait;
use serenity::builder::CreateMessage;
use serenity::model::channel::Message;
use serenity::model::gateway::Ready;
use serenity::prelude::*;

use tokio::fs::File;
use tokio::io::AsyncReadExt;

use crate::games::netrunner;

struct State {
	data_by_title: HashMap<String, serde_json::Value>,
}

#[async_trait]
impl EventHandler for State {
	async fn message(&self, ctx: Context, msg: Message) {
		// build here for debug only, shouldn't be here
		let re = Regex::new(r"\[\[(?<title_query>.*)\]\]").unwrap();
		let Some(q) = re.captures(&msg.content) else { return };
		
		let tq = &q["title_query"];
		
		let builder = 
			if let Some(card) = self.data_by_title.get(tq) {
				netrunner::create_embed(card)
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
	
	// Load test data file
	let mut file = File::open("core.json").await.expect("open test data file");
	let mut file_contents = vec![];
	file.read_to_end(&mut file_contents).await.expect("read test data file");
	let data: Vec<serde_json::Value> = serde_json::from_slice(&file_contents).expect("parse data file");
	
	let data_by_title = data
		.iter()
		.map(|c| (c["title"].as_str().unwrap().to_owned(), c.clone()))
		.collect::<HashMap<_,_>>();
	
	let state = State { data_by_title };
	
	let intents = GatewayIntents::GUILD_MESSAGES
		| GatewayIntents::DIRECT_MESSAGES
		| GatewayIntents::MESSAGE_CONTENT;
	let mut client =
		Client::builder(&token, intents).event_handler(state).await.expect("Err creating client");

	if let Err(why) = client.start().await {
		println!("Client error: {why:?}");
	}
}
