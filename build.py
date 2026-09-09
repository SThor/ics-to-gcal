from pathlib import Path
import shutil
import subprocess


def main():
    project_root = Path(__file__).resolve().parent
    client_secret = project_root / "client_secret.json"
    distribution_dir = project_root / "dist" / "ics-to-gcal"

    if not client_secret.is_file():
        raise SystemExit("Missing client_secret.json in the project root.")

    subprocess.run(
        [
            "pyinstaller",
            "--noconsole",
            "--noconfirm",
            "--name",
            "ics-to-gcal",
            "import_ics.py",
        ],
        cwd=project_root,
        check=True,
    )
    shutil.copy2(client_secret, distribution_dir / client_secret.name)
    print(f"Built {distribution_dir} and copied client_secret.json.")


if __name__ == "__main__":
    main()