import sys
import json
import logging
import traceback
from pathlib import Path
from typing import Dict, Any, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class FormAutomationError(Exception):
    pass


def find_field(page, field_name: str, container=None, search_in_frames=True):
    base = container if container else page

    label = base.locator(f"label:has-text('{field_name}')").first
    if label.count() > 0:
        for_id = label.get_attribute("for")
        if for_id:
            element = base.locator(f"[id='{for_id}']").first
            if element.count() > 0:
                logger.debug(f"Найдено поле '{field_name}' по for")
                return element

    element = base.locator(
        f"label:has-text('{field_name}') >> input, "
        f"label:has-text('{field_name}') >> textarea, "
        f"label:has-text('{field_name}') >> select"
    ).first
    if element.count() > 0:
        logger.debug(f"Найдено поле '{field_name}' по комбинатору")
        return element

    element = base.locator(
        f"input[placeholder*='{field_name}'], "
        f"textarea[placeholder*='{field_name}'], "
        f"select[placeholder*='{field_name}']"
    ).first
    if element.count() > 0:
        logger.debug(f"Найдено поле '{field_name}' по placeholder")
        return element

    element = base.locator(
        f"input[name*='{field_name}'], "
        f"textarea[name*='{field_name}'], "
        f"select[name*='{field_name}']"
    ).first
    if element.count() > 0:
        logger.debug(f"Найдено поле '{field_name}' по name")
        return element

    element = base.locator(
        f"input[id*='{field_name}'], "
        f"textarea[id*='{field_name}'], "
        f"select[id*='{field_name}']"
    ).first
    if element.count() > 0:
        logger.debug(f"Найдено поле '{field_name}' по id")
        return element

    element = base.locator(f"[aria-label*='{field_name}']").first
    if element.count() > 0:
        logger.debug(f"Найдено поле '{field_name}' по aria-label")
        return element

    if search_in_frames:
        for frame in page.frames:
            if frame == page:
                continue
            element = find_field(frame, field_name, None, False)
            if element:
                return element

    logger.warning(f"Поле '{field_name}' не найдено")
    return None

def fill_step(page, step_data: Dict[str, Any]):
    for field_name, value in step_data.items():
        element = find_field(page, field_name)
        if element:
            element.fill("")
            element.fill(str(value))
            logger.info(f"Заполнено поле '{field_name}': {value}")
        else:
            logger.warning(f"Поле '{field_name}' пропущено – не найдено на странице")


def fill_select(page, select_data: Dict[str, str], container=None):
    for label_text, value in select_data.items():
        element = find_field(page, label_text, container, search_in_frames=True)
        if element is None:
            logger.warning(f"Выпадающий список '{label_text}' не найден")
            continue

        tag_name = element.evaluate("el => el.tagName.toLowerCase()")
        if tag_name != "select":
            logger.warning(f"Найденный элемент для '{label_text}' не является select (тег: {tag_name})")
            continue

        element.select_option(label=value)
        logger.info(f"Выбрано значение '{value}' в списке '{label_text}'")


def upload_file(page, file_path: str):
    try:
        file_input = page.locator("input[type='file']")
        file_input.wait_for(state="visible", timeout=10000)
        file_input.set_input_files(file_path)
        logger.info(f"Файл {file_path} выбран для загрузки")
        page.wait_for_selector("button:has-text('Зафиксировать идентификатор'):not([disabled])", timeout=15000)
        logger.info("Кнопка 'Зафиксировать идентификатор' активна")
    except PlaywrightTimeoutError:
        page.wait_for_load_state("networkidle")
        logger.info("Загрузка файла завершена (ожидание сети)")
    except Exception as e:
        raise FormAutomationError(f"Ошибка при загрузке файла: {e}")


def click_next(page, step_name: str, button_name: str):
    button = page.locator(f"button:has-text('{button_name}')")
    if button.count() > 0:
        logger.info(f"Нажата кнопка '{button_name}' на шаге {step_name}")
        button.click()
        return
    raise FormAutomationError(f"Не найдена кнопка перехода на шаге {step_name}")


def run_automation(data: Dict[str, Any]) -> Dict[str, Any]:
    file_path = data.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise FormAutomationError(f"Файл не найден: {file_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=ChromeWhatsNewUI',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-automation',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-extensions'
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)\
             Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            // Также удалить другие признаки автоматизации
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        page.goto("https://sixmo.ru/")

        try:
            logger.info("Открытие страницы https://sixmo.ru/")
            page.goto("https://sixmo.ru/", timeout=30000)
            page.wait_for_load_state("networkidle")


            steps = data.get("steps", [])
            for i, step in enumerate(steps, start=1):
                logger.info(f"=== Шаг {i} ===")
                """logger.info("Текущий URL: " + page.url)
                iframes = page.frames
                logger.info(f"Количество iframe: {len(iframes)}")
                labels = page.locator("label.field-label").all_text_contents()
                logger.info(f"Найдены метки: {labels}")"""
                labels = page.locator("label.field-label").all_text_contents()
                logger.info(f"Найдены метки: {labels}")

                if "fields" in step:
                    fill_step(page, step["fields"])

                if "select" in step:
                    fill_select(page, step["select"])

                if step.get("upload_file"):
                    upload_file(page, file_path)

                if "button" in step:
                    click_next(page, f"step{i}", step["button"])
                    page.wait_for_selector("form.step-card, .field-shell", timeout=100000)
                    if i == 2:
                        page.wait_for_selector("label:has-text('Как называется платформа')", timeout=10000)
                    logger.info("Текущий URL: " + page.url)

            try:
                page.wait_for_selector(".result-card", timeout=15000)

                identifier = page.locator(".identifier-box strong").inner_text()
                result_title = page.locator(".result-card h2").inner_text()

                return {
                    "success": True,
                    "identifier": identifier,
                    "result": result_title,
                }
            except PlaywrightTimeoutError:
                screenshot_bytes = page.screenshot(full_page=True)
                return {
                    "success": False,
                    "error": "Не удалось получить финальный результат",
                    "screenshot": screenshot_bytes.hex()
                }

        except Exception as e:
            logger.error(f"Ошибка: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
            }
        finally:
            browser.close()


def main():
    if len(sys.argv) < 2:
        print("Использование: python form_automation.py <input.json>")
        print("Или: cat input.json | python form_automation.py")
        sys.exit(1)

    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            input_data = json.load(f)


    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Некорректный JSON: {e}"}))
        sys.exit(1)

    try:
        result = run_automation(input_data)
        print(json.dumps(result, ensure_ascii=False))
    except FormAutomationError as e:
        print(json.dumps({"success": False, "error": str(e)}))


if __name__ == "__main__":
    main()