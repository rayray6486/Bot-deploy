# SHC RAG Runbook

This add-on gives Slum House Capital agents a shared retrieval-augmented knowledge layer. Follow the quick steps below whenever you add market PDFs or need to refresh the index.

## 1. Add training material
1. Drop new PDFs under `knowledge/market/` (nested folders allowed).
2. Keep filenames descriptive – the stem becomes the source shortname used in citations.
3. Only include text-based PDFs. Scanned images without selectable text are ignored.

## 2. Build or refresh the index
Run the ingestion helper any time new PDFs arrive or existing ones change. The script reuses unchanged chunks by file size and mtime, so re-running nightly is safe.

```bash
python scripts/ingest_docs.py
```

Outputs land in `data/index/` (`index.faiss` + `meta.json`). The folder is git-ignored; redeployments should rebuild locally. If no PDFs are found you will see a warning and the index is cleared.

## 3. Use the RAG commands
* `/ask <question>` – returns a concise 6–10 line answer with compact citations like `[Candlestick_Playbook §3]`.
* `/learn search <query>` – surfaces the top five chunks with short snippets. Click the buttons to expand any chunk inline.
* `/explain_signal <ticker> <setup> [timeframe]` – produces an 8–12 line playbook: thesis, entry/invalid, risk note, and two traps plus citations.

All bot replies paraphrase the sources and never quote more than ~90 consecutive characters.

## 4. Automatic agent usage
WriterAgent and RiskAgent call the same RAG backend when drafting alerts:
* “Why this setup” paragraphs cite the same `[Doc §N]` labels and append a `Sources:` line.
* Risk alerts finish with a “Watch-outs” section when traps are available.

## 5. Copyright & safety
* Only ingest documents you have rights to use internally.
* The RAG layer paraphrases; do not paste verbatim excerpts exceeding 90 characters.
* Citations stay compact (e.g., `[Brooks_BarByBar §12]`).
* Environment variables:
  * `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`)
  * `NEMOTRON_MODEL` (default `nemotron-mini`)
  * `OPENAI_API_KEY` and `OPENAI_MODEL` for fallback synthesis (optional)
  * `LEARN_CHANNEL_ID` to direct educational posts if needed.

Schedule the ingestion script nightly or trigger it after any PDF change so every agent uses the latest knowledge.
