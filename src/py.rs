use std::{ffi::CString, path::Path, str::FromStr};

use anyhow::{Result, bail};
use pyo3::prelude::*;
use pythonize::{depythonize, pythonize};
use serde::Deserialize;
use serenity::builder::{CreateEmbed, CreateEmbedFooter};

#[derive(Clone, Debug, Deserialize)]
pub struct PergamonEmbed {
    // pub author
    pub color: Option<u32>,
    pub description: Option<String>,
    pub fields: Option<Vec<PergamonEmbedField>>,
    pub footer: Option<PergamonEmbedFooter>,
    pub image: Option<String>,
    pub thumbnail: Option<String>,
    // pub timestamp
    pub title: Option<String>,
    pub url: Option<String>,
    // pub attachment
}

#[derive(Clone, Debug, Deserialize)]
pub struct PergamonEmbedField {
    pub name: String,
    pub value: String,
    pub inline: Option<bool>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct PergamonEmbedFooter {
    pub text: String,
    pub icon_url: Option<String>,
}

impl From<PergamonEmbed> for CreateEmbed {
    fn from(pe: PergamonEmbed) -> Self {
        let mut ce = CreateEmbed::new();

        ce = match pe.color {
            Some(x) => ce.color(x),
            None => ce,
        };

        ce = match pe.description {
            Some(x) => ce.description(x),
            None => ce,
        };

        ce = match pe.fields {
            Some(x) => ce.fields(x.into_iter().map(|f| (f.name, f.value, f.inline.unwrap_or(false)))),
            None => ce,
        };

        ce = match pe.footer {
            Some(x) => ce.footer(x.into()),
            None => ce,
        };

        ce = match pe.image {
            Some(x) => ce.image(x),
            None => ce,
        };

        ce = match pe.thumbnail {
            Some(x) => ce.thumbnail(x),
            None => ce,
        };

        ce = match pe.title {
            Some(x) => ce.title(x),
            None => ce,
        };

        ce = match pe.url {
            Some(x) => ce.url(x),
            None => ce,
        };

        ce
    }
}

impl From<PergamonEmbedFooter> for CreateEmbedFooter {
    fn from(pef: PergamonEmbedFooter) -> Self {
        let mut cef = CreateEmbedFooter::new(pef.text);

        cef = match pef.icon_url {
            Some(x) => cef.icon_url(x),
            None => cef,
        };

        cef
    }
}

pub const MAX_TITLE: usize = 256;
pub const MAX_DESCRIPTION: usize = 4096;
pub const MAX_FOOTER: usize = 2048;
pub const MAX_FIELDS: usize = 25;
pub const MAX_FIELD_NAME: usize = 256;
pub const MAX_FIELD_VALUE: usize = 1024;
pub const MAX_TOTAL: usize = 6000;

/// Checks an embed against Discord's limits, counting characters as Discord does.
pub fn validate_embed(embed: &PergamonEmbed) -> Result<()> {
    let len = |s: &Option<String>| s.as_deref().map_or(0, |s| s.chars().count());
    let title = len(&embed.title);
    let description = len(&embed.description);
    let footer = embed.footer.as_ref().map_or(0, |f| f.text.chars().count());

    let fields = embed.fields.as_deref().unwrap_or_default();

    if title > MAX_TITLE {
        bail!("embed title is {title} characters, the limit is {MAX_TITLE}");
    }
    if description > MAX_DESCRIPTION {
        bail!("embed description is {description} characters, the limit is {MAX_DESCRIPTION}");
    }
    if footer > MAX_FOOTER {
        bail!("embed footer is {footer} characters, the limit is {MAX_FOOTER}");
    }

    if fields.len() > MAX_FIELDS {
        bail!("embed has {} fields, the limit is {MAX_FIELDS}", fields.len());
    }
    let mut fields_total = 0;
    for field in fields {
        let (name, value) = (field.name.chars().count(), field.value.chars().count());
        if name == 0 || value == 0 {
            bail!("embed field {:?} has an empty name or value", field.name);
        }
        if name > MAX_FIELD_NAME {
            bail!("embed field name is {name} characters, the limit is {MAX_FIELD_NAME}");
        }
        if value > MAX_FIELD_VALUE {
            bail!("embed field value is {value} characters, the limit is {MAX_FIELD_VALUE}");
        }
        fields_total += name + value;
    }

    let total = title + description + footer + fields_total;
    if total > MAX_TOTAL {
        bail!("embed is {total} characters in total, the limit is {MAX_TOTAL}");
    }

    Ok(())
}

/// Runs `code` as the module `module` and calls its `embed(card)` function.
pub fn render_embed(code: &str, module: &str, card: &serde_json::Value) -> Result<PergamonEmbed> {
    Python::attach(|py| -> Result<PergamonEmbed> {
        let card_py = pythonize(py, card)?;
        let embed_fn: Py<PyAny> = PyModule::from_code(
            py,
            CString::new(code)?.as_c_str(),
            CString::from_str(&format!("{module}.py"))?.as_ref(),
            CString::from_str(module)?.as_ref(),
        )?
        .getattr("embed")?
        .into();

        let embed_py = embed_fn.call1(py, (card_py,))?;
        let embed = depythonize(&embed_py.into_bound(py))?;

        Ok(embed)
    })
}

/// Reads `<scripts_dir>/<game>.py` on every call, so script edits take effect without a rebuild.
pub fn get_embed(scripts_dir: &Path, game: &str, card: &serde_json::Value) -> Result<PergamonEmbed> {
    let code = std::fs::read_to_string(scripts_dir.join(format!("{game}.py")))?;

    render_embed(&code, game, card)
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    // `render_embed` registers the script as a module in `sys.modules`, which a later call of the same name would reuse,
    // so every test uses its own module name.

    fn embed_json(embed: PergamonEmbed) -> serde_json::Value {
        serde_json::to_value(CreateEmbed::from(embed)).unwrap()
    }

    fn footer(text: &str) -> PergamonEmbedFooter {
        PergamonEmbedFooter {
            text: text.into(),
            icon_url: None,
        }
    }

    fn field(name: &str, value: &str, inline: Option<bool>) -> PergamonEmbedField {
        PergamonEmbedField {
            name: name.into(),
            value: value.into(),
            inline,
        }
    }

    fn empty() -> PergamonEmbed {
        PergamonEmbed {
            color: None,
            description: None,
            fields: None,
            footer: None,
            image: None,
            thumbnail: None,
            title: None,
            url: None,
        }
    }

    #[test]
    fn full_embed_converts() {
        let embed = PergamonEmbed {
            color: Some(0xff4500),
            description: Some("d".into()),
            fields: Some(vec![field("n", "v", Some(true))]),
            footer: Some(footer("f")),
            image: Some("https://example.com/i.png".into()),
            thumbnail: Some("https://example.com/t.png".into()),
            title: Some("t".into()),
            url: Some("https://example.com".into()),
        };

        let value = embed_json(embed);

        assert_eq!(value["color"], 0xff4500);
        assert_eq!(value["description"], "d");
        assert_eq!(value["fields"][0]["name"], "n");
        assert_eq!(value["fields"][0]["value"], "v");
        assert_eq!(value["fields"][0]["inline"], true);
        assert_eq!(value["footer"]["text"], "f");
        assert_eq!(value["image"]["url"], "https://example.com/i.png");
        assert_eq!(value["thumbnail"]["url"], "https://example.com/t.png");
        assert_eq!(value["title"], "t");
        assert_eq!(value["url"], "https://example.com");
    }

    #[test]
    fn empty_embed_sets_nothing() {
        let value = embed_json(empty());

        for key in ["color", "description", "fields", "footer", "image", "thumbnail", "title", "url"] {
            assert!(value.get(key).is_none_or(|v| v.is_null()), "{key} should not be set: {value}");
        }
    }

    #[test]
    fn field_inline_defaults_to_false() {
        let value = embed_json(PergamonEmbed {
            fields: Some(vec![field("a", "b", None), field("c", "d", Some(true))]),
            ..empty()
        });

        assert_eq!(value["fields"][0]["inline"], false);
        assert_eq!(value["fields"][1]["inline"], true);
    }

    #[test]
    fn footer_icon_is_optional() {
        let without = embed_json(PergamonEmbed {
            footer: Some(footer("f")),
            ..empty()
        });
        assert_eq!(without["footer"]["text"], "f");
        assert!(without["footer"].get("icon_url").is_none_or(|v| v.is_null()));

        let with = embed_json(PergamonEmbed {
            footer: Some(PergamonEmbedFooter {
                text: "f".into(),
                icon_url: Some("https://example.com/i.png".into()),
            }),
            ..empty()
        });
        assert_eq!(with["footer"]["icon_url"], "https://example.com/i.png");
    }

    #[test]
    fn render_happy_path() {
        let code = r#"
def embed(card):
    return {"title": card["title"], "color": 255, "footer": {"text": "foot"}}
"#;

        let embed = render_embed(code, "game_0", &json!({"title": "Hedge Fund"})).unwrap();

        assert_eq!(embed.title.as_deref(), Some("Hedge Fund"));
        assert_eq!(embed.color, Some(255));
        assert_eq!(embed.footer.unwrap().text, "foot");
        assert!(embed.description.is_none());
    }

    #[test]
    fn render_reads_fields() {
        let code = "def embed(card):\n    return {'fields': [{'name': 'n', 'value': 'v'}, {'name': 'a', 'value': 'b', 'inline': True}]}";

        let embed = render_embed(code, "game_9", &json!({})).unwrap();
        let fields = embed.fields.unwrap();

        assert_eq!(fields.len(), 2);
        assert_eq!((fields[0].name.as_str(), fields[0].value.as_str(), fields[0].inline), ("n", "v", None));
        assert_eq!(fields[1].inline, Some(true));
    }

    #[test]
    fn render_requires_embed_function() {
        assert!(render_embed("x = 1", "game_1", &json!({})).is_err());
    }

    #[test]
    fn render_reports_syntax_errors() {
        assert!(render_embed("def embed(card:", "game_2", &json!({})).is_err());
    }

    #[test]
    fn render_reports_raising_scripts() {
        let err = render_embed("def embed(card):\n    raise ValueError('boom')", "game_3", &json!({})).unwrap_err();

        assert!(err.to_string().contains("boom"), "{err}");
    }

    #[test]
    fn render_rejects_wrong_return_types() {
        assert!(render_embed("def embed(card):\n    return [1, 2]", "game_4", &json!({})).is_err());
        assert!(render_embed("def embed(card):\n    return {'color': 'red'}", "game_5", &json!({})).is_err());
        // does not fit the u32 the Rust side stores
        assert!(render_embed("def embed(card):\n    return {'color': 2 ** 40}", "game_6", &json!({})).is_err());
    }

    #[test]
    fn render_ignores_unknown_keys() {
        let embed = render_embed("def embed(card):\n    return {'title': 't', 'author': 'a'}", "game_7", &json!({})).unwrap();

        assert_eq!(embed.title.as_deref(), Some("t"));
    }

    #[test]
    fn card_round_trips_nested_json_unicode_and_null() {
        let code = "def embed(card):\n    return {'description': repr(card)}";
        let card = json!({"a": {"b": [1, 2.5, true, null]}, "name": "Déjà Vu \u{2022}"});

        let embed = render_embed(code, "game_8", &card).unwrap();

        assert_eq!(embed.description.unwrap(), "{'a': {'b': [1, 2.5, True, None]}, 'name': 'Déjà Vu \u{2022}'}");
    }

    #[test]
    fn get_embed_reads_the_script_from_the_directory() {
        let dir = std::env::temp_dir().join(format!("pergamon-py-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("demo.py"), "def embed(card):\n    return {'title': card['t']}").unwrap();

        let found = get_embed(&dir, "demo", &json!({"t": "hello"}));
        let missing = get_embed(&dir, "absent", &json!({}));
        std::fs::remove_dir_all(&dir).unwrap();

        assert_eq!(found.unwrap().title.as_deref(), Some("hello"));
        assert!(missing.is_err());
    }

    fn text(len: usize) -> Option<String> {
        Some("é".repeat(len))
    }

    #[test]
    fn validate_accepts_embeds_at_the_limits() {
        assert!(validate_embed(&empty()).is_ok());
        assert!(
            validate_embed(&PergamonEmbed {
                title: text(MAX_TITLE),
                ..empty()
            })
            .is_ok()
        );
        assert!(
            validate_embed(&PergamonEmbed {
                description: text(MAX_DESCRIPTION),
                ..empty()
            })
            .is_ok()
        );
        assert!(
            validate_embed(&PergamonEmbed {
                footer: Some(footer(&"é".repeat(MAX_FOOTER))),
                ..empty()
            })
            .is_ok()
        );
        // title 256 + description 3744 + footer 2000 = 6000
        let total = PergamonEmbed {
            title: text(MAX_TITLE),
            description: text(3744),
            footer: Some(footer(&"é".repeat(2000))),
            ..empty()
        };
        assert!(validate_embed(&total).is_ok());

        let fields = |n: usize, name: usize, value: usize| PergamonEmbed {
            fields: Some((0..n).map(|_| field(&"é".repeat(name), &"é".repeat(value), None)).collect()),
            ..empty()
        };
        assert!(validate_embed(&fields(MAX_FIELDS, 1, 1)).is_ok());
        assert!(validate_embed(&fields(1, MAX_FIELD_NAME, 1)).is_ok());
        assert!(validate_embed(&fields(1, 1, MAX_FIELD_VALUE)).is_ok());
        // fields 5 * (256 + 1024) = 6400 is too much, so 4 * 1280 + title 256 + description 624 = 6000
        let total = PergamonEmbed {
            title: text(MAX_TITLE),
            description: text(624),
            ..fields(4, MAX_FIELD_NAME, MAX_FIELD_VALUE)
        };
        assert!(validate_embed(&total).is_ok());
    }

    #[test]
    fn validate_rejects_embeds_over_the_limits() {
        assert!(
            validate_embed(&PergamonEmbed {
                title: text(MAX_TITLE + 1),
                ..empty()
            })
            .is_err()
        );
        assert!(
            validate_embed(&PergamonEmbed {
                description: text(MAX_DESCRIPTION + 1),
                ..empty()
            })
            .is_err()
        );
        assert!(
            validate_embed(&PergamonEmbed {
                footer: Some(footer(&"é".repeat(MAX_FOOTER + 1))),
                ..empty()
            })
            .is_err()
        );
        let total = PergamonEmbed {
            title: text(MAX_TITLE),
            description: text(3745),
            footer: Some(footer(&"é".repeat(2000))),
            ..empty()
        };
        assert!(validate_embed(&total).is_err());

        let fields = |n: usize, name: usize, value: usize| PergamonEmbed {
            fields: Some((0..n).map(|_| field(&"é".repeat(name), &"é".repeat(value), None)).collect()),
            ..empty()
        };
        assert!(validate_embed(&fields(MAX_FIELDS + 1, 1, 1)).is_err());
        assert!(validate_embed(&fields(1, MAX_FIELD_NAME + 1, 1)).is_err());
        assert!(validate_embed(&fields(1, 1, MAX_FIELD_VALUE + 1)).is_err());
        assert!(validate_embed(&fields(1, 0, 1)).is_err());
        assert!(validate_embed(&fields(1, 1, 0)).is_err());
        let total = PergamonEmbed {
            title: text(MAX_TITLE),
            description: text(625),
            ..fields(4, MAX_FIELD_NAME, MAX_FIELD_VALUE)
        };
        assert!(validate_embed(&total).is_err());
    }
}
