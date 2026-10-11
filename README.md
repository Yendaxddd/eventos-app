# 🎮 QTE Discord Bot - Advanced Roleplay Combat System

A feature-rich Discord bot for real-time QTE (Quick Time Events) combat with roleplay integration, domain expansions, and AI-powered interactions.

## 🖥️ App de escritorio (Windows)

Eventos App es una aplicación de Windows con ventana propia (sin terminal): panel con estado del bot,
botones de acciones rápidas (QTE individuales/grupales, checkpoint, sincronizar comandos), registro en vivo
y una pantalla de configuración donde pegas el token.

**Instalarla (recomendado)**
1. Descarga `EventosApp-Setup-X.Y.Z.exe`: en la pestaña *Actions* de GitHub, último run de **Build Windows app**
   → *Artifacts* → `EventosApp-Installer` (o en *Releases* si se publicó un tag `vX.Y.Z`).
2. Ábrelo y sigue el asistente. Instala solo para tu usuario (no pide administrador) y crea acceso directo
   en el escritorio y en el menú Inicio.
3. Abre *Eventos App* → *Configuración* → pega el token → *Guardar cambios* → *Panel* → *Iniciar bot*.
4. Con el bot conectado, en *Configuración* → **Evento** elige el **servidor, el canal y los roles** de los
   desplegables (con búsqueda) y pulsa *Aplicar al evento*. Equivale a `/setchannel` y crea el hilo «📊 HP Bars».

**Bots auxiliares (evitar el rate limit).** Discord limita cuántos mensajes manda cada bot por canal (~5 cada 5 s).
Con varios bots, el principal reparte los mensajes (QTE, respuestas, imágenes) entre todos y las ráfagas salen sin esperas:
1. En el Developer Portal crea otra aplicación por cada auxiliar (*Bot* → *Reset Token*). No necesitan intents especiales.
2. *Configuración* → **Bots auxiliares** → pega el token → *Agregar bot auxiliar*.
3. Pulsa *Invitar* (copia el enlace), ábrelo en el navegador y añádelo a tu servidor.
4. Inicia el bot. *Probar* envía y borra un mensaje de prueba para confirmar que puede escribir en el canal.

Las reacciones también se reparten entre los bots. Más detalle (latencias, límites, cuántos jugadores aguanta y la
prueba de rendimiento de la app) en [docs/RENDIMIENTO.md](docs/RENDIMIENTO.md).

Los mensajes con botones siempre salen por el bot principal. Si un auxiliar no puede escribir en el canal, el mensaje
sale por otro bot y ese auxiliar se aparta de ese canal. En una prueba contra un Discord simulado (5 mensajes/5 s por bot),
una ráfaga de 12 mensajes tarda ~10 s con 1 bot, ~5 s con 2 y menos de 0.5 s con 3 o más.

