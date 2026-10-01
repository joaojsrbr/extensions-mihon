# Repositório de extensões Mihon / Tachiyomi

O [generate_index.py](generate_index.py) cria os índices e links de download a partir dos APKs presentes em `apk/`. Ele usa os metadados reais dos APKs e das fontes gerados pelo Gradle.

## Estrutura

- `apk/`: APKs distribuídos pelo repositório.
- `metadata/`: arquivos `keiyoushi-source-info.json` do Gradle, renomeados para `<packageName>.json`.
- [sources_config.json](sources_config.json): configuração das fontes, atualizada com os metadados do build. Para extensões antigas sem metadados Gradle, continua sendo a configuração manual.
- `icon/`: ícones extraídos dos APKs.
- [repo.json](repo.json): nome, endereço e impressão digital da chave do repositório.
- `index.json` / `index.min.json`: índices formatado e minificado.
- [index.html](index.html): links para os APKs disponíveis.

## Requisitos

- Python **3.10 ou superior**. Confira com `python --version`; Python 2 não executa o gerador.
- Android SDK com `aapt2`. Informe `--sdk`, configure `ANDROID_HOME` / `ANDROID_SDK_ROOT` ou disponibilize `aapt2` no PATH.
- `apksigner`, incluído no Android SDK, para verificar os certificados dos APKs.

O código de versão é lido do APK. O gerador não calcula esse valor a partir do nome do arquivo: `1.6.10`, por exemplo, não significa que o `versionCode` seja `10`.

## Atualizar uma extensão

1. Compile a extensão em modo release:

   ```powershell
   .\gradlew.bat :src:pt:egotoons:assembleRelease --console=plain
   ```

2. Copie o APK de `src/pt/egotoons/build/outputs/apk/release/` para `apk/`.
3. Copie `src/pt/egotoons/build/keiyoushi-source-info.json` para `metadata/eu.kanade.tachiyomi.extension.pt.egotoons.json`. APK e metadados devem vir do mesmo build.
4. Gere os índices usando um executável Python 3:

   ```powershell
   python generate_index.py --sdk D:\Android_sdk
   ```

Também é possível informar outro diretório de metadados:

```powershell
python generate_index.py --sdk D:\Android_sdk --metadata-dir caminho\dos\metadados
```

O gerador seleciona a maior versão de cada pacote, preserva os IDs das fontes como strings para evitar perda de precisão e atualiza a classificação de conteúdo a partir do manifesto. APKs ilegíveis, metadados de versões diferentes e fontes incompletas interrompem a geração antes da substituição dos índices. Cada arquivo gerado é substituído por uma gravação temporária no mesmo diretório.

## Assinatura antes da publicação

Todos os APKs precisam ser assinados com a chave esperada em `repo.json`. O gerador avisa quando o certificado difere e não troca automaticamente a impressão digital configurada.

Os APKs atuais foram assinados com `D:\android_key\mihon_extensions.jks`, usando o alias `joaojsr`. O certificado SHA-256 corresponde à impressão digital declarada em `repo.json`:

```text
665b87fa815a0ec29fedbc6288417b7f68a224adb993988e7e58ddb589017681
```

A cada novo build, assine o APK com essa mesma chave antes de copiá-lo para o repositório. Um `assembleRelease` sem uma chave de produção configurada pode gerar um APK assinado com a chave de depuração. Não salve senhas no repositório.

## Endereço do índice

Após publicar os arquivos, o endereço configurado para o repositório é:

```text
https://raw.githubusercontent.com/joaojsrbr/extensions-mihon/refs/heads/main/index.min.json
```

Atualizar os arquivos locais não publica alterações no GitHub.
