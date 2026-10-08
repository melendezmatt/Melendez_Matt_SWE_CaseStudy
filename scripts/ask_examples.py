"""Ask the brief's six example questions through a running API and print the answers.

    python scripts/ask_examples.py [--base-url http://localhost:8000] [--pause 65] [--only 3 4]

`--pause` waits between questions, for free-tier LLMs with a requests-per-minute limit.

Prints the answers for reading; `pytest -m live` asks the same questions and checks them.
Uses only the standard library.
"""

import argparse
import json
import time
import urllib.error
import urllib.request

QUESTIONS = [
    "What were NVDA's revenue and net income for the last three fiscal years?",
    "Which of the five companies had the highest gross margin last year?",
    "What is AAPL's trailing P/E right now?",
    "What new risk factors did NVDA add in its latest 10-K versus the prior year?",
    "How did MSFT's revenue grow last year, and what did management attribute it to?",
    "What is the company's forward guidance for next quarter?",
]


def ask(base_url: str, question: str) -> dict:
    request = urllib.request.Request(
        f"{base_url}/ask",
        data=json.dumps({"question": question}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--pause", type=float, default=0, help="seconds between questions")
    parser.add_argument("--only", type=int, nargs="*", help="question numbers to ask (1-6)")
    args = parser.parse_args()

    for number, question in enumerate(QUESTIONS, start=1):
        if args.only and number not in args.only:
            continue
        if args.pause and number > (min(args.only) if args.only else 1):
            time.sleep(args.pause)
        try:
            result = ask(args.base_url, question)
        except urllib.error.HTTPError as exc:
            print(f"\nQ: {question}\nERROR {exc.code}: {exc.read().decode()}")
            continue
        tools = ", ".join(c["tool"] + ("" if c["ok"] else " (failed)") for c in result["tool_calls"])
        print(f"\nQ: {question}")
        print(f"route: {result['route']}   tools: {tools or 'none'}")
        print(f"A: {result['answer']}")
        if result.get("unverified_numbers"):
            print(f"(figures not found in any tool result: {', '.join(result['unverified_numbers'])})")


if __name__ == "__main__":
    main()
