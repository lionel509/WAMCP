
import argparse
import subprocess
import sys

def run_command(command):
    """Runs a command and prints its output."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True)
        if process.stdout is None:
            raise RuntimeError("Failed to capture process stdout")
        for line in iter(process.stdout.readline, ''):
            sys.stdout.write(line)
        process.stdout.close()
        return_code = process.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, command)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)

def main():
    """Main function to parse arguments and run docker-compose."""
    parser = argparse.ArgumentParser(description="Start services with docker-compose.")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["up", "down"],
        default="up",
        help="Command to run: 'up' to start services, 'down' to stop them. Defaults to 'up'.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild images before starting services (docker-compose up --build).",
    )
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="Force recreate containers (docker-compose up --force-recreate).",
    )
    parser.add_argument(
        "--detached",
        "-d",
        action="store_true",
        help="Run containers in detached mode (docker-compose up -d).",
    )

    args = parser.parse_args()

    if args.command == "down":
        cmd = "docker-compose down"
        print(f"Running: {cmd}")
        run_command(cmd)
        return

    if args.command == "up":
        cmd = ["docker-compose up"]
        if args.rebuild:
            cmd.append("--build")
        if args.force_recreate:
            cmd.append("--force-recreate")
        if args.detached:
            cmd.append("-d")
        
        full_command = " ".join(cmd)
        print(f"Running: {full_command}")
        run_command(full_command)

if __name__ == "__main__":
    main()
