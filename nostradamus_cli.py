"""Menú interactivo de operación manual para Nostradamus V6."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from colorama import Fore, Style, just_fix_windows_console

from src.paper_trading import read_hash_chain


PROJECT_ROOT = Path(__file__).resolve().parent
BOGOTA = ZoneInfo("America/Bogota")
PAPER_WINDOW_START = time(19, 0)
PAPER_WINDOW_END = time(20, 30)
WIDTH = 76
COLOR_ENABLED = sys.stdout.isatty() and "NO_COLOR" not in os.environ
PIXEL_LOGO = (
    " █▄ █  ▄▀▄  ▄▀▀  ▀█▀  █▀█  ▄▀▄  █▀▄  ▄▀▄  █▄ ▄█  █ █  ▄▀▀\n"
    " █ ▀█  ▀▄▀  ▄██   █   █▀▄  █▀█  █▄▀  █▀█  █ ▀ █  ▀▄▀  ▄██"
)


def _paint(text: object, color: str = "", *, bright: bool = False) -> str:
    value = str(text)
    if not COLOR_ENABLED:
        return value
    prefix = (Style.BRIGHT if bright else "") + color
    return f"{prefix}{value}{Style.RESET_ALL}"


def _bar(value: float | None, *, width: int = 18) -> str:
    if value is None:
        return "░" * width
    bounded = min(1.0, max(0.0, float(value)))
    filled = round(bounded * width)
    return "█" * filled + "░" * (width - filled)


def _action_color(action: object) -> str:
    return {
        "operate": Fore.GREEN,
        "no_trade": Fore.YELLOW,
        "abstain": Fore.MAGENTA,
        "already_decided": Fore.CYAN,
    }.get(str(action), Fore.WHITE)


def _section(title: str) -> None:
    print("\n" + _paint(f"┌─ {title} " + "─" * max(1, WIDTH - len(title) - 4), Fore.CYAN))


def _print_reason(reason: object) -> None:
    lines = textwrap.wrap(str(reason), width=68) or [""]
    for index, line in enumerate(lines):
        prefix = "  └─ " if index == 0 else "     "
        print(_paint(prefix + line, Fore.WHITE))


def _clear_screen() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def _configure_console() -> None:
    just_fix_windows_console()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def is_paper_window(moment: datetime) -> bool:
    """Indica si el momento local conserva el horizonte diario del modelo."""
    local = moment.astimezone(BOGOTA)
    return PAPER_WINDOW_START <= local.time().replace(tzinfo=None) <= PAPER_WINDOW_END


def _groq_configured() -> bool:
    if os.getenv("GROQ_API_KEY") and os.getenv("GROQ_MODEL"):
        return True
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return False
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    key = values.get("GROQ_API_KEY", "")
    model = values.get("GROQ_MODEL", "")
    return bool(key and model and "aqui_va" not in key)


def _header() -> None:
    now = datetime.now(BOGOTA)
    window = "ABIERTA" if is_paper_window(now) else "CERRADA"
    groq = "configurado" if _groq_configured() else "sin configurar"
    print(_paint("═" * WIDTH, Fore.CYAN, bright=True))
    print(_paint(PIXEL_LOGO, Fore.MAGENTA, bright=True))
    print(_paint(" " * 19 + "N O S T R A D A M U S   //   V 6", Fore.CYAN, bright=True))
    print(_paint(" " * 15 + "QUANT CORE · SENTIMENT NODE · PAPER MODE", Fore.WHITE))
    print(_paint("═" * WIDTH, Fore.CYAN, bright=True))
    window_text = _paint(
        f"● {window}", Fore.GREEN if window == "ABIERTA" else Fore.RED, bright=True
    )
    groq_text = _paint(
        f"● {groq}", Fore.GREEN if groq == "configurado" else Fore.YELLOW, bright=True
    )
    print(f" {_paint('◷ HORA CO'.ljust(18), Fore.CYAN, bright=True)} {now:%Y-%m-%d %H:%M:%S}")
    print(f" {_paint('◆ VENTANA V6'.ljust(18), Fore.CYAN, bright=True)} {window_text}  19:00–20:30")
    print(f" {_paint('◆ GROQ'.ljust(18), Fore.CYAN, bright=True)} {groq_text}")
    print(_paint("─" * WIDTH, Fore.BLUE))


def _confirm(prompt: str) -> bool:
    answer = input(
        f"{_paint('CONFIRMAR', Fore.YELLOW, bright=True)} · {prompt} "
        f"{_paint('[s/N]', Fore.YELLOW)}: "
    )
    return answer.strip().casefold() in {"s", "si", "sí", "y", "yes"}


def _pause() -> None:
    input(_paint("\n↵ Presiona Enter para volver al menú...", Fore.CYAN))


def _run_python(arguments: list[str], *, log_directory: Path) -> int:
    """Ejecuta un componente con el mismo Python y conserva salida en vivo."""
    log_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f")
    log_path = log_directory / f"menu_{stamp}.log"
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, *arguments]
    _section("EJECUCIÓN EN VIVO")
    print(f" {_paint('▶ PROCESO', Fore.GREEN, bright=True)}  {' '.join(arguments)}")
    print(f" {_paint('▣ LOG', Fore.CYAN, bright=True)}      {log_path.relative_to(PROJECT_ROOT)}\n")
    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8", newline="") as log:
            for line in process.stdout:
                if "error" in line.casefold() or "failed" in line.casefold():
                    rendered = _paint(line.rstrip("\n"), Fore.RED)
                elif line.startswith("[Fase") or line.startswith("Ingeniería"):
                    rendered = _paint(line.rstrip("\n"), Fore.CYAN)
                else:
                    rendered = line.rstrip("\n")
                print(rendered)
                log.write(line)
        return int(process.wait())
    except KeyboardInterrupt:
        if "process" in locals():
            process.terminate()
            process.wait(timeout=10)
        print(_paint("\n■ Ejecución interrumpida por el usuario.", Fore.YELLOW, bright=True))
        return 130


def _warn_timing() -> bool:
    now = datetime.now(BOGOTA)
    if is_paper_window(now):
        return True
    _section("ALERTA TEMPORAL")
    print(_paint(" ⚠ FUERA DE VENTANA 19:00–20:30 DE COLOMBIA", Fore.YELLOW, bright=True))
    print(" La Fase 6 se abstendrá para no reutilizar una predicción diaria tarde.")
    return _confirm("¿Deseas ejecutar de todas formas para registrar la abstención?")


def _run_sentiment(*, ask_confirmation: bool = True) -> int:
    if not _groq_configured():
        print(_paint("\n✖ Falta GROQ_API_KEY o GROQ_MODEL en el archivo .env.", Fore.RED, bright=True))
        return 2
    if ask_confirmation and not _confirm(
        "Esta acción puede realizar hasta 10 llamadas a Groq. ¿Continuar?"
    ):
        return 1
    return _run_python(
        [
            "phase4_sentiment.py",
            "--provider",
            "google_news",
            "--with-llm",
            "--archive-run",
            "--output-dir",
            "output/v4_history",
        ],
        log_directory=PROJECT_ROOT / "output/v4_history/logs",
    )


def run_daily_cycle() -> None:
    if not _warn_timing():
        return
    if not _confirm("El ciclo completo usará Groq y Yahoo Finance. ¿Continuar?"):
        return
    result = _run_sentiment(ask_confirmation=False)
    if result != 0:
        print(_paint("\n✖ V4 no terminó correctamente; V6 no se ejecutará.", Fore.RED, bright=True))
        return
    result = _run_python(
        ["phase6_paper_trade.py"],
        log_directory=PROJECT_ROOT / "output/v6/logs",
    )
    if result == 0:
        print(_paint("\n✔ Ciclo diario terminado correctamente.", Fore.GREEN, bright=True))
        show_status(wait=False)
    else:
        print(_paint("\n✖ V6 terminó con error. Revisa el log mostrado arriba.", Fore.RED, bright=True))


def run_sentiment_only() -> None:
    result = _run_sentiment()
    print(
        _paint("\n✔ V4 terminada.", Fore.GREEN, bright=True)
        if result == 0
        else _paint("\n✖ V4 no se completó.", Fore.RED, bright=True)
    )


def run_paper_only() -> None:
    if not _warn_timing():
        return
    result = _run_python(
        ["phase6_paper_trade.py"],
        log_directory=PROJECT_ROOT / "output/v6/logs",
    )
    print(
        _paint("\n✔ V6 terminada.", Fore.GREEN, bright=True)
        if result == 0
        else _paint("\n✖ V6 no se completó.", Fore.RED, bright=True)
    )


def show_status(*, wait: bool = True) -> None:
    path = PROJECT_ROOT / "output/v6/status.json"
    _section("ESTADO DEL PAPER TRADING")
    if not path.is_file():
        print(_paint("○ Todavía no existe ninguna ejecución de Fase 6.", Fore.YELLOW))
    else:
        status = json.loads(path.read_text(encoding="utf-8"))
        portfolio = status.get("portfolio", {})
        initial = float(portfolio.get("initial_capital", 0))
        current = float(portfolio.get("current_capital", 0))
        total_return = float(portfolio.get("total_return", 0))
        drawdown = float(portfolio.get("max_drawdown", 0))
        return_color = Fore.GREEN if total_return >= 0.0 else Fore.RED
        print(f" {_paint('CAPITAL INICIAL'.ljust(24), Fore.CYAN)} {_paint(f'{initial:,.2f}', Fore.WHITE, bright=True)}")
        print(f" {_paint('CAPITAL SIMULADO'.ljust(24), Fore.CYAN)} {_paint(f'{current:,.2f}', Fore.WHITE, bright=True)}")
        print(f" {_paint('RETORNO'.ljust(24), Fore.CYAN)} {_paint(f'{total_return:.4%}', return_color, bright=True)}")
        print(f" {_paint('DRAWDOWN MÁX.'.ljust(24), Fore.CYAN)} {_paint(f'{drawdown:.4%}', Fore.RED if drawdown < 0 else Fore.GREEN)}")
        print(f" {_paint('OPERACIONES CERRADAS'.ljust(24), Fore.CYAN)} {int(portfolio.get('settled_trades', 0))}")
        brier = portfolio.get("recent_brier")
        print(f" {_paint('BRIER RECIENTE'.ljust(24), Fore.CYAN)} {'N/D' if brier is None else f'{float(brier):.4f}'}")
        print(_paint("\n ÚLTIMAS DECISIONES", Fore.MAGENTA, bright=True))
        for ticker, decision in sorted(status.get("latest_decisions", {}).items()):
            probability = decision.get("probability_calibrated")
            probability_text = "N/D" if probability is None else f"{float(probability):.4f}"
            action = decision.get("action")
            probability_value = None if probability is None else float(probability)
            action_text = _paint(action, _action_color(action), bright=True)
            bar_color = Fore.GREEN if probability_value is not None and probability_value >= 0.5 else Fore.YELLOW
            print(f"\n {_paint(ticker, Fore.CYAN, bright=True)}  [{action_text}]")
            print(f"  P {_paint(_bar(probability_value), bar_color)} {probability_text}")
            print(
                f"  Sentimiento: {_paint(decision.get('sentiment'), Fore.MAGENTA)}  ·  "
                f"Exposición: {float(decision.get('exposure', 0.0)):.4f}"
            )
            _print_reason(decision.get("reason"))
    if wait:
        _pause()


def show_history() -> None:
    _section("RESUMEN DE HISTORIAL")
    index_path = PROJECT_ROOT / "output/v4_history/collection_index.jsonl"
    v4_records = []
    if index_path.is_file():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            try:
                v4_records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    print(f" {_paint('V4 ARCHIVADAS'.ljust(22), Fore.CYAN)} {len(v4_records)}")
    if v4_records:
        print(f" {_paint('ÚLTIMA V4'.ljust(22), Fore.CYAN)} {v4_records[-1].get('decision_at')}")
    try:
        decisions = read_hash_chain(PROJECT_ROOT / "output/v6/decisions.jsonl")
        settlements = read_hash_chain(PROJECT_ROOT / "output/v6/settlements.jsonl")
        print(f" {_paint('DECISIONES V6'.ljust(22), Fore.CYAN)} {len(decisions)}")
        print(f" {_paint('LIQUIDACIONES V6'.ljust(22), Fore.CYAN)} {len(settlements)}")
        if decisions:
            print(_paint("\n ÚLTIMOS REGISTROS V6", Fore.MAGENTA, bright=True))
            for record in decisions[-5:]:
                probability = record.get("probability_calibrated")
                probability_text = "N/D" if probability is None else f"{float(probability):.4f}"
                action = record.get("action")
                print(
                    f"  {record.get('decision_at')}  {_paint(record.get('asset'), Fore.CYAN)}  "
                    f"{_paint(action, _action_color(action), bright=True)}  p={probability_text}"
                )
    except ValueError as exc:
        print(_paint(f"✖ ALERTA DE INTEGRIDAD: {exc}", Fore.RED, bright=True))
    _pause()


def update_labels() -> None:
    result = _run_python(
        ["phase4_labels.py", "--sample-size", "100"],
        log_directory=PROJECT_ROOT / "output/v4_history/logs",
    )
    if result == 0:
        print(_paint("\n✔ Cola actualizada: data/labels/phase4_labeling_queue.csv", Fore.GREEN, bright=True))
        print("Edita únicamente manual_label y label_notes.")


def run_tests() -> None:
    result = _run_python(
        ["-m", "unittest", "discover", "-s", "tests", "-v"],
        log_directory=PROJECT_ROOT / "output/test_logs",
    )
    print(
        _paint("\n✔ Pruebas aprobadas.", Fore.GREEN, bright=True)
        if result == 0
        else _paint("\n✖ Hay pruebas fallidas.", Fore.RED, bright=True)
    )


def show_help() -> None:
    _section("AYUDA RÁPIDA")
    print(
        """
