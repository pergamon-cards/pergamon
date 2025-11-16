# pergamon.games

## Getting started

1. Install rust (via [`rustup`](https://rustup.rs))
2. `git clone` this repo
3. `git clone` the [netrunner card data repo](https://github.com/Null-Signal-Games/netrunner-cards-json) under `data/netrunner`.
4. Run `data/netrunner/load_data.py` to create sqlite database
5. `cargo run` (with Discord token in `DISCORD_TOKEN` env variable)
