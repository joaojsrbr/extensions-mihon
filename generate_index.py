#!/usr/bin/env python3
"""
Gera index.min.json, index.json e index.html para repositório de extensões Mihon/Tachiyomi.

Uso:
    python generate_index.py --sdk D:\\Android_sdk

O script:
  1. Escaneia a pasta apk/ por arquivos .apk
  2. Extrai os códigos de versão e a classificação de conteúdo reais via aapt2
  3. Extrai ícones dos APKs para a pasta icon/
  4. Lê os IDs e URLs dos metadados Gradle ou de sources_config.json para APKs antigos
  5. Confere assinaturas e gera índices com uma versão por pacote
"""

import argparse
import html
import json
import os
import re
import subprocess
import shutil
import sys
import zipfile
from pathlib import Path

# =============================================================================
# Paths
# =============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
APK_DIR = SCRIPT_DIR / "apk"
ICON_DIR = SCRIPT_DIR / "icon"
INDEX_JSON = SCRIPT_DIR / "index.json"
INDEX_MIN_JSON = SCRIPT_DIR / "index.min.json"
INDEX_HTML = SCRIPT_DIR / "index.html"
SOURCES_CONFIG = SCRIPT_DIR / "sources_config.json"
METADATA_DIR = SCRIPT_DIR / "metadata"


def write_text_atomic(path, content):
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def sdk_version_key(path):
    numbers = tuple(int(part) for part in re.findall(r"\d+", path.name))
    return numbers[:3], "-" not in path.name, numbers[3:]


