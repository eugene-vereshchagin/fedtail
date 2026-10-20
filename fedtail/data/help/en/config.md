# Settings

There's no settings window — it's all in the config. How it works, and where the full reference is.

## How the config works

- ≡ → "Open config" — `config.toml` in your editor. Changed it — restart fedtail.
- Every setting is in it, by chapter, each with its default value and an explanation.
- A value you wrote stays yours even when a new version changes the default. Want the program's
  default — comment the line out.
- A new version brought settings — fedtail says so at start. `fedtail --update-config` adds them
  to the right chapters with explanations, `--rebuild-config` rebuilds the file anew with your
  values. The old file stays as `config.toml.bak`.
- The full reference of the running version always lies next to it — `config.example.en.toml`
  and `config.example.ru.toml`. Updates take the explanations in your file's language.

## Reference

Every setting with its default and explanation, in tables by chapter →
[the settings reference](ref/config.md).

Which feature which setting turns on → [the feature list](ref/features.md).
