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
    // pub fields
    pub footer: Option<PergamonEmbedFooter>,
    pub image: Option<String>,
    pub thumbnail: Option<String>,
    // pub timestamp
    pub title: Option<String>,
    pub url: Option<String>,
    // pub attachment
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
pub const MAX_TOTAL: usize = 6000;

/// Checks an embed against Discord's limits, counting characters as Discord does.
/// `PergamonEmbed` has no fields yet, so the field-count and field name/value limits are not checked.
pub fn validate_embed(embed: &PergamonEmbed) -> Result<()> {
    let len = |s: &Option<String>| s.as_deref().map_or(0, |s| s.chars().count());
    let title = len(&embed.title);
    let description = len(&embed.description);
    let footer = embed.footer.as_ref().map_or(0, |f| f.text.chars().count());

    if title > MAX_TITLE {
        bail!("embed title is {title} characters, the limit is {MAX_TITLE}");
    }
    if description > MAX_DESCRIPTION {
        bail!("embed description is {description} characters, the limit is {MAX_DESCRIPTION}");
    }
    if footer > MAX_FOOTER {
        bail!("embed footer is {footer} characters, the limit is {MAX_FOOTER}");
    }

    let total = title + description + footer;
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
