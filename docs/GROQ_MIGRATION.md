# QM-01 - QuickMind Groq-only AI

QuickMind calls Groq directly for its text, task, subtask, document, Outlook and vision AI features. It no longer requires Ollama, Mistral or LLaVA to run these features.

## Configuration

Set a real `GROQ_API_KEY` in the local, **untracked** QuickMind `.env` file for desktop use, or in the environment passed to Docker. Never commit credentials.

Optional variables:
- `GROQ_MODEL=llama-3.3-70b-versatile`
- `GROQ_VISION=meta-llama/llama-4-scout-17b-16e-instruct`

Validate these models against the account's accessible models if Groq reports HTTP 404. Vision requires an image-capable model.

For the BDS Local Lab, configure these variables in the **untracked** `BDS-Infrastructure/.env`; the `compose.quickmind.yaml` stack forwards them into the QuickMind container.

## Start and verify from the BDS Local Lab

```powershell
cd C:\code\python\QuickMind
git fetch origin
git switch feature/qm-01-groq-only

cd ..\BDS-Infrastructure
docker compose -f compose.quickmind.yaml up -d --build
docker compose -f compose.quickmind.yaml ps
Invoke-RestMethod http://localhost:8765/health
Invoke-RestMethod http://localhost:8765/ai/status
```

The status endpoint should report `groq_key: true`, `groq: true`, `active: groq/<model>`, and `ollama: false`. Test `/task/ai`, `/task/{id}/subtasks/ai`, `/groq/status` and the web assistant/vision workflow. A real request requires a valid API key, network access and available provider quota.

Offline regression tests:

```powershell
cd C:\code\python\QuickMind
python -m pip install -r requirements.api.txt
python -m unittest discover -s tests -v
```

No database migration is needed. The named `quickmind-data` volume must not be deleted. Do not use `docker compose down -v`.

## Boundaries and future convergence

`agents/ai_client.py` is the interim provider adapter. Business logic remains in QuickMind. A future AgentHub AI Gateway can replace the adapter without changing each caller; no shared gateway is deployed as part of QM-01.

**Security:** Passing a Groq key into Compose makes it available inside the QuickMind container. Keep it out of Git and logs; authorize only BDS internal callers to QuickMind HTTP endpoints.
