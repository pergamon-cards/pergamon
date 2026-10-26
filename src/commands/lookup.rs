use std::path::Path;
use std::sync::LazyLock;
use std::time::Duration;

use regex::Regex;

// use rune::alloc::prelude::TryClone;
// use rune::runtime::{Vm, VmResult};

use serenity::all::{ChannelId, UserId};
use serenity::builder::{CreateAllowedMentions, CreateButton, CreateEmbed, CreateInteractionResponse, CreateMessage};
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
    // a lookup can wait on a button click or a slow render, longer than Discord's 3 seconds to answer
    ctx.defer().await?;

    match run(&title, ctx.data(), ctx.serenity_context(), ctx.channel_id(), ctx.author().id).await {
        Ok(reply) => {
            ctx.send(reply.into_poise()).await?;
            Ok(())
        }
        Err(e) => {
            let _ = ctx.say("Something went wrong looking that card up").await;
            Err(e)
        }
    }
}

/// What a lookup answers with. The caller sends it: as the response to a slash command, or as a message in the channel.
#[derive(Debug)]
pub enum Reply {
    Embed(Box<CreateEmbed>),
    Text(String),
}

/// Allowed mentions that ping nobody. Every message the bot sends uses it, because replies echo what users typed
/// (`[[@everyone]]` -> "@everyone not found").
fn no_mentions() -> CreateAllowedMentions {
    CreateAllowedMentions::new()
}

impl Reply {
    fn into_message(self) -> CreateMessage {
        match self {
            Reply::Embed(embed) => CreateMessage::new().embed(*embed),
            Reply::Text(text) => CreateMessage::new().content(text),
        }
        .allowed_mentions(no_mentions())
    }

