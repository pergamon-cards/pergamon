mod regex;

use std::sync::Arc;

use anyhow::Context;

use rune::termcolor::{ColorChoice, StandardStream};
use rune::{Diagnostics, Source, Sources};

use serenity::builder::{CreateEmbed, CreateEmbedFooter};

use tracing::info;

pub fn try_from_rune_object_to_embed(obj: rune::runtime::Object) -> anyhow::Result<CreateEmbed> {
	let mut ret = CreateEmbed::new();

	ret = match obj.get("title") {
		Some(title) => ret.title(title.clone().into_string()?),
		None => ret,
	};
	
	ret = match obj.get("color") {
		Some(color) => ret.color(color.as_signed()? as u64),
		None => ret,
	};

	ret = match obj.get("url") {
		Some(url) => ret.url(url.clone().into_string()?),
		None => ret,
	};

	ret = match obj.get("thumbnail") {
		Some(thumbnail) => ret.thumbnail(thumbnail.clone().into_string()?),
		None => ret,
	};

	ret = match obj.get("field") {
		Some(field) => {
			let field_rt = field.clone().into_tuple()?;
			let header = field_rt[0].clone().into_string()?;
			let body = field_rt[1].clone().into_string()?;
			ret.field(header, body, false)
		}
		None => ret,
	};

	ret = match obj.get("footer") {
		Some(footer) => {
			let footer = CreateEmbedFooter::new(footer.clone().into_string()?);
			ret.footer(footer)
		}
		None => ret,
	};

	Ok(ret)
}

#[tracing::instrument(level = "info", err)]
pub fn create_rune_runtime() -> rune::support::Result<(Arc<rune::runtime::RuntimeContext>, Arc<rune::Unit>)> {
	let m = regex::Regex::module()?;
	
	let mut context = rune::Context::with_default_modules().context("Failed to create context")?;
	context
		.install(rune_modules::json::module(true).context("Failed to load json module")?)
		.context("Failed to install context")?;
	context.install(m)?;
	let runtime = Arc::new(context.runtime().context("Failed to create runtime")?);

	let mut sources = Sources::new();

	for entry in std::fs::read_dir("games").context("Script directory doesn't exist")? {
		let entry = entry?;
		let path = entry.path();
		if path.extension().unwrap() == "rn" {
			sources.insert(Source::from_path(&path)?).context(format!("Failed to insert source at {}", path.display()))?;
			info!("Loaded game script at {}", path.display());
		}
	}

	let mut diagnostics = Diagnostics::new();

	let unit = match rune::prepare(&mut sources)
		.with_context(&context)
		.with_diagnostics(&mut diagnostics)
		.build()
		.context("Failed to prepare rune") {
			Ok(u) => Ok(u),
			Err(e) => {
			   if !diagnostics.is_empty() {
				   let mut writer = StandardStream::stderr(ColorChoice::Always);
				   diagnostics.emit(&mut writer, &sources)?;
			   }
			   Err(e)
			}
		}?;

	let unit = Arc::new(unit);

	Ok((runtime, unit))
}
