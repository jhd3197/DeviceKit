<div align="center">

<img width="130" alt="DeviceKit" src="assets/logo.svg" />

# DeviceKit

**统一的 Android 设备集群与测试自动化平台。**

从一个仪表盘控制整个 Android 设备集群——运行自动化任务、实时投屏、
捕捉视觉回归，并借助 AI 驱动的分析调试失败。

[English](../README.md) | [Español](README.es.md) | 中文版 | [Português](README.pt.md)

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

[快速开始](#-快速开始) · [截图](#-截图) · [功能特性](#-功能特性) · [架构](#-架构) · [路线图](#-路线图) · [文档](#-文档) · [贡献](#-贡献) · [Discord](#-社区)

</div>

---

<p align="center">
  <img alt="DeviceKit 集群总览" width="100%" src="screenshots/dashboard.png" />
</p>

---

## 为什么选择 DeviceKit？

用 Android 设备做测试通常意味着在多个终端之间来回敲 ADB 命令、
手动记录哪台设备在跑什么，出问题时还要翻日志。DeviceKit 采用了不同的思路：一个
统一的平台，自动发现你的设备，让你通过网页
仪表盘控制它们，并把繁琐的部分自动化。

整个系统由**四个协同工作的组件**构成——一个管理设备状态并编排操作的 Python/Flask
后端，一个用于仪表盘和可视化编辑器的 React 前端，一个运行
在每台设备上、上报指标并接收命令的 Kotlin 代理应用，以及一个用于脚本和
CI 流水线的 Python 库
（[`pip install droidlink`](https://pypi.org/project/droidlink/)）。开箱即用的 **AI 驱动自动化**：用自然语言描述你的需求，
DeviceKit 就会生成可执行的步骤；当 UI 元素
在应用版本之间移动时，自愈重试会重新找到它们；当测试失败时，
调试包会把截图、日志、UI 层级和设备状态打包成一次
下载——并可选地进行 AI 根因分析。

---

## 🚀 快速开始

> ⏱️ 插上设备，它会自动出现。

### 方式一：Docker（推荐）

```bash
git clone https://github.com/jhd3197/DeviceKit.git
cd DeviceKit
cp .env.example .env
docker-compose up
```

| 服务 | URL |
|---------|-----|
| 前端 | http://localhost:3847 |
| API | http://localhost:5890 |
| DynamoDB（本地） | http://localhost:8321 |

### 方式二：手动安装

```bash
# 后端
cd backend
pip install -r requirements.txt
python app.py                # API 位于 http://localhost:5050

# 前端（另开一个终端）
cd frontend
npm install
npm run dev                  # 开发服务器位于 http://localhost:5173
```

### 连接设备

```bash
# USB ：直接插入设备即可（已启用 ADB / USB 调试）
# WiFi：安装代理 APK —— 同一网络下自动发现后端
```

**需要代理应用？** 后端通过 `GET /agent/apk` 提供下载，也可以从
`agent-android/` 自行构建。

### 用 Python 驱动

```python
# pip install droidlink —— 同一个集群，用脚本或 CI 驱动
def test_login_flow(device):
    device.app.start("com.example.app")
    device.input.tap(540, 1200)
    device.input.type_text("user@test.com")
    assert device.screen.capture() is not None
```

---

<!-- DK:SHOTS:START -->
## 📸 截图

|                            集群总览                            |                            节点控制                            |
| :------------------------------------------------------------: | :------------------------------------------------------------: |
|          ![集群总览](screenshots/dashboard.png)           |         ![节点控制](screenshots/node-detail.png)          |
|   _实时集群指标、KPI 卡片、健康度分布、进行中的运行、最近失败以及 FQL 查询栏_   |   _单设备实时投屏、实时诊断仪表、ADB shell、指标历史和宏快捷操作_   |

|                           自动化运行                            |                           自动化编辑器                           |
| :-------------------------------------------------------------: | :--------------------------------------------------------------: |
|       ![自动化运行](screenshots/automation-run.png)        |      ![自动化编辑器](screenshots/automation-editor.png)       |
|   _逐步实时结果、自愈（原始 → 修复对比）、视觉回归断言，以及失败时自动生成并附带 AI 分析的调试包_   |   _步骤构建器，支持重排 + 逐步 AI 优化、"用 AI 生成"、标签和视觉基线_   |

|                          工作流构建器                           |                            自动化列表                            |
| :-------------------------------------------------------------: | :--------------------------------------------------------------: |
|         ![工作流构建器](screenshots/workflow.png)          |         ![自动化列表](screenshots/automations.png)          |
|   _基于节点的可视化自动化画布——串联触发器、点击、等待、断言和分支_   |   _所有自动化任务及其步骤、标签、运行/定时/分享/克隆控制，以及最近运行动态_   |

|                           设备对比                            |                            指标监控                            |
| :-----------------------------------------------------------: | :------------------------------------------------------------: |
|           ![设备对比](screenshots/compare.png)            |           ![指标监控](screenshots/monitor.png)            |
|   _最多 4 台设备并排展示，叠加同步的历史趋势曲线和每台设备的仪表盘_   |   _跨设备指标图表，可选时间范围，另有基于通知总线的阈值告警规则_   |

<details>
<summary><strong>查看全部截图</strong></summary>

<br>

|                            设备分组                            |                           Pipeline / CI                           |
| :------------------------------------------------------------: | :---------------------------------------------------------------: |
|            ![设备分组](screenshots/groups.png)            |            ![Pipeline / CI](screenshots/pipeline.png)            |
|   _带标签和颜色编码的分组，支持批量操作——重启、锁定、安装、运行自动化_   |   _构建列表、逐测试结果，以及来自 droidlink pytest 插件的失败截图_   |

|                             配置档案                             |                            远程 ADB                             |
| :--------------------------------------------------------------: | :-------------------------------------------------------------: |
|              ![配置档案](screenshots/profiles.png)              |              ![远程 ADB](screenshots/remote-adb.png)              |
|   _每台设备的 AI 人格和多供应商模型配置（Claude、GPT、Groq、Ollama、Google）_   |   _浏览器内 ADB shell，带命令历史和预设，另有文件浏览器_   |

|                             设备注册                             |                            命令历史                             |
| :--------------------------------------------------------------: | :-------------------------------------------------------------: |
|             ![设备注册](screenshots/enrollment.png)             |          ![命令历史](screenshots/command-history.png)          |
|   _代理配对与审批队列，支持新设备的局域网自动发现_   |   _全集群范围的命令时间线，记录每条命令的状态和执行者_   |

|                              任务                               |                              通知                              |
| :-------------------------------------------------------------: | :------------------------------------------------------------: |
|                ![任务](screenshots/jobs.png)                 |            ![通知](screenshots/notifications.png)             |
|   _排队中、运行中和已完成的后台任务——自动化、批量安装、基线捕获_   |   _入门引导 + 告警动态，支持多种投递渠道（webhook、Slack、邮件）_   |

|                              扩展                               |                              设置                               |
| :-------------------------------------------------------------: | :-------------------------------------------------------------: |
|             ![扩展](screenshots/extensions.png)              |               ![设置](screenshots/settings.png)                |
|   _已安装扩展以及可浏览、一键安装的远程注册表_   |   _实例标识、API 访问、两步验证、AI/投屏/调试包配置，以及外观/白标品牌定制_   |

</details>
<!-- DK:SHOTS:END -->

---

## 🎯 功能特性

### 🛰️ 集群管理

| | |
|---|---|
| **实时指标**<br>每台设备的 CPU、内存、电量、温度和存储，实时推送。 | **集群健康度**<br>整个集群的健康 / 警告 / 严重聚合计数。 |
| **设备分组**<br>标签、颜色编码，以及对任意选择的批量操作。 | **设备对比**<br>最多 4 台设备并排展示，实时图表同步联动。 |
| **自动接入**<br>新设备一连上就会自动上报。 | **命令历史**<br>全集群范围的操作审计时间线。 |

### 🔎 集群查询语言（FQL）

| | |
|---|---|
| **类 SQL 过滤**<br>`android_version < 13 AND battery > 20 AND status = 'idle'` | **自动补全 + 预设**<br>查询栏字段补全，内置常用预设（低电量、离线、系统过旧）。 |
| **已保存查询**<br>保存你常用的过滤器。 | **查询 → 批量操作**<br>把查询结果直接接到重启、锁定、安装 APK 或运行自动化上。 |
| **CSV 导出**<br>把任何查询结果带走。 | |

### 🤖 自动化引擎

| | |
|---|---|
| **14 种步骤类型**<br>点击、滑动、输入、按键、打开/关闭应用、推送/拉取文件、等待、断言、截图等等。 | **拖拽编辑器**<br>可视化步骤构建器，带预览和实时设备上下文。 |
| **工作流构建器**<br>基于节点的画布，支持分支和多步骤自动化。 | **录制自动化**<br>在设备上点击、滑动，即可生成对应步骤。 |
| **定时与分享**<br>按间隔运行，支持暂停/恢复；可克隆，支持 JSON 导出导入。 | |

### ✨ AI 驱动的自动化

| | |
|---|---|
| **生成**<br>把自然语言描述变成可执行的自动化步骤。 | **优化**<br>用对话式指令修改单个步骤。 |
| **解释**<br>用自然语言总结任何自动化任务的作用。 | **自愈**<br>当 UI 元素在应用版本之间移动时，AI 会自动重新定位目标并重试。 |

### 🖼️ 视觉回归测试

| | |
|---|---|
| **截图断言**<br>`screenshot_assert` 步骤与已存储的基线进行比对。 | **SSIM 差异引擎**<br>像素级差异对比，阈值可配置。 |
| **AI 差异分析**<br>区分有意义的 UI 变化和渲染噪声。 | **区域遮罩**<br>排除动态内容（时钟、广告、时间戳）。 |
| **按机型维护基线**<br>按设备型号和版本跟踪基线，输出通过 / 失败 / 待复核报告。 | |

### 📺 设备实时投屏

| | |
|---|---|
| **MJPEG 流媒体**<br>真正的实时视频，而非截图轮询，画质自适应（5 / 15 / 30 fps）。 | **多人观看**<br>观看人数徽章和共享会话。 |
| **触控叠加层**<br>涟漪动画展示每一次交互。 | **会话录制**<br>逐帧回放，带事件标记。 |
| **延迟指示器**<br>绿（<100 ms）、黄（<300 ms）、红（>300 ms），可自动降级为截图轮询。 | |

### 🧰 失败调试包

| | |
|---|---|
| **自动生成**<br>任何自动化步骤或测试失败时自动创建。 | **一包打尽**<br>截图、logcat（最后 100 行）、设备状态、UI 层级 XML、最近操作和设备属性。 |
| **AI 分析**<br>将调试包发送给 AI，获得根因假设和修复建议。 | **可分享**<br>限时链接，可与队友分享调试包；ZIP 下载，保留 30 天。 |

### 🔬 CI/CD 集成

| | |
|---|---|
| **droidlink pytest 插件**<br>`device` 和 `device_pool` fixtures，`pip install droidlink`。 | **失败自动截图**<br>每个失败的测试都会捕获设备状态。 |
| **构建跟踪**<br>逐测试结果与构建生命周期关联。 | **并行安全**<br>为并行测试运行器提供设备锁定，并附带 GitHub Actions 模板。 |

### 🖥️ 远程控制与 AI 代理

| | |
|---|---|
| **远程 ADB 与文件**<br>浏览器内 ADB shell，带历史和预设，另有可搜索的文件浏览器。 | **Prompture AI 代理**<br>每台设备都能变成对话式代理：多供应商（Claude、GPT、Groq、Ollama、Google）、按设备配置模型 + 记忆、直接调用工具、token/成本跟踪。 |
| **扩展**<br>内置目录 + 远程注册表，并配有已安装扩展管理器。 | |

---

## 🏗️ 架构

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

1. **Android 代理**运行在每台设备上——在 9800 端口提供 HTTP API，并向后端上报指标
2. **Flask 后端**将 ADB 连接的设备与代理注册的设备合并为统一集群
3. **React 前端**通过 SSE 订阅实时更新，其余均走 REST
4. **droidlink 库**直接连接设备，用于脚本和 CI——USB 走 ADB 端口转发，WiFi 走自动发现
5. **pytest 插件**分配设备、运行测试，并把结果回传到仪表盘

**[完整架构 →](ARCHITECTURE.md)** · **[集群协议 →](FLEET_CONTRACT.md)**

---

## 🗺️ 路线图

- [x] 集群管理——实时指标、健康度聚合、设备分组、设备对比
- [x] 集群查询语言——类 SQL 过滤、预设、查询 → 批量操作、CSV 导出
- [x] 自动化引擎——14 种步骤类型、拖拽编辑器、录制、定时、分享
- [x] 工作流构建器——基于节点的可视化自动化画布
- [x] AI 自动化——自然语言生成 / 优化 / 解释
- [x] 自愈——AI 重新定位移动过的 UI 目标并重试
- [x] 视觉回归——SSIM 差异、AI 分析、区域遮罩、按机型维护基线
- [x] 实时投屏——MJPEG、画质自适应、触控叠加层、会话录制
- [x] 调试包——自动捕获、AI 根因分析、可分享链接
- [x] CI/CD——droidlink pytest 插件、并行设备锁定、GitHub Actions 模板
- [x] Prompture AI 代理——按设备的对话式代理，支持工具调用
- [x] 远程 ADB 与文件浏览器
- [x] 代理集群——注册、审批队列、局域网发现、命令队列、分批更新
- [x] 扩展——内置目录 + 远程注册表
- [x] 外观——浅色 / 深色 / 跟随系统主题、强调色、白标品牌定制
- [ ] 公共 API + MCP 服务器——带作用域的 `dk_` 密钥、自动 OpenAPI、`devicekit` CLI

完整历史与即将推出的阶段：**[ROADMAP.md](../ROADMAP.md)**

---

## 📖 文档

完整的文档套件位于 **[`docs/`](README.md)**——从那里
查看全景。重点文档：

| 指南 | 描述 |
| --- | --- |
| [文档索引](README.md) | 全景图——每篇文档按解答的问题分组 |
| [快速上手](getting-started.md) | 安装 → 启动后端 → 连接设备 → 第一个自动化 |
| [架构](ARCHITECTURE.md) | 四个组件及其通信方式（建议先读） |
| [集群协议](FLEET_CONTRACT.md) | 代理 ↔ 后端协议：注册/心跳/状态/命令、HMAC、能力 |
| [扩展指南](extensions/guide.md) | 构建扩展——贡献点、SDK、清单、教程 |
| [AI 代理](ai-agent.md) | 基于 Prompture 的设备代理：工具、确认门、会话模式 |
| [droidlink](droidlink.md) | 用 Python 驱动 DeviceKit 管理的集群（`pip install droidlink`） |
| [CI/CD 配置](ci-setup.md) | GitHub Actions 集成、设备 fixtures、并行测试 |
| [MCP 服务器](mcp-server.md) | 面向 AI 代理的 Model Context Protocol 接口 |
| [路线图](../ROADMAP.md) | 完整开发历史与即将推出的阶段 |

---

## 🧱 技术栈

| 层级 | 技术 |
|-------|------------|
| 后端 | Python 3.11、Flask、31 个可组合 mixin、SSE |
| 前端 | React 18、Vite、Tailwind CSS |
| 代理 | Kotlin（Android）、后台服务、HTTP 服务器、UDP 发现、无障碍服务 |
| 库 | `droidlink`（PyPI）—— CLI + pytest 插件 |
| 设备控制 | ADB、UIAutomator2、Chrome DevTools Protocol |
| 持久化 | DynamoDB（本地或 AWS）、S3 文件存储 |
| 流媒体 | MJPEG 代理，画质自适应 |
| AI | Prompture（多供应商：Claude、GPT、Groq、Ollama、Google） |

---

## ⚙️ 环境变量

| 变量 | 默认值 | 描述 |
|----------|---------|-------------|
| `API_PORT` | `5050` | Flask API 端口 |
| `API_HOST` | `0.0.0.0` | Flask 绑定地址 |
| `API_KEY` | – | 用于端点认证的 API 密钥（未设置则禁用） |
| `AGENT_TOKENS` | – | 逗号分隔的代理认证令牌 |
| `AWS_ACCESS_KEY_ID` | – | DynamoDB/S3 的 AWS 凭证 |
| `AWS_SECRET_ACCESS_KEY` | – | AWS 凭证 |
| `AWS_REGION` | `us-east-1` | AWS 区域 |
| `DYNAMODB_TABLE_PREFIX` | `devicekit_` | 表名前缀 |
| `DYNAMODB_ENDPOINT` | – | 本地 DynamoDB 地址（如 `http://localhost:8321`） |
| `CORS_ORIGINS` | `*` | 允许的 CORS 来源 |
| `DEVICE_IDS` | – | 逗号分隔的设备序列号 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DEBUG_MODE` | `false` | 启用 Flask 调试模式 |
| `PROMPTURE_DEFAULT_MODEL` | – | 设备代理的默认 AI 模型 |

---

## ✅ 兼容性

| 组件 | 要求 |
| --- | --- |
| **后端** | Python 3.11+ |
| **前端** | Node 18+，任意现代浏览器 |
| **Android 设备** | Android 7+（API 24+），已启用 USB 调试 |
| **代理应用** | Android 8+（API 26+）以获得完整功能 |
| **Docker** | Docker 20+，docker-compose v2 |
| **操作系统** | Windows、macOS、Linux |

---

## 🛠️ 故障排除

**设备没有出现？** —— 确认 USB 调试已开启，运行 `adb devices`
确认 ADB 能看到设备，并检查 `adb` 是否在你的 PATH 中。

**代理卡在"连接中…"？** —— 代理连不上后端。USB 连接时
运行 `adb reverse tcp:5050 tcp:5050`；WiFi 连接时在代理
设置中把后端地址改为你机器的 IP。

**投屏加载不出来？** —— 代理应用必须在运行；确保 9800 端口
可达（USB 时执行 `adb forward tcp:9800 tcp:9800`），并尝试更低画质的预设。

**Docker 出问题？** —— 运行 `docker-compose logs`，确保 3847 / 5890 / 8321
端口未被占用，并检查 `.env` 中的 AWS 凭证是否有效（或使用 DynamoDB Local）。

---

## 🤝 贡献

欢迎贡献！

```
fork → feature branch → commit → push → pull request
```

1. **报告 Bug** —— [GitHub Issues](https://github.com/jhd3197/DeviceKit/issues)
2. **提出功能需求** —— [GitHub Discussions](https://github.com/jhd3197/DeviceKit/discussions)
3. **提交 PR** —— Bug 修复、新的步骤类型、前端改进
4. **完善文档** —— 仓库中的所有 `.md` 文件

---

## 💛 支持 DeviceKit

DeviceKit 是自由开源软件。如果它帮你节省了时间，你可以帮助它继续前行：

- ⭐ [给仓库点颗星](https://github.com/jhd3197/DeviceKit) —— 不花一分钱，帮助却很大
- 💖 [GitHub Sponsors](https://github.com/sponsors/jhd3197)
- ☕ [Buy Me a Coffee](https://buymeacoffee.com/jhd3197)

### 💎 加密货币

| | 资产 | 网络 | 地址 |
|:---:|---|---|---|
| <img src="images/funding/usdt-trc20.png" width="110" alt="USDT TRC-20 捐赠地址二维码" /> | **USDT** | **TRC-20** · Tron | `TTiCtqLauF1iSW2YGB3b78KmRxRqoLCgeL` |
| <img src="images/funding/usdt-erc20.png" width="110" alt="USDT 与 ETH ERC-20 捐赠地址二维码" /> | **USDT / ETH** | **ERC-20** · Ethereum | `0xD13D5355Fa214e8317fea2ff192a065BaeC13527` |
| <img src="images/funding/btc.png" width="110" alt="比特币捐赠地址二维码" /> | **BTC** | **Bitcoin** | `bc1qatx67n3qxdvuv3arc9j8aytk34f22g02k9c7vr` |
| <img src="images/funding/sol.png" width="110" alt="Solana 捐赠地址二维码" /> | **SOL** | **Solana** | `AWXzqtBEgUfteHPQtDegsZ6D5y57M3GGdKPD8rR7h6xu` |

TRC-20 手续费最低——通常不到一美元——是小额捐赠最友好的
选择。ERC-20 的 gas 费可能比捐赠金额本身还高。

<sub>二维码由 [`scripts/generate-funding-qr.mjs`](../scripts/generate-funding-qr.mjs) 在本地生成，编码前会对每个地址进行校验和验证。</sub>

---

## 🔭 相关项目

**[ServerKit](https://github.com/jhd3197/ServerKit)** —— 一个轻量、现代的服务器控制面板，
管理 Web 应用、数据库、Docker 和安全——自托管基础设施，
无需 Kubernetes 的复杂度。

**[Faro](https://github.com/jhd3197/faro)** —— 同一作者出品的现代桌面客户端，支持 SFTP、FTP、SSH 和 S3 兼容存储。保存一次服务器，即可在双栏视图中浏览文件，并在同一 SSH 会话上打开终端——还支持拖拽传输、单向目录同步和就地编辑。它甚至有一个 **Agent Bridge**，让 Claude Code（或任何 MCP 代理）通过你已认证的会话在机器上执行命令，逐命令审批，无需共享凭证。

> DeviceKit 在浏览器中管理你的 Android 集群；Faro 则是桌面伴侣，负责所有机器上的文件传输、shell 和临时操作。[获取构建版本 →](https://github.com/jhd3197/faro/releases/latest)

**[LocalKit](https://github.com/jhd3197/LocalKit)** —— 一键搭建本地 WordPress 站点。每个站点都作为独立的 Docker Compose 项目运行，还可以通过 `serverkit-localkit` 扩展把代码推送、数据库推拉直达你的 ServerKit 服务器。

---

## 💬 社区

[![Discord](https://img.shields.io/badge/Discord-加入我们-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/ZKk6tkCQfG)

加入 Discord 提问、分享反馈，或获取配置方面的帮助。

---

## 📄 许可证

本项目采用 **MIT 许可证**授权。详见 [LICENSE](../LICENSE)。

**Android** 是 Google LLC 的商标。本项目**与 Google LLC 无任何隶属关系，
也未获得其认可或赞助。**

---

<div align="center">

**DeviceKit** —— 一个仪表盘，管理你的整个 Android 集群。

[报告 Bug](https://github.com/jhd3197/DeviceKit/issues) · [功能建议](https://github.com/jhd3197/DeviceKit/discussions)

由 [Juan Denis](https://juandenis.com) 用 ❤️ 制作

</div>
