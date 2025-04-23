#!/usr/bin/env python3
# aibuddy.py - CLI Assistant using local GGUF model
# Adapted from DeepSeek CLI Assistant example

import click
import json
import os
import sys
import subprocess
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
import shlex

# Configuration
CONFIG_DIR = Path.home() / ".config" / "aibuddy"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
MODEL_PATH = "/home/katana/projects/linux/aibuddy/agentica-org_DeepScaleR-1.5B-Preview-Q8_0.gguf"

# Default server settings
DEFAULT_CONFIG = {
    "model_path": MODEL_PATH,
    "server_host": "localhost",
    "server_port": 8080,
    "context_length": 4096,
    "thread_count": 4
}

def ensure_config_exists():
    """Create config directory and files if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    
    if not HISTORY_FILE.exists():
        with open(HISTORY_FILE, "w") as f:
            json.dump([], f)

def load_config():
    """Load the configuration."""
    ensure_config_exists()
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_history(description, command):
    """Save a command to history."""
    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)
    
    history.append({
        "description": description, 
        "command": command,
        "timestamp": import_time.time()
    })
    
    # Keep only the last 100 entries
    if len(history) > 100:
        history = history[-100:]
    
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def is_server_running(host, port):
    """Check if the server is running."""
    try:
        response = requests.get(f"http://{host}:{port}/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def call_llm_api(prompt, config):
    """Call the local LLM API with the given prompt."""
    host = config.get("server_host", "localhost")
    port = config.get("server_port", 8080)
    
    # Check if server is running
    if not is_server_running(host, port):
        click.echo("Server is not running. Starting server...")
        # Start the server in the background
        start_server(config)
        # Wait for server to start
        import time
        for _ in range(10):
            if is_server_running(host, port):
                break
            click.echo("Waiting for server to start...")
            time.sleep(1)
        else:
            click.echo("Failed to start server.")
            return None

    # Format messages for API
    messages = [
        {"role": "system", "content": "You are an expert Linux command line assistant. Generate accurate, secure commands for user requests."},
        {"role": "user", "content": prompt}
    ]
    
    # Make API request
    try:
        response = requests.post(
            f"http://{host}:{port}/v1/chat/completions",
            json={
                "model": "local-model",
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1024
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            click.echo(f"Error: API returned status code {response.status_code}")
            return None
    except Exception as e:
        click.echo(f"Error calling API: {str(e)}")
        return None

def start_server(config):
    """Start the LLM server in the background."""
    model_path = config.get("model_path", MODEL_PATH)
    port = config.get("server_port", 8080)
    
    if not os.path.exists(model_path):
        click.echo(f"Error: Model not found at {model_path}")
        sys.exit(1)
    
    # Create a script to start the server with llama.cpp
    server_script = CONFIG_DIR / "start_server.sh"
    with open(server_script, "w") as f:
        f.write(f"""#!/bin/bash
SERVER_LOG="{CONFIG_DIR}/server.log"
echo "Starting server at $(date)" > "$SERVER_LOG"

# Check if llama-server exists and is in PATH
if ! command -v llama-server &> /dev/null; then
    # Try to find it in common locations
    if [ -f "$HOME/llama.cpp/llama-server" ]; then
        LLAMA_SERVER="$HOME/llama.cpp/llama-server"
    elif [ -f "/usr/local/bin/llama-server" ]; then
        LLAMA_SERVER="/usr/local/bin/llama-server"
    else
        echo "llama-server not found. Please install llama.cpp and make sure llama-server is in your PATH." >> "$SERVER_LOG"
        exit 1
    fi
else
    LLAMA_SERVER="llama-server"
fi

# Start the server
"$LLAMA_SERVER" \\
    --model "{model_path}" \\
    --port {port} \\
    --threads {config.get("thread_count", 4)} \\
    --ctx-size {config.get("context_length", 4096)} \\
    --host {config.get("server_host", "127.0.0.1")} \\
    >> "$SERVER_LOG" 2>&1 &

echo "Server started with PID $!" >> "$SERVER_LOG"
""")
    
    os.chmod(server_script, 0o755)
    subprocess.Popen([str(server_script)], shell=True, start_new_session=True)
    click.echo(f"Server starting in background. Log: {CONFIG_DIR}/server.log")

def execute_command(command):
    """Execute a command and return its output."""
    try:
        # Display the command for transparency
        click.echo(f"\nExecuting: {command}\n")
        
        # Get confirmation if command is potentially dangerous
        if any(danger_word in command for danger_word in ["rm", "sudo", "dd", "mkfs", "> /dev", "chmod", "reboot", "shutdown"]):
            if not click.confirm("This command may modify your system. Proceed?"):
                return "Command execution cancelled."
        
        # Execute command
        result = subprocess.run(
            command, 
            shell=True, 
            text=True, 
            capture_output=True
        )
        
        output = result.stdout
        if result.stderr:
            output += "\nErrors:\n" + result.stderr
        
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"

def fix_command_errors(error_text, original_command):
    """Use the LLM to fix errors in a command."""
    config = load_config()
    prompt = f"""
The following Linux command failed:

```
{original_command}
```

With this error:
```
{error_text}
```

