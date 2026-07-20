<div align="center">

<img width="130" alt="DeviceKit" src="assets/logo.svg" />

# DeviceKit

**Uma plataforma unificada de frota de dispositivos Android e automação de testes.**

Controle uma frota de dispositivos Android a partir de um único painel — execute automações, transmita
telas em tempo real, detecte regressões visuais e depure falhas com
análise assistida por IA.

[English](../README.md) | [Español](README.es.md) | [中文版](README.zh-CN.md) | Português

<br>

![Android](https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![Kotlin](https://img.shields.io/badge/Kotlin-7F52FF?style=for-the-badge&logo=kotlin&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
[![Discord](https://img.shields.io/discord/1470639209059455008?style=for-the-badge&logo=discord&logoColor=white&label=Discord&color=5865F2)](https://discord.gg/ZKk6tkCQfG)

[![GitHub Stars](https://img.shields.io/github/stars/jhd3197/DeviceKit?style=flat-square&color=f5c542)](https://github.com/jhd3197/DeviceKit/stargazers)
[![Downloads](https://img.shields.io/github/downloads/jhd3197/DeviceKit/total?style=flat-square)](https://github.com/jhd3197/DeviceKit/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](../LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![React](https://img.shields.io/badge/react-18-61DAFB.svg?style=flat-square&logo=react&logoColor=black)](https://reactjs.org)
[![Flask](https://img.shields.io/badge/flask-3.0-000000.svg?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![PyPI](https://img.shields.io/badge/pip-droidlink-3775A9.svg?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/droidlink/)

<br>

[Início Rápido](#-início-rápido) · [Capturas](#-capturas-de-tela) · [Funcionalidades](#-funcionalidades) · [Arquitetura](#-arquitetura) · [Roadmap](#-roadmap) · [Documentação](#-documentação) · [Contribuir](#-contribuir) · [Discord](#-comunidade)

</div>

---

<p align="center">
  <img alt="Visão geral da frota do DeviceKit" width="100%" src="screenshots/dashboard.png" />
</p>

---

## Por que DeviceKit?

Gerenciar dispositivos Android para testes normalmente significa malabarismos com comandos ADB entre
terminais, controle manual de qual dispositivo está rodando o quê, e garimpar
logs quando algo quebra. O DeviceKit adota uma abordagem diferente: uma única
plataforma que descobre seus dispositivos, permite controlá-los a partir de um painel
web e automatiza as partes tediosas.

Tudo são **quatro componentes trabalhando juntos** — um backend em Python/Flask
que gerencia o estado dos dispositivos e orquestra as ações, um frontend em React para o
painel e os editores visuais, um app agente em Kotlin que roda em cada dispositivo para
reportar métricas e aceitar comandos, e uma biblioteca Python
([`pip install droidlink`](https://pypi.org/project/droidlink/)) para scripts e
pipelines de CI. Você tem **automação assistida por IA** desde o início: descreva o que
quer em linguagem natural e o DeviceKit gera passos executáveis; quando elementos da UI
se movem entre versões do app, as retentativas autocuráveis os encontram novamente; quando testes falham,
os pacotes de depuração reúnem capturas de tela, logs, hierarquia da UI e estado do dispositivo em um único
download — com análise opcional de causa raiz por IA.

---

## 🚀 Início Rápido

> ⏱️ Conecte um dispositivo e ele aparece automaticamente.

### Opção 1: Docker (Recomendada)

```bash
git clone https://github.com/jhd3197/DeviceKit.git
cd DeviceKit
cp .env.example .env
docker-compose up
```

| Serviço | URL |
|---------|-----|
| Frontend | http://localhost:3847 |
| API | http://localhost:5890 |
| DynamoDB (local) | http://localhost:8321 |

### Opção 2: Instalação Manual

```bash
# Backend
cd backend
pip install -r requirements.txt
python app.py                # API em http://localhost:5050

# Frontend (em um segundo terminal)
cd frontend
npm install
npm run dev                  # servidor de desenvolvimento em http://localhost:5173
```

### Conectar um Dispositivo

```bash
# USB : basta conectar o dispositivo (ADB / depuração USB ativada)
# WiFi: instale o APK do agente — mesma rede, descobre o backend automaticamente
```

**Precisa do app do agente?** O backend o serve em `GET /agent/apk`, ou compile a partir de
`agent-android/`.

### Controle a partir do Python

```python
# pip install droidlink — a mesma frota, a partir de um script ou CI
def test_login_flow(device):
    device.app.start("com.example.app")
    device.input.tap(540, 1200)
    device.input.type_text("user@test.com")
    assert device.screen.capture() is not None
```

---

<!-- DK:SHOTS:START -->
## 📸 Capturas de Tela

|                        Visão Geral da Frota                         |                          Controle de Nó                          |
| :-----------------------------------------------------------------: | :--------------------------------------------------------------: |
|      ![Visão Geral da Frota](screenshots/dashboard.png)          |        ![Controle de Nó](screenshots/node-detail.png)         |
|   _Métricas da frota em tempo real, cartões KPI, distribuição de saúde, execuções ativas, falhas recentes e a barra de consultas FQL_   |   _Transmissão ao vivo por dispositivo, medidores de diagnóstico ao vivo, shell ADB, histórico de métricas e ações rápidas de macro_   |

|                        Execução de Automação                        |                         Editor de Automação                         |
| :-----------------------------------------------------------------: | :-----------------------------------------------------------------: |
|      ![Execução de Automação](screenshots/automation-run.png)      |      ![Editor de Automação](screenshots/automation-editor.png)      |
|   _Resultados ao vivo por passo, autocura (diff original → curado), asserts de regressão visual e um pacote de depuração gerado automaticamente com análise de IA em caso de falha_   |   _Construtor de passos com reordenação + refinamento por IA por passo, "Gerar com IA", tags e baselines visuais_   |

|                        Construtor de Workflows                        |                             Automações                             |
| :-------------------------------------------------------------------: | :----------------------------------------------------------------: |
|        ![Construtor de Workflows](screenshots/workflow.png)          |            ![Automações](screenshots/automations.png)             |
|   _Canvas visual de automação baseado em nós — encadeie gatilhos, toques, esperas, asserts e ramificações_   |   _Todas as automações com passos, tags, controles de executar/agendar/compartilhar/clonar e um feed de execuções recentes_   |

|                       Comparação de Dispositivos                       |                          Monitor de Métricas                          |
| :--------------------------------------------------------------------: | :-------------------------------------------------------------------: |
|      ![Comparação de Dispositivos](screenshots/compare.png)         |          ![Monitor de Métricas](screenshots/monitor.png)           |
|   _Até 4 dispositivos lado a lado com sobreposição sincronizada de tendências históricas e medidores por dispositivo_   |   _Gráficos de métricas entre dispositivos em períodos selecionáveis, mais regras de alerta por limite no barramento de notificações_   |

<details>
<summary><strong>Ver todas as capturas</strong></summary>

<br>

|                        Grupos de Dispositivos                         |                            Pipeline / CI                            |
| :-------------------------------------------------------------------: | :-----------------------------------------------------------------: |
|        ![Grupos de Dispositivos](screenshots/groups.png)           |             ![Pipeline / CI](screenshots/pipeline.png)             |
|   _Grupos com tags e código de cores, com ações em massa — reiniciar, bloquear, instalar, executar automações_   |   _Lista de builds, resultados por teste e capturas de falhas do plugin pytest do droidlink_   |

|                               Perfis                               |                             ADB Remoto                              |
| :----------------------------------------------------------------: | :-----------------------------------------------------------------: |
|               ![Perfis](screenshots/profiles.png)                 |              ![ADB Remoto](screenshots/remote-adb.png)             |
|   _Personalidades de IA por dispositivo e configuração de modelos multi-provedor (Claude, GPT, Groq, Ollama, Google)_   |   _Shell ADB no navegador com histórico de comandos e predefinições, mais um explorador de arquivos_   |

|                            Registro de Agentes                            |                        Histórico de Comandos                        |
| :-----------------------------------------------------------------------: | :-----------------------------------------------------------------: |
|                 ![Registro de Agentes](screenshots/enrollment.png)                 |     ![Histórico de Comandos](screenshots/command-history.png)     |
|   _Pareamento do agente e fila de aprovação com descoberta automática em LAN para novos dispositivos_   |   _Uma linha do tempo de toda a frota com cada comando emitido, seu status e quem o executou_   |

|                                Tarefas                                |                            Notificações                            |
| :-------------------------------------------------------------------: | :----------------------------------------------------------------: |
|                 ![Tarefas](screenshots/jobs.png)                   |          ![Notificações](screenshots/notifications.png)           |
|   _Tarefas em segundo plano enfileiradas, em execução e concluídas — automações, instalações em massa, capturas de baseline_   |   _Feed de onboarding + alertas com canais de entrega (webhook, Slack, e-mail)_   |

|                              Extensões                               |                             Configurações                              |
| :------------------------------------------------------------------: | :--------------------------------------------------------------------: |
|             ![Extensões](screenshots/extensions.png)              |               ![Configurações](screenshots/settings.png)              |
|   _Extensões instaladas mais um registro remoto para explorar e instalar mais com um clique_   |   _Identidade da instância, acesso à API, 2FA, configuração de IA/streaming/pacotes de depuração e aparência/marca branca_   |

</details>
<!-- DK:SHOTS:END -->

---

## 🎯 Funcionalidades

### 🛰️ Gerenciamento de Frota

| | |
|---|---|
| **Métricas em tempo real**<br>CPU, RAM, bateria, temperatura e armazenamento por dispositivo, transmitidos ao vivo. | **Saúde da frota**<br>Distribuição agregada de saudável / alerta / crítico em toda a frota. |
| **Grupos de dispositivos**<br>Tags, código de cores e ações em massa em qualquer seleção. | **Comparação de dispositivos**<br>Até 4 dispositivos lado a lado com gráficos em tempo real sincronizados. |
| **Onboarding automático**<br>Novos dispositivos se anunciam no momento em que se conectam. | **Histórico de comandos**<br>Uma linha do tempo de auditoria de toda a frota com cada ação emitida. |

### 🔎 Linguagem de Consulta da Frota

| | |
|---|---|
| **Filtragem estilo SQL**<br>`android_version < 13 AND battery > 20 AND status = 'idle'` | **Autocompletar + predefinições**<br>Completar campos na barra de consultas, mais opções integradas (bateria fraca, offline, SO desatualizado). |
| **Consultas salvas**<br>Guarde os filtros que você mais usa. | **Consulta → ação em massa**<br>Direcione os resultados diretamente para reiniciar, bloquear, instalar APK ou executar automação. |
| **Exportação CSV**<br>Leve qualquer resultado de consulta com você. | |

### 🤖 Motor de Automação

| | |
|---|---|
| **14 tipos de passos**<br>Toque, deslizar, digitar, pressionar tecla, abrir/fechar app, enviar/baixar arquivos, espera, assert, captura e mais. | **Editor de arrastar e soltar**<br>Construtor visual de passos com pré-visualizações e contexto do dispositivo ao vivo. |
| **Construtor de workflows**<br>Canvas baseado em nós para automações ramificadas de vários passos. | **Gravar automações**<br>Toque e deslize no dispositivo; receba os passos gerados. |
| **Agendar e compartilhar**<br>Execute em intervalos com pausa/retomada; clone, exporte e importe como JSON. | |

### ✨ Automação com IA

| | |
|---|---|
| **Gerar**<br>Transforme uma descrição em linguagem natural em passos de automação executáveis. | **Refinar**<br>Modifique passos individuais com instruções conversacionais. |
| **Explicar**<br>Obtenha um resumo em linguagem natural do que qualquer automação faz. | **Autocura**<br>Quando elementos da UI se movem entre versões do app, a IA relocaliza os alvos e tenta novamente automaticamente. |

### 🖼️ Testes de Regressão Visual

| | |
|---|---|
| **Asserts de captura**<br>Um passo `screenshot_assert` compara com baselines armazenadas. | **Motor de diff SSIM**<br>Diff de pixels com limites configuráveis. |
| **Análise de diff com IA**<br>Distingue mudanças significativas na UI de ruído de renderização. | **Mascaramento de regiões**<br>Exclua conteúdo dinâmico (relógios, anúncios, timestamps). |
| **Baselines por modelo**<br>Baselines rastreadas por modelo e versão do dispositivo, com relatórios de aprovado / reprovado / precisa de revisão. | |

### 📺 Transmissão de Dispositivos ao Vivo

| | |
|---|---|
| **Streaming MJPEG**<br>Vídeo em tempo real, não polling de capturas, com qualidade adaptativa (5 / 15 / 30 fps). | **Multi-espectador**<br>Emblemas de contagem de espectadores e sessões compartilhadas. |
| **Sobreposição de toque**<br>Animações de ondulação mostram cada interação. | **Gravação de sessões**<br>Reprodução quadro a quadro com marcadores de eventos. |
| **Indicador de latência**<br>Verde (<100 ms), amarelo (<300 ms), vermelho (>300 ms), com fallback automático para polling de capturas. | |

### 🧰 Pacotes de Depuração de Falhas

| | |
|---|---|
| **Gerados automaticamente**<br>Criados em qualquer falha de passo de automação ou de teste. | **Tudo em um pacote**<br>Captura de tela, logcat (últimas 100 linhas), estado do dispositivo, XML da hierarquia da UI, ações recentes e propriedades do dispositivo. |
| **Análise com IA**<br>Envia o pacote para obter uma hipótese de causa raiz e correções sugeridas. | **Compartilhável**<br>Links por tempo limitado para compartilhar pacotes com a equipe; download em ZIP, retenção de 30 dias. |

### 🔬 Integração CI/CD

| | |
|---|---|
| **Plugin pytest do droidlink**<br>Fixtures `device` e `device_pool`, `pip install droidlink`. | **Captura automática em falhas**<br>Cada teste que falha captura o estado do dispositivo. |
| **Rastreamento de builds**<br>Resultados por teste vinculados ao ciclo de vida de um build. | **Seguro em paralelo**<br>Bloqueio de dispositivos para executores de testes em paralelo, com template de GitHub Actions incluído. |

### 🖥️ Controle Remoto e Agentes de IA

| | |
|---|---|
| **ADB remoto e arquivos**<br>Shell ADB no navegador com histórico e predefinições, mais um explorador de arquivos com busca. | **Agentes de IA Prompture**<br>Cada dispositivo se torna um agente conversacional: multi-provedor (Claude, GPT, Groq, Ollama, Google), modelo + memória por dispositivo, uso direto de ferramentas e rastreamento de tokens/custos. |
| **Extensões**<br>Um catálogo integrado e um registro remoto, com um gerenciador de extensões instaladas. | |

---

## 🏗️ Arquitetura

```
                        ┌────────────────────┐
                        │   React Frontend   │  Dashboard, visual editors,
                        │   (Vite/Tailwind)  │  live streams — SSE + REST
                        └─────────┬──────────┘
                                  │  REST API + SSE
                        ┌─────────┴──────────┐
                        │   Flask Backend    │  Merges ADB + agent devices
              ┌─────────┤   (31 mixins)      ├─────────┐  into one fleet
              │         └─────────┬──────────┘         │
      DynamoDB│ / S3              │ ADB / HTTP          │ REST
              ▼                   ▼                     ▼
     ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐
     │  Persistence   │  │  Android Agent  │  │ pytest+droidlink │
     │  + File store  │  │  (Kotlin app)   │  │  scripts + CI    │
     └────────────────┘  │  HTTP :9800     │  └──────────────────┘
                         │  UDP  :9801     │
                         └─────────────────┘
```

1. **O agente Android** roda em cada dispositivo — serve uma API HTTP na porta 9800 e reporta métricas ao backend
2. **O backend Flask** funde os dispositivos conectados via ADB e os registrados pelo agente em uma frota unificada
3. **O frontend React** assina SSE para atualizações em tempo real e usa REST para todo o resto
4. **A biblioteca droidlink** conecta diretamente aos dispositivos para scripts e CI — USB via redirecionamento de portas ADB, WiFi via descoberta automática
5. **O plugin pytest** aloca dispositivos, executa testes e reporta os resultados ao painel

**[Arquitetura completa →](ARCHITECTURE.md)** · **[Contrato da frota →](FLEET_CONTRACT.md)**

---

## 🗺️ Roadmap

- [x] Gerenciamento de frota — métricas em tempo real, agregação de saúde, grupos de dispositivos, comparação
- [x] Linguagem de Consulta da Frota — filtragem estilo SQL, predefinições, consulta → ação em massa, exportação CSV
- [x] Motor de automação — 14 tipos de passos, editor de arrastar e soltar, gravação, agendamento, compartilhamento
- [x] Construtor de workflows — canvas visual de automação baseado em nós
- [x] Automação com IA — gerar / refinar / explicar a partir de linguagem natural
- [x] Autocura — a IA relocaliza alvos de UI movidos e tenta novamente
- [x] Regressão visual — diff SSIM, análise com IA, mascaramento de regiões, baselines por modelo
- [x] Streaming ao vivo — MJPEG, qualidade adaptativa, sobreposição de toque, gravação de sessões
- [x] Pacotes de depuração — captura automática, causa raiz com IA, links compartilháveis
- [x] CI/CD — plugin pytest do droidlink, bloqueio de dispositivos em paralelo, template de GitHub Actions
- [x] Agentes de IA Prompture — agentes conversacionais por dispositivo com uso de ferramentas
- [x] ADB remoto e explorador de arquivos
- [x] Frota de agentes — registro, fila de aprovação, descoberta em LAN, fila de comandos, atualizações em etapas
- [x] Extensões — catálogo integrado + registro remoto
- [x] Aparência — temas claro / escuro / sistema, cores de destaque, marca branca
- [ ] API pública + servidor MCP — chaves `dk_` com escopo, OpenAPI automático, CLI `devicekit`

Histórico completo e próximas fases: **[ROADMAP.md](../ROADMAP.md)**

---

## 📖 Documentação

A suíte completa de documentação vive em **[`docs/`](README.md)** — comece por lá
para ver o mapa. Os destaques:

| Guia | Descrição |
| --- | --- |
| [Índice da Documentação](README.md) | O mapa — cada documento, agrupado pelo que responde |
| [Primeiros Passos](getting-started.md) | Instalar → rodar o backend → conectar um dispositivo → primeira automação |
| [Arquitetura](ARCHITECTURE.md) | Os quatro componentes e como se comunicam (leia primeiro) |
| [Contrato da Frota](FLEET_CONTRACT.md) | Protocolo agente ↔ backend: registro/heartbeat/estado/comandos, HMAC, capacidades |
| [Guia de Extensões](extensions/guide.md) | Crie uma extensão — pontos de contribuição, SDK, manifesto, tutorial |
| [Agente de IA](ai-agent.md) | Agentes de dispositivo com Prompture: ferramentas, portão de confirmação, modos de sessão |
| [droidlink](droidlink.md) | Controle uma frota gerenciada pelo DeviceKit a partir do Python (`pip install droidlink`) |
| [Configuração de CI/CD](ci-setup.md) | Integração com GitHub Actions, fixtures de dispositivos, testes em paralelo |
| [Servidor MCP](mcp-server.md) | Superfície do Model Context Protocol para agentes de IA |
| [Roadmap](../ROADMAP.md) | Histórico completo de desenvolvimento e próximas fases |

---

## 🧱 Stack Tecnológico

| Camada | Tecnologia |
|-------|------------|
| Backend | Python 3.11, Flask, 31 mixins combináveis, SSE |
| Frontend | React 18, Vite, Tailwind CSS |
| Agente | Kotlin (Android), serviço em segundo plano, servidor HTTP, descoberta UDP, serviço de acessibilidade |
| Biblioteca | `droidlink` (PyPI) — CLI + plugin pytest |
| Controle de dispositivos | ADB, UIAutomator2, Chrome DevTools Protocol |
| Persistência | DynamoDB (local ou AWS), armazenamento de arquivos S3 |
| Streaming | Proxy MJPEG com qualidade adaptativa |
| IA | Prompture (multi-provedor: Claude, GPT, Groq, Ollama, Google) |

---

## ⚙️ Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|---------|-------------|
| `API_PORT` | `5050` | Porta da API Flask |
| `API_HOST` | `0.0.0.0` | Endereço de escuta do Flask |
| `API_KEY` | – | Chave de API para autenticação dos endpoints (desativada se não definida) |
| `AGENT_TOKENS` | – | Tokens separados por vírgula para autenticação dos agentes |
| `AWS_ACCESS_KEY_ID` | – | Credenciais da AWS para DynamoDB/S3 |
| `AWS_SECRET_ACCESS_KEY` | – | Credenciais da AWS |
| `AWS_REGION` | `us-east-1` | Região da AWS |
| `DYNAMODB_TABLE_PREFIX` | `devicekit_` | Prefixo do nome das tabelas |
| `DYNAMODB_ENDPOINT` | – | URL do DynamoDB local (ex.: `http://localhost:8321`) |
| `CORS_ORIGINS` | `*` | Origens CORS permitidas |
| `DEVICE_IDS` | – | Seriais de dispositivos separados por vírgula |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `DEBUG_MODE` | `false` | Ativa o modo debug do Flask |
| `PROMPTURE_DEFAULT_MODEL` | – | Modelo de IA padrão para os agentes de dispositivo |

---

## ✅ Compatibilidade

| Componente | Requisitos |
| --- | --- |
| **Backend** | Python 3.11+ |
| **Frontend** | Node 18+, qualquer navegador moderno |
| **Dispositivos Android** | Android 7+ (API 24+), depuração USB ativada |
| **App do Agente** | Android 8+ (API 26+) para o conjunto completo de funcionalidades |
| **Docker** | Docker 20+, docker-compose v2 |
| **SO** | Windows, macOS, Linux |

---

## 🛠️ Solução de Problemas

**O dispositivo não aparece?** — Verifique se a depuração USB está ativada, execute `adb devices` para
confirmar que o ADB o vê, e confira se `adb` está no seu PATH.

**Agente travado em "Conectando…"?** — O agente não consegue alcançar o backend. Por USB,
execute `adb reverse tcp:5050 tcp:5050`; por WiFi, defina a URL do backend nas
configurações do agente com o IP da sua máquina.

**A transmissão não carrega?** — O app do agente precisa estar em execução; certifique-se de que a porta 9800 esteja
acessível (`adb forward tcp:9800 tcp:9800` por USB) e tente uma predefinição de qualidade menor.

**Problemas com Docker?** — Execute `docker-compose logs`, certifique-se de que as portas 3847 / 5890 / 8321
estejam livres, e verifique se o `.env` tem credenciais válidas da AWS (ou use o DynamoDB Local).

---

## 🤝 Contribuir

Contribuições são bem-vindas!

```
fork → feature branch → commit → push → pull request
```

1. **Reporte bugs** — [GitHub Issues](https://github.com/jhd3197/DeviceKit/issues)
2. **Solicite funcionalidades** — [GitHub Discussions](https://github.com/jhd3197/DeviceKit/discussions)
3. **Envie PRs** — Correções de bugs, novos tipos de passos, melhorias no frontend
4. **Melhore a documentação** — Todos os arquivos `.md` do repositório

---

## 💛 Apoie o DeviceKit

O DeviceKit é livre e de código aberto. Se ele economiza seu tempo, você pode ajudar a mantê-lo funcionando:

- ⭐ [Dê uma estrela no repositório](https://github.com/jhd3197/DeviceKit) — não custa nada e ajuda muito
- 💖 [GitHub Sponsors](https://github.com/sponsors/jhd3197)
- ☕ [Buy Me a Coffee](https://buymeacoffee.com/jhd3197)

### 💎 Criptomoedas

| | Ativo | Rede | Endereço |
|:---:|---|---|---|
| <img src="images/funding/usdt-trc20.png" width="110" alt="Código QR do endereço de doação USDT TRC-20" /> | **USDT** | **TRC-20** · Tron | `TTiCtqLauF1iSW2YGB3b78KmRxRqoLCgeL` |
| <img src="images/funding/usdt-erc20.png" width="110" alt="Código QR do endereço de doação USDT e ETH ERC-20" /> | **USDT / ETH** | **ERC-20** · Ethereum | `0xD13D5355Fa214e8317fea2ff192a065BaeC13527` |
| <img src="images/funding/btc.png" width="110" alt="Código QR do endereço de doação de Bitcoin" /> | **BTC** | **Bitcoin** | `bc1qatx67n3qxdvuv3arc9j8aytk34f22g02k9c7vr` |
| <img src="images/funding/sol.png" width="110" alt="Código QR do endereço de doação de Solana" /> | **SOL** | **Solana** | `AWXzqtBEgUfteHPQtDegsZ6D5y57M3GGdKPD8rR7h6xu` |

TRC-20 tem as taxas mais baixas — normalmente menos de um dólar — então é
a opção mais amigável para uma doação pequena. O gas de ERC-20 pode custar mais
do que a própria doação.

<sub>Os códigos QR são gerados localmente pelo [`scripts/generate-funding-qr.mjs`](../scripts/generate-funding-qr.mjs), que valida a soma de verificação de cada endereço antes de codificá-lo.</sub>

---

## 🔭 Projetos Relacionados

**[ServerKit](https://github.com/jhd3197/ServerKit)** — Um painel de controle de servidores leve e moderno
para aplicações web, bancos de dados, Docker e segurança — infraestrutura auto-hospedada
sem a complexidade do Kubernetes.

**[Faro](https://github.com/jhd3197/faro)** — Um cliente de desktop moderno para SFTP, FTP, SSH e armazenamento compatível com S3, do mesmo autor. Salve um servidor uma vez e depois navegue pelos arquivos em uma visão de painel duplo e abra um terminal na mesma sessão SSH — além de transferências com arrastar e soltar, sincronização de diretórios em um sentido e edição in loco. Ele até tem um **Agent Bridge** que permite ao Claude Code (ou qualquer agente MCP) executar comandos em uma máquina através da sua sessão autenticada, com aprovação por comando e sem compartilhar credenciais.

> O DeviceKit gerencia sua frota Android pelo navegador; o Faro é o companheiro de desktop para transferências de arquivos, shells e trabalho pontual em todas as suas máquinas. [Baixe uma versão →](https://github.com/jhd3197/faro/releases/latest)

**[LocalKit](https://github.com/jhd3197/LocalKit)** — Crie sites WordPress locais com um clique. Cada site roda como seu próprio projeto isolado de Docker Compose, e você pode enviar código ou enviar/puxar bancos de dados diretamente para o seu servidor ServerKit através da extensão `serverkit-localkit`.

---

## 💬 Comunidade

[![Discord](https://img.shields.io/badge/Discord-Junte--se-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/ZKk6tkCQfG)

Entre no Discord para fazer perguntas, compartilhar feedback ou obter ajuda com a sua configuração.

---

## 📄 Licença

Este projeto está licenciado sob a **Licença MIT**. Consulte [LICENSE](../LICENSE) para
todos os detalhes.

**Android** é uma marca registrada da Google LLC. Este projeto **não é afiliado,
endossado ou patrocinado pela Google LLC.**

---

<div align="center">

**DeviceKit** — Um painel para toda a sua frota Android.

[Reportar um Bug](https://github.com/jhd3197/DeviceKit/issues) · [Solicitar uma Funcionalidade](https://github.com/jhd3197/DeviceKit/discussions)

Feito com ❤️ por [Juan Denis](https://juandenis.com)

</div>