Para **actualizar**, ejecuta el instalador nuevo encima: se conservan tu `settings.json`, los datos de jugadores
(`data\`) y los GIFs (`assets\`). Al **desinstalar** te pregunta si quieres borrar también esos datos; por defecto no.

**Versión portátil (zip):** `EventosApp-windows.zip` (artifact del mismo run). Descomprime en cualquier carpeta
y abre `EventosApp.exe`, sin instalar nada.

Todo (datos, assets, logs, `settings.json`) vive en la carpeta de la app; para respaldarla basta con copiarla
(con el instalador: `%LOCALAPPDATA%\Programs\EventosApp`, o el botón *Carpeta de datos* de la app).
Windows SmartScreen puede avisar la primera vez porque el instalador y el `.exe` no están firmados.

**Construirla tú mismo** (Windows, Python 3.11+):
```powershell
powershell -ExecutionPolicy Bypass -File discord-bot\packaging\build_windows.ps1
```
Genera `discord-bot\dist\EventosApp\EventosApp.exe`, `EventosApp-windows.zip` y el instalador
`EventosApp-Setup-X.Y.Z.exe` (este último necesita [Inno Setup 6](https://jrsoftware.org/isdl.php) o `choco install innosetup`;
sin él se omite). Para probar el `.exe` construido:
`EventosApp.exe --smoke-test` (escribe `logs\smoke_test.json`).

**Ejecutarla desde el código** (sin compilar):
```bash
pip install -r discord-bot/requirements.txt -r discord-bot/requirements-desktop.txt
python discord-bot/run_app.py
```

El modo sin ventana (`python advanced_qte_hp_system_debug.py`, Docker, Railway) sigue funcionando como antes.

## ✨ Features

### Core Combat Mechanics
- **Real-time QTE System**: Evade, Parry, Counter actions with precise timing
- **HP & Damage System**: Variable damage based on difficulty levels
- **REVENGE Mode**: Activates at 20% HP with enhanced abilities
- **Black Flash**: Perfect timing special mechanic with chain combos
- **Power System**: Charge-based ultimate abilities with cooldowns

### Advanced Features
- **Domain Expansions**: Special abilities with unique GIFs and effects
- **Domain Clash**: 1v1 typing competition when domains collide
- **Status Effects**: Bleed, Burn, Poison, and more
- **Boss Battles**: Cooperative boss fights with Tupperbox integration
- **Skill Trees & Achievements**: Progress tracking and rewards
- **AI Integration**: Optional Ollama-powered responses

### QTE Variations
- **Standard QTE**: Classic evade/parry timing
- **Combo QTE**: Multi-button sequences
- **Direction QTE**: Arrow input challenges
- **Fake QTE**: Trap QTEs that punish action

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Discord Bot Token
- Discord Server with required channel and roles

### Installation

1. **Clone and setup**:
```bash
cd eventos-app/discord-bot
pip install -r requirements.txt
```

2. **Configure environment** (copy `.env.example` to `.env`):
```env
DISCORD_TOKEN=your_bot_token_here
QTE_CHANNEL_ID=your_channel_id
QTE_PLAYER_ROLE_ID=your_role_id
ADMIN_ROLE_ID=optional_admin_role_id
HP_BAR_THREAD_ID=optional_thread_id

# Optional: External AI endpoint (for Railway/cloud deployment)
OLLAMA_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_MODEL=elbot
```

3. **Run the bot**:
```bash
python advanced_qte_hp_system_debug.py
```

## 🐳 Docker Deployment

### Local Docker
```bash
docker-compose up -d
```

### Railway Deployment
1. Connect your GitHub repository to Railway
2. Set environment variables in Railway dashboard
3. Deploy automatically via `railway.json`

**Note**: AI features require an external Ollama instance. Set `OLLAMA_ENDPOINT` to your Ollama server URL.

## 📁 Project Structure

```
eventos-app/
├── discord-bot/
│   ├── advanced_qte_hp_system_debug.py  # Main bot code
│   ├── special_objects_manager.py       # Special items system
│   ├── gm_commands.py                   # GM command utilities
│   ├── attack_validator.py              # Attack validation
│   ├── changelog_manager.py             # Version tracking
│   ├── requirements.txt                 # Python dependencies
│   ├── Dockerfile                       # Container config
│   ├── docker-compose.yml               # Local deployment
│   ├── assets/                          # Domain GIFs and media
│   └── data/                            # Runtime data (JSON)
├── Dockerfile                           # Railway deployment
├── railway.json                         # Railway config
├── Modelfile                            # Custom AI model config
└── GM_COMMANDS_GUIDE.md                 # GM reference
```

## 🎯 QTE Timing Windows

| Difficulty | Evade Window | Parry Window | Damage |
|------------|--------------|--------------|--------|
| Easy       | 6.0s         | 4-7s         | 1-3    |
| Medium     | 4.5s         | 3-5s         | 1-5    |
| Hard       | 4.0s         | 2.5-4.5s     | 1-10   |
| Impossible | 1.5s         | 0.8-1.7s     | 15     |

## 🌟 Special Mechanics

### REVENGE Mode (20% HP)
- Parry windows shift 0.3s earlier
- Windows 30% tighter
- +50% damage multiplier
- +10% Black Flash chance

### Black Flash Chain
- Level 1: 25 damage, 10s cooldown
- Level 2: 50 damage, 30s cooldown
- Level 3: 100 damage, 60s cooldown
- Level 4: 200 damage, 120s cooldown

## ⚙️ Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot token from Discord Developer Portal |
| `QTE_CHANNEL_ID` | Yes | Channel ID for QTE messages |
| `QTE_PLAYER_ROLE_ID` | Yes | Role ID for QTE participants |
| `ADMIN_ROLE_ID` | No | Role ID for admin commands |
| `HP_BAR_THREAD_ID` | No | Thread ID for HP bar displays |
| `OLLAMA_ENDPOINT` | No | External AI API endpoint |
| `OLLAMA_MODEL` | No | AI model name (default: dolphin-phi:2.7b) |

## 📜 Slash Commands

The bot provides 52+ slash commands including:
- `/qte` - Trigger QTE events
- `/boss` - Boss management
- `/domain` - Domain expansion controls
- `/stats` - Player statistics
- `/register` - Character registration
- `/power` - Ultimate abilities
- `/ai` - AI interaction settings

See `/help` in Discord for full command list.

## 🔧 Local Development

### Keyboard Hotkeys (requires `keyboard` library + root on Linux)
- `F9-F12`: Trigger QTEs (Easy/Medium/Hard/Impossible)
- `Shift+F9-F12`: Group QTEs
- `F8`: Healing checkpoint
- `F7`: Force sync commands
- `Alt+F9`: Toggle batch mode

### Running with hotkeys (Linux)
```bash
sudo python advanced_qte_hp_system_debug.py
```

## 📝 Changelog

See [CHANGELOG.md](discord-bot/CHANGELOG.md) for version history.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

Private project - All rights reserved.

---

**Questions?** Check the in-game `/help` command or review the code comments!
