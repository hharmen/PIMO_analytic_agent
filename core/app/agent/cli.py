"""Агент из консоли (из папки core/):

    python -m app.agent.cli --models
    python -m app.agent.cli "текст требований"
    python -m app.agent.cli --file requirements.txt
"""

import argparse
import json
import sys

from app import config
from app.agent.service import get_llm_client, missing_llm_settings, run_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Агент-аналитик в консоли")
    parser.add_argument("text", nargs="?", help="Текст требований")
    parser.add_argument("--file", help="Файл с текстом требований (UTF-8)")
    parser.add_argument("--models", action="store_true", help="Показать модели, доступные по ключу")
    parser.add_argument("--show-model", action="store_true", help="Напечатать построенную JSON-модель")
    args = parser.parse_args()

    missing = missing_llm_settings(("LLM_BASE_URL", "LLM_API_KEY") if args.models else ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"))
    if missing:
        print("Задайте переменные окружения: " + ", ".join(missing), file=sys.stderr)
        return 2

    if args.models:
        for model in get_llm_client().models.list():
            print(model.id)
        return 0

    text = open(args.file, encoding="utf-8").read() if args.file else args.text
    if not text:
        parser.error("нужен текст требований или --file")

    print(f"LLM: {config.LLM_MODEL}, checker: {config.CHECKER_URL}\n")
    reply = run_agent([{"role": "user", "content": text}])

    if args.show_model and reply.model:
        print("=== Модель ===")
        print(json.dumps(reply.model, ensure_ascii=False, indent=2))
    if reply.check_result:
        print("=== Проверка ===")
        print(f"Общий статус: {reply.check_result.get('status')}")
        for item in reply.check_result.get("results", []):
            print(f"  {item['property_id']} ({item['property_type']}): {item['status']}")
    print("\n=== Ответ агента ===")
    print(reply.text)
    print(f"\nТокены: {reply.usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
