from __future__ import annotations

import re

from src.domain import PRECATORIO_PATTERN
from src.services import RPA_SOURCE_URL


def coletar_precatorios_tjpr(ente_devedor: str | None, timeout_segundos: int) -> list[str]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright nao esta instalado. Execute: python -m pip install -e . && python -m playwright install chromium") from exc

    pattern = re.compile(rf"\b{PRECATORIO_PATTERN}\b")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(RPA_SOURCE_URL, wait_until="domcontentloaded", timeout=60_000)
            _try_select_debtor(page, ente_devedor)
            page.wait_for_function(
                f"document.body && /{PRECATORIO_PATTERN}/.test(document.body.innerText)",
                timeout=timeout_segundos * 1000,
            )
            text = page.locator("body").inner_text()
            return _dedupe_preserving_order(pattern.findall(text))
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Tempo esgotado aguardando a pesquisa manual e a tabela de resultados.") from exc
        finally:
            browser.close()


def _try_select_debtor(page, ente_devedor: str | None) -> None:
    if not ente_devedor:
        return

    candidates = page.locator("select")
    for index in range(candidates.count()):
        select = candidates.nth(index)
        try:
            select.select_option(label=ente_devedor, timeout=1_000)
            return
        except Exception:
            continue


def _dedupe_preserving_order(numbers: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for number in numbers:
        if number in seen:
            continue
        seen.add(number)
        deduped.append(number)
    return deduped

