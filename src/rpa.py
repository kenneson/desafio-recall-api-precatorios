from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.domain import COLETA_PRECATORIO_PATTERN, OFICIO_PRECATORIO_PATTERN, PRECATORIO_PATTERN
from src.services import RPA_SOURCE_URL


class RpaNoCollectableNumbers(RuntimeError):
    pass


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
            # linhas de resultado em vez de tentar burlar a verificacao.
            page.wait_for_function(
                """
                () => {
                    const normalize = (text) => text.normalize("NFD")
                        .replace(/[\\u0300-\\u036f]/g, "")
                        .toLowerCase();
                    return Array.from(document.querySelectorAll("table")).some((table) => {
                        const headerCells = Array.from(table.querySelectorAll("thead th"));
                        const fallbackHeaderCells = Array.from(table.querySelectorAll("tr:first-child th, tr:first-child td"));
                        const headers = (headerCells.length ? headerCells : fallbackHeaderCells)
                            .map((cell) => normalize(cell.innerText));
                        const hasAutosColumn = headers.some((header) =>
                            header.includes("autos") && header.includes("precatorio")
                        );
                        const bodyRows = table.tBodies.length
                            ? Array.from(table.tBodies).flatMap((tbody) => Array.from(tbody.rows))
                            : Array.from(table.querySelectorAll("tr")).slice(1);
                        const hasRows = bodyRows.some((row) => row.innerText.trim());
                        return hasAutosColumn && hasRows;
                    });
                }
                """,
                timeout=timeout_segundos * 1000,
            )
            numbers = extract_precatorio_numbers_from_tables(_extract_html_tables(page))
            if not numbers:
                raise RpaNoCollectableNumbers(
                    "Tabela carregada, mas nenhum identificador de precatorio foi encontrado nas colunas esperadas."
                )
            return numbers
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


def extract_precatorio_numbers_from_tables(tables: list[dict[str, Any]]) -> list[str]:
    for table in tables:
        headers = [str(header) for header in table.get("headers", [])]
        autos_index = _find_column_index(headers, ("autos", "precatorio"))
        if autos_index is None:
            continue

        numbers: list[str] = []
        for row in table.get("rows", []):
            if autos_index >= len(row):
                continue
            numbers.extend(extract_precatorio_numbers(str(row[autos_index])))
        if numbers:
            return _dedupe_preserving_order(numbers)

    for table in tables:
        headers = [str(header) for header in table.get("headers", [])]
        oficio_index = _find_column_index(headers, ("oficio", "precatorio"))
        if oficio_index is None:
            continue

        numbers = []
        for row in table.get("rows", []):
            if oficio_index >= len(row):
                continue
            numbers.extend(extract_oficio_precatorio_numbers(str(row[oficio_index])))
        if numbers:
            return _dedupe_preserving_order(numbers)

    return []


def extract_oficio_precatorio_numbers(text: str) -> list[str]:
    pattern = re.compile(rf"\b{OFICIO_PRECATORIO_PATTERN}\b")
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


def _extract_html_tables(page) -> list[dict[str, list[Any]]]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll("table")).map((table) => {
            const headerCells = Array.from(table.querySelectorAll("thead th"));
            const fallbackHeaderCells = Array.from(table.querySelectorAll("tr:first-child th, tr:first-child td"));
            const headers = (headerCells.length ? headerCells : fallbackHeaderCells)
                .map((cell) => cell.innerText.trim());

            const bodyRows = table.tBodies.length
                ? Array.from(table.tBodies).flatMap((tbody) => Array.from(tbody.rows))
                : Array.from(table.querySelectorAll("tr")).slice(1);

            const rows = bodyRows.map((row) =>
                Array.from(row.querySelectorAll("td")).map((cell) => cell.innerText.trim())
            );

            return { headers, rows };
        })
        """
    )


def _find_column_index(headers: list[str], required_terms: tuple[str, ...]) -> int | None:
    normalized_terms = tuple(_normalize_text(term) for term in required_terms)
    for index, header in enumerate(headers):
        normalized_header = _normalize_text(header)
        if all(term in normalized_header for term in normalized_terms):
            return index
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
