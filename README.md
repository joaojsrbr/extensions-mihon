# Repositório de Extensões para Mihon / Tachiyomi

Este projeto gerencia e gera o índice de um repositório personalizado de extensões APK para o **Mihon** (e outros leitores de mangá baseados no Tachiyomi). Ele escaneia uma pasta contendo os APKs das extensões, extrai automaticamente os metadados (como nome, pacote, versão e ícone) e gera a estrutura estática necessária para servir como repositório.

## 📁 Estrutura do Projeto

* `apk/`: Diretório onde devem ser colocados os arquivos `.apk` das extensões.
* `icon/`: Pasta onde os ícones extraídos dos APKs são salvos automaticamente (utilizados no aplicativo).
* [generate_index.py](file:///f:/extensions-repo/generate_index.py): Script Python 3 responsável por processar os APKs e gerar os arquivos do repositório.
* [repo.json](file:///f:/extensions-repo/repo.json): Contém os metadados do seu repositório (Nome, site e chave de assinatura).
* [sources_config.json](file:///f:/extensions-repo/sources_config.json): Mapeamento de metadados das fontes dentro de cada extensão (como IDs, URLs base, status de NSFW, README e Changelog).
* `index.json` / `index.min.json`: Índices de extensões gerados automaticamente pelo script (são lidos pelo app Mihon).
* [index.html](file:///f:/extensions-repo/index.html): Página web simples gerada automaticamente com a lista de extensões para download direto via navegador.

## 🛠️ Pré-requisitos

1. **Python 3.x** instalado.
2. *(Opcional, mas recomendado)* **Android SDK (aapt2)**:
    * O script tenta localizar o utilitário `aapt2` automaticamente no PATH do sistema, nas variáveis de ambiente `ANDROID_HOME` / `ANDROID_SDK_ROOT` ou nos caminhos padrão de instalação do Android Studio.
    * **Vantagem**: Com o `aapt2`, o script consegue extrair com precisão os metadados e o ícone diretamente do binário do APK.
    * **Fallback**: Caso o `aapt2` não esteja instalado ou configurado, o script fará o parsing baseado no nome do arquivo do APK (ex: `tachiyomi-pt.lycantoons-v1.4.5-release.apk`), mas os ícones das extensões não serão extraídos.

## 🚀 Como Usar

### 1. Configurar o Repositório (`repo.json`)

Antes de rodar o script, configure os dados do seu repositório no arquivo [repo.json](file:///f:/extensions-repo/repo.json):

```json
{
  "meta": {
    "name": "Apex Repo",
    "website": "https://github.com/joaojsrbr/extensions-mihon",
    "signingKeyFingerprint": "665b87fa815a0ec29fedbc6288417b7f68a224adb993988e7e58ddb589017681"
  }
}
```

### 2. Adicionar as Extensões (APKs)

Coloque os arquivos `.apk` das suas extensões dentro da pasta `apk/`.

### 3. Executar o Script de Geração

Abra o terminal na raiz do projeto e execute:

```powershell
python generate_index.py
```

### 4. Configurar Novas Extensões (`sources_config.json`)

Se você adicionar uma nova extensão pela primeira vez, o script irá detectá-la automaticamente e adicioná-la com valores padrão ao arquivo [sources_config.json](file:///f:/extensions-repo/sources_config.json).

Abra o arquivo [sources_config.json](file:///f:/extensions-repo/sources_config.json) e configure os campos corretos para a nova extensão, como o `id` e a `baseUrl` correspondentes:

```json
  "eu.kanade.tachiyomi.extension.pt.lycantoons": {
    "nsfw": 0,
    "hasReadme": 0,
    "hasChangelog": 0,
    "sources": [
      {
        "name": "Lycan Toons",
        "lang": "pt-BR",
        "id": 10,
        "baseUrl": "https://lycantoons.com"
      }
    ]
  }
```

*Nota: Após atualizar as configurações no `sources_config.json`, execute o script `python generate_index.py` novamente para gerar o índice definitivo com os IDs corretos.*

## 📱 Adicionando o Repositório no Mihon / Tachiyomi

Para usar as extensões geradas pelo seu repositório no aplicativo:

1. Copie a URL do repositório:

   ```
   https://raw.githubusercontent.com/joaojsrbr/extensions-mihon/refs/heads/main/index.min.json
   ```

2. No aplicativo **Mihon**, vá em **Configurações** > **Procurar** > **Repositórios de extensões** > **Adicionar repositório**.
3. Cole a URL do repositório e confirme.
