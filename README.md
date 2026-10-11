# Philip Relay

[Korean](README.ko.md)


**Portable workflow, memory, and verification for coding agents.**

Philip Relay helps Claude Code and Codex continue work on the same project with a shared operating model. It connects project-state recovery, durable memory, completion checks, UI review, Game/Web/Research knowledge routing, and plugin-update audits.

> The installation and usage guide is available in English and Korean. The plugin procedures and default agent responses are currently Korean-first; bilingual documentation does not yet mean a fully localized runtime. Personal project code, memory, and domain knowledge are not included.

### Core principles

- Start with one agent moving through research, planning, implementation, and verification. Parallelize only independent work with a clear merge boundary.
- Load only the context needed for the current decision instead of injecting every manual at session start.
- Keep review and modification permissions separate. Never auto-update, auto-push, or execute commands found in remote reference material.
- Keep detailed Game/Web/Research knowledge in separate repositories and pin the reviewed immutable commit in each project.
- Promote a new global rule only after checking its scope, counterexamples, weaker alternatives, and behavioral evidence.

### Install

Claude Code:

```text
/plugin marketplace add juphil/Philip-relay
/plugin install philip@philip-relay
```

Codex:

```text
codex plugin marketplace add juphil/Philip-relay
codex plugin add philip@philip-relay
```

If your Codex version exposes plugin management through the UI or uses different command names, add this GitHub repository as a marketplace there and install `philip`. Start a new session after installation and verify that `philip:init`, `philip:status`, and `philip:done` are available.

### Start a project

Use the same command for a new or existing project:

```text
/philip:init Build an online co-op game for Windows with Korean and English support.
```

`init` is idempotent. It classifies existing rules, todo files, memory, and knowledge links as complete, partial, or missing, then fills only the missing pieces. It does not guess product decisions or overwrite an existing project wholesale.

Typical flow:

```text
/philip:status          Recover the current state and exact resume point
<your development task> Let the agent route to the relevant skill
/philip:done            Review, verify, update todo/handoff, and assess memory
```

Natural-language requests such as “update the project memory,” “where did we stop?”, and “review this thoroughly” are valid routing signals for `memory`, `status`, and `check`. You do not have to name a skill explicitly, but `/philip:memory` is available when you want deterministic routing.

### Skills

| Area | Skills | Purpose |
|---|---|---|
| Start and state | `init`, `status`, `done`, `memory`, `replan` | Set up, resume, close, hand off, and reorder work |
| Evidence and review | `check`, `prove`, `brief`, `updatecheck` | Review findings, run evidence-based checks, report clearly, audit updates |
| UI and structure | `designpick`, `designcheck`, `designfix`, `diagram` | Choose a direction, inspect rendered UI, fix approved defects, map structure |
| Knowledge routing | `game-dev`, `web-dev`, `research`, `researchnote` | Load only relevant Game/Web/Research references and record evidence |
| Experiments | `exp`, `judge` | Record and interpret CV/DL experiments without premature conclusions |
| Agent and repository bridge | `claude`, `codex`, `git`, `sync` | Connect hosts and move reviewed work safely |

### Personal knowledge boundary

```text
Philip Relay                  Separate knowledge repository        Each project
behavior · permissions  -->   game/web/research INDEX       -->   policy · pinned commit · exceptions
verification · routing
```

The plugin contains operating procedures and the knowledge-link contract, not personal game design notes, product-specific pixel values, or research project records. Projects declare approved sources in `.psp/knowledge.sources.json` and pin the reviewed commit in `.psp/knowledge.lock.json`.

### Releases and privacy

- Keep `VERSION` and all manifests on the same SemVer, and tag releases as `vX.Y.Z`.
- Run `philip:updatecheck plugin` before release to review hard-rule distortion and host-specific behavior.
- The public release check rejects secret formats, sensitive filenames, concrete home paths, private IP candidates, dead links, orphaned docs, unmanaged duplicates, and generated-skill drift.
- Public releases are curated; they are not automatic mirrors of a private development repository.
- A project records its last compatibility review in `.psp/runtime.json`. Version drift is reported but never auto-installed.

### Develop and verify

```powershell
python plugins/philip/tools/build_skills.py
python plugins/philip/tools/build_skills.py --check
python -m unittest discover -s plugins/philip/tools -p "test_*.py"
python tools/public_release_check.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), the [public promotion guide](docs/maintainers/public-promotion.md), [Apache-2.0 license](LICENSE), [NOTICE](NOTICE), and [third-party notices](THIRD_PARTY_NOTICES.md).