Please provide a corrected version of the command that will work, and briefly explain what was wrong.
"""
    
    response = call_llm_api(prompt, config)
    if response:
        click.echo("\n" + response + "\n")
        
        # Try to extract just the command from the response
        command_lines = []
        in_code_block = False
        for line in response.split('\n'):
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            if in_code_block and line.strip() and not line.startswith('#'):
                command_lines.append(line)
        
        if command_lines:
            fixed_command = command_lines[0]
            if click.confirm(f"Would you like to execute the fixed command? [{fixed_command}]"):
                return execute_command(fixed_command)
    
    return None

@click.group()
def cli():
    """AIBuddy CLI Assistant - Help with Linux commands."""
    ensure_config_exists()

@cli.command()
@click.argument("description")
@click.option("--execute", "-e", is_flag=True, help="Execute the generated command")
def generate(description, execute):
    """Generate a command from a natural language description."""
    config = load_config()
    
    click.echo("Generating command...")
    prompt = f"Generate a Linux bash command that will: {description}\nProvide ONLY the command with NO explanations."
    
    response = call_llm_api(prompt, config)
    
    if response:
        # Try to extract just the command
        command = response.strip()
        
        # Remove code block formatting if present
        if command.startswith("```") and command.endswith("```"):
            command = "\n".join(command.split("\n")[1:-1])
        
        # Remove bash/shell prefix if present
        command = command.replace("```bash", "").replace("```shell", "").replace("```", "").strip()
        
        click.echo(click.style("\nGenerated Command:", fg="green"))
        click.echo(click.style(f"{command}\n", fg="bright_white"))
        
        # Save to history
        save_history(description, command)
        
        # Execute if requested
        if execute:
            output = execute_command(command)
            click.echo(click.style("\nOutput:", fg="green"))
            click.echo(output)
            
            # If there's an error, offer to fix it
            if "error" in output.lower() or "not found" in output.lower():
                if click.confirm("Would you like me to try to fix any errors in this command?"):
                    fix_command_errors(output, command)
    else:
        click.echo("Failed to generate command.")

@cli.command()
@click.argument("command", nargs=-1)
def explain(command):
    """Explain what a command does."""
    config = load_config()
    
    # Join arguments into a single command string
    cmd_str = " ".join(command)
    
    click.echo("Analyzing command...")
    prompt = f"""Explain what this Linux command does in detail:
    
{cmd_str}

Break down each part of the command, any options/flags used, and potential side effects or security considerations."""
    
    response = call_llm_api(prompt, config)
    
    if response:
        click.echo("\n" + response)
    else:
        click.echo("Failed to analyze command.")

@cli.command()
@click.argument("command", nargs=-1)
def fix(command):
    """Try to fix errors in a command."""
    config = load_config()
    
    # Join arguments into a single command string
    cmd_str = " ".join(command)
    
    click.echo("Attempting to execute command first to see if it has errors...")
    output = execute_command(cmd_str)
    
    if "error" in output.lower() or "not found" in output.lower() or "command not found" in output.lower():
        click.echo(click.style("Command had errors:", fg="red"))
        click.echo(output)
        click.echo("\nAttempting to fix the command...")
        
        fixed_output = fix_command_errors(output, cmd_str)
        if fixed_output:
            click.echo(click.style("\nOutput from fixed command:", fg="green"))
            click.echo(fixed_output)
    else:
        click.echo(click.style("Command executed successfully:", fg="green"))
        click.echo(output)

@cli.command()
def history():
    """Show command history."""
    with open(HISTORY_FILE, "r") as f:
        history = json.load(f)
    
    if not history:
        click.echo("No command history found.")
        return
    
    click.echo(click.style("Command History:", fg="green"))
    
    for i, entry in enumerate(history[-10:], 1):
        click.echo(f"{i}. \"{entry['description']}\"")
        click.echo(f"   {entry['command']}")
        click.echo()

@cli.command()
def config():
    """Configure the AIBuddy CLI Assistant."""
    current_config = load_config()
    
    click.echo("Current configuration:")
    for key, value in current_config.items():
        click.echo(f"{key}: {value}")
    
    if click.confirm("Would you like to update the configuration?"):
        # Model path
        model_path = click.prompt("Model path", default=current_config.get("model_path", MODEL_PATH))
        
        # Server settings
        server_host = click.prompt("Server host", default=current_config.get("server_host", "localhost"))
        server_port = click.prompt("Server port", default=current_config.get("server_port", 8080), type=int)
        
        # Performance settings
        thread_count = click.prompt("Thread count", default=current_config.get("thread_count", 4), type=int)
        context_length = click.prompt("Context length", default=current_config.get("context_length", 4096), type=int)
        
        # Update config
        new_config = {
            "model_path": model_path,
            "server_host": server_host,
            "server_port": server_port,
            "thread_count": thread_count,
            "context_length": context_length
        }
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(new_config, f, indent=2)
        
        click.echo("Configuration updated!")

@cli.command()
def server():
    """Manage the LLM server."""
    config = load_config()
    host = config.get("server_host", "localhost")
    port = config.get("server_port", 8080)
    
    if is_server_running(host, port):
        click.echo(f"Server is running at http://{host}:{port}")
        if click.confirm("Would you like to restart the server?"):
            # TODO: Implement proper server stopping
            click.echo("Restarting server...")
            start_server(config)
    else:
        click.echo("Server is not running.")
        if click.confirm("Would you like to start the server?"):
            start_server(config)

if __name__ == "__main__":
    import time as import_time
    cli()
