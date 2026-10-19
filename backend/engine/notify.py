"""Phone alerts: Telegram (private, recommended) and/or ntfy.sh. Both free. Silent if not configured.

backend/.env:
  TELEGRAM_BOT_TOKEN=123456:ABC...   (from @BotFather)
  TELEGRAM_CHAT_ID=123456789         (your numeric chat id)
  NTFY_TOPIC=some-long-random-name   (optional; anyone who knows the topic name can read it)
"""
from __future__ import annotations

import logging
import os
import threading

import requests

log = logging.getLogger("engine.notify")


def configured() -> bool:
    return bool((os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")) or os.getenv("NTFY_TOPIC"))


def _send(text: str) -> None:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram send failed: %s", exc)
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=text.encode("utf-8"), timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("ntfy send failed: %s", exc)


def send(text: str) -> None:
    """Fire-and-forget so a slow network never blocks the market loop."""
    if configured():
        threading.Thread(target=_send, args=(text,), daemon=True).start()


def fmt_event(ev: dict) -> str | None:
    t = ev.get("trade") or {}
    if ev["type"] == "paper_entry":
        return (f"PAPER ENTRY [{t['strategy']}]\n{t['side']} {t['symbol']}\n"
                f"{t['lots']} lot ({t['quantity']} qty) @ Rs {t['entry_premium']}"
                f"{' (over your risk budget)' if t.get('oversize') else ''}\n"
                f"Index stop {t['index_stop']:.0f} | target {t['index_target']:.0f}")
    if ev["type"] == "paper_exit":
        return (f"PAPER EXIT [{t['strategy']}] {t['symbol']}\n"
                f"Out @ Rs {t['exit_premium']} ({t['reason']})\nP&L Rs {t['pnl']:,.0f} after charges")
    return None
