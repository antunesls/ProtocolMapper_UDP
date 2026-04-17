# ProtocolMapper UDP

Gateway de comandos UDP com mapeamento de regras, despacho multi-protocolo e painel web de administração.

Escuta pacotes UDP, compara o conteúdo com regras configuradas (hex exato, texto exato ou regex) e dispara ações em um ou mais protocolos de saída: HTTP, UDP, TCP, MQTT, WebSocket (Soundcraft UI24R/UI16/UI12), sequências temporizadas e ramps de interpolação de valor.

---

## Funcionalidades

- **Listener UDP assíncrono** — asyncio nativo, sem threads extras
- **7 tipos de handler de saída**: `http`, `udp`, `tcp`, `mqtt`, `ui24r`, `sequence`, `ramp`
- **Correspondência de regras**: hex exato, texto exato, regex
- **Painel web** (Tailwind + Alpine.js) com dashboard em tempo real via WebSocket
- **Autenticação HTTP Basic** com bcrypt
- **Persistência SQLite** via aiosqlite
- **Pool de conexões persistentes** para o Soundcraft UI24R / UI16 / UI12
- **Ramps** com easing (linear, ease_in, ease_out, ease_in_out)
- **Sequences** paralelas ou seriais com delay configurável
- **Módulo auxiliar `ui24r_commands`** para gerar comandos e configurações sem escrever caminhos manuais

---

## Requisitos

- Python 3.11+
- pip

---

## Instalação

```bash
git clone <repo-url> ProtocolMapper_UDP
cd ProtocolMapper_UDP

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Configurar o `.env`

Copie o arquivo de exemplo e ajuste os valores:

```bash
cp .env.example .env
```

Campos disponíveis:

| Variável | Padrão | Descrição |
|---|---|---|
| `HOST` | `0.0.0.0` | Interface de escuta do servidor web |
| `PORT` | `8000` | Porta HTTP do servidor web |
| `ADMIN_USERNAME` | `admin` | Usuário do painel web |
| `ADMIN_PASSWORD_HASH` | — | Hash bcrypt da senha |
| `UDP_LISTEN_IP` | `0.0.0.0` | Interface de escuta UDP (padrão, sobrescrito pela UI) |
| `UDP_LISTEN_PORT` | `5005` | Porta UDP (padrão, sobrescrito pela UI) |
| `DATABASE_URL` | `data/mapper.db` | Caminho do banco SQLite |
| `LOG_MAX_ENTRIES` | `1000` | Entradas máximas no buffer de log em memória |

O arquivo `.env` padrão já contém o hash bcrypt da senha `admin`.

### Gerar hash de senha personalizada

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'sua_senha', bcrypt.gensalt()).decode())"
```

Cole o resultado em `ADMIN_PASSWORD_HASH` no `.env`.

---

## Executando

```bash
python3 run.py
```

