# -*- coding: utf-8 -*-
"""
PR alert bot: polls GitHub PRs and sends Telegram alerts.
Events: new PR, review submitted, merge/close, new pushes (head sha change).
Single pass per run; state persisted in pr_alert_state.json.
First run seeds state silently (no alert spam).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "pr_alert_config.json"
STATE_PATH = BASE_DIR / "pr_alert_state.json"

MAX_ALERTS_PER_RUN = 20


def http_json(url, headers=None, method="GET", payload=None):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, method=method, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gh_get(cfg, path):
    return http_json(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"token {cfg['github_token']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pr-alert-bot",
        },
    )


def tg_send(cfg, text):
    http_json(
        f"https://api.telegram.org/bot{cfg['tg_token']}/sendMessage",
        method="POST",
        payload={
            "chat_id": cfg["tg_chat_id"],
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def pr_line(pr):
    return (
        f"<a href=\"{pr['html_url']}\">#{pr['number']}</a> "
        f"<b>{esc(pr['title'])}</b> ({esc(pr['user']['login'])})"
    )


REVIEW_LABELS = {
    "APPROVED": "✅ аппрув",
    "CHANGES_REQUESTED": "🔁 запрошены правки",
    "COMMENTED": "💬 комментарий",
    "DISMISSED": "🚫 ревью снято",
}


def load_config():
    env = os.environ
    if env.get("GH_TOKEN") and env.get("TG_TOKEN") and env.get("TG_CHAT_ID"):
        return {
            "repo": env.get("REPO", "Eksiled/jobbot"),
            "github_token": env["GH_TOKEN"],
            "tg_token": env["TG_TOKEN"],
            "tg_chat_id": env["TG_CHAT_ID"],
        }
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def main():
    cfg = load_config()
    repo = cfg["repo"]

    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    else:
        state = {"prs": {}}
    prs_state = state.setdefault("prs", {})
    seeded = bool(prs_state)

    pulls = gh_get(
        cfg,
        f"/repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=30",
    )

    alerts = []

    for pr in pulls:
        num = str(pr["number"])
        prev = prs_state.get(num)
        cur = {
            "state": pr["state"],
            "head_sha": pr["head"]["sha"],
            "merged": bool(pr.get("merged_at")),
            "review_ids": prev["review_ids"] if prev else [],
            "title": pr["title"],
        }

        if prev is None:
            if seeded:
                alerts.append(f"🆕 <b>Новый PR</b>\n{pr_line(pr)}")
            # fetch reviews so first-seen PRs don't replay old reviews
            reviews = gh_get(cfg, f"/repos/{repo}/pulls/{num}/reviews")
            cur["review_ids"] = [r["id"] for r in reviews]
            prs_state[num] = cur
            continue

        # merge / close
        if prev["state"] == "open" and pr["state"] == "closed":
            if pr.get("merged_at"):
                by = (pr.get("merged_by") or {}).get("login", "?")
                alerts.append(
                    f"🟣 <b>PR влит</b> (merge by {esc(by)})\n{pr_line(pr)}"
                )
            else:
                alerts.append(f"❌ <b>PR закрыт без мержа</b>\n{pr_line(pr)}")

        # new pushes
        if (
            pr["state"] == "open"
            and prev["state"] == "open"
            and prev["head_sha"] != pr["head"]["sha"]
        ):
            alerts.append(f"📦 <b>Новые коммиты в PR</b>\n{pr_line(pr)}")

        # reviews: only refetch when something changed on the PR
        if pr["state"] == "open" or prev["state"] == "open":
            try:
                reviews = gh_get(cfg, f"/repos/{repo}/pulls/{num}/reviews")
            except urllib.error.HTTPError:
                reviews = []
            known = set(prev.get("review_ids", []))
            for r in reviews:
                if r["id"] not in known:
                    label = REVIEW_LABELS.get(r["state"], r["state"].lower())
                    body = (r.get("body") or "").strip()
                    extra = f"\n<i>{esc(body[:200])}</i>" if body else ""
                    alerts.append(
                        f"👀 <b>Ревью по PR: {label}</b> от {esc(r['user']['login'])}\n"
                        f"{pr_line(pr)}{extra}"
                    )
                    known.add(r["id"])
            cur["review_ids"] = sorted(known)

        prs_state[num] = cur

    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    for text in alerts[:MAX_ALERTS_PER_RUN]:
        tg_send(cfg, text)
        time.sleep(0.3)

    print(f"pulls={len(pulls)} alerts={len(alerts)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
