import sys
import os
import subprocess
import shlex
import readline

def main():

    # Autocomplete setup
    setup_autocomplete()

    while True:
        
        try:
            command_line = input("$ ")
        except EOFError:
            break

        # Handle empty input
        if not command_line:
            continue

        if '|' in command_line:
            execute_pipeline(command_line)
            continue

        # Parsing the string input into command and arguments
        # shlex.split correctly handles quoted strings and escape characters
        parts = shlex.split(command_line)

        # Handle output redirection
        redirect_operators = ['>', '1>', '2>', '>>', '1>>', '2>>']
        redirect_index = -1
        redirect_op = None

        for op in redirect_operators:
            if op in parts:
                redirect_index = parts.index(op)
                redirect_op = op
                break

        # make sure that the operator exists and the is a output file specified
        if redirect_index != -1 and redirect_index < len(parts) - 1:
            output_file = parts[redirect_index + 1]
            command_parts = parts[:redirect_index]
            
            # Determine mode and feature
            mode = 'a' if redirect_op in ('>>', '1>>', '2>>') else 'w'
            feature = 'stderr' if redirect_op in ('2>', '2>>') else 'stdout'
            
            file_redirection(output_file, mode, " ".join(command_parts), feature)
            continue

        # this is the shell command itself
        command = parts[0]

        # this is the arguments of that command
        args = parts[1:]

        
        """
        Built-in commands:
        - exit: Exit the shell
        - pwd: Print the current working directory
        - echo: Print arguments (string) to the console
        - cat: Concatenate and display file contents
        - type: Identify if a command is built-in or external
        - cd: Change the current working directory
        - history: Show command history
        """
        
        # Exit command
        if command == "exit":
            break
        elif command == "pwd":
            # This asks the OS kernel for the current working directory
            print(os.getcwd())
            continue
        # Echo command
        elif command == "echo":
            # Use " ".join to handle multiple arguments (ex. echo arg1 arg2)
                print(" ".join(args))
        # Cat command
        elif command == "cat":
            if args:
                for filename in args:
                    try:
                        with open(filename, 'r') as file:
                            print(file.read(), end='')
                    except FileNotFoundError:
                        print(f"cat: {filename}: No such file or directory")
            else:
                # If no arguments, read from standard input
                print(sys.stdin.read(), end='')
                        
        # Type command
        elif command == "type":
            if args:
                print(type_of_command(args[0]).format(command=args[0]))
            continue
        # cd command
        elif command == "cd":
            if args:
                path = os.path.expanduser(args[0])
                try:
                    os.chdir(path)
                except FileNotFoundError:
                    print(f"cd: {args[0]}: No such file or directory")

            # cd with no arguments goes to the home directory
            else:
                os.chdir(os.path.expanduser("~"))

        elif command == "history":

            # if an argument is provided and it's a digit, show last n commands
            if args and args[0].isdigit():
                n = int(args[0])
                total = readline.get_current_history_length()
                start = max(1, total - n + 1)  # Start from (total - n + 1), but at least 1
                for i in range(start, total + 1):
                    print(f"{i}  {readline.get_history_item(i)}")

            # else print all history comands
            else:
                for i in range(1, readline.get_current_history_length() + 1):
                    print(f"{i}  {readline.get_history_item(i)}")

        # External programs
        else:
            full_path = find_in_path(command)
            if full_path:
                # Run the external program with arguments
                # We pass the full parts list to ensure command and args stay synced
                subprocess.run(parts)
            else:
                print(f"{command}: command not found")
'''
FUNCTIONS
'''

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
    
    options = [cmd for cmd in commands if cmd.startswith(text)]
    options = list(set(options))  # Remove duplicates
    
    if state < len(options):
        # Only add space for single match
        if len(options) == 1:
            return options[state] + ' '
        else:
            return options[state]
    return None
    
def setup_autocomplete():
    if 'libedit' in readline.__doc__:
        # macOS uses libedit, not GNU readline
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        # Linux uses GNU readline
        readline.parse_and_bind("tab: complete")
    
    readline.set_completer(completer)

def execute_pipeline(command_line):
    """Execute a pipeline of commands connected by |"""
    commands = command_line.split('|')
    
    if len(commands) < 2:
        print("Pipeline requires at least 2 commands")
        return
    
    processes = []
    builtins = ["echo", "exit", "type", "pwd", "cd"]
    
    for i, cmd in enumerate(commands):
        cmd = cmd.strip()
        if not cmd:
            continue
            
        parts = shlex.split(cmd)
        command = parts[0]
        args = parts[1:]
        
        # Determine stdin and stdout
        stdin = processes[-1].stdout if i > 0 else None
        stdout = subprocess.PIPE if i < len(commands) - 1 else None
        
        if command in builtins:
            # Execute builtin and capture output
            output = execute_builtin_capture(command, args, stdin)
            
            # Create a process that outputs the builtin result
            if output is not None:
                process = subprocess.Popen(
                    ['echo', output],
                    stdin=None,
                    stdout=stdout,
                    stderr=None
                )
            else:
                # For builtins that don't output (like cd)
                continue
        else:
            # External command
            process = subprocess.Popen(
                parts,
                stdin=stdin,
                stdout=stdout,
                stderr=None
            )
        
        processes.append(process)
        
        # Close previous stdout
        if i > 0 and processes[-2].stdout:
            processes[-2].stdout.close()
    
    # Wait for all
    for process in processes:
        process.wait()

def execute_builtin_capture(command, args, stdin_pipe):
    
    # Execute built-in commands and ouput string

    if command == "echo":
        return " ".join(args)
    elif command == "pwd":
        return os.getcwd()
    elif command == "type":
        if args:
            return type_of_command(args[0]).format(command=args[0])
    elif command == "cd":
        # cd doesn't output anything
        return None
    return None
    
def find_in_path(command):
    path_env = os.getenv("PATH")
    if path_env:
        for directory in path_env.split(os.pathsep):
            full_path = os.path.join(directory, command)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                return full_path
    return None

def type_of_command(command):
    builtins = ["echo", "exit", "type", "pwd", "cd", "history"]
    if command in builtins:
        return "{command} is a shell builtin"
    
    path = find_in_path(command)
    if path:
        return f"{{command}} is {path}"
        
    return "{command}: not found"

def file_redirection(file_path, mode, command_line, feature):
    # Create directory only if there's a directory path
    dir_path = os.path.dirname(file_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    with open(file_path, mode) as file:
        parts = shlex.split(command_line)
        if feature == 'stdout':
            subprocess.run(parts, stdout=file)
        elif feature == 'stderr':
            subprocess.run(parts, stderr=file)

if __name__ == "__main__":
    main()