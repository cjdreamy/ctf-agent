# CTF Agent — Featherless setup and operator notes

This companion guide documents the Featherless integration and practical run commands. The original `README.md` remains the project overview. The existing Docker sandbox image is reused; model providers run in the host Python process, while solver tools execute in per-solver Docker containers.

## How the pieces fit

- `ctf-solve` runs the coordinator and solver orchestration on the host.
- The coordinator can use Claude SDK, Codex, or Featherless. When `FEATHERLESS_API_KEY` is set, Featherless is selected automatically unless `--coordinator` is supplied.
- Each selected solver model receives the challenge prompt and tool results, and can call tools such as `bash`, `read_file`, and `write_file` against its isolated challenge workspace in Docker.
- `featherless/<Hugging Face model ID>` routes through Featherless's OpenAI-compatible chat API. For example, `featherless/Qwen/Qwen3-Coder-30B-A3B-Instruct` preserves the full repository-style model ID.

## Setup

1. Install the project dependencies:

   ```bash
   uv sync
   ```

2. Build the sandbox once if the image is not already available:

   ```bash
   docker build -f sandbox/Dockerfile.sandbox -t ctf-sandbox .
   ```

   The Dockerfile is `sandbox/Dockerfile.sandbox`; this project does not need a second copy. Check for the existing image with `docker image inspect ctf-sandbox`.

3. Create `.env` from `.env.example`, then set the Featherless key and CTFd connection:

   ```env
   FEATHERLESS_API_KEY=your_featherless_key
   CTFD_URL=https://ctf.example.com
   CTFD_TOKEN=your_ctfd_token
   ```

   Keep `.env` private and out of version control. Add `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, and other credentials only for providers you use.

4. Confirm the desired model's exact API model ID in the Featherless model catalog. API compatibility does not guarantee that every model supports the tool calls or structured output this agent uses; models with reliable tool calling are preferred.

## Run commands

Solve one downloaded challenge locally without submitting a flag:

```bash
uv run ctf-solve \
  --challenge challenges/<challenge-directory> \
  --models 'featherless/Qwen/Qwen3-Coder-30B-A3B-Instruct' \
  --no-submit -v
```
GLM 4.7
DeepSeek V3.2
Qwen3-Coder

Run several Featherless solvers in parallel on one challenge (each spec starts a solver):

```bash
uv run ctf-solve \
  --challenge challenges/<challenge-directory> \
  --models 'featherless/Qwen/Qwen3-Coder-30B-A3B-Instruct' \
  --models 'featherless/deepseek-ai/DeepSeek-V3.2' \
  --no-submit -v
```

Run the coordinator and solvers against CTFd using only Featherless credentials:

```bash
uv run ctf-solve \
  --ctfd-url https://ctf.example.com \
  --ctfd-token "$CTFD_TOKEN" \
  --models 'featherless/Qwen/Qwen3-Coder-30B-A3B-Instruct' \
  --models 'featherless/deepseek-ai/DeepSeek-V3.2' \
  --max-challenges 3 -v
```

The Featherless coordinator defaults to the first Featherless model in `--models`. To use a different model, pass `--coordinator-model 'featherless/<model-id>'`. Claude and Codex coordinator choices remain available when their CLIs are configured. For Gemini solvers, use `google/<model-id>` (for example `google/gemini-3-flash-preview`). You can combine model specs from supported providers by repeating `--models`.

When `FEATHERLESS_API_KEY` is set and no `--models` are supplied, the CLI defaults to the documented Qwen3-Coder model. Otherwise it uses the built-in Claude/Codex lineup. Explicit `--models` makes API usage and concurrency predictable. `--max-challenges` controls challenge concurrency; the number of Docker solver containers can reach `max-challenges × number of models`.

## Fast and accurate solving

- Start with a small mixed lineup of capable, tool-using models; expand only when model quality justifies the additional latency and API cost.
- Use `--no-submit` while checking an unfamiliar model or challenge workflow. It prevents CTFd submissions but still lets the model return a candidate flag.
- Keep challenge concurrency modest until you know your Docker host and provider limits can handle the resulting number of containers and requests.
- Models differ in tool-call support, context limits, latency, and cost. Confirm those details in the Featherless catalog and monitor solver logs/traces; no model lineup guarantees a solve.
- The sandbox is shared with the selected solver's challenge files and tools. Use it only for authorized CTF environments.

## Existing and added provider behavior

| Spec prefix | Backend | Credential |
|---|---|---|
| `claude-sdk/` | Claude Agent SDK solver | Claude CLI/session, with Anthropic key as applicable |
| `codex/` | Codex CLI solver | Configured Codex CLI |
| `google/` | Pydantic AI Google model | `GEMINI_API_KEY` |
| `featherless/` | Pydantic AI OpenAI-compatible solver and coordinator | `FEATHERLESS_API_KEY` |
| `bedrock/`, `azure/`, `zen/` | Existing API model backends | Corresponding settings in `.env.example` |

Featherless API reference: [API overview](https://featherless.ai/docs/api-overview-and-common-options) and [quickstart](https://featherless.ai/docs/quickstart-guide). The integration uses their documented base URL `https://api.featherless.ai/v1`.
