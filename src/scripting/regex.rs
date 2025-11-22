use anyhow::anyhow;

use rune::{Any, ContextError, Module};

#[derive(Debug, Any)]
pub struct Regex { regex: regex::Regex }

impl Regex {
	#[rune::function(path = Self::new)]
	pub fn new(re: &str) -> anyhow::Result<Self> {
		match regex::Regex::new(re) {
			Ok(regex) => Ok(Self { regex }),
			Err(err) => Err(anyhow!("Failed to compile regex: {:?}", err)),
		}
	}
	
	#[rune::function]
	pub fn replace_all(&self, before: &str, haystack: &str) -> String {
		self.regex.replace_all(before, haystack).to_string()
	}
	
	pub fn module() -> Result<Module, ContextError> {
		let mut module = Module::new();
		module.ty::<Regex>()?;
		module.function_meta(Regex::new)?;
		module.function_meta(Regex::replace_all)?;
		Ok(module)
	}
}
