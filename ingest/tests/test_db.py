from ingest.db import conninfo, load_settings

FILE = """
token = "t"

[database]
host = "localhost"
port = 5432
username = "u"
password = "p"
database = "pergamon"
max_connections = 5
"""


def config(tmp_path, name="dev"):
    (tmp_path / f"{name}.toml").write_text(FILE)
    return tmp_path


def test_reads_the_dev_file_by_default(tmp_path):
    assert load_settings(config(tmp_path), env={})["host"] == "localhost"


def test_run_env_selects_the_file(tmp_path):
    config(tmp_path, "prod")
    assert load_settings(tmp_path, env={"PERGAMON_RUN_ENV": "prod"})["database"] == "pergamon"


def test_env_overrides_single_keys(tmp_path):
    settings = load_settings(config(tmp_path), env={"PERGAMON_DATABASE_HOST": "db", "PERGAMON_DATABASE_PORT": "6543"})
    assert settings["host"] == "db" and settings["port"] == 6543 and settings["username"] == "u"


def test_conninfo(tmp_path):
    assert conninfo(load_settings(config(tmp_path), env={})) == "host=localhost port=5432 dbname=pergamon user=u password=p"
