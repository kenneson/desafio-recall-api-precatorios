from __future__ import annotations

import re
import unicodedata

from src.domain import COLETA_PRECATORIO_PATTERN
from src.services import RPA_SOURCE_URL


def coletar_precatorios_tjpr(ente_devedor: str | None, timeout_segundos: int) -> list[str]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright nao esta instalado. Execute: "
            "python -m pip install -r requirements.txt && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(RPA_SOURCE_URL, wait_until="domcontentloaded", timeout=60_000)
            _try_select_debtor(page, ente_devedor)
            # O portal exige captcha/pesquisa manual; aguarda a tabela expor
            # um identificador coletavel em vez de tentar burlar a verificacao.
            page.wait_for_function(
                "(pattern) => document.body && new RegExp(pattern).test(document.body.innerText)",
                arg=rf"\b{COLETA_PRECATORIO_PATTERN}\b",
                timeout=timeout_segundos * 1000,
            )
            text = page.locator("body").inner_text()
            return extract_precatorio_numbers(text)
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
            options = select.evaluate(
                """
                (element) => Array.from(element.options).map((option) => ({
                    label: option.label || option.textContent || "",
                    value: option.value || ""
                }))
                """
            )
            selected_option = choose_debtor_option(options, ente_devedor)
            if not selected_option:
                continue
            if selected_option["value"]:
                select.select_option(value=selected_option["value"], timeout=1_000)
            else:
                select.select_option(label=selected_option["label"], timeout=1_000)
            return
        except Exception:
            continue


def extract_precatorio_numbers(text: str) -> list[str]:
    pattern = re.compile(rf"\b{COLETA_PRECATORIO_PATTERN}\b")
    return _dedupe_preserving_order(pattern.findall(text))


def choose_debtor_option(options: list[dict[str, str]], desired: str) -> dict[str, str] | None:
    desired_normalized = _normalize_text(desired)
    if not desired_normalized:
        return None

    # As opcoes do TJPR incluem sufixos como "Regime geral"; prefixo/contencao
    # permite payloads como "CURITIBA" sem hard-code.
    normalized_options = [
        (option, _normalize_text(option.get("label", "")))
        for option in options
        if option.get("label") and "selecione" not in _normalize_text(option.get("label", ""))
    ]

    for option, label in normalized_options:
        if label == desired_normalized:
            return option

    for option, label in normalized_options:
        if label.startswith(desired_normalized):
            return option

    for option, label in normalized_options:
        if desired_normalized in label:
            return option

    return None


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_marks.lower()).strip()


def _dedupe_preserving_order(numbers: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for number in numbers:
        if number in seen:
            continue
        seen.add(number)
        deduped.append(number)
    return deduped