# =============================================================================
# Buscar aapt2
# =============================================================================
def find_aapt2(sdk=None):
    """Procura o binário aapt2 no PATH e no Android SDK."""
    # Tentar no PATH
    aapt2_name = "aapt2.exe" if sys.platform == "win32" else "aapt2"
    try:
        result = subprocess.run(
            [aapt2_name, "version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return aapt2_name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Tentar via ANDROID_HOME / ANDROID_SDK_ROOT
    for sdk_path in (sdk, os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")):
        if not sdk_path:
            continue
        build_tools = Path(sdk_path) / "build-tools"
        if not build_tools.exists():
            continue
        # Pegar a versão mais recente
        versions = sorted(
            [d for d in build_tools.iterdir() if d.is_dir()],
            key=sdk_version_key,
            reverse=True,
        )
        for version_dir in versions:
            aapt2 = version_dir / aapt2_name
            if aapt2.exists():
                return str(aapt2)

    # Tentar caminhos comuns no Windows
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            sdk_dir = Path(local_app) / "Android" / "Sdk" / "build-tools"
            if sdk_dir.exists():
                versions = sorted(
                    [d for d in sdk_dir.iterdir() if d.is_dir()],
                    key=sdk_version_key,
                    reverse=True,
                )
                for version_dir in versions:
                    aapt2 = version_dir / "aapt2.exe"
                    if aapt2.exists():
                        return str(aapt2)

    return None


# =============================================================================
# Extrair metadados do APK via aapt2
# =============================================================================
def parse_apk_aapt2(apk_path, aapt2):
    """Extrai metadados do APK usando aapt2 dump badging."""
    try:
        result = subprocess.run(
            [aapt2, "dump", "badging", str(apk_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        output = result.stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"    ❌ Erro ao executar aapt2: {e}")
        return None

    if result.returncode != 0 or not output:
        print(f"    ❌ aapt2 não conseguiu ler {apk_path.name}: {result.stderr.strip()}")
        return None

    info = {}

    # Package: name, versionCode, versionName
    m = re.search(
        r"package:\s+name='([^']+)'\s+versionCode='(\d+)'\s+"
        r"(?:compileSdkVersion='\d+'\s+compileSdkVersionCodename='[^']*'\s+)?"
        r"versionName='([^']+)'",
        output,
    )
    if not m:
        # Fallback com regex mais simples
        m = re.search(r"package:\s+name='([^']+)'", output)
        if m:
            info["pkg"] = m.group(1)
        m2 = re.search(r"versionCode='(\d+)'", output)
        if m2:
            info["code"] = int(m2.group(1))
        m3 = re.search(r"versionName='([^']+)'", output)
        if m3:
            info["version"] = m3.group(1)
    else:
        info["pkg"] = m.group(1)
        info["code"] = int(m.group(2))
        info["version"] = m.group(3)

    # Application label
    m = re.search(r"application-label:'([^']+)'", output)
    if m:
        info["label"] = m.group(1)

    # Badging does not expose application meta-data; read the compiled manifest.
    manifest = subprocess.run(
        [aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=True,
    ).stdout
    values = {}
    for block in re.findall(r"E: meta-data.*?(?=\n\s*E:|\Z)", manifest, re.S):
        name = re.search(r':name\([^)]*\)="([^"]+)"', block)
        value = re.search(r':value\([^)]*\)=(0x[0-9a-fA-F]+|\d+)', block)
        if name and value:
            values[name.group(1)] = int(value.group(1), 0)
    for field in ("nsfw", "hasReadme", "hasChangelog"):
        info[field] = values.get(f"tachiyomi.extension.{field}", 0)

    # Icon path (para extração)
    icons = re.findall(r"application-icon-(\d+):'([^']+)'", output)
    if icons:
        info["icon_path"] = max(icons, key=lambda icon: int(icon[0]))[1]
    else:
        icon_match = re.search(r"application:.*?icon='([^']+)'", output)
        if icon_match:
            info["icon_path"] = icon_match.group(1)

    return info if all(field in info for field in ("pkg", "code", "version")) else None


# =============================================================================
# Metadados das fontes gerados pelo Gradle
# =============================================================================
def load_source_metadata(info, metadata_dir):
    metadata_path = metadata_dir / f"{info['pkg']}.json"
    if not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = (info["pkg"], info["code"], info["version"])
    actual = (metadata["packageName"], metadata["versionCode"], metadata["versionName"])
    if actual != expected:
        raise ValueError(f"Metadados desatualizados em {metadata_path.name}; copie os metadados do mesmo build do APK")
    return metadata


def validate_sources(sources, pkg):
    if not sources:
        raise ValueError(f"{pkg}: nenhuma fonte configurada")
    normalized = []
    for source in sources:
        source_id = int(source["id"])
        if not 0 < source_id <= 2**63 - 1 or not source.get("name") or not source.get("lang"):
            raise ValueError(f"{pkg}: fonte com ID, nome ou idioma inválido")
        if not re.match(r"https?://[^/]+", source.get("baseUrl", "")):
            raise ValueError(f"{pkg}: URL da fonte ausente ou inválida")
        # Strings preserve 64-bit IDs when consumers read the JSON with JavaScript.
        normalized.append({**source, "id": str(source_id)})
    return normalized


def signing_warnings(aapt2, apk_paths):
    aapt_path = Path(shutil.which(aapt2) or aapt2)
    signer = aapt_path.with_name("apksigner.bat" if sys.platform == "win32" else "apksigner")
    if not signer.exists():
        return ["apksigner não encontrado; a chave de assinatura não foi conferida"]
    repo_path = SCRIPT_DIR / "repo.json"
    if not repo_path.exists():
        return []
    configured = json.loads(repo_path.read_text(encoding="utf-8"))["meta"]["signingKeyFingerprint"].lower()
    warnings = []
    for apk_path in apk_paths:
        result = subprocess.run(
            [str(signer), "verify", "--print-certs", str(apk_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            raise ValueError(f"Assinatura inválida: {apk_path.name}")
        fingerprints = re.findall(r"certificate SHA-256 digest: ([0-9a-fA-F]{64})", result.stdout)
        if configured not in [fingerprint.lower() for fingerprint in fingerprints]:
            warnings.append(f"{apk_path.name}: certificado diferente de repo.json. Assine com a chave original antes de publicar.")
    return warnings


# =============================================================================
# Extrair ícone do APK
# =============================================================================
def extract_icon(apk_path, pkg_name, icon_internal_path=None):
    """Extrai o ícone do APK (ZIP) e salva na pasta icon/."""
    ICON_DIR.mkdir(exist_ok=True)
    icon_out = ICON_DIR / f"{pkg_name}.png"

    try:
        with zipfile.ZipFile(str(apk_path), "r") as z:
            # Tentar caminho específico do aapt2
            if icon_internal_path and icon_internal_path in z.namelist():
                data = z.read(icon_internal_path)
                icon_out.write_bytes(data)
                return True

            # Tentar caminhos comuns (preferência: maior resolução)
            icon_candidates = []
            for name in z.namelist():
                if "ic_launcher" in name and name.endswith(".png"):
                    # Priorizar por resolução
                    priority = 0
                    if "xxxhdpi" in name:
                        priority = 4
                    elif "xxhdpi" in name:
                        priority = 3
                    elif "xhdpi" in name:
                        priority = 2
                    elif "hdpi" in name:
                        priority = 1
                    icon_candidates.append((priority, name))

            if icon_candidates:
                icon_candidates.sort(reverse=True)
                best_icon = icon_candidates[0][1]
                data = z.read(best_icon)
                icon_out.write_bytes(data)
                return True

    except Exception as e:
        print(f"    ⚠️  Erro ao extrair ícone: {e}")

    return False


# =============================================================================
# Utilitários
# =============================================================================
def get_lang_from_pkg(pkg_name):
    """Extrai o código de idioma do package name."""
    parts = pkg_name.split(".")
    try:
        idx = parts.index("extension")
        lang = parts[idx + 1]
        # Mapeamento de códigos comuns
        lang_map = {
            "pt": "pt-BR",
            "all": "all",
        }
        return lang_map.get(lang, lang)
    except (ValueError, IndexError):
        return "all"


def load_sources_config():
    """Carrega configuração de fontes do sources_config.json."""
    if SOURCES_CONFIG.exists():
        with open(SOURCES_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_sources_config(config):
    """Salva configuração de fontes no sources_config.json."""
    write_text_atomic(SOURCES_CONFIG, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def generate_html(extensions):
    """Gera o index.html com links para os APKs."""
    links = []
    for ext in extensions:
        name = html.escape(ext["name"].removeprefix("Tachiyomi: "))
        apk = html.escape(ext["apk"], quote=True)
        version = html.escape(ext["version"])
        lang = html.escape(ext["lang"])
        links.append(f'<a href="apk/{apk}">{name} v{version} [{lang}]</a>')

    links_str = "\n".join(links)

    page = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Extensões Mihon - Repositório</title>
</head>
<body>
    <h1>Extensões Disponíveis</h1>
    <pre>
{links_str}
    </pre>
</body>
</html>
"""
    write_text_atomic(INDEX_HTML, page)


# =============================================================================
# Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, help="Diretório do Android SDK")
    parser.add_argument("--metadata-dir", type=Path, default=METADATA_DIR, help="Metadados keiyoushi-source-info.json renomeados por pacote")
    args = parser.parse_args()
    print("=" * 60)
    print("  Gerador de index.min.json - Repositório Mihon")
    print("=" * 60)

    # Verificar pasta de APKs
    if not APK_DIR.exists():
        print(f"\n❌ Pasta não encontrada: {APK_DIR}")
        print("   Crie a pasta 'apk/' e coloque seus APKs nela.")
        sys.exit(1)

    # Buscar aapt2
    print("\n🔍 Procurando aapt2...")
    aapt2 = find_aapt2(args.sdk)

    if aapt2:
        print(f"   ✅ Encontrado: {aapt2}")
    else:
        raise ValueError("aapt2 não encontrado. Use --sdk ou configure ANDROID_HOME; o nome do arquivo não contém o versionCode real.")

    # Carregar config de fontes
    sources_config = load_sources_config()

    # Escanear APKs
    apk_files = sorted(APK_DIR.glob("*.apk"))
    if not apk_files:
        print(f"\n❌ Nenhum APK encontrado em: {APK_DIR}")
        sys.exit(1)

    print(f"\n📦 {len(apk_files)} APK(s) encontrado(s)\n")

    selected = {}
    warnings = []
    for apk_path in apk_files:
        info = parse_apk_aapt2(apk_path, aapt2)
        if info is None:
            raise ValueError(f"Não foi possível ler {apk_path.name}; os índices existentes foram preservados")
        previous = selected.get(info["pkg"])
        if previous is None or info["code"] > previous[1]["code"]:
            if previous:
                warnings.append(f"Versão antiga omitida: {previous[0].name}")
            selected[info["pkg"]] = (apk_path, info)
        else:
            warnings.append(f"Versão duplicada ou antiga omitida: {apk_path.name}")
    warnings.extend(signing_warnings(aapt2, [item[0] for item in selected.values()]))

    extensions = []
    config_updated = False

    for pkg in sorted(selected):
        apk_path, info = selected[pkg]
        print(f"  📱 {apk_path.name}")
        lang = get_lang_from_pkg(pkg)
        label = info.get("label", f"Tachiyomi: {pkg.split('.')[-1].title()}")

        # Extrair ícone
        icon_path = info.get("icon_path")
        if extract_icon(apk_path, pkg, icon_path):
            print(f"     🎨 Ícone extraído")
        else:
            print(f"     ⚠️  Ícone não encontrado no APK")

        # Obter configuração de fontes
        metadata = load_source_metadata(info, args.metadata_dir)
        if metadata:
            sources = validate_sources(metadata["sources"], pkg)
        elif pkg in sources_config:
            sources = validate_sources(sources_config[pkg]["sources"], pkg)
        else:
            raise ValueError(f"{pkg}: copie o keiyoushi-source-info.json do build para metadata/{pkg}.json; IDs provisórios não serão publicados")
        config = {"sources": sources, **{field: info[field] for field in ("nsfw", "hasReadme", "hasChangelog")}}
        if sources_config.get(pkg) != config:
            sources_config[pkg] = config
            config_updated = True

        # Montar entrada do index
        pkg_config = sources_config.get(pkg, {})
        entry = {
            "name": label,
            "pkg": pkg,
            "apk": apk_path.name,
            "lang": lang,
            "code": info["code"],
            "version": info["version"],
            "nsfw": pkg_config.get("nsfw", info.get("nsfw", 0)),
            "hasReadme": pkg_config.get("hasReadme", info.get("hasReadme", 0)),
            "hasChangelog": pkg_config.get("hasChangelog", info.get("hasChangelog", 0)),
            "sources": sources,
        }

        extensions.append(entry)
        print(f"     ✅ {label} v{entry['version']} (code={entry['code']})")

    if not extensions:
        print("\n❌ Nenhuma extensão processada!")
        sys.exit(1)

    # Salvar sources_config.json se houve mudanças
    if config_updated:
        save_sources_config(sources_config)
        print(f"\n📝 sources_config.json atualizado")

    # Gerar index.json (formatado)
    write_text_atomic(INDEX_JSON, json.dumps(extensions, indent=2, ensure_ascii=False) + "\n")
    print(f"\n📄 index.json gerado ({INDEX_JSON.name})")

    # Gerar index.min.json (minificado)
    write_text_atomic(INDEX_MIN_JSON, json.dumps(extensions, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"📄 index.min.json gerado ({INDEX_MIN_JSON.name})")

    # Gerar index.html
    generate_html(extensions)
    print(f"📄 index.html gerado ({INDEX_HTML.name})")

    # Resumo
    print(f"\n{'=' * 60}")
    print(f"  ✅ {len(extensions)} extensão(ões) processada(s) com sucesso!")
    print(f"{'=' * 60}")

    # Avisos
    if warnings:
        print(f"\n⚠️  Avisos:")
        for w in warnings:
            print(f"   • {w}")

    print()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"\n❌ {error}", file=sys.stderr)
        sys.exit(1)