1. El ciclo diario completo es la opción habitual.
2. Ejecútalo una vez al día entre 19:05 y 20:15, hora de Colombia.
3. 'no_trade' significa que las reglas rechazaron la operación.
4. 'abstain' significa que faltó una condición de seguridad o temporal.
5. 'operate' solo crea una operación simulada; nunca envía una orden real.
6. No cierres la ventana mientras V4 está consultando Groq.

Documentación: docs/PROTOCOLO_FASE_6.md
""".strip()
    )
    _pause()


def main() -> int:
    _configure_console()
    actions: dict[str, tuple[str, Callable[[], None]]] = {
        "1": ("Ejecutar ciclo diario completo (V4 + V6)", run_daily_cycle),
        "2": ("Recolectar únicamente sentimiento V4", run_sentiment_only),
        "3": ("Ejecutar únicamente paper trading V6", run_paper_only),
        "4": ("Ver estado actual del paper trading", show_status),
        "5": ("Ver resumen del historial", show_history),
        "6": ("Actualizar cola de etiquetado humano", update_labels),
        "7": ("Ejecutar todas las pruebas", run_tests),
        "8": ("Ayuda", show_help),
    }
    while True:
        _clear_screen()
        _header()
        print(_paint("  CONTROL DE MISIONES", Fore.MAGENTA, bright=True))
        print()
        icons = {
            "1": "▶",
            "2": "◈",
            "3": "◆",
            "4": "▣",
            "5": "▤",
            "6": "✎",
            "7": "✓",
            "8": "?",
        }
        for key, (label, _) in actions.items():
            key_box = _paint(f"[{key}]", Fore.CYAN, bright=True)
            label_color = Fore.GREEN if key == "1" else Fore.WHITE
            print(f"  {key_box} {_paint(icons[key], Fore.MAGENTA)}  {_paint(label, label_color, bright=key == '1')}")
        print(f"  {_paint('[0]', Fore.RED, bright=True)} ■  Salir")
        print(_paint("\n" + "─" * WIDTH, Fore.BLUE))
        try:
            selection = input(
                f" {_paint('nostradamus@v6', Fore.GREEN, bright=True)}"
                f"{_paint(':~$', Fore.CYAN, bright=True)} "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print(_paint("\n■ Saliendo.", Fore.YELLOW))
            return 0
        if selection == "0":
            print(_paint("Hasta luego, operador.", Fore.CYAN, bright=True))
            return 0
        action = actions.get(selection)
        if action is None:
            print(_paint("✖ Opción inválida.", Fore.RED, bright=True))
            _pause()
            continue
        try:
            action[1]()
        except KeyboardInterrupt:
            print(_paint("\n■ Operación cancelada.", Fore.YELLOW, bright=True))
        except Exception as exc:
            print(_paint(f"\n✖ ERROR: {type(exc).__name__}: {exc}", Fore.RED, bright=True))
        if selection not in {"4", "5", "8"}:
            _pause()


if __name__ == "__main__":
    raise SystemExit(main())
