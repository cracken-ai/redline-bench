"""Concurrent, uncapped generation against any OpenAI-compatible endpoint (vLLM, OpenRouter, ...).

Sends each benchmark prompt to the model under test. Issues many requests at once (so a local
vLLM batches them) with a large timeout and NO max_tokens — a low cap would truncate reasoning
models mid-thought and be misread as a refusal. Writes {item, model_response, error} jsonl (the
input run_judge.py consumes) and resumes by skipping item ids already present in --output.
"""
from __future__ import annotations

import argparse
import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class EmptyAnswer(Exception):
    """The endpoint returned no usable final answer (empty content, no refusal).

    Reasoning models sometimes stream a truncated chain-of-thought with an empty `content`
    and no error — this is a generation/stream failure, NOT a safety refusal. If it were saved
    as the model_response, the judge (which grades only the text after the last </think>) would
    see nothing and mislabel it a refusal. We raise instead, so the caller retries, and only
    persist it as an `error` if it never recovers — keeping it out of the refusal count.
    """


# Transient generation failures worth retrying: an empty/broken final answer, a dropped or
# truncated stream (IncompleteRead), a DNS/connection blip (URLError), a 5xx from the provider,
# or a socket timeout. All of these are provider/network instability, not a real model refusal —
# retrying usually recovers a full answer, so none of them should be persisted as a response.
RETRYABLE = (
    EmptyAnswer,
    urllib.error.URLError,
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    ConnectionError,
    TimeoutError,
)


def _one_call(url: str, payload: dict, headers: dict, timeout: int) -> str:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    choice = data["choices"][0]
    msg = choice["message"]
    finish = choice.get("finish_reason")
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    if not content.strip() and msg.get("refusal"):
        return msg["refusal"]
    # A truncated generation (finish_reason == "length") or a reasoning trace that never produced
    # a final answer (content empty while reasoning is present) is a broken output, not a refusal.
    if finish == "length" or (reasoning and not content.strip()):
        raise EmptyAnswer(f"finish={finish} content_len={len(content)} reasoning_len={len(reasoning)}")
    # Reasoning models return the chain-of-thought in a separate `reasoning` field. Reconstruct
    # the baseline shape "<reasoning></think><final answer>" so the judge (which strips up to the
    # last </think>) grades only the final answer, exactly as for the local vLLM baselines.
    if reasoning:
        return f"{reasoning}\n</think>\n{content}"
    return content


def complete(prompt: str, base_url: str, model: str, api_key: str | None, timeout: int,
             retries: int = 3) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions" if url.endswith("/v1") else f"{url}/v1/chat/completions"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _one_call(url, payload, headers, timeout)
        except urllib.error.HTTPError as exc:
            # A 4xx is a real client error (bad model slug, auth, malformed request) -> don't
            # retry, it will only fail the same way. A 5xx is a provider hiccup -> retry.
            last = exc
            if exc.code < 500 or attempt >= retries:
                raise
            time.sleep(2 * (attempt + 1))
        except RETRYABLE as exc:  # broken stream / dropped connection / no final answer -> retry
            last = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    assert last is not None
    raise last


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="dummy")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    items = [json.loads(l) for l in args.dataset.open() if l.strip()]
    if args.limit:
        items = items[: args.limit]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    done_ids = set()
    if args.output.exists():
        for l in args.output.open():
            try:
                done_ids.add(json.loads(l)["item"]["id"])
            except Exception:  # noqa: BLE001
                pass
    todo = [it for it in items if it.get("id") not in done_ids]
    print(f"[gen] {len(todo)} todo / {len(items)} total ({len(done_ids)} already done)", flush=True)

    out_f = args.output.open("a")
    lock = threading.Lock()
    counter = {"n": 0}

    def work(item: dict) -> None:
        try:
            resp = complete(item["prompt"], args.base_url, args.model, args.api_key, args.timeout)
            rec = {"item": item, "model_response": resp, "error": None}
        except Exception as exc:  # noqa: BLE001
            rec = {"item": item, "model_response": "", "error": f"{type(exc).__name__}: {exc}"}
        with lock:
            out_f.write(json.dumps(rec) + "\n")
            out_f.flush()
            counter["n"] += 1
            print(f"[gen] {counter['n']}/{len(todo)} {item.get('id')}: "
                  f"len={len(rec['model_response'] or '')} err={rec['error']}", flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        list(ex.map(work, todo))
    out_f.close()
    print("[gen] DONE", flush=True)


if __name__ == "__main__":
    main()
