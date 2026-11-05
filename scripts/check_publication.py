"""Verifica arquivos publicáveis sem adicionar, commitar ou enviar nada ao GitHub."""

import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERN = re.compile(r"(?:nvapi-[A-Za-z0-9_-]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})")
PRIVATE_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]")
EXCLUDED_DIRS = {".venv", ".tools", ".python", ".uv-cache", ".cache", "backups", "filesIAColab"}


def git_files(args):
    output = subprocess.check_output([
        "git", *args, "ls-files", "--cached", "--others", "--exclude-standard", "-z",
    ], cwd=ROOT)
    return sorted(set(name.decode("utf-8") for name in output.split(b"\0") if name))


def publication_files():
    if (ROOT / ".git").exists():
        return git_files([])
    # Repositório descartável: o projeto não é inicializado nem tem seu índice alterado.
    with tempfile.TemporaryDirectory(prefix="fia-publication-") as temporary:
        git_dir = Path(temporary) / "audit.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(git_dir)], check=True)
        return git_files([f"--git-dir={git_dir}", f"--work-tree={ROOT}"])


def local_secrets():
    secrets = []
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("\"'")
            if any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")) and len(value) >= 12:
                secrets.append(value)
    return secrets


def main():
    errors = []
    files = publication_files()
    secrets = local_secrets()
    for name in files:
        path = ROOT / name
        if not path.is_file():
            continue
        parts = Path(name).parts
        if (parts[0] in EXCLUDED_DIRS or parts[0].startswith("vector_store_method_")
                or (path.name.startswith(".env") and path.name != ".env.example")
                or (path.name.startswith("avaliacao") and path.suffix in {".csv", ".json"})):
            errors.append(f"Arquivo local incluído pelo Git: {name}")
        if path.stat().st_size > 50 * 1024 * 1024:
            errors.append(f"Arquivo maior que 50 MiB: {name}")
        if path.suffix.lower() not in {".md", ".txt", ".py", ".json", ".ipynb", ".csv", ".yml", ".yaml", ".toml"} and path.name not in {".env.example", ".gitignore"}:
            continue
        content = path.read_text(encoding="utf-8-sig")
        if SECRET_PATTERN.search(content) or any(value in content for value in secrets):
            errors.append(f"Possível credencial em {name}; valor omitido.")
        if path.suffix == ".ipynb":
            notebook = json.loads(content)
            for index, cell in enumerate(notebook["cells"]):
                if cell.get("outputs") or cell.get("execution_count") is not None:
                    errors.append(f"Saída ou contador de execução em {name}, célula {index}.")
                if cell["cell_type"] == "code":
                    compile("".join(cell["source"]), f"{name}:cell-{index}", "exec")
            if PRIVATE_PATH.search(content.replace("\\\\", "\\")):
                errors.append(f"Caminho pessoal absoluto no notebook: {name}")
        if path.name.startswith("requirements") and ("@ file:" in content or "-e " in content):
            errors.append(f"Dependência com caminho local em {name}")
    print(f"Arquivos candidatos à publicação: {len(files)}")
    if errors:
        print("\n".join(errors))
        return 1
    print("OK: sem credenciais detectadas, saídas de notebook ou arquivos locais indevidos.")
    if not (ROOT / "LICENSE").exists():
        print("Observação: licença do código ainda não definida; consulte NOTICE.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
