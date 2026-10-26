use std::path::Path;
use std::sync::LazyLock;
use std::time::Duration;

use regex::Regex;

// use rune::alloc::prelude::TryClone;
// use rune::runtime::{Vm, VmResult};

use serenity::all::ChannelId;
use serenity::builder::{CreateButton, CreateMessage};
use serenity::model::channel::Message;

use sqlx::postgres::PgRow;
use sqlx::{PgPool, Row};

use tracing::{error, info};

use crate::{
    State,
    py::{get_embed, validate_embed}, /*scripting*/
};

#[poise::command(prefix_command, slash_command)]
pub async fn lookup(ctx: poise::Context<'_, State, anyhow::Error>, title: String) -> anyhow::Result<()> {
    run(title, ctx.data(), ctx.serenity_context().clone(), ctx.channel_id()).await
}

/// A card row as stored in the `cards` table.
#[derive(Debug, Clone, PartialEq)]
pub struct CardRow {
    pub game: String,
    pub title: String,
    pub card: serde_json::Value,
}

impl CardRow {
    fn from_row(row: &PgRow) -> Result<Self, sqlx::Error> {
        Ok(Self {
            game: row.try_get("game")?,
            title: row.try_get("title")?,
            card: row.try_get("card")?,
        })
    }
}

/// What a prefix search resolved to.
#[derive(Debug, Clone, PartialEq)]
pub enum LookupOutcome {
    NotFound,
    Found(CardRow),
    /// Distinct titles, in the order they were returned.
    Ambiguous(Vec<String>),
}

/// Returns the (trimmed, non-empty) text of every `[[...]]` in a message.
pub fn parse_inline_queries(content: &str) -> Vec<String> {
    static RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\[\[(?<title_query>.+?)\]\]").expect("Error building regex"));

    RE.captures_iter(content).map(|c| c["title_query"].trim().to_string()).filter(|q| !q.is_empty()).collect()
}

/// Escapes `\`, `%` and `_` so user text matches literally in a `LIKE` pattern.
pub fn escape_like(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        if matches!(c, '\\' | '%' | '_') {
            out.push('\\');
        }
        out.push(c);
    }
    out
}

/// Decides what to do with the rows of a prefix search.
pub fn resolve(rows: Vec<CardRow>) -> LookupOutcome {
    let mut titles: Vec<String> = Vec::new();
    for row in &rows {
        if !titles.contains(&row.title) {
            titles.push(row.title.clone());
        }
    }

    match titles.len() {
        0 => LookupOutcome::NotFound,
        1 => LookupOutcome::Found(rows.into_iter().next().expect("rows is not empty")),
        _ => LookupOutcome::Ambiguous(titles),
    }
}

/// Cards whose title starts with `query`, oldest first.
pub async fn find_cards(pool: &PgPool, query: &str) -> anyhow::Result<Vec<CardRow>> {
    let pattern = format!("{}%", escape_like(query));

    let rows = sqlx::query("SELECT game, title, card FROM cards WHERE title LIKE $1 ORDER BY id LIMIT 10")
        .bind(pattern)
        .fetch_all(pool)
        .await?;

    Ok(rows.iter().map(CardRow::from_row).collect::<Result<_, _>>()?)
}

/// The first card whose title is exactly `title`.
pub async fn find_exact(pool: &PgPool, title: &str) -> anyhow::Result<Option<CardRow>> {
    let row = sqlx::query("SELECT game, title, card FROM cards WHERE title = $1 ORDER BY id LIMIT 1")
        .bind(title)
        .fetch_optional(pool)
        .await?;

    Ok(row.as_ref().map(CardRow::from_row).transpose()?)
}

/// The message with one button per title; a button's custom id is the title.
pub fn disambiguation_message(titles: &[String]) -> CreateMessage {
    titles.iter().fold(CreateMessage::new().content("Please select the card you're looking for"), |msg, t| {
        msg.button(CreateButton::new(t).label(t))
    })
}

pub async fn lookup_inline(state: &State, ctx: serenity::all::Context, msg: Message) {
    for query in parse_inline_queries(&msg.content) {
        info!("Captured card lookup for {query} from message");

        if let Err(e) = run(query, state, ctx.clone(), msg.channel_id).await {
            error!("{e}");
        }
    }
}

async fn run(query: String, state: &State, ctx: serenity::all::Context, channel_id: ChannelId) -> anyhow::Result<()> {
    let entry = match resolve(find_cards(&state.database, &query).await?) {
        LookupOutcome::NotFound => None,
        LookupOutcome::Found(row) => Some(row),
        LookupOutcome::Ambiguous(titles) => {
            let m = channel_id.send_message(&ctx, disambiguation_message(&titles)).await?;

            let interaction = match m.await_component_interaction(&ctx.shard).timeout(Duration::from_secs(60 * 3)).await {
                Some(x) => Some(x),
                None => {
                    let _ = m.reply(&ctx, "Timed out").await;
                    None
                }
            };

            m.delete(&ctx).await.unwrap();

            match interaction {
                Some(interaction) => find_exact(&state.database, &interaction.data.custom_id).await?,
                None => return Ok(()),
            }
        }
    };

    if let Some(row) = entry {
        let embed = get_embed(Path::new("games"), &row.game, &row.card)?;
        validate_embed(&embed)?;
        let embed = embed.into();
        println!("{embed:?}");
        // create discord message with embed and send
        let builder = CreateMessage::new().embed(embed);
        let _msg = channel_id.send_message(&ctx.http, builder).await.inspect_err(|e| error!("Error sending message to Discord: {e}"))?;

    //         let card = row.get::<String, _>("card"); // get json data as string (for rune reasons)
    //         let game = row.get::<String, _>("game");
    //
    //         // build rune vm
    //         let vm = Vm::new(state.runtime.clone(), state.unit.clone());
    //
    //         // create execution struct, i.e. rune function call
    //         let execution = vm.try_clone().unwrap().send_execute([&game, "embed"], (card,))?;
    //
    //         // run in separate thread
    //         let _ = tokio::spawn(async move {
    //             // run rune function
    //             let output = match execution.async_complete().await {
    //                 VmResult::Ok(out) => out,
    //                 VmResult::Err(e) => {
    //                     error!("Error running rune function: {e}");
    //                     return;
    //                 }
    //             };
    //
    //             // convert rune value into module struct
    //             let output: rune::runtime::Object = match rune::from_value(output) {
    //                 Ok(out) => out,
    //                 Err(e) => {
    //                     error!("Error converting from rune value to rune object: {e}");
    //                     return;
    //                 }
    //             };
    //
    //             // convert module struct into serenity discord embed
    //             let embed = match scripting::try_from_rune_object_to_embed(output) {
    //                 Ok(em) => em,
    //                 Err(e) => {
    //                     error!("Error creating embed from script: {e}");
    //                     return;
    //                 }
    //             };
    //
    //             // create discord message with embed and send
    //             let builder = CreateMessage::new().embed(embed);
    //             let _msg = match channel_id.send_message(&ctx.http, builder).await {
    //                 Ok(msg) => msg,
    //                 Err(e) => {
    //                     error!("Error sending message to Discord: {e}");
    //                     return;
    //                 }
    //             };
    //         });
    } else {
        let builder = CreateMessage::new().content(format!("{query} not found"));
        let _msg = channel_id.send_message(&ctx.http, builder).await?;
    }

    Ok(())
}
