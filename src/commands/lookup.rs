use std::collections::HashSet;
use std::time::Duration;

use regex::Regex;

use rune::alloc::prelude::TryClone;
use rune::runtime::{Vm, VmResult};

use serenity::all::ChannelId;
use serenity::builder::{CreateButton, CreateMessage};
use serenity::model::channel::Message;

use sqlx::Row;

use tracing::{error, info};

use crate::{State, scripting};

#[poise::command(prefix_command, slash_command)]
pub async fn lookup(ctx: poise::Context<'_, State, anyhow::Error>, title: String) -> anyhow::Result<()> {
    run(title, ctx.data(), ctx.serenity_context().clone(), ctx.channel_id()).await
}

pub async fn lookup_inline(state: &State, ctx: serenity::all::Context, msg: Message) {
    // build here for debug only, shouldn't be here
    let re = Regex::new(r"\[\[(?<title_query>.*)\]\]").expect("Error building regex");

    if let Some(q) = re.captures(&msg.content) {
        let query = &q["title_query"];
        info!("Captured card lookup for {query} from message");

        if let Err(e) = run(query.to_string(), state, ctx, msg.channel_id).await {
            error!("{e}");
        }
    }
}

async fn run(query: String, state: &State, ctx: serenity::all::Context, channel_id: ChannelId) -> anyhow::Result<()> {
    let pattern = format!("{query}%");

    let mut results = sqlx::query("SELECT game, title, card FROM cards WHERE title LIKE ? ORDER BY rowid LIMIT 10")
        .bind(pattern)
        .fetch_all(&state.database)
        .await?;

    let entry = if results.len() == 1 {
        Some(results.remove(0))
    } else if results.len() == 0 {
        None
    } else {
        let unique_card_titles = results.iter().map(|r| r.get::<String, _>("title")).collect::<HashSet<_>>();

        let selected_card = if unique_card_titles.len() == 1 {
            results[0].get::<String, _>("title")
        } else {
            let card_selection_buttons = unique_card_titles.iter().map(|t| CreateButton::new(t).label(t)).collect::<Vec<_>>();

            let card_selection_msg_init = CreateMessage::new().content("Please select the card you're looking for");
            let card_selection_msg = card_selection_buttons.into_iter().fold(card_selection_msg_init, |acc, b| acc.button(b));

            let m = channel_id.send_message(&ctx, card_selection_msg).await?;

            let interaction = match m.await_component_interaction(&ctx.shard).timeout(Duration::from_secs(60 * 3)).await {
                Some(x) => Some(x),
                None => {
                    let _ = m.reply(&ctx, "Timed out").await;
                    None
                }
            };

            m.delete(&ctx).await.unwrap();

            if let Some(interaction) = interaction {
                interaction.data.custom_id
            } else {
                return Ok(());
            }
        };

        let entry = sqlx::query("SELECT game, title, card FROM cards WHERE title LIKE ? ORDER BY rowid LIMIT 1")
            .bind(selected_card)
            .fetch_one(&state.database)
            .await?;

        Some(entry)
    };

    if let Some(row) = entry {
        let card = row.get::<String, _>("card"); // get json data as string (for rune reasons)
        let game = row.get::<String, _>("game");

        // build rune vm
        let vm = Vm::new(state.runtime.clone(), state.unit.clone());

        // create execution struct, i.e. rune function call
        let execution = vm.try_clone().unwrap().send_execute([&game, "embed"], (card,))?;

        // run in separate thread
        let _ = tokio::spawn(async move {
            // run rune function
            let output = match execution.async_complete().await {
                VmResult::Ok(out) => out,
                VmResult::Err(e) => {
                    error!("Error running rune function: {e}");
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
            let embed = match scripting::try_from_rune_object_to_embed(output) {
                Ok(em) => em,
                Err(e) => {
                    error!("Error creating embed from script: {e}");
                    return;
                }
            };

            // create discord message with embed and send
            let builder = CreateMessage::new().embed(embed);
            let _msg = match channel_id.send_message(&ctx.http, builder).await {
                Ok(msg) => msg,
                Err(e) => {
                    error!("Error sending message to Discord: {e}");
                    return;
                }
            };
        });
    } else {
        let builder = CreateMessage::new().content(&format!("{query} not found"));
        let _msg = channel_id.send_message(&ctx.http, builder).await?;
    }

    Ok(())
}
