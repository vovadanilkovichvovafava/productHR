"""Отправить дамп базы в бэкенд по частям и дождаться pg_restore (27.10.2026).

Пара к api/routes/dump_import.py. Только стандартная библиотека — запускается
любым python3 на компьютере, без установки пакетов.

    python3 upload_dump.py --url https://<бэкенд> --dump ~/Downloads/x.dump \\
        --token-file ~/Downloads/newhr-import-token.txt

Токен — то же значение, что в переменной IMPORT_DUMP_TOKEN у бэкенда. Части
по 20 МБ (ниже лимита Cloudflare в 100 МБ на запрос), каждая с повтором и
сверкой хеша. Восстановление ЗАМЕНЯЕТ базу бэкенда содержимым дампа.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

CHUNK = 20 * 1024 * 1024
RETRIES = 5


def call(url: str, token: str, method: str, path: str, data: bytes = None, json_body=None, timeout: int = 300):
    headers = {"X-Import-Token": token}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url.rstrip("/") + "/api/dump-import" + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--chunk-mb", type=int, default=CHUNK // (1024 * 1024))
    args = ap.parse_args()

    token = open(os.path.expanduser(args.token_file)).read().strip()
    path = os.path.expanduser(args.dump)
    size = os.path.getsize(path)
    chunk = args.chunk_mb * 1024 * 1024

    print(f"Файл {os.path.basename(path)}: {size / 1024 / 1024:.0f} МБ, считаю хеш…", flush=True)
    whole = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            whole.update(block)
    digest = whole.hexdigest()

    call(args.url, token, "POST", "/start")
    started = time.time()
    with open(path, "rb") as f:
        offset = 0
        while offset < size:
            data = f.read(chunk)
            expected = hashlib.sha256(data).hexdigest()
            for attempt in range(1, RETRIES + 1):
                try:
                    res = call(args.url, token, "PUT", f"/chunk?offset={offset}", data=data)
                    if res.get("sha256") != expected:
                        raise RuntimeError("хеш части не совпал")
                    break
                except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
                    if attempt == RETRIES:
                        print(f"\nЧасть с позиции {offset} не ушла: {e}", file=sys.stderr)
                        return 1
                    time.sleep(3 * attempt)
            offset += len(data)
            speed = offset / max(time.time() - started, 1) / 1024 / 1024
            print(f"\rОтправлено {offset * 100 // size}% ({offset / 1024 / 1024:.0f} МБ, {speed:.1f} МБ/с)", end="", flush=True)
    print("\nВсё отправлено, сервер сверяет хеш и запускает восстановление…", flush=True)

    try:
        call(args.url, token, "POST", "/finish", json_body={"size": size, "sha256": digest})
    except urllib.error.HTTPError as e:
        print(f"Сервер отказал: {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1

    while True:
        time.sleep(10)
        try:
            st = call(args.url, token, "GET", "/status", timeout=60)
        except urllib.error.URLError as e:
            print(f"  (статус не получен: {e}, жду)", flush=True)
            continue
        if st["stage"] == "restoring":
            print(f"  восстанавливается… строк с ошибками пока: {st['errors']}", flush=True)
            continue
        print(f"Итог: {st['stage']}, код {st['returncode']}, строк с ошибками {st['errors']}")
        for line in st.get("stderr_tail") or []:
            print("   ", line)
        return 0 if st["stage"] in ("done", "done_with_errors") else 2


if __name__ == "__main__":
    sys.exit(main())
