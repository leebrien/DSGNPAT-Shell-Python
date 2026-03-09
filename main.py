import sys
import os
import subprocess
import shlex
import readline

last_history_length = 0

def main():
    global last_history_length

    setup_autocomplete()

    # Use HISTFILE only if provided
    histfile = os.environ.get("HISTFILE")

    if histfile and os.path.exists(histfile):
        try:
            readline.read_history_file(histfile)
        except (FileNotFoundError, OSError):
            pass

    # Everything read so far is already persisted
    last_history_length = readline.get_current_history_length()

    while True:
        try:
            command_line = input("$ ")
        except EOFError:
            break

        if not command_line:
            continue

        if '|' in command_line:
            execute_pipeline(command_line)
            continue

        parts = shlex.split(command_line)

        redirect_operators = ['>', '1>', '2>', '>>', '1>>', '2>>']
        redirect_index = -1
        redirect_op = None

        for op in redirect_operators:
            if op in parts:
                redirect_index = parts.index(op)
                redirect_op = op
                break

        if redirect_index != -1 and redirect_index < len(parts) - 1:
            output_file = parts[redirect_index + 1]
            command_parts = parts[:redirect_index]

            mode = 'a' if redirect_op in ('>>', '1>>', '2>>') else 'w'
            feature = 'stderr' if redirect_op in ('2>', '2>>') else 'stdout'

            file_redirection(output_file, mode, " ".join(command_parts), feature)
            continue

        command = parts[0]
        args = parts[1:]

        if command == "exit":
            break

        elif command == "pwd":
            print(os.getcwd())

        elif command == "echo":
            print(" ".join(args))

        elif command == "cat":
            if args:
                for filename in args:
                    try:
                        with open(filename, 'r') as file:
                            print(file.read(), end='')
                    except FileNotFoundError:
                        print(f"cat: {filename}: No such file or directory")
            else:
                print(sys.stdin.read(), end='')

        elif command == "type":
            if args:
                print(type_of_command(args[0]).format(command=args[0]))

        elif command == "cd":
            if args:
                path = os.path.expanduser(args[0])
                try:
                    os.chdir(path)
                except FileNotFoundError:
                    print(f"cd: {args[0]}: No such file or directory")
            else:
                os.chdir(os.path.expanduser("~"))

        elif command == "history":
            
            total_history = readline.get_current_history_length()
            
            if args and args[0].isdigit():
                n = int(args[0])
                start = max(1, total_history - n + 1)
                for i in range(start, total_history + 1):
                    print(f"{i}  {readline.get_history_item(i)}")

            elif args and args[0] == '-r' and len(args) > 1:
                try:
                    readline.read_history_file(args[1])
                    last_history_length = readline.get_current_history_length()
                except (FileNotFoundError, OSError):
                    print(f"history: {args[1]}: No such file or directory")

            elif args and args[0] == '-w' and len(args) > 1:
                try:
                    readline.write_history_file(args[1])
                    last_history_length = readline.get_current_history_length()
                except Exception as e:
                    print(f"history: could not write to {args[1]}: {e}")

            elif args and args[0] == '-a' and len(args) > 1:
                hist_path = args[1]
                current_length = readline.get_current_history_length()
                to_append = current_length - last_history_length

                if to_append > 0:
                    try:
                        readline.append_history_file(to_append, hist_path)
                        last_history_length = current_length
                    except Exception as e:
                        print(f"history: could not append to {hist_path}: {e}")

            else:
                for i in range(1, total_history + 1):
                    item = readline.get_history_item(i)
                    if item:
                        print(f"{i:d}  {item}")

        else:
            full_path = find_in_path(command)
            if full_path:
                subprocess.run(parts)
            else:
                print(f"{command}: command not found")

    # write history on exit
    if histfile:
        try:
            readline.write_history_file(histfile)
        except Exception:
            pass
        

def completer(text, state):
    commands = ["exit", "pwd", "echo", "cat", "type", "cd", "history"]

    path_env = os.getenv("PATH")
    if path_env:
        for directory in path_env.split(os.pathsep):
            try:
                for item in os.listdir(directory):
                    if os.access(os.path.join(directory, item), os.X_OK):
                        commands.append(item)
            except FileNotFoundError:
                continue

    options = sorted(set(cmd for cmd in commands if cmd.startswith(text)))

    if state < len(options):
        return options[state] + (' ' if len(options) == 1 else '')
    return None

def setup_autocomplete():
    if 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
    readline.set_completer(completer)

def execute_pipeline(command_line):
    commands = command_line.split('|')
    processes = []
    builtins = ["echo", "exit", "type", "pwd", "cd"]

    for i, cmd in enumerate(commands):
        parts = shlex.split(cmd.strip())
        stdin = processes[-1].stdout if i > 0 else None
        stdout = subprocess.PIPE if i < len(commands) - 1 else None

        if parts[0] in builtins:
            output = execute_builtin_capture(parts[0], parts[1:], stdin)
            process = subprocess.Popen(['echo', output], stdout=stdout)
        else:
            process = subprocess.Popen(parts, stdin=stdin, stdout=stdout)

        processes.append(process)

        if i > 0 and processes[-2].stdout:
            processes[-2].stdout.close()

    for p in processes:
        p.wait()

def execute_builtin_capture(command, args, stdin):
    if command == "echo":
        return " ".join(args)
    if command == "pwd":
        return os.getcwd()
    if command == "type" and args:
        return type_of_command(args[0]).format(command=args[0])
    return ""

def find_in_path(command):
    for directory in os.getenv("PATH", "").split(os.pathsep):
        full = os.path.join(directory, command)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None

def type_of_command(command):
    if command in ["echo", "exit", "type", "pwd", "cd", "history"]:
        return "{command} is a shell builtin"
    path = find_in_path(command)
    if path:
        return f"{{command}} is {path}"
    return "{command}: not found"

def file_redirection(file_path, mode, command_line, feature):
    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(file_path, mode) as file:
        parts = shlex.split(command_line)
        if feature == 'stdout':
            subprocess.run(parts, stdout=file)
        else:
            subprocess.run(parts, stderr=file)

if __name__ == "__main__":
    main()
