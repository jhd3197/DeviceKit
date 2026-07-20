<div align="center">

<img width="130" alt="DeviceKit" src="assets/logo.svg" />

# DeviceKit

**Una plataforma unificada de flota de dispositivos Android y automatización de pruebas.**

Controla una flota de dispositivos Android desde un solo panel — ejecuta automatizaciones, transmite
pantallas en tiempo real, detecta regresiones visuales y depura fallos con
análisis asistido por IA.

[English](../README.md) | Español | [中文版](README.zh-CN.md) | [Português](README.pt.md)

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

[Inicio Rápido](#-inicio-rápido) · [Capturas](#-capturas-de-pantalla) · [Funcionalidades](#-funcionalidades) · [Arquitectura](#-arquitectura) · [Hoja de Ruta](#-hoja-de-ruta) · [Documentación](#-documentación) · [Contribuir](#-contribuir) · [Discord](#-comunidad)

</div>

---

<p align="center">
  <img alt="Vista general de la flota de DeviceKit" width="100%" src="screenshots/dashboard.png" />
</p>

---

## ¿Por qué DeviceKit?

Gestionar dispositivos Android para pruebas suele significar hacer malabares con comandos ADB entre
terminales, llevar la cuenta a mano de qué dispositivo ejecuta qué, y rebuscar en los
logs cuando algo se rompe. DeviceKit propone otro enfoque: una única
plataforma que descubre tus dispositivos, te permite controlarlos desde un panel
web y automatiza las partes tediosas.

Todo son **cuatro componentes trabajando juntos** — un backend en Python/Flask
que gestiona el estado de los dispositivos y orquesta las acciones, un frontend en React para el
panel y los editores visuales, una app agente en Kotlin que se ejecuta en cada dispositivo para
reportar métricas y aceptar comandos, y una librería de Python
([`pip install droidlink`](https://pypi.org/project/droidlink/)) para scripts y
pipelines de CI. Obtienes **automatización asistida por IA** desde el primer momento: describe lo que
quieres en lenguaje natural y DeviceKit genera pasos ejecutables; cuando los elementos de la UI
se mueven entre versiones de la app, los reintentos auto-recuperables los vuelven a encontrar; cuando las pruebas fallan,
los paquetes de depuración reúnen capturas, logs, jerarquía de UI y estado del dispositivo en una sola
descarga — con análisis opcional de causa raíz por IA.

---

## 🚀 Inicio Rápido

> ⏱️ Enchufa un dispositivo y aparece automáticamente.

### Opción 1: Docker (Recomendada)

```bash
git clone https://github.com/jhd3197/DeviceKit.git
cd DeviceKit
cp .env.example .env
docker-compose up
```

| Servicio | URL |
|---------|-----|
| Frontend | http://localhost:3847 |
| API | http://localhost:5890 |
| DynamoDB (local) | http://localhost:8321 |

### Opción 2: Instalación Manual

```bash
# Backend
cd backend
pip install -r requirements.txt
python app.py                # API en http://localhost:5050

# Frontend (en una segunda terminal)
cd frontend
npm install
npm run dev                  # servidor de desarrollo en http://localhost:5173
```

### Conectar un Dispositivo

```bash
# USB : simplemente enchufa el dispositivo (ADB / depuración USB activada)
# WiFi: instala el APK del agente — misma red, descubre el backend automáticamente
```

**¿Necesitas la app del agente?** El backend la sirve en `GET /agent/apk`, o compílala desde
`agent-android/`.

### Contrólalo desde Python

```python
# pip install droidlink — la misma flota, desde un script o CI
def test_login_flow(device):
    device.app.start("com.example.app")
    device.input.tap(540, 1200)
    device.input.type_text("user@test.com")
    assert device.screen.capture() is not None
```

---

<!-- DK:SHOTS:START -->
## 📸 Capturas de Pantalla

|                     Vista General de la Flota                      |                          Control de Nodo                          |
| :----------------------------------------------------------------: | :---------------------------------------------------------------: |
|      ![Vista General de la Flota](screenshots/dashboard.png)      |       ![Control de Nodo](screenshots/node-detail.png)        |
|   _Métricas de la flota en vivo, tarjetas KPI, distribución de salud, ejecuciones activas, fallos recientes y la barra de consultas FQL_   |   _Transmisión en vivo por dispositivo, indicadores de diagnóstico en vivo, shell ADB, historial de métricas y macro acciones rápidas_   |

|                      Ejecución de Automatización                      |                        Editor de Automatización                        |
| :-------------------------------------------------------------------: | :--------------------------------------------------------------------: |
|    ![Ejecución de Automatización](screenshots/automation-run.png)    |    ![Editor de Automatización](screenshots/automation-editor.png)    |
|   _Resultados en vivo por paso, auto-recuperación (diff original → recuperado), asserts de regresión visual y un paquete de depuración auto-generado con análisis de IA en caso de fallo_   |   _Constructor de pasos con reordenado + refinado por IA paso a paso, "Generar con IA", etiquetas y líneas base visuales_   |

|                        Constructor de Workflows                        |                           Automatizaciones                           |
| :--------------------------------------------------------------------: | :------------------------------------------------------------------: |
|        ![Constructor de Workflows](screenshots/workflow.png)        |       ![Automatizaciones](screenshots/automations.png)          |
|   _Lienzo visual de automatización basado en nodos — encadena disparadores, toques, esperas, asserts y ramificaciones_   |   _Todas las automatizaciones con pasos, etiquetas, controles de ejecutar/programar/compartir/clonar y un feed de ejecuciones recientes_   |

|                      Comparación de Dispositivos                       |                          Monitor de Métricas                          |
| :--------------------------------------------------------------------: | :-------------------------------------------------------------------: |
|      ![Comparación de Dispositivos](screenshots/compare.png)      |          ![Monitor de Métricas](screenshots/monitor.png)          |
|   _Hasta 4 dispositivos lado a lado con una superposición sincronizada de tendencias históricas e indicadores por dispositivo_   |   _Gráficas de métricas entre dispositivos en periodos seleccionables, más reglas de alerta por umbral sobre el bus de notificaciones_   |

<details>
<summary><strong>Ver todas las capturas</strong></summary>

<br>

|                         Grupos de Dispositivos                         |                            Pipeline / CI                            |
| :--------------------------------------------------------------------: | :-----------------------------------------------------------------: |
|        ![Grupos de Dispositivos](screenshots/groups.png)          |             ![Pipeline / CI](screenshots/pipeline.png)             |
|   _Grupos etiquetados y con código de color, con acciones en masa — reiniciar, bloquear, instalar, ejecutar automatizaciones_   |   _Lista de builds, resultados por test y capturas de fallos del plugin pytest de droidlink_   |

|                              Perfiles                              |                             ADB Remoto                             |
| :----------------------------------------------------------------: | :----------------------------------------------------------------: |
|              ![Perfiles](screenshots/profiles.png)              |              ![ADB Remoto](screenshots/remote-adb.png)          |
|   _Personalidades de IA por dispositivo y configuración de modelos multi-proveedor (Claude, GPT, Groq, Ollama, Google)_   |   _Shell ADB en el navegador con historial de comandos y presets, más un explorador de archivos_   |

|                            Enrolamiento                            |                        Historial de Comandos                        |
| :----------------------------------------------------------------: | :-----------------------------------------------------------------: |
|            ![Enrolamiento](screenshots/enrollment.png)            |     ![Historial de Comandos](screenshots/command-history.png)     |
|   _Emparejamiento del agente y cola de aprobación con descubrimiento automático en LAN para nuevos dispositivos_   |   _Una línea de tiempo de toda la flota con cada comando emitido, su estado y quién lo ejecutó_   |

|                              Trabajos                               |                           Notificaciones                           |
| :-----------------------------------------------------------------: | :----------------------------------------------------------------: |
|                ![Trabajos](screenshots/jobs.png)                 |         ![Notificaciones](screenshots/notifications.png)          |
|   _Trabajos en segundo plano en cola, en ejecución y completados — automatizaciones, instalaciones en masa, capturas de líneas base_   |   _Feed de onboarding + alertas con canales de entrega (webhook, Slack, email)_   |

|                             Extensiones                             |                              Ajustes                               |
| :-----------------------------------------------------------------: | :----------------------------------------------------------------: |
|            ![Extensiones](screenshots/extensions.png)            |                ![Ajustes](screenshots/settings.png)               |
|   _Extensiones instaladas más un registro remoto para explorar e instalar más con un clic_   |   _Identidad de la instancia, acceso a la API, 2FA, configuración de IA/streaming/paquetes de depuración y apariencia/marca blanca_   |

</details>
<!-- DK:SHOTS:END -->

---

## 🎯 Funcionalidades

### 🛰️ Gestión de Flota

| | |
|---|---|
| **Métricas en tiempo real**<br>CPU, RAM, batería, temperatura y almacenamiento por dispositivo, transmitidas en vivo. | **Salud de la flota**<br>Distribución agregada de saludable / advertencia / crítico en toda la flota. |
| **Grupos de dispositivos**<br>Etiquetas, código de color y acciones en masa sobre cualquier selección. | **Comparación de dispositivos**<br>Hasta 4 dispositivos lado a lado con gráficas en tiempo real sincronizadas. |
| **Onboarding automático**<br>Los nuevos dispositivos se anuncian en el momento en que se conectan. | **Historial de comandos**<br>Una línea de tiempo de auditoría de toda la flota con cada acción emitida. |

### 🔎 Lenguaje de Consultas de Flota

| | |
|---|---|
| **Filtrado tipo SQL**<br>`android_version < 13 AND battery > 20 AND status = 'idle'` | **Autocompletado + presets**<br>Completado de campos en la barra de consultas, más predefinidos (batería baja, sin conexión, SO desactualizado). |
| **Consultas guardadas**<br>Guarda los filtros que más usas. | **Consulta → acción en masa**<br>Dirige los resultados directamente a reiniciar, bloquear, instalar APK o ejecutar una automatización. |
| **Exportación a CSV**<br>Llévate cualquier resultado de consulta contigo. | |

### 🤖 Motor de Automatización

| | |
|---|---|
| **14 tipos de pasos**<br>Toque, deslizar, escribir, pulsar tecla, abrir/cerrar app, subir/bajar archivos, espera, assert, captura y más. | **Editor de arrastrar y soltar**<br>Constructor visual de pasos con vistas previas y contexto del dispositivo en vivo. |
| **Constructor de workflows**<br>Lienzo basado en nodos para automatizaciones ramificadas de varios pasos. | **Grabar automatizaciones**<br>Toca y desliza en el dispositivo; recibe los pasos generados. |
| **Programar y compartir**<br>Ejecuta en intervalos con pausa/reanudación; clona, exporta e importa como JSON. | |

### ✨ Automatización con IA

| | |
|---|---|
| **Generar**<br>Convierte una descripción en lenguaje natural en pasos de automatización ejecutables. | **Refinar**<br>Modifica pasos individuales con instrucciones conversacionales. |
| **Explicar**<br>Obtén un resumen en lenguaje natural de lo que hace cualquier automatización. | **Auto-recuperación**<br>Cuando los elementos de la UI se mueven entre versiones de la app, la IA re-localiza los objetivos y reintenta automáticamente. |

### 🖼️ Pruebas de Regresión Visual

| | |
|---|---|
| **Asserts de captura**<br>Un paso `screenshot_assert` compara contra líneas base almacenadas. | **Motor de diff SSIM**<br>Diff de píxeles con umbrales configurables. |
| **Análisis de diff con IA**<br>Distingue cambios significativos de la UI del ruido de renderizado. | **Enmascaramiento de regiones**<br>Excluye contenido dinámico (relojes, anuncios, marcas de tiempo). |
| **Líneas base por modelo**<br>Líneas base registradas por modelo y versión de dispositivo, con informes de aprobado / fallido / requiere revisión. | |

### 📺 Transmisión de Dispositivos en Vivo

| | |
|---|---|
| **Streaming MJPEG**<br>Vídeo en tiempo real, no sondeo de capturas, con calidad adaptativa (5 / 15 / 30 fps). | **Multi-espectador**<br>Insignias de número de espectadores y sesiones compartidas. |
| **Superposición táctil**<br>Animaciones de onda muestran cada interacción. | **Grabación de sesiones**<br>Reproducción fotograma a fotograma con marcadores de eventos. |
| **Indicador de latencia**<br>Verde (<100 ms), amarillo (<300 ms), rojo (>300 ms), con fallback automático a sondeo de capturas. | |

### 🧰 Paquetes de Depuración de Fallos

| | |
|---|---|
| **Auto-generados**<br>Se crean ante cualquier fallo de paso de automatización o de test. | **Todo en un paquete**<br>Captura, logcat (últimas 100 líneas), estado del dispositivo, XML de la jerarquía de UI, acciones recientes y propiedades del dispositivo. |
| **Análisis con IA**<br>Envía el paquete para obtener una hipótesis de causa raíz y correcciones sugeridas. | **Compartible**<br>Enlaces de tiempo limitado para compartir paquetes con tu equipo; descarga como ZIP, retención de 30 días. |

### 🔬 Integración CI/CD

| | |
|---|---|
| **Plugin pytest de droidlink**<br>Fixtures `device` y `device_pool`, `pip install droidlink`. | **Captura automática en fallos**<br>Cada test que falla captura el estado del dispositivo. |
| **Seguimiento de builds**<br>Resultados por test vinculados al ciclo de vida de un build. | **Seguro en paralelo**<br>Bloqueo de dispositivos para ejecutores de tests en paralelo, con plantilla de GitHub Actions incluida. |

### 🖥️ Control Remoto y Agentes de IA

| | |
|---|---|
| **ADB remoto y archivos**<br>Shell ADB en el navegador con historial y presets, más un explorador de archivos con búsqueda. | **Agentes de IA Prompture**<br>Cada dispositivo se convierte en un agente conversacional: multi-proveedor (Claude, GPT, Groq, Ollama, Google), modelo + memoria por dispositivo, uso directo de herramientas y seguimiento de tokens/costes. |
| **Extensiones**<br>Un catálogo integrado y un registro remoto, con un gestor de extensiones instaladas. | |

---

## 🏗️ Arquitectura

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

1. **El agente Android** se ejecuta en cada dispositivo — sirve una API HTTP en el puerto 9800 y reporta métricas al backend
2. **El backend Flask** fusiona los dispositivos conectados por ADB y los registrados por el agente en una flota unificada
3. **El frontend React** se suscribe a SSE para actualizaciones en tiempo real y usa REST para todo lo demás
4. **La librería droidlink** se conecta directamente a los dispositivos para scripts y CI — USB vía redirección de puertos ADB, WiFi vía descubrimiento automático
5. **El plugin pytest** asigna dispositivos, ejecuta tests y reporta los resultados al panel

**[Arquitectura completa →](ARCHITECTURE.md)** · **[Contrato de flota →](FLEET_CONTRACT.md)**

---

## 🗺️ Hoja de Ruta

- [x] Gestión de flota — métricas en tiempo real, agregación de salud, grupos de dispositivos, comparación
- [x] Lenguaje de Consultas de Flota — filtrado tipo SQL, presets, consulta → acción en masa, exportación CSV
- [x] Motor de automatización — 14 tipos de pasos, editor de arrastrar y soltar, grabación, programación, compartir
- [x] Constructor de workflows — lienzo visual de automatización basado en nodos
- [x] Automatización con IA — generar / refinar / explicar desde lenguaje natural
- [x] Auto-recuperación — la IA re-localiza objetivos de UI movidos y reintenta
- [x] Regresión visual — diff SSIM, análisis con IA, enmascaramiento de regiones, líneas base por modelo
- [x] Streaming en vivo — MJPEG, calidad adaptativa, superposición táctil, grabación de sesiones
- [x] Paquetes de depuración — captura automática, causa raíz con IA, enlaces compartibles
- [x] CI/CD — plugin pytest de droidlink, bloqueo de dispositivos en paralelo, plantilla de GitHub Actions
- [x] Agentes de IA Prompture — agentes conversacionales por dispositivo con uso de herramientas
- [x] ADB remoto y explorador de archivos
- [x] Flota de agentes — enrolamiento, cola de aprobación, descubrimiento LAN, cola de comandos, actualizaciones escalonadas
- [x] Extensiones — catálogo integrado + registro remoto
- [x] Apariencia — temas claro / oscuro / sistema, colores de acento, marca blanca
- [ ] API pública + servidor MCP — claves `dk_` con ámbitos, OpenAPI automático, CLI `devicekit`

Historial completo y próximas fases: **[ROADMAP.md](../ROADMAP.md)**

---

## 📖 Documentación

La suite completa de documentación vive en **[`docs/`](README.md)** — empieza ahí
para ver el mapa. Lo más destacado:

| Guía | Descripción |
| --- | --- |
| [Índice de Documentación](README.md) | El mapa — cada documento, agrupado por lo que responde |
| [Primeros Pasos](getting-started.md) | Instalar → ejecutar el backend → conectar un dispositivo → primera automatización |
| [Arquitectura](ARCHITECTURE.md) | Los cuatro componentes y cómo se comunican (léelo primero) |
| [Contrato de Flota](FLEET_CONTRACT.md) | Protocolo agente ↔ backend: registro/heartbeat/estado/comandos, HMAC, capacidades |
| [Guía de Extensiones](extensions/guide.md) | Crea una extensión — puntos de contribución, SDK, manifiesto, tutorial |
| [Agente de IA](ai-agent.md) | Agentes de dispositivo respaldados por Prompture: herramientas, puerta de confirmación, modos de sesión |
| [droidlink](droidlink.md) | Controla una flota gestionada por DeviceKit desde Python (`pip install droidlink`) |
| [Configuración de CI/CD](ci-setup.md) | Integración con GitHub Actions, fixtures de dispositivos, pruebas en paralelo |
| [Servidor MCP](mcp-server.md) | Superficie del Model Context Protocol para agentes de IA |
| [Hoja de Ruta](../ROADMAP.md) | Historial completo de desarrollo y próximas fases |

---

## 🧱 Stack Tecnológico

| Capa | Tecnología |
|-------|------------|
| Backend | Python 3.11, Flask, 31 mixins componibles, SSE |
| Frontend | React 18, Vite, Tailwind CSS |
| Agente | Kotlin (Android), servicio en segundo plano, servidor HTTP, descubrimiento UDP, servicio de accesibilidad |
| Librería | `droidlink` (PyPI) — CLI + plugin pytest |
| Control de dispositivos | ADB, UIAutomator2, Chrome DevTools Protocol |
| Persistencia | DynamoDB (local o AWS), almacenamiento de archivos S3 |
| Streaming | Proxy MJPEG con calidad adaptativa |
| IA | Prompture (multi-proveedor: Claude, GPT, Groq, Ollama, Google) |

---

## ⚙️ Variables de Entorno

| Variable | Predeterminado | Descripción |
|----------|---------|-------------|
| `API_PORT` | `5050` | Puerto de la API Flask |
| `API_HOST` | `0.0.0.0` | Dirección de escucha de Flask |
| `API_KEY` | – | Clave de API para autenticar los endpoints (desactivada si no se define) |
| `AGENT_TOKENS` | – | Tokens separados por comas para la autenticación de agentes |
| `AWS_ACCESS_KEY_ID` | – | Credenciales de AWS para DynamoDB/S3 |
| `AWS_SECRET_ACCESS_KEY` | – | Credenciales de AWS |
| `AWS_REGION` | `us-east-1` | Región de AWS |
| `DYNAMODB_TABLE_PREFIX` | `devicekit_` | Prefijo de nombre de tabla |
| `DYNAMODB_ENDPOINT` | – | URL de DynamoDB local (p. ej. `http://localhost:8321`) |
| `CORS_ORIGINS` | `*` | Orígenes CORS permitidos |
| `DEVICE_IDS` | – | Seriales de dispositivos separados por comas |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `DEBUG_MODE` | `false` | Activa el modo debug de Flask |
| `PROMPTURE_DEFAULT_MODEL` | – | Modelo de IA predeterminado para los agentes de dispositivo |

---

## ✅ Compatibilidad

| Componente | Requisitos |
| --- | --- |
| **Backend** | Python 3.11+ |
| **Frontend** | Node 18+, cualquier navegador moderno |
| **Dispositivos Android** | Android 7+ (API 24+), depuración USB activada |
| **App del Agente** | Android 8+ (API 26+) para el conjunto completo de funcionalidades |
| **Docker** | Docker 20+, docker-compose v2 |
| **SO** | Windows, macOS, Linux |

---

## 🛠️ Solución de Problemas

**¿El dispositivo no aparece?** — Verifica que la depuración USB esté activada, ejecuta `adb devices` para
confirmar que ADB lo ve, y comprueba que `adb` esté en tu PATH.

**¿El agente se queda en "Conectando…"?** — El agente no puede alcanzar el backend. Por USB,
ejecuta `adb reverse tcp:5050 tcp:5050`; por WiFi, define la URL del backend en los
ajustes del agente con la IP de tu máquina.

**¿El stream no carga?** — La app del agente debe estar en ejecución; asegúrate de que el puerto 9800 sea
alcanzable (`adb forward tcp:9800 tcp:9800` por USB) y prueba un preset de menor calidad.

**¿Problemas con Docker?** — Ejecuta `docker-compose logs`, asegúrate de que los puertos 3847 / 5890 / 8321
estén libres, y comprueba que `.env` tenga credenciales de AWS válidas (o usa DynamoDB Local).

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas!

```
fork → feature branch → commit → push → pull request
```

1. **Reporta errores** — [GitHub Issues](https://github.com/jhd3197/DeviceKit/issues)
2. **Solicita funcionalidades** — [GitHub Discussions](https://github.com/jhd3197/DeviceKit/discussions)
3. **Envía PRs** — Correcciones de errores, nuevos tipos de pasos, mejoras del frontend
4. **Mejora la documentación** — Todos los archivos `.md` del repositorio

---

## 💛 Apoya a DeviceKit

DeviceKit es libre y de código abierto. Si te ahorra tiempo, puedes ayudar a mantenerlo en marcha:

- ⭐ [Dale una estrella al repositorio](https://github.com/jhd3197/DeviceKit) — no cuesta nada y ayuda mucho
- 💖 [GitHub Sponsors](https://github.com/sponsors/jhd3197)
- ☕ [Buy Me a Coffee](https://buymeacoffee.com/jhd3197)

### 💎 Criptomonedas

| | Activo | Red | Dirección |
|:---:|---|---|---|
| <img src="images/funding/usdt-trc20.png" width="110" alt="Código QR de la dirección de donación USDT TRC-20" /> | **USDT** | **TRC-20** · Tron | `TTiCtqLauF1iSW2YGB3b78KmRxRqoLCgeL` |
| <img src="images/funding/usdt-erc20.png" width="110" alt="Código QR de la dirección de donación USDT y ETH ERC-20" /> | **USDT / ETH** | **ERC-20** · Ethereum | `0xD13D5355Fa214e8317fea2ff192a065BaeC13527` |
| <img src="images/funding/btc.png" width="110" alt="Código QR de la dirección de donación de Bitcoin" /> | **BTC** | **Bitcoin** | `bc1qatx67n3qxdvuv3arc9j8aytk34f22g02k9c7vr` |
| <img src="images/funding/sol.png" width="110" alt="Código QR de la dirección de donación de Solana" /> | **SOL** | **Solana** | `AWXzqtBEgUfteHPQtDegsZ6D5y57M3GGdKPD8rR7h6xu` |

TRC-20 tiene las comisiones más bajas — normalmente menos de un dólar — así que es
la opción más cómoda para una donación pequeña. El gas de ERC-20 puede costar más
que la propia donación.

<sub>Los códigos QR se generan localmente con [`scripts/generate-funding-qr.mjs`](../scripts/generate-funding-qr.mjs), que valida la suma de verificación de cada dirección antes de codificarla.</sub>

---

## 🔭 Proyectos Relacionados

**[ServerKit](https://github.com/jhd3197/ServerKit)** — Un panel de control de servidores ligero y moderno
para aplicaciones web, bases de datos, Docker y seguridad — infraestructura autoalojada
sin la complejidad de Kubernetes.

**[Faro](https://github.com/jhd3197/faro)** — Un cliente de escritorio moderno para SFTP, FTP, SSH y almacenamiento compatible con S3, del mismo autor. Guarda un servidor una vez y luego explora sus archivos en una vista de doble panel y abre una terminal sobre la misma sesión SSH — además de transferencias con arrastrar y soltar, sincronización de directorios en un sentido y edición in situ. Incluso tiene un **Agent Bridge** que permite a Claude Code (o cualquier agente MCP) ejecutar comandos en un servidor a través de tu sesión autenticada, con aprobación por comando y sin compartir credenciales.

> DeviceKit gestiona tu flota Android desde el navegador; Faro es el compañero de escritorio para transferencias de archivos, shells y trabajo puntual en todos tus servidores. [Descarga una versión →](https://github.com/jhd3197/faro/releases/latest)

**[LocalKit](https://github.com/jhd3197/LocalKit)** — Levanta sitios WordPress locales en un clic. Cada sitio se ejecuta como su propio proyecto aislado de Docker Compose, y puedes enviar código o enviar/traer bases de datos directamente a tu servidor ServerKit mediante la extensión `serverkit-localkit`.

---

## 💬 Comunidad

[![Discord](https://img.shields.io/badge/Discord-Únete-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/ZKk6tkCQfG)

Únete al Discord para hacer preguntas, compartir comentarios u obtener ayuda con tu configuración.

---

## 📄 Licencia

Este proyecto está licenciado bajo la **Licencia MIT**. Consulta [LICENSE](../LICENSE) para
todos los detalles.

**Android** es una marca registrada de Google LLC. Este proyecto **no está afiliado a,
ni respaldado ni patrocinado por Google LLC.**

---

<div align="center">

**DeviceKit** — Un panel para toda tu flota Android.

[Reportar un Error](https://github.com/jhd3197/DeviceKit/issues) · [Solicitar una Funcionalidad](https://github.com/jhd3197/DeviceKit/discussions)

Hecho con ❤️ por [Juan Denis](https://juandenis.com)

</div>
