import os
import subprocess
import sys

# --- Konfiguracja ---
DOCKER_DIR = "dockerubuntu"
DOCKER_COMPOSE_FILE = "ubuntu.yml"
DOCKERFILE_NAME = "Dockerfile"

# --- Treść Dockerfile (Instaluje Chrome i Edge) ---
DOCKERFILE_CONTENT = """
FROM lscr.io/linuxserver/webtop:ubuntu-xfce

RUN apt-get update && apt-get install -y \\
    gnupg \\
    wget \\
    curl \\
    ca-certificates \\
    software-properties-common

# Instalacja Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \\
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \\
    && apt-get update && apt-get install -y google-chrome-stable

# Instalacja Microsoft Edge
RUN curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg \\
    && install -o root -g root -m 644 microsoft.gpg /etc/apt/trusted.gpg.d/ \\
    && echo "deb [arch=amd64] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge-dev.list \\
    && rm microsoft.gpg \\
    && apt-get update && apt-get install -y microsoft-edge-stable

RUN apt-get clean && rm -rf /var/lib/apt/lists/*
"""

# --- Treść docker-compose ---
DOCKER_COMPOSE_CONTENT = """
services:
  ubuntu-desktop:
    build: .
    container_name: ubuntu-browsers
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Warsaw
      - SUBFOLDER=/
      - TITLE=Ubuntu 24 Edge+Chrome
    volumes:
      - ./config:/config
    ports:
      - "8006:3000"
    shm_size: "16g"
    restart: unless-stopped
"""


def run_command(command, cwd=None, ignore_errors=False):
    """Uruchamia polecenie systemowe."""
    print(f"--- Uruchamianie: {' '.join(command)} ---")
    try:
        process = subprocess.run(
            command, check=True, capture_output=True, text=True, cwd=cwd)
        print(process.stdout)
        print("--- OK ---")
    except subprocess.CalledProcessError as e:
        if ignore_errors:
            print(
                f"Ostrzeżenie: Polecenie zwróciło błąd, ale kontynuujemy (kod {e.returncode}).")
            print(e.stderr)
        else:
            print(f"BŁĄD KRYTYCZNY: {' '.join(command)}")
            print(f"Kod błędu: {e.returncode}")
            print(f"STDERR:\n{e.stderr}")
            sys.exit(1)


def main():
    if os.geteuid() != 0:
        print("BŁĄD: Uruchom skrypt przez sudo!")
        sys.exit(1)

    print("Krok 0: Naprawa konfliktów pakietów (czyszczenie starego Dockera)...")

    # 1. Próba naprawy przerwanych instalacji
    run_command(["apt-get", "install", "-f", "-y"], ignore_errors=True)

    # 2. Usunięcie pakietów, które powodują konflikt (containerd.io vs docker.io)
    pkgs_to_remove = ["docker", "docker-engine", "docker.io",
                      "containerd", "runc", "containerd.io", "docker-doc", "podman-docker"]
    run_command(["apt-get", "remove", "-y"] +
                pkgs_to_remove, ignore_errors=True)

    # 3. Czyszczenie resztek
    run_command(["apt-get", "autoremove", "-y"], ignore_errors=True)

    print("\nKrok 1: Instalacja Docker i Docker Compose...")
    run_command(["apt-get", "update"])
    run_command(["apt-get", "install", "docker.io", "docker-compose", "-y"])

    print(f"\nKrok 2: Tworzenie plików w katalogu '{DOCKER_DIR}'...")
    if not os.path.exists(DOCKER_DIR):
        os.makedirs(DOCKER_DIR)

    print("\nKrok 3: Zatrzymywanie starego środowiska (jeśli istnieje)...")
    # Używamy ignore_errors=True, bo za pierwszym razem kontener nie istnieje i polecenie zwróci błąd
    run_command(["docker-compose", "-f", DOCKER_COMPOSE_FILE,
                "down", "-v"], cwd=DOCKER_DIR, ignore_errors=True)

    print("\nKrok 4: Budowanie i uruchamianie...")
    # Uruchomienie kontenera
    run_command(["docker-compose", "-f", DOCKER_COMPOSE_FILE,
                "up", "--build", "-d"], cwd=DOCKER_DIR)

    print("\n--- SUKCES ---")
    print("Dostęp: http://localhost:8006")

    dockerfile_path = os.path.join(DOCKER_DIR, DOCKERFILE_NAME)
    if not os.path.exists(dockerfile_path):
        with open(dockerfile_path, "w") as f:
            f.write(DOCKERFILE_CONTENT)
        print("Utworzono Dockerfile.")

    composefile_path = os.path.join(DOCKER_DIR, DOCKER_COMPOSE_FILE)
    if not os.path.exists(composefile_path):
        with open(composefile_path, "w") as f:
            f.write(DOCKER_COMPOSE_CONTENT)
        print("Utworzono ubuntu.yml.")

    print("\nKrok 3: Budowanie i uruchamianie...")
    # Uruchomienie kontenera
    run_command(["docker-compose", "-f", DOCKER_COMPOSE_FILE,
                "up", "--build", "-d"], cwd=DOCKER_DIR)

    print("\n--- SUKCES ---")
    print("Dostęp: http://localhost:8006")


if __name__ == "__main__":
    main()
