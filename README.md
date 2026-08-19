# bank_agent

Logs in to a bank portal (login form in a **varying** location), passes an **email-OTP**
step by reading the code from Gmail, then **downloads the latest statement PDF** — for each
(bank, user), launchable from a small UI. Ships with **20 mock bank portals** to run against.

Design: **hybrid** — deterministic Playwright drives the flow; Claude Opus (Azure AI Foundry)
is used only for the hard judgement calls. Built on harness-engineering principles
(context, loops, memory, security). See `.claude/skills/bank-statement-agent/SKILL.md`.

## Layout

```
banks/     20 mock portals (one FastAPI app; login placement varies per bank)
harness/   the automation: vault, llm, email_reader, detect, stages, agent, memory
ui/        the launcher web page
secrets/   vault.yaml (gitignored) — credentials; vault.example.yaml is the template
config.yaml  runtime switches (mail + llm backends, ports)
```

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp secrets/vault.example.yaml secrets/vault.yaml   # already present for local testing
```

## Run (local, offline — default)

```bash
# 1) start the 20 mock banks
python -m bank_agent.banks.run                      # http://127.0.0.1:8000/bank/bank01/

# 2a) run one job from the CLI
python -m bank_agent.harness.run_job --bank bank03 --user user1
python -m bank_agent.harness.run_job --bank bank03 --user user1 --headed   # watch it

# 2b) or use the UI
python -m bank_agent.ui.run                         # http://127.0.0.1:8500/
```

Statements land in `downloads/<bank>/<user>/`. Per-run events go to `journal.jsonl`
(redacted); learned per-bank login shapes go to `recipes/<bank>.json`.

## Switch to the production paths (config.yaml)

- **Real Gmail OTP:** set `mail.backend: gmail` and put a 16-char **Gmail App Password** in
  `secrets/vault.yaml` (`gmail_app_password`). Banks then send via Gmail SMTP and the reader
  pulls the code via IMAP — no code change.
- **Real Claude Opus:** set `llm.backend: azure` and fill `azure_foundry` in the vault
  (endpoint, api_key, model). The three judgement calls then use the model; everything else
  is unchanged.

## Security

Vault-injection: the model only ever sees placeholders — real credentials and the OTP are
typed into the page by deterministic code and are **never** sent to the LLM, logged, or
screenshotted (verified: 0 secrets in `journal.jsonl`). Each (bank, user) runs in an
isolated browser context; downloads are validated as real PDFs.

## Status

Verified end-to-end on all **20/20** banks (all five login-placement variants): login → OTP
→ latest-statement download, with recipe cache populated and no secret leakage.
