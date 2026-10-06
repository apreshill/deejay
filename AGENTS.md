# AGENTS.md

Pixeltable is an OLTP database for multimodal AI. You declare tables, views, and computed columns as a class-based schema and define a service over them in one `app.py`, then create and serve it with the `pxt` CLI.

The app is specified in `spec/deejay-spec.md`. The DJ knowledge it follows is in `notes`.

Do the phases below in order. Finish the phase you were given, then stop. Do not start the next phase until the human asks for it. Do not open an interactive editor.

Add the skill for the schema DSL before you write `app.py`: `npx skills add pixeltable/pixeltable-skill`. The SDK API reference is at https://docs.pixeltable.com/sdk/latest/pixeltable.

The CLI is a `pxt <noun> <verb>` grammar. `schema`, `service`, and `db` share `diff` and `update`. Run `pxt --help` rather than guessing. Docs: https://docs.pixeltable.com (any page takes a `.md` suffix). A `diff` that exits 2 means there is something to apply. That is the preview, not a failure.

Cloud deploy follows the [Pixeltable Cloud guide](https://github.com/pixeltable/pixeltable/blob/main/docs/release/cloud.mdx).

Use one `app.py`. Use class-based schemas. Put the feature UDFs, the key-relation UDF, the preview UDF, and the `phrase_splitter` iterator in one project module that `app.py` imports. Prefer built-in UDFs and UDAs over custom functions where one exists. You are a user of the released `pixeltable` package. Report bugs. Do not patch its source.

## Phase 1. Plan

Read `spec/deejay-spec.md`, `notes`, and this file. Propose how you will build the service.

The plan names:

- the environment manager, after you ask the human which one to use
- whether `librosa`, `pedalboard`, `transformers`, and `torch` resolve with `pixeltable[serve]` 0.7.14 in one lockfile, and any conflict
- the tables, the `phrases` view, the computed columns, and the routes
- for `/mixable`, the samples lookup, and the `phrases` iterator, which version you will try first and the fallback the spec gives

Do not edit files. Do not run `pxt`. You may run a dependency resolve that does not install into this project, such as `uv pip compile`. Stop after the plan.

## Phase 2. Local

Build and run on this machine only. The target is a local catalog path, `/deejay`, not a `pxt://` URI.

1. Install Pixeltable and the dependencies with the environment manager the human chose, using the Environment section of the README, if `pxt --version` is not already 0.7.14 in this project.
2. If `pyproject.toml` has no `[[tool.pixeltable.database]]` entry, run `pxt init`. That entry is the local database. Leave it unnamed.
3. Write `app.py` and the project module.
4. `pxt schema diff app.py /deejay`
5. `pxt schema update app.py /deejay`
6. `pxt service diff app.py /deejay`
7. `pxt service update app.py /deejay -f`
8. `pxt service list /deejay`. Copy the `http://127.0.0.1:<port>` URL from that output.
9. Upload the three test clips from the spec, in the order the spec gives, with curl and no API key. Show each command and response.
10. Call `/mixable` for the `9A` clip. Show the command and the response.
11. Call `/match` for the `9A` clip with both sentences in the spec. Show each command and response. If `OPENAI_API_KEY` is unset, show the curls and say the calls were not made. Do not write the key into the repo.
12. Create one sample of the `8A` and `9A` pair. Show the command and the response.
13. Show `pxt rows /deejay/tracks`, `pxt rows /deejay/phrases`, and `pxt rows /deejay/samples`.
14. From the rows and responses, give the file path or URL of one original song, one phrase, and the sample. The human opens those paths to listen.

Do not run `pxt db`. Do not pass a `pxt://` URI to any command. Do not create an API key. Stop and report what the spec's **Report back** section asks for after phase 2.

## Phase 3. Cloud

Start this phase only after the human says the local result is good.

A `pxt login` session is enough to deploy. Check `pxt whoami`. If it says not signed in, stop and ask the human to run `pxt login`. Do not run `pxt login` yourself. Do not create an API key unless the human asks. Do not read or write `~/.pixeltable/config.toml`.

Get the org slug from `pxt org list`. The first word is the slug. `pxt whoami` does not print it.

Two addresses. Do not mix them.

- `DB` is `pxt://<org>:<db>` with no catalog path. `pxt db` accepts only this form.
- `PATH` is `$DB/deejay`. `pxt schema` and `pxt service` take `PATH`.

Choose `<db>` like this. Run `pxt ls pxt://<org>:main`. If that catalog has tables, `<db>` is a new name, `deejay`, and you do not update `main`. If `main` has no tables, `<db>` is `main`.

Keep the local database entry. Add a second `[[tool.pixeltable.database]]` entry in `pyproject.toml`. Do not put the hosted name on the local entry.

```toml
[[tool.pixeltable.database]]
name = 'pxt://<org>:<db>'
```

Then run these commands, in this order. Pass `-f` on `pxt db update` and `pxt service update`.

1. `pxt db diff $DB`
2. `pxt db update $DB -f`
3. `pxt schema diff app.py $PATH`
4. `pxt schema update app.py $PATH`
5. `pxt service diff app.py $PATH`
6. `pxt service update app.py $PATH -f`
7. `pxt service list $PATH`
8. Upload the three test clips into the hosted table, call `/mixable` for the `9A` clip, call `/match` for the `9A` clip with both sentences in the spec, create one sample, and show `pxt rows $PATH/tracks`, `pxt rows $PATH/phrases`, and `pxt rows $PATH/samples`. The hosted `/match` call also needs `OPENAI_API_KEY` on the service. If that key is not available there, show the curls and say the calls were not made.

`pxt db update` uploads the project and builds the image when the Python environment changed. The first build takes several minutes, and longer with `torch`. It does not insert rows and it does not start HTTP. `pxt schema update` creates the tables and the view. `pxt service update` starts the hosted routes. `pxt service run` is local only. Do not use it in this phase.

Copy the service URL from `pxt service list`. Do not invent the hostname. A call to that URL needs the human's key in the `X-api-key` header. A call with no key returns 401. Ask the human for the key, or ask them to run `pxt key create`. If they have not given you a key, show the curls with a placeholder and say the calls were not made.

Stop. Report what the spec's **Report back** section asks for after phase 3.
