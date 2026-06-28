#!/usr/bin/env python3
"""
Gera index.min.json, index.json e index.html para repositório de extensões Mihon/Tachiyomi.

Uso:
    python generate_index.py

O script:
  1. Escaneia a pasta apk/ por arquivos .apk
  2. Extrai metadados via aapt2 (ou pelo nome do arquivo como fallback)
  3. Extrai ícones dos APKs para a pasta icon/
  4. Lê configuração de fontes de sources_config.json
  5. Gera index.min.json, index.json e index.html
"""

import json
import os
import re
import subprocess
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


# =============================================================================
# Buscar aapt2
# =============================================================================
def find_aapt2():
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
    for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk_path = os.environ.get(env_var)
        if not sdk_path:
            continue
        build_tools = Path(sdk_path) / "build-tools"
        if not build_tools.exists():
            continue
        # Pegar a versão mais recente
        versions = sorted(
            [d for d in build_tools.iterdir() if d.is_dir()],
            key=lambda p: p.name,
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
                    key=lambda p: p.name,
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
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"    ❌ Erro ao executar aapt2: {e}")
        return None

    if not output:
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

    # Meta-data: NSFW
    nsfw_match = re.search(
        r"meta-data:.*?name='tachiyomi\.extension\.nsfw'.*?value='(\d+)'",
        output,
    )
    info["nsfw"] = int(nsfw_match.group(1)) if nsfw_match else 0

    # Meta-data: hasReadme
    readme_match = re.search(
        r"meta-data:.*?name='tachiyomi\.extension\.hasReadme'.*?value='(\d+)'",
        output,
    )
    info["hasReadme"] = int(readme_match.group(1)) if readme_match else 0

    # Meta-data: hasChangelog
    changelog_match = re.search(
        r"meta-data:.*?name='tachiyomi\.extension\.hasChangelog'.*?value='(\d+)'",
        output,
    )
    info["hasChangelog"] = int(changelog_match.group(1)) if changelog_match else 0

    # Icon path (para extração)
    icon_match = re.search(r"application:.*?icon='([^']+)'", output)
    if icon_match:
        info["icon_path"] = icon_match.group(1)

    return info if "pkg" in info else None


# =============================================================================
# Fallback: extrair metadados do nome do arquivo
# =============================================================================
def parse_apk_filename(filename):
    """
    Fallback: extrai metadados do nome do arquivo APK.
    Formato esperado: tachiyomi-<lang>.<name>-v<version>[-release].apk
    Exemplo: tachiyomi-pt.lycantoons-v1.4.4-release.apk
    """
    m = re.match(
        r"tachiyomi-([a-z]+(?:-[a-z]+)?)\.([a-z0-9]+)-v([\d.]+)(?:-release)?\.apk",
        filename,
        re.IGNORECASE,
    )
    if not m:
        return None

    lang_code = m.group(1)
    name = m.group(2)
    version = m.group(3)

    # Derivar versionCode do último segmento da versão
    version_parts = version.split(".")
    code = int(version_parts[-1]) if version_parts else 1

    pkg = f"eu.kanade.tachiyomi.extension.{lang_code}.{name}"

    return {
        "pkg": pkg,
        "code": code,
        "version": version,
        "label": f"Tachiyomi: {name.replace('_', ' ').title()}",
        "nsfw": 0,
        "hasReadme": 0,
        "hasChangelog": 0,
    }


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
    with open(SOURCES_CONFIG, "w", encoding="utf-8", newline="\n") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def generate_html(extensions):
    """Gera o index.html com links para os APKs."""
    links = []
    for ext in extensions:
        name = ext["name"].replace("Tachiyomi: ", "")
        apk = ext["apk"]
        version = ext["version"]
        lang = ext["lang"]
        links.append(f'<a href="apk/{apk}">{name} v{version} [{lang}]</a>')

    links_str = "\n".join(links)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
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
    with open(INDEX_HTML, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)


# =============================================================================
# Main
# =============================================================================
def main():
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
    aapt2 = find_aapt2()

    if aapt2:
        print(f"   ✅ Encontrado: {aapt2}")
    else:
        print("   ⚠️  aapt2 não encontrado!")
        print("   Usando fallback (parsing do nome do arquivo).")
        print("   Para resultados mais precisos, instale o Android SDK.")

    # Carregar config de fontes
    sources_config = load_sources_config()

    # Escanear APKs
    apk_files = sorted(APK_DIR.glob("*.apk"))
    if not apk_files:
        print(f"\n❌ Nenhum APK encontrado em: {APK_DIR}")
        sys.exit(1)

    print(f"\n📦 {len(apk_files)} APK(s) encontrado(s)\n")

    extensions = []
    config_updated = False
    warnings = []

    for apk_path in apk_files:
        print(f"  📱 {apk_path.name}")

        # Extrair metadados
        info = None
        if aapt2:
            info = parse_apk_aapt2(apk_path, aapt2)

        if not info:
            info = parse_apk_filename(apk_path.name)

        if not info or "pkg" not in info:
            print(f"     ❌ Não foi possível extrair metadados!")
            warnings.append(f"APK ignorado: {apk_path.name}")
            continue

        pkg = info["pkg"]
        lang = get_lang_from_pkg(pkg)
        label = info.get("label", f"Tachiyomi: {pkg.split('.')[-1].title()}")

        # Extrair ícone
        icon_path = info.get("icon_path")
        if extract_icon(apk_path, pkg, icon_path):
            print(f"     🎨 Ícone extraído")
        else:
            print(f"     ⚠️  Ícone não encontrado no APK")

        # Obter configuração de fontes
        if pkg in sources_config:
            sources = sources_config[pkg]["sources"]
        else:
            # Criar template automático
            ext_name = label.replace("Tachiyomi: ", "")
            sources = [
                {
                    "name": ext_name,
                    "lang": lang,
                    "id": 0,
                    "baseUrl": "",
                }
            ]
            sources_config[pkg] = {"sources": sources}
            config_updated = True
            warnings.append(
                f"Nova extensão detectada: {pkg}\n"
                f"       → Edite sources_config.json e preencha 'id' e 'baseUrl'"
            )

        # Montar entrada do index
        entry = {
            "name": label,
            "pkg": pkg,
            "apk": apk_path.name,
            "lang": lang,
            "code": info.get("code", 1),
            "version": info.get("version", "1.0.0"),
            "nsfw": info.get("nsfw", 0),
            "hasReadme": info.get("hasReadme", 0),
            "hasChangelog": info.get("hasChangelog", 0),
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
    with open(INDEX_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(extensions, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\n📄 index.json gerado ({INDEX_JSON.name})")

    # Gerar index.min.json (minificado)
    with open(INDEX_MIN_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(extensions, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")
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
    main()