    fn into_poise(self) -> poise::CreateReply {
        match self {
            Reply::Embed(embed) => poise::CreateReply::default().embed(*embed),
            Reply::Text(text) => poise::CreateReply::default().content(text),
        }
        .allowed_mentions(no_mentions())
    }
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

/// The most `[[...]]` lookups answered for one message.
pub const MAX_INLINE_QUERIES: usize = 5;

/// Returns the (trimmed, non-empty) text of the first `MAX_INLINE_QUERIES` `[[...]]` in a message.
pub fn parse_inline_queries(content: &str) -> Vec<String> {
    static RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\[\[(?<title_query>.+?)\]\]").expect("Error building regex"));

    RE.captures_iter(content)
        .map(|c| c["title_query"].trim().to_string())
        .filter(|q| !q.is_empty())
        .take(MAX_INLINE_QUERIES)
        .collect()
}

/// The queries to look up for a message: none when a bot wrote it, so the bot never answers bots or itself.
pub fn queries_for_message(author_is_bot: bool, content: &str) -> Vec<String> {
    if author_is_bot { Vec::new() } else { parse_inline_queries(content) }
}

/// The query without surrounding whitespace, or `None` when nothing is left to look up.
pub fn normalize_query(query: &str) -> Option<&str> {
    let query = query.trim();
    if query.is_empty() { None } else { Some(query) }
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

/// Cards whose title starts with `query` (ignoring case), oldest first.
pub async fn find_cards(pool: &PgPool, query: &str) -> anyhow::Result<Vec<CardRow>> {
    let pattern = format!("{}%", escape_like(query));

    let rows = sqlx::query("SELECT game, title, card FROM cards WHERE title ILIKE $1 ORDER BY id LIMIT 10")
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

/// Longest button label Discord accepts, in characters.
const MAX_BUTTON_LABEL: usize = 80;

/// `s` cut to at most `limit` characters, with `…` as the last one when it was cut.
fn truncate_label(s: &str, limit: usize) -> String {
    if s.chars().count() <= limit {
        return s.to_string();
    }
    s.chars().take(limit - 1).chain(std::iter::once('\u{2026}')).collect()
}

/// The message with one button per title. A button's custom id is the title's index (a title can be longer
/// than the 100 characters a custom id allows) and its label is the title, cut to fit.
pub fn disambiguation_message(titles: &[String]) -> CreateMessage {
    titles
        .iter()
        .enumerate()
        .fold(CreateMessage::new().content("Please select the card you're looking for"), |msg, (i, t)| {
            msg.button(CreateButton::new(i.to_string()).label(truncate_label(t, MAX_BUTTON_LABEL)))
        })
        .allowed_mentions(no_mentions())
}

pub async fn lookup_inline(state: &State, ctx: serenity::all::Context, msg: Message) {
    for query in queries_for_message(msg.author.bot, &msg.content) {
        info!("Captured card lookup for {query} from message");

        match run(&query, state, &ctx, msg.channel_id, msg.author.id).await {
            Ok(reply) => {
                let _ = msg
                    .channel_id
                    .send_message(&ctx.http, reply.into_message())
                    .await
                    .inspect_err(|e| error!("Error sending message to Discord: {e}"));
            }
            Err(e) => error!("{e}"),
        }
    }
}

/// Looks up `query`, asking `requester` to pick when several titles match, and returns what to answer with.
async fn run(query: &str, state: &State, ctx: &serenity::all::Context, channel_id: ChannelId, requester: UserId) -> anyhow::Result<Reply> {
    let Some(query) = normalize_query(query) else {
        return Ok(Reply::Text("Please give a card name to look up".into()));
    };

    let entry = match resolve(find_cards(&state.database, query).await?) {
        LookupOutcome::NotFound => None,
        LookupOutcome::Found(row) => Some(row),
        LookupOutcome::Ambiguous(titles) => {
            let m = channel_id.send_message(ctx, disambiguation_message(&titles)).await?;

            // only the person who asked can pick
            let interaction = m.await_component_interaction(&ctx.shard).author_id(requester).timeout(Duration::from_secs(60 * 3)).await;

            if let Some(interaction) = &interaction {
                let _ = interaction
                    .create_response(ctx, CreateInteractionResponse::Acknowledge)
                    .await
                    .inspect_err(|e| error!("Error acknowledging button click: {e}"));
            }

            // the picker is only clutter once answered or timed out; failing to remove it (missing permission, already deleted) is not fatal
            let _ = m.delete(ctx).await.inspect_err(|e| error!("Error deleting the disambiguation message: {e}"));

            match interaction {
                Some(interaction) => match interaction.data.custom_id.parse::<usize>().ok().and_then(|i| titles.get(i)) {
                    Some(title) => find_exact(&state.database, title).await?,
                    None => None,
                },
                None => return Ok(Reply::Text("Timed out".into())),
            }
        }
    };

    match entry {
        Some(row) => {
            let embed = get_embed(Path::new("games"), &row.game, &row.card)?;
            validate_embed(&embed)?;
            let embed = embed.into();
            println!("{embed:?}");
            Ok(Reply::Embed(Box::new(embed)))
        }
        None => Ok(Reply::Text(format!("{query} not found"))),
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    fn row(game: &str, title: &str, n: i64) -> CardRow {
        CardRow {
            game: game.into(),
            title: title.into(),
            card: json!({ "n": n }),
        }
    }

    #[test]
    fn parse_finds_no_queries() {
        assert!(parse_inline_queries("").is_empty());
        assert!(parse_inline_queries("just a message with [single] brackets").is_empty());
    }

    #[test]
    fn parse_finds_one_query() {
        assert_eq!(parse_inline_queries("have you seen [[Hedge Fund]]?"), ["Hedge Fund"]);
    }

    #[test]
    fn parse_finds_two_queries_on_one_line() {
        assert_eq!(parse_inline_queries("[[Hedge Fund]] or [[Sure Gamble]]"), ["Hedge Fund", "Sure Gamble"]);
    }

    #[test]
    fn parse_trims_whitespace() {
        assert_eq!(parse_inline_queries("[[  Hedge Fund \t]]"), ["Hedge Fund"]);
    }

    #[test]
    fn parse_stops_at_the_cap() {
        let content: String = (1..=7).map(|i| format!("[[Card {i}]] ")).collect();

        let queries = parse_inline_queries(&content);

        assert_eq!(queries.len(), MAX_INLINE_QUERIES);
        assert_eq!(queries.first().map(String::as_str), Some("Card 1"));
        assert_eq!(queries.last().map(String::as_str), Some("Card 5"));
    }

    #[test]
    fn parse_cap_ignores_empty_queries() {
        let content = format!("[[]] {}", (1..=6).map(|i| format!("[[Card {i}]]")).collect::<String>());

        assert_eq!(parse_inline_queries(&content).len(), MAX_INLINE_QUERIES);
    }

    #[test]
    fn parse_skips_empty_queries() {
        assert!(parse_inline_queries("[[]]").is_empty());
        assert!(parse_inline_queries("[[   ]]").is_empty());
    }

    #[test]
    fn parse_handles_unbalanced_and_nested_brackets() {
        assert!(parse_inline_queries("[[Hedge Fund]").is_empty());
        assert!(parse_inline_queries("[Hedge Fund]]").is_empty());
        assert_eq!(parse_inline_queries("[[[Hedge Fund]]]"), ["[Hedge Fund"]);
        assert_eq!(parse_inline_queries("[[a [[b]]"), ["a [[b"]);
    }

    #[test]
    fn parse_does_not_span_lines() {
        assert!(parse_inline_queries("[[Hedge\nFund]]").is_empty());
    }

    #[test]
    fn bot_messages_are_ignored() {
        assert!(queries_for_message(true, "[[Hedge Fund]]").is_empty());
        assert_eq!(queries_for_message(false, "[[Hedge Fund]]"), ["Hedge Fund"]);
    }

    #[test]
    fn normalize_query_trims_and_rejects_empty() {
        assert_eq!(normalize_query("  Hedge Fund \n"), Some("Hedge Fund"));
        assert_eq!(normalize_query(""), None);
        assert_eq!(normalize_query(" \t\n "), None);
    }

    #[test]
    fn text_reply_becomes_message_content() {
        let value = serde_json::to_value(Reply::Text("Hedge Fund not found".into()).into_message()).unwrap();

        assert_eq!(value["content"], "Hedge Fund not found");
        assert!(value["embeds"].as_array().is_none_or(|e| e.is_empty()));
    }

    #[test]
    fn replies_ping_nobody() {
        for reply in [
            Reply::Text("@everyone not found".into()),
            Reply::Embed(Box::new(CreateEmbed::new())),
        ] {
            let value = serde_json::to_value(reply.into_message()).unwrap();

            assert_eq!(value["allowed_mentions"]["parse"], json!([]));
        }
    }

    #[test]
    fn disambiguation_message_pings_nobody() {
        let value = serde_json::to_value(disambiguation_message(&["@everyone".to_string()])).unwrap();

        assert_eq!(value["allowed_mentions"]["parse"], json!([]));
    }

    #[test]
    fn embed_reply_becomes_one_embed() {
        let value = serde_json::to_value(Reply::Embed(Box::new(CreateEmbed::new().title("Hedge Fund"))).into_message()).unwrap();

        assert_eq!(value["embeds"][0]["title"], "Hedge Fund");
        assert!(value["content"].is_null());
    }

    #[test]
    fn escape_like_escapes_wildcards_and_backslashes() {
        assert_eq!(escape_like("plain"), "plain");
        assert_eq!(escape_like("100%"), "100\\%");
        assert_eq!(escape_like("a_b"), "a\\_b");
        assert_eq!(escape_like("a\\b"), "a\\\\b");
        assert_eq!(escape_like("%_\\"), "\\%\\_\\\\");
        assert_eq!(escape_like("Déjà Vu"), "Déjà Vu");
    }

    #[test]
    fn resolve_no_rows_is_not_found() {
        assert_eq!(resolve(vec![]), LookupOutcome::NotFound);
    }

    #[test]
    fn resolve_one_row_is_found() {
        let r = row("netrunner", "Hedge Fund", 1);

        assert_eq!(resolve(vec![r.clone()]), LookupOutcome::Found(r));
    }

    #[test]
    fn resolve_reprints_are_found_as_the_first_printing() {
        let first = row("netrunner", "Hedge Fund", 1);
        let second = row("netrunner", "Hedge Fund", 2);

        assert_eq!(resolve(vec![first.clone(), second]), LookupOutcome::Found(first));
    }

    #[test]
    fn resolve_distinct_titles_are_ambiguous_in_order() {
        let rows = vec![
            row("netrunner", "Hedge Fund", 1),
            row("netrunner", "Hedge Fund (alt)", 2),
            row("netrunner", "Hedge Fund", 3),
            row("netrunner", "Hedgehog", 4),
        ];

        assert_eq!(resolve(rows), LookupOutcome::Ambiguous(vec!["Hedge Fund".into(), "Hedge Fund (alt)".into(), "Hedgehog".into()]));
    }

    #[test]
    fn disambiguation_message_has_a_button_per_title() {
        let titles: Vec<String> = (0..3).map(|i| format!("Card {i}")).collect();

        let value = serde_json::to_value(disambiguation_message(&titles)).unwrap();

        let buttons: Vec<_> = value["components"].as_array().unwrap().iter().flat_map(|r| r["components"].as_array().unwrap()).collect();
        assert_eq!(buttons.len(), 3);
        for (button, title) in buttons.iter().zip(&titles) {
            assert_eq!(button["label"], title.as_str());
        }
        let ids: Vec<_> = buttons.iter().map(|b| b["custom_id"].as_str().unwrap()).collect();
        assert_eq!(ids, ["0", "1", "2"]);
    }

    #[test]
    fn disambiguation_message_cuts_long_titles_to_fit_discord() {
        let long = "x".repeat(150);
        let titles = vec![long.clone(), "é".repeat(80), "é".repeat(81)];

        let value = serde_json::to_value(disambiguation_message(&titles)).unwrap();

        let buttons: Vec<_> = value["components"].as_array().unwrap().iter().flat_map(|r| r["components"].as_array().unwrap()).collect();
        let labels: Vec<&str> = buttons.iter().map(|b| b["label"].as_str().unwrap()).collect();
        assert_eq!(labels[0].chars().count(), 80);
        assert!(labels[0].ends_with('\u{2026}'));
        assert_eq!(labels[1], "é".repeat(80));
        assert_eq!(labels[2].chars().count(), 80);
        assert!(buttons.iter().all(|b| b["custom_id"].as_str().unwrap().len() <= 100));
    }

    #[test]
    fn disambiguation_message_fills_action_rows_of_five() {
        let titles: Vec<String> = (0..10).map(|i| format!("Card {i}")).collect();

        let value = serde_json::to_value(disambiguation_message(&titles)).unwrap();

        let rows: Vec<usize> = value["components"].as_array().unwrap().iter().map(|r| r["components"].as_array().unwrap().len()).collect();
        assert_eq!(rows, [5, 5]);
    }
}
