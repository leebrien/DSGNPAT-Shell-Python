import sys
import os
import subprocess
import shlex
import readline
from abc import ABC, abstractmethod

# SINGLE SOURCE OF TRUTH: all builtin names
# (fixes Code Smell #2 – duplicated builtin lists)
BUILTINS = {"exit", "pwd", "echo", "cat", "type", "cd", "history"}


# TEMPLATE PATTERN
# Abstract base class that defines the skeleton
# of execute() while leaving the step-by-step
# behaviour to each concrete command subclass.
# (fixes Code Smell #4 & #6 – long if-elif chain
#  and primitive-string command representation)

class Command(ABC):
    """Abstract base for every shell command."""

    # Template method – defines the algorithm skeleton
    def execute(self, args: list[str]) -> None:
        self.validate(args)          # optional hook
        self.run(args)               # mandatory step – implemented by subclass

    def validate(self, args: list[str]) -> None:
        """Optional pre-execution hook; subclasses may override."""
        pass

    @abstractmethod
    def run(self, args: list[str]) -> None:
        """Concrete behaviour goes here."""

    def capture(self, args: list[str]) -> str:
        """Return output as a string (used by pipelines). Override as needed."""
        return ""


# ── Concrete commands ─────────────────────────

class ExitCommand(Command):
    def run(self, args):
        raise SystemExit(0)

    def capture(self, args):
        return ""


class PwdCommand(Command):
    def run(self, args):
        print(os.getcwd())

    def capture(self, args):
        return os.getcwd()


class EchoCommand(Command):
    def run(self, args):
        print(" ".join(args))

    def capture(self, args):
        return " ".join(args)


class CatCommand(Command):
    def run(self, args):
        if args:
            for filename in args:
                try:
                    with open(filename, 'r') as f:
                        print(f.read(), end='')
                except FileNotFoundError:
                    print(f"cat: {filename}: No such file or directory")
        else:
            print(sys.stdin.read(), end='')


class TypeCommand(Command):
    def run(self, args):
        if args:
            print(ShellFacade.type_of_command(args[0]))

    def capture(self, args):
        return ShellFacade.type_of_command(args[0]) if args else ""


class CdCommand(Command):
    def run(self, args):
        path = os.path.expanduser(args[0]) if args else os.path.expanduser("~")
        try:
            os.chdir(path)
        except FileNotFoundError:
            target = args[0] if args else "~"
            print(f"cd: {target}: No such file or directory")


class HistoryCommand(Command):
    def __init__(self):
        self._last_length = 0

    def run(self, args):
        total = readline.get_current_history_length()

        if args and args[0].isdigit():
            n = int(args[0])
            start = max(1, total - n + 1)
            for i in range(start, total + 1):
                print(f"{i}  {readline.get_history_item(i)}")

        elif args and args[0] == '-r' and len(args) > 1:
            try:
                readline.read_history_file(args[1])
                self._last_length = readline.get_current_history_length()
            except (FileNotFoundError, OSError):
                print(f"history: {args[1]}: No such file or directory")

        elif args and args[0] == '-w' and len(args) > 1:
            try:
                readline.write_history_file(args[1])
                self._last_length = readline.get_current_history_length()
            except Exception as e:
                print(f"history: could not write to {args[1]}: {e}")

        elif args and args[0] == '-a' and len(args) > 1:
            current = readline.get_current_history_length()
            to_append = current - self._last_length
            if to_append > 0:
                try:
                    readline.append_history_file(to_append, args[1])
                    self._last_length = current
                except Exception as e:
                    print(f"history: could not append to {args[1]}: {e}")

        else:
            for i in range(1, total + 1):
                item = readline.get_history_item(i)
                if item:
                    print(f"{i:d}  {item}")


