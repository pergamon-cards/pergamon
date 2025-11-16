use serenity::builder::{CreateEmbed, CreateEmbedFooter, CreateMessage};

pub fn create_embed(card: &serde_json::Value) -> CreateMessage {
    let mut footer_string = String::default();
    footer_string.push_str(faction_code(card["faction_code"].as_str().unwrap()));
    footer_string.push_str(" \u{2022} ");
    footer_string.push_str(card["pack_code"].as_str().unwrap());
    footer_string.push_str(" #");
    footer_string.push_str(&card["position"].to_string());
    let footer = CreateEmbedFooter::new(footer_string);

    let mut url_string = String::default();
    url_string.push_str("https://netrunnerdb.com/en/card/");
    url_string.push_str(card["code"].as_str().unwrap());

    let mut img_url_string = String::default();
    img_url_string.push_str("https://card-images.netrunnerdb.com/v2/large/");
    img_url_string.push_str(card["code"].as_str().unwrap());
    img_url_string.push_str(".jpg");

    let embed = CreateEmbed::new()
        .title(card["title"].as_str().unwrap())
        .url(url_string)
        .thumbnail(img_url_string)
        .field(
            format!(
                "{}: {} - Cost: {} - Trash: {} - Influence: {}",
                card["type_code"].as_str().unwrap(),
                card["keywords"].as_str().unwrap(),
                card["cost"],
                card["trash_cost"],
                card["faction_cost"]
            ),
            card["text"].as_str().unwrap(),
            false,
        )
        .footer(footer);

    CreateMessage::new().embed(embed)
}

fn faction_code(code: &str) -> &str {
    match code {
        "anarch" => "Anarch",
        "criminal" => "Criminal",
        "shaper" => "Shaper",
        "nbn" => "NBN",
        "jinteki" => "Jinteki",
        "weyland-consortium" => "Weyland Consortium",
        "hass-biodroid" => "Haas-Biodroid",
        s => s,
    }
}