Saída esperada:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     UDP listener started on 0.0.0.0:5005
```

Abra o navegador em **http://localhost:8000** — login padrão: `admin` / `admin`.

---

## Painel Web

| Página | URL | Descrição |
|---|---|---|
| Dashboard | `/` | Log de pacotes em tempo real via WebSocket |
| Mapeamentos | `/mappings` | CRUD de regras de mapeamento |
| Configurações | `/settings` | IP/porta UDP, máximo de entradas no log |

---

## Tipos de saída e `output_config`

Cada mapeamento define um tipo de saída e um bloco `output_config` em JSON.

### `http`

```json
{
  "url": "http://192.168.1.10/api/action",
  "method": "POST",
  "headers": {"X-Token": "abc"},
  "body": {"key": "value"}
}
```

### `udp`

```json
{
  "host": "192.168.1.10",
  "port": 7000,
  "data": "HELLO"
}
```

### `tcp`

```json
{
  "host": "192.168.1.10",
  "port": 9000,
  "data": "CMD\r\n"
}
```

### `mqtt`

```json
{
  "broker": "mqtt://192.168.1.20",
  "topic": "sala/luz",
  "payload": "ON",
  "qos": 1
}
```

### `ui24r`

```json
{
  "host": "192.168.1.100",
  "port": 80,
  "commands": [
    "SETD^i.0.mix^0.74900",
    "SETD^i.0.mute^1"
  ]
}
```

### `ramp`

```json
{
  "target": {
    "type": "ui24r",
    "output_config": {
      "host": "192.168.1.100",
      "port": 80,
      "commands": ["SETD^i.0.mix^{value}"]
    }
  },
  "from_value": 0.0,
  "to_value": 0.749,
  "duration_ms": 2000,
  "fps": 30,
  "easing": "ease_in_out"
}
```

Valores de `easing`: `linear`, `ease_in`, `ease_out`, `ease_in_out`.

### `sequence`

```json
{
  "mode": "parallel",
  "actions": [
    {
      "type": "ui24r",
      "output_config": {
        "host": "192.168.1.100",
        "port": 80,
        "commands": ["SETD^i.0.mute^1"]
      }
    },
    {
      "delay_before_ms": 500,
      "type": "http",
      "output_config": {
        "url": "http://192.168.1.10/api/notify",
        "method": "GET"
      }
    }
  ]
}
```

`mode`: `parallel` (todas simultâneas) ou `serial` (respeita `delay_before_ms` sequencialmente).

---

## Módulo auxiliar `ui24r_commands`

O módulo `app/handlers/ui24r_commands.py` oferece funções de alto nível para o Soundcraft UI24R / UI16 / UI12 sem escrever caminhos `SETD` manualmente.

### Importação

```python
from app.handlers.ui24r_commands import (
    db_to_fader, fader_to_db,
    cmd_fader, cmd_mute, cmd_eq_band,
    config_fader, config_mute,
    preset_fade_ramp, preset_snapshot, preset_mute_all_inputs,
    list_channels, list_parameters,
)
```

### Conversões de valor

```python
db_to_fader(-10.0)    # dB → valor linear do fader (0.0–1.0)
fader_to_db(0.749)    # valor linear → dB
```

### Construtores de comando (retornam `str`, sem `3:::`)

```python
# Tipos de canal: 'i'=input, 'l'=line, 'p'=player,
#                 'f'=fx, 's'=sub, 'a'=aux, 'v'=vca
# Numeração 1-based (canal 1 = primeiro canal)

cmd_fader('i', 1, db=0)         # → 'SETD^i.0.mix^0.74900'
cmd_fader('i', 1, value=0.5)    # → por valor linear direto
cmd_mute('i', 1, muted=True)    # → 'SETD^i.0.mute^1'
cmd_solo('i', 1, solo=True)
cmd_pan('i', 1, value=0.5)      # 0=esquerda, 0.5=centro, 1=direita
cmd_gain(1, db=20.0, model='ui24')
cmd_phantom(1, enabled=True)
cmd_aux_send('i', 1, aux_num=1, db=-6.0)
cmd_fx_send('i', 1, fx_num=1, db=-6.0)
cmd_delay('i', 1, ms=10.0)
cmd_channel_name('i', 1, name='KICK')

# EQ — retorna lista de strings
cmd_eq_band('i', 1, band=2, freq=1000, gain_db=3.0, q=1.4)
cmd_eq_hpf('i', 1, freq=80.0)
cmd_eq_lpf('i', 1, freq=12000.0)
cmd_eq_bypass('i', 1, bypass=True)

# Dinâmicos — retornam lista de strings
cmd_compressor('i', 1, threshold_db=-20, ratio=4.0, attack_ms=5, release_ms=50)
cmd_gate('i', 1, threshold_db=-40, attack_ms=1, release_ms=100)

# Grupos de mute
cmd_mute_group([1, 2, 3])       # → 'SETD^mgmask^7'

# Master / globais
cmd_master_fader(db=-6.0)
cmd_master_dim(enabled=True)
cmd_headphone_vol(value=0.8)
cmd_solo_vol(value=0.7)
```

### Geradores de `output_config`

```python
host = '192.168.1.100'