# ═════════════════════════════════════════════
# FACADE PATTERN
# ShellFacade exposes a single, simplified
# interface over the complex subsystems:
#   • PATH resolution
#   • command-type detection
#   • I/O redirection
#   • pipeline execution
#   • tab-completion setup
# (fixes Code Smell #1 & #3 & #5 – oversized
#  main(), scattered logic, multiple change
#  reasons for a single function)
# ═════════════════════════════════════════════
class ShellFacade:
    """Simplified interface over all shell subsystems."""

    # Registry: maps command name → Command instance
    # Adding a new command = one line here.
    # (fixes Code Smell #3 – scattered modifications)
    _history_cmd = HistoryCommand()
    _registry: dict[str, Command] = {
        "exit":    ExitCommand(),
        "pwd":     PwdCommand(),
        "echo":    EchoCommand(),
        "cat":     CatCommand(),
        "type":    TypeCommand(),
        "cd":      CdCommand(),
        "history": _history_cmd,
    }

    # ── Path helpers ──────────────────────────

    @staticmethod
    def find_in_path(command: str) -> str | None:
        for directory in os.getenv("PATH", "").split(os.pathsep):
            full = os.path.join(directory, command)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
        return None

    @staticmethod
    def type_of_command(command: str) -> str:
        if command in BUILTINS:
            return f"{command} is a shell builtin"
        path = ShellFacade.find_in_path(command)
        if path:
            return f"{command} is {path}"
        return f"{command}: not found"

    # ── Dispatch ──────────────────────────────

    @classmethod
    def dispatch(cls, parts: list[str]) -> None:
        """Route a parsed command to the right Command object or subprocess."""
        command, args = parts[0], parts[1:]
        if command in cls._registry:
            cls._registry[command].execute(args)
        else:
            full_path = cls.find_in_path(command)
            if full_path:
                subprocess.run(parts)
            else:
                print(f"{command}: command not found")

    # ── I/O Redirection ───────────────────────

    @classmethod
    def handle_redirection(cls, parts: list[str]) -> bool:
        """
        Detect and handle output/error redirection.
        Returns True if redirection was processed, False otherwise.
        """
        redirect_ops = ['>', '1>', '2>', '>>', '1>>', '2>>']
        for op in redirect_ops:
            if op in parts:
                idx = parts.index(op)
                if idx < len(parts) - 1:
                    output_file = parts[idx + 1]
                    command_parts = parts[:idx]
                    mode = 'a' if op in ('>>', '1>>', '2>>') else 'w'
                    feature = 'stderr' if op in ('2>', '2>>') else 'stdout'
                    cls._redirect_output(output_file, mode, command_parts, feature)
                    return True
        return False

    @staticmethod
    def _redirect_output(file_path: str, mode: str, parts: list[str], feature: str) -> None:
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(file_path, mode) as f:
            if feature == 'stdout':
                subprocess.run(parts, stdout=f)
            else:
                subprocess.run(parts, stderr=f)

    # ── Pipeline ─────────────────────────────

    @classmethod
    def execute_pipeline(cls, command_line: str) -> None:
        commands = command_line.split('|')
        processes = []

        for i, cmd in enumerate(commands):
            parts = shlex.split(cmd.strip())
            stdin = processes[-1].stdout if i > 0 else None
            stdout = subprocess.PIPE if i < len(commands) - 1 else None

            if parts[0] in BUILTINS:
                output = cls._capture_builtin(parts[0], parts[1:])
                process = subprocess.Popen(['echo', output], stdout=stdout)
            else:
                process = subprocess.Popen(parts, stdin=stdin, stdout=stdout)

            processes.append(process)
            if i > 0 and processes[-2].stdout:
                processes[-2].stdout.close()

        for p in processes:
            p.wait()

    @classmethod
    def _capture_builtin(cls, command: str, args: list[str]) -> str:
        cmd_obj = cls._registry.get(command)
        if cmd_obj:
            return cmd_obj.capture(args)
        return ""

    # ── Tab completion ────────────────────────

    @classmethod
    def setup_autocomplete(cls) -> None:
        def completer(text, state):
            commands = list(BUILTINS)
            path_env = os.getenv("PATH")
            if path_env:
                for directory in path_env.split(os.pathsep):
                    try:
                        for item in os.listdir(directory):
                            if os.access(os.path.join(directory, item), os.X_OK):
                                commands.append(item)
                    except FileNotFoundError:
                        continue
            options = sorted(set(c for c in commands if c.startswith(text)))
            if state < len(options):
                return options[state] + (' ' if len(options) == 1 else '')
            return None

        if 'libedit' in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        readline.set_completer(completer)


# ═════════════════════════════════════════════
# MAIN – now thin: only REPL loop + history I/O
# (fixes Code Smell #1 & #5 – oversized main
#  with too many responsibilities)
# ═════════════════════════════════════════════
def main():
    ShellFacade.setup_autocomplete()

    histfile = os.environ.get("HISTFILE")
    if histfile and os.path.exists(histfile):
        try:
            readline.read_history_file(histfile)
        except (FileNotFoundError, OSError):
            pass

    while True:
        try:
            command_line = input("$ ")
        except EOFError:
            break

        if not command_line:
            continue

        if '|' in command_line:
            ShellFacade.execute_pipeline(command_line)
            continue

        parts = shlex.split(command_line)

        if ShellFacade.handle_redirection(parts):
            continue

        try:
            ShellFacade.dispatch(parts)
        except SystemExit:
            break

    if histfile:
        try:
            readline.write_history_file(histfile)
        except Exception:
            pass


if __name__ == "__main__":
    main()