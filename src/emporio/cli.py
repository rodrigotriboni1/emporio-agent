"""Terminal chat with Mel: `uv run python -m emporio.cli`."""

import os
import sys
import traceback

from emporio import config
from emporio.agent import Deps, agent

GENERIC_ERROR = "Desculpe, tive um problema para responder agora. Pode tentar de novo em instantes?"


def main() -> None:
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    try:
        deps = Deps(now=config.clock())
    except ValueError as error:
        sys.exit(str(error))
    history = []
    print("Olá! Eu sou a Mel, do Empório da Música. Para sair, use Ctrl+D ou Ctrl+C.")
    try:
        while True:
            text = input("Você: ").strip()
            if not text:
                continue
            try:
                result = agent.run_sync(text, message_history=history, deps=deps)
            except Exception as error:
                print(GENERIC_ERROR)
                print(f"[error] {error!r}", file=sys.stderr)
                traceback.print_exc()
                continue
            history = result.all_messages()
            print(f"Mel: {result.output}")
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    # Here, not in main(): the tests drive main() without a key.
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        sys.exit("OPENROUTER_API_KEY is not set. Add it to .env (see .env.example).")
    main()