# output_config pronto para o handler 'ui24r'
cfg = config_fader(host, 'i', 1, db=0)
# → {'host': '192.168.1.100', 'port': 80, 'commands': ['SETD^i.0.mix^0.74900']}

cfg = config_mute(host, 'i', 1, muted=True)
cfg = config_solo(host, 'i', 1, solo=True)
cfg = config_gain(host, 1, db=20.0, model='ui24')
cfg = config_eq_band(host, 'i', 1, band=1, freq=100, gain_db=6.0)
cfg = config_mute_group(host, [1, 2])

# Múltiplos comandos em uma única conexão
cfg = config_multi(host, [
    cmd_mute('i', 1, muted=True),
    cmd_mute('i', 2, muted=True),
    cmd_master_dim(enabled=True),
])
```

### Presets completos

```python
# Ramp de fade (pronto para usar como output_config do handler 'ramp')
ramp_cfg = preset_fade_ramp(
    host='192.168.1.100',
    ch_type='i',
    ch_num=1,
    from_db=-60.0,
    to_db=0.0,
    duration_ms=3000,
    easing='ease_in_out',
    fps=30,
)

# Snapshot de múltiplos faders em paralelo
snapshot = preset_snapshot(
    host='192.168.1.100',
    channels=[
        {'ch_type': 'i', 'ch_num': 1, 'db': -6.0},
        {'ch_type': 'i', 'ch_num': 2, 'db': -12.0},
        {'ch_type': 's', 'ch_num': 1, 'db': 0.0},
    ]
)

# Mutar todos os inputs de um modelo
mute_cfg = preset_mute_all_inputs(
    host='192.168.1.100',
    ch_count=24,   # use DEVICE_CAPS['ui24']['input']
    muted=True,
)
```

### Listagem / introspecção

```python
# Listar todos os canais de input do UI24R
for ch in list_channels('ui24', 'i'):
    print(ch['label'], ch['fader_path'], ch['mute_path'])

# Listar todos os parâmetros de um canal (EQ, dinâmicos, sends, delay…)
params = list_parameters('i', 1, model='ui24')
print(params['eq_bands'])   # lista de dicts por banda
print(params['aux_sends'])  # lista de sends para cada aux

# Listar buses
list_fx_buses('ui24')   # → [{'num': 1, 'path_prefix': 'f.0', ...}, ...]
list_aux_buses('ui24')  # → [{'num': 1, 'path_prefix': 'a.0', ...}, ...]
```

---

## Arquitetura

```
run.py
└── app/
    ├── main.py              # FastAPI + lifespan + BasicAuthMiddleware
    ├── config.py            # Pydantic BaseSettings (.env)
    ├── core/
    │   ├── udp_server.py    # asyncio.DatagramProtocol, reiniciável
    │   ├── dispatcher.py    # mapper → handler → log
    │   ├── mapper.py        # correspondência de regras
    │   └── log_buffer.py    # deque circular + broadcast WebSocket
    ├── db/
    │   ├── database.py      # aiosqlite helpers
    │   └── repository.py    # CRUD de mapeamentos e settings
    ├── api/
    │   ├── routes/          # rotas REST e WebSocket
    │   └── schemas/         # modelos Pydantic (InputType, OutputType…)
    ├── handlers/
    │   ├── __init__.py      # HANDLER_REGISTRY (7 handlers)
    │   ├── http_handler.py
    │   ├── udp_handler.py
    │   ├── tcp_handler.py
    │   ├── mqtt_handler.py
    │   ├── ui24r_handler.py # pool de conexões WS persistentes
    │   ├── ramp_handler.py  # interpolação com easing
    │   ├── sequence_handler.py
    │   └── ui24r_commands.py  # módulo auxiliar de alto nível
    └── web/
        └── templates/       # base.html, dashboard.html, mappings.html, settings.html
```

---

## Licença

MIT
