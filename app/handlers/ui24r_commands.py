"""
Módulo auxiliar de alto nível para o Soundcraft UI24R / UI16 / UI12.

Fornece funções facilitadas para controlar o mixer sem precisar escrever
caminhos SETD manualmente:

  - Conversões de valor  (dB ↔ linear, ms → s, gain dB ↔ linear)
  - Capacidades por modelo  (quantos canais de cada tipo)
  - Construtores de comandos  (retornam strings SETD/SETS prontas, sem '3:::')
  - Geradores de output_config  (dicts prontos para o handler 'ui24r')
  - Presets completos  (ramp de fade, snapshot de faders, mute-all)
  - Funções de listagem  (canais, parâmetros, FX buses, AUX buses)

Uso rápido::

    from app.handlers.ui24r_commands import (
        db_to_fader, fader_to_db,
        cmd_fader, cmd_mute, cmd_eq_band,
        config_fader, preset_fade_ramp,
        list_channels, list_parameters,
    )

    # Gera comando bruto (sem '3:::'):
    cmd = cmd_fader('i', 1, db=0)    # → 'SETD^i.0.mix^0.74900'

    # Gera output_config pronto para o handler ui24r:
    cfg = config_fader('192.168.1.100', 'i', 1, db=0)
    # → {'host': '192.168.1.100', 'port': 80, 'commands': ['SETD^i.0.mix^0.74900']}

    # Lista canais de input do UI24R:
    for ch in list_channels('ui24', 'i'):
        print(ch['label'], ch['fader_path'])

Tipos de canal (ch_type):
  'i' = input    'l' = line     'p' = player
  'f' = fx       's' = sub      'a' = aux      'v' = vca

Numeração de canal é 1-based (mais natural); a conversão para 0-based é interna.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Capacidades por modelo
# ---------------------------------------------------------------------------

#: Número de canais disponíveis por tipo em cada modelo de mixer.
DEVICE_CAPS: dict[str, dict[str, int]] = {
    "ui12": {"input": 8,  "line": 2, "player": 2, "fx": 4, "sub": 4, "aux": 4,  "vca": 0},
    "ui16": {"input": 12, "line": 2, "player": 2, "fx": 4, "sub": 4, "aux": 6,  "vca": 0},
    "ui24": {"input": 24, "line": 2, "player": 2, "fx": 4, "sub": 6, "aux": 10, "vca": 6},
}

#: Mapeamento: tipo curto → (chave em DEVICE_CAPS, label legível)
_CH_TYPE_META: dict[str, tuple[str, str]] = {
    "i": ("input",  "Input"),
    "l": ("line",   "Line"),
    "p": ("player", "Player"),
    "f": ("fx",     "FX"),
    "s": ("sub",    "Sub"),
    "a": ("aux",    "Aux"),
    "v": ("vca",    "VCA"),
}

#: Bits dos grupos de mute para uso em mgmask
_MUTE_GROUP_BITS: dict[int | str, int] = {
    1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, "fx": 22, "all": 23,
}

#: Tipos de FX disponíveis no mixer
FX_TYPES: dict[int, str] = {0: "Reverb", 1: "Delay", 2: "Chorus", 3: "Room"}


# ---------------------------------------------------------------------------
# Conversões de valor
# (portadas de soundcraft-ui-main/packages/mixer-connection/src/lib/
#  utils/value-converters/value-converters.ts)
# ---------------------------------------------------------------------------

def _fader_to_linear_amp(v: float) -> float:
    """Função de transferência interna: posição do fader (0..1) → amplitude linear."""
    v = max(0.0, min(1.0, v))
    P = (
        23.90844819639692
        + (-26.23877598214595 + (12.195249692570245 - 0.4878099877028098 * v) * v) * v
    ) * v
    exp_P = math.exp(P)
    if v < 0.055:
        return math.sin(28.559933214452666 * v) * exp_P * 2.676529517952372e-4
    return exp_P * 2.676529517952372e-4


def _fader_to_linear_amp_deriv(v: float) -> float:
    """Derivada de _fader_to_linear_amp (para o método de Newton)."""
    P = (
        23.90844819639692
        + (-26.23877598214595 + (12.195249692570245 - 0.4878099877028098 * v) * v) * v
    ) * v
    Pprime = (
        23.90844819639692
        + (-52.4775519642919 + (36.58574907771074 - 1.9512399508112392 * v) * v) * v
    )
    exp_P = math.exp(P)
    if v < 0.055:
        wv = 28.559933214452666 * v
        return 2.676529517952372e-4 * exp_P * (
            28.559933214452666 * math.cos(wv) + math.sin(wv) * Pprime
        )
    return 2.676529517952372e-4 * exp_P * Pprime


def db_to_fader(db: float) -> float:
    """Converte dB (−∞..+10) para valor linear do fader (0.0..1.0).

    Usa o método de Newton para inverter a curva de transferência real do mixer.
    0 dB ≈ 0.749  |  +10 dB = 1.0  |  −∞ dB = 0.0

    Exemplos::

        db_to_fader(0)    # → 0.74900...
        db_to_fader(-10)  # → 0.55600...
        db_to_fader(-60)  # → 0.09700...
    """
    if db <= -200:
        return 0.0
    if db >= 10:
        return 1.0
    target = 10 ** (db / 20)
    v = 0.5
    for _ in range(20):
        f = _fader_to_linear_amp(v)
        df = _fader_to_linear_amp_deriv(v)
        if abs(df) < 1e-30:
            break
        delta = (f - target) / df
        v -= delta
        v = max(1e-10, min(1.0, v))
        if abs(delta) < 1e-15:
            break
    return round(v * 1e11) / 1e11


def fader_to_db(v: float) -> float:
    """Converte valor linear do fader (0.0..1.0) para dB.

    Exemplos::

        fader_to_db(0.749)  # → 0.0
        fader_to_db(1.0)    # → 10.0
        fader_to_db(0.0)    # → -inf
    """
    lin = _fader_to_linear_amp(v)
    if lin < 1e-10:
        return -math.inf
    result = round(20 * math.log10(lin) * 10) / 10
    return result or 0.0


def gain_to_linear(db: float, model: str = "ui24") -> float:
    """Converte dB de ganho de hardware para valor linear (0..1).

    UI24R: −6..+57 dB  |  UI12/UI16: −40..+50 dB

    Exemplos::

        gain_to_linear(20, 'ui24')  # → 0.44776...
        gain_to_linear(0,  'ui16')  # → 0.44444...
    """
    lo, hi = (-6.0, 57.0) if model == "ui24" else (-40.0, 50.0)
    return max(0.0, min(1.0, (db - lo) / (hi - lo)))


def linear_to_gain_db(v: float, model: str = "ui24") -> float:
    """Converte valor linear (0..1) para dB de ganho de hardware."""
    lo, hi = (-6.0, 57.0) if model == "ui24" else (-40.0, 50.0)
    return lo + v * (hi - lo)


def delay_ms_to_raw(ms: float) -> float:
    """Converte milissegundos para o valor raw de delay aceito pelo mixer (segundos)."""
    return ms / 1000.0


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _idx(ch_num: int) -> int:
    """Converte número de canal 1-based para índice 0-based."""
    return ch_num - 1


def _base_config(host: str, port: int, commands: list[str], delay_ms: float = 0) -> dict[str, Any]:
    cfg: dict[str, Any] = {"host": host, "port": port, "commands": commands}
    if delay_ms > 0:
        cfg["delay_ms"] = delay_ms
    return cfg


# ---------------------------------------------------------------------------
# Construtores de comandos de baixo nível
# ---------------------------------------------------------------------------
# Todos retornam strings SEM o prefixo '3:::'.
# Numeração de canal é 1-based; a conversão para 0-based é interna.
# Use diretamente em output_config['commands'] do handler ui24r.

def cmd_fader(ch_type: str, ch_num: int, *, value: float | None = None, db: float | None = None) -> str:
    """Posição do fader de um canal. Informe *value* (0..1) OU *db* (−∞..+10).

    Exemplos::

        cmd_fader('i', 1, db=0)       # → 'SETD^i.0.mix^0.74900'
        cmd_fader('i', 1, value=0.5)  # → 'SETD^i.0.mix^0.50000'
        cmd_fader('a', 2, db=-10)     # → AUX 2 master fader
    """
    v = db_to_fader(db) if db is not None else (value if value is not None else 0.0)
    return f"SETD^{ch_type}.{_idx(ch_num)}.mix^{v:.5f}"


def cmd_master_fader(*, value: float | None = None, db: float | None = None) -> str:
    """Fader master (L+R). Informe *value* (0..1) OU *db*.

    Exemplo::

        cmd_master_fader(db=0)  # → 'SETD^m.mix^0.74900'
    """
    v = db_to_fader(db) if db is not None else (value if value is not None else 0.0)
    return f"SETD^m.mix^{v:.5f}"


def cmd_mute(ch_type: str, ch_num: int, muted: bool) -> str:
    """Mute/unmute de um canal.

    Exemplos::

        cmd_mute('i', 1, True)   # → 'SETD^i.0.mute^1'
        cmd_mute('i', 1, False)  # → 'SETD^i.0.mute^0'
    """
    return f"SETD^{ch_type}.{_idx(ch_num)}.mute^{1 if muted else 0}"


def cmd_solo(ch_type: str, ch_num: int, soloed: bool) -> str:
    """Solo/unsolo de um canal (tipos 'i' e 'l').

    Exemplo::

        cmd_solo('i', 2, True)  # → 'SETD^i.1.solo^1'
    """
    return f"SETD^{ch_type}.{_idx(ch_num)}.solo^{1 if soloed else 0}"


def cmd_pan(ch_type: str, ch_num: int, pan: float = 0.5) -> str:
    """Panorama (0.0=esquerda, 0.5=centro, 1.0=direita).

    Exemplo::

        cmd_pan('i', 1, 0.5)  # → 'SETD^i.0.pan^0.5'
    """
    return f"SETD^{ch_type}.{_idx(ch_num)}.pan^{pan}"


def cmd_master_pan(pan: float = 0.5) -> str:
    """Panorama do bus master.

    Exemplo::

        cmd_master_pan(0.5)  # → 'SETD^m.pan^0.5'
    """
    return f"SETD^m.pan^{pan}"


def cmd_gain(
    ch_num: int,
    *,
    value: float | None = None,
    db: float | None = None,
    model: str = "ui24",
) -> str:
    """Ganho de pré-amplificador (hardware).

    UI24R usa ``hw.<N>.gain``; UI12/UI16 usa ``i.<N>.gain``.
    Informe *value* (0..1) OU *db*.

    Exemplos::

        cmd_gain(1, db=20, model='ui24')  # → 'SETD^hw.0.gain^0.44776'
        cmd_gain(1, db=10, model='ui16')  # → 'SETD^i.0.gain^0.55556'
    """
    v = gain_to_linear(db, model) if db is not None else (value if value is not None else 0.0)
    path = f"hw.{_idx(ch_num)}.gain" if model == "ui24" else f"i.{_idx(ch_num)}.gain"
    return f"SETD^{path}^{v:.5f}"


def cmd_phantom(ch_num: int, on: bool, model: str = "ui24") -> str:
    """Liga/desliga phantom power (+48V) em um canal.

    Exemplos::

        cmd_phantom(1, True,  'ui24')  # → 'SETD^hw.0.phantom^1'
        cmd_phantom(1, False, 'ui16')  # → 'SETD^i.0.phantom^0'
    """
    path = f"hw.{_idx(ch_num)}.phantom" if model == "ui24" else f"i.{_idx(ch_num)}.phantom"
    return f"SETD^{path}^{1 if on else 0}"


def cmd_aux_send(
    ch_num: int,
    aux_num: int,
    *,
    value: float | None = None,
    db: float | None = None,
) -> str:
    """Nível de send do canal de input para um AUX bus.

    Exemplo::

        cmd_aux_send(1, 1, db=-6)  # → 'SETD^i.0.aux.0.value^0.62500'
    """
    v = db_to_fader(db) if db is not None else (value if value is not None else 0.0)
    return f"SETD^i.{_idx(ch_num)}.aux.{_idx(aux_num)}.value^{v:.5f}"


def cmd_aux_send_pan(ch_num: int, aux_num: int, pan: float = 0.5) -> str:
    """Pan do send de canal para AUX (em buses stereo-linked).

    Exemplo::

        cmd_aux_send_pan(1, 1, 0.0)  # → 'SETD^i.0.aux.0.pan^0.0'
    """
    return f"SETD^i.{_idx(ch_num)}.aux.{_idx(aux_num)}.pan^{pan}"


def cmd_aux_send_post(ch_num: int, aux_num: int, post: bool = True) -> str:
    """Define PRE/POST fader para send de canal em AUX.

    post=True → post-fader (padrão)  |  post=False → pre-fader

    Exemplo::

        cmd_aux_send_post(1, 1, False)  # → 'SETD^i.0.aux.0.post^0'
    """
    return f"SETD^i.{_idx(ch_num)}.aux.{_idx(aux_num)}.post^{1 if post else 0}"


def cmd_fx_send(
    ch_num: int,
    fx_num: int,
    *,
    value: float | None = None,
    db: float | None = None,
) -> str:
    """Nível de send do canal de input para um FX bus.

    Exemplo::

        cmd_fx_send(1, 1, db=-12)  # → 'SETD^i.0.fx.0.value^0.55900'
    """
    v = db_to_fader(db) if db is not None else (value if value is not None else 0.0)
    return f"SETD^i.{_idx(ch_num)}.fx.{_idx(fx_num)}.value^{v:.5f}"


def cmd_delay(ch_type: str, ch_num: int, delay_ms: float) -> str:
    """Delay de canal em milissegundos.

    Range: input 0–250 ms | aux/master 0–500 ms

    Exemplo::

        cmd_delay('i', 1, 20)   # → 'SETD^i.0.delay^0.02'
        cmd_delay('a', 1, 100)  # → 'SETD^a.0.delay^0.1'
    """
    return f"SETD^{ch_type}.{_idx(ch_num)}.delay^{delay_ms_to_raw(delay_ms)}"


def cmd_master_delay(side: str, delay_ms: float) -> str:
    """Delay do bus master. side='L' ou 'R'.

    Exemplo::

        cmd_master_delay('L', 50)  # → 'SETD^m.delayL^0.05'
    """
    return f"SETD^m.delay{side.upper()}^{delay_ms_to_raw(delay_ms)}"


def cmd_eq_band(
    ch_type: str,
    ch_num: int,
    band: int,
    *,
    freq: float | None = None,
    gain_db: float | None = None,
    q: float | None = None,
) -> list[str]:
    """Parâmetros de uma banda de EQ paramétrico (bandas 1–5).

    Retorna lista de comandos — apenas os parâmetros fornecidos geram comando.

    Exemplo::

        cmd_eq_band('i', 1, 2, freq=1000, gain_db=3.0, q=1.4)
        # → ['SETD^i.0.eq.b2.freq^1000',
        #     'SETD^i.0.eq.b2.gain^3.0',
        #     'SETD^i.0.eq.b2.q^1.4']
    """
    prefix = f"{ch_type}.{_idx(ch_num)}.eq.b{band}"
    cmds = []
    if freq is not None:
        cmds.append(f"SETD^{prefix}.freq^{freq}")
    if gain_db is not None:
        cmds.append(f"SETD^{prefix}.gain^{gain_db}")
    if q is not None:
        cmds.append(f"SETD^{prefix}.q^{q}")
    return cmds


def cmd_eq_hpf(
    ch_type: str,
    ch_num: int,
    freq: float | None = None,
    slope: float | None = None,
) -> list[str]:
    """High-pass filter de um canal. Retorna lista de comandos.

    Exemplo::

        cmd_eq_hpf('i', 1, freq=80, slope=24)
        # → ['SETD^i.0.eq.hpf.freq^80', 'SETD^i.0.eq.hpf.slope^24']
    """
    prefix = f"{ch_type}.{_idx(ch_num)}.eq.hpf"
    cmds = []
    if freq is not None:
        cmds.append(f"SETD^{prefix}.freq^{freq}")
    if slope is not None:
        cmds.append(f"SETD^{prefix}.slope^{slope}")
    return cmds


def cmd_eq_lpf(
    ch_type: str,
    ch_num: int,
    freq: float | None = None,
    slope: float | None = None,
) -> list[str]:
    """Low-pass filter de um canal. Retorna lista de comandos.

    Exemplo::

        cmd_eq_lpf('i', 1, freq=8000)  # → ['SETD^i.0.eq.lpf.freq^8000']
    """
    prefix = f"{ch_type}.{_idx(ch_num)}.eq.lpf"
    cmds = []
    if freq is not None:
        cmds.append(f"SETD^{prefix}.freq^{freq}")
    if slope is not None:
        cmds.append(f"SETD^{prefix}.slope^{slope}")
    return cmds


def cmd_eq_bypass(ch_type: str, ch_num: int, bypassed: bool) -> str:
    """Bypass do EQ de um canal.

    Exemplo::

        cmd_eq_bypass('i', 1, True)  # → 'SETD^i.0.eq.bypass^1'
    """
    return f"SETD^{ch_type}.{_idx(ch_num)}.eq.bypass^{1 if bypassed else 0}"


def cmd_compressor(
    ch_type: str,
    ch_num: int,
    *,
    threshold: float | None = None,
    ratio: float | None = None,
    attack: float | None = None,
    release: float | None = None,
    gain: float | None = None,
    outgain: float | None = None,
    bypass: bool | None = None,
    softknee: bool | None = None,
    autogain: bool | None = None,
) -> list[str]:
    """Parâmetros do compressor de dinâmica. Retorna lista de comandos.

    Todos os parâmetros são opcionais — apenas os fornecidos geram comando.

    Exemplo::

        cmd_compressor('i', 1, threshold=0.5, ratio=0.3, bypass=False)
        # → ['SETD^i.0.dyn.threshold^0.5',
        #     'SETD^i.0.dyn.ratio^0.3',
        #     'SETD^i.0.dyn.bypass^0']
    """
    prefix = f"{ch_type}.{_idx(ch_num)}.dyn"
    mapping = {
        "threshold": threshold, "ratio": ratio, "attack": attack,
        "release": release, "gain": gain, "outgain": outgain,
    }
    cmds = [f"SETD^{prefix}.{k}^{v}" for k, v in mapping.items() if v is not None]
    if bypass is not None:
        cmds.append(f"SETD^{prefix}.bypass^{1 if bypass else 0}")
    if softknee is not None:
        cmds.append(f"SETD^{prefix}.softknee^{1 if softknee else 0}")
    if autogain is not None:
        cmds.append(f"SETD^{prefix}.autogain^{1 if autogain else 0}")
    return cmds


def cmd_gate(
    ch_type: str,
    ch_num: int,
    *,
    thresh: float | None = None,
    attack: float | None = None,
    hold: float | None = None,
    release: float | None = None,
    depth: float | None = None,
    bypass: bool | None = None,
    enabled: bool | None = None,
) -> list[str]:
    """Parâmetros do gate de um canal. Retorna lista de comandos.

    Exemplo::

        cmd_gate('i', 1, thresh=0.4, bypass=False)
        # → ['SETD^i.0.gate.thresh^0.4', 'SETD^i.0.gate.bypass^0']
    """
    prefix = f"{ch_type}.{_idx(ch_num)}.gate"
    mapping = {
        "thresh": thresh, "attack": attack, "hold": hold,
        "release": release, "depth": depth,
    }
    cmds = [f"SETD^{prefix}.{k}^{v}" for k, v in mapping.items() if v is not None]
    if bypass is not None:
        cmds.append(f"SETD^{prefix}.bypass^{1 if bypass else 0}")
    if enabled is not None:
        cmds.append(f"SETD^{prefix}.enabled^{1 if enabled else 0}")
    return cmds


def cmd_channel_name(ch_type: str, ch_num: int, name: str) -> str:
    """Define o nome de um canal (usa SETS, máx. 20 chars, sem '^').

    Exemplo::

        cmd_channel_name('i', 1, 'KICK')  # → 'SETS^i.0.name^KICK'
    """
    safe_name = name[:20].replace("^", "")
    return f"SETS^{ch_type}.{_idx(ch_num)}.name^{safe_name}"


def cmd_mute_group(groups: list[int | str]) -> str:
    """Liga grupos de mute via bitmask.

    Grupos válidos: 1–6 (grupos normais), 'fx' (bit 22), 'all' (bit 23).
    Passe [] para limpar todos os mutes.

    Exemplos::

        cmd_mute_group([1, 2])   # → 'SETD^mgmask^3'
        cmd_mute_group(['all'])  # → 'SETD^mgmask^8388608'
        cmd_mute_group([])       # → 'SETD^mgmask^0'
    """
    mask = 0
    for g in groups:
        if g in _MUTE_GROUP_BITS:
            mask |= 1 << _MUTE_GROUP_BITS[g]
    return f"SETD^mgmask^{mask}"


def cmd_master_dim(on: bool) -> str:
    """Liga/desliga DIM do master (somente UI24R).

    Exemplo::

        cmd_master_dim(True)  # → 'SETD^m.dim^1'
    """
    return f"SETD^m.dim^{1 if on else 0}"


def cmd_headphone_vol(hp_num: int, *, value: float | None = None, db: float | None = None) -> str:
    """Volume do fone de ouvido hp_num (1-based).

    Exemplo::

        cmd_headphone_vol(1, db=-6)  # → 'SETD^settings.hpvol.0^0.62500'
    """
    v = db_to_fader(db) if db is not None else (value if value is not None else 0.5)
    return f"SETD^settings.hpvol.{_idx(hp_num)}^{v:.5f}"


def cmd_solo_vol(*, value: float | None = None, db: float | None = None) -> str:
    """Volume do barramento de solo.

    Exemplo::

        cmd_solo_vol(db=-3)  # → 'SETD^settings.solovol^0.68...'
    """
    v = db_to_fader(db) if db is not None else (value if value is not None else 0.5)
    return f"SETD^settings.solovol^{v:.5f}"


def cmd_fx_type(fx_num: int, fx_type: int) -> str:
    """Tipo de efeito em um FX bus (0=Reverb, 1=Delay, 2=Chorus, 3=Room).

    Exemplo::

        cmd_fx_type(1, 0)  # → 'SETD^f.0.fxtype^0'  (Reverb no FX1)
    """
    return f"SETD^f.{_idx(fx_num)}.fxtype^{fx_type}"


def cmd_fx_param(fx_num: int, param_num: int, value: float) -> str:
    """Parâmetro (1–6) de um FX bus.

    Exemplo::

        cmd_fx_param(1, 1, 0.6)  # → 'SETD^f.0.par1^0.6'
    """
    return f"SETD^f.{_idx(fx_num)}.par{param_num}^{value}"


def cmd_fx_bpm(fx_num: int, bpm: float) -> str:
    """BPM do FX bus para delay sincronizado (20–400).

    Exemplo::

        cmd_fx_bpm(1, 120)  # → 'SETD^f.0.bpm^120'
    """
    return f"SETD^f.{_idx(fx_num)}.bpm^{bpm}"


# ---------------------------------------------------------------------------
# Geradores de output_config (prontos para o handler ui24r)
# ---------------------------------------------------------------------------

def config_fader(
    host: str,
    ch_type: str,
    ch_num: int,
    *,
    value: float | None = None,
    db: float | None = None,
    port: int = 80,
) -> dict[str, Any]:
    """output_config para ajustar o fader de um canal.

    Exemplo::

        config_fader('192.168.1.100', 'i', 1, db=0)
        # → {'host': '192.168.1.100', 'port': 80, 'commands': ['SETD^i.0.mix^0.74900']}
    """
    return _base_config(host, port, [cmd_fader(ch_type, ch_num, value=value, db=db)])


def config_mute(host: str, ch_type: str, ch_num: int, muted: bool, port: int = 80) -> dict[str, Any]:
    """output_config para mutar/desmutar um canal.

    Exemplo::

        config_mute('192.168.1.100', 'i', 3, True)
    """
    return _base_config(host, port, [cmd_mute(ch_type, ch_num, muted)])


def config_solo(host: str, ch_type: str, ch_num: int, soloed: bool, port: int = 80) -> dict[str, Any]:
    """output_config para solear/dessolar um canal."""
    return _base_config(host, port, [cmd_solo(ch_type, ch_num, soloed)])


def config_gain(
    host: str,
    ch_num: int,
    *,
    value: float | None = None,
    db: float | None = None,
    model: str = "ui24",
    port: int = 80,
) -> dict[str, Any]:
    """output_config para ajustar o ganho de pré-amp de um canal."""
    return _base_config(host, port, [cmd_gain(ch_num, value=value, db=db, model=model)])


def config_eq_band(
    host: str,
    ch_type: str,
    ch_num: int,
    band: int,
    *,
    freq: float | None = None,
    gain_db: float | None = None,
    q: float | None = None,
    port: int = 80,
) -> dict[str, Any]:
    """output_config para ajustar uma banda de EQ.

    Exemplo::

        config_eq_band('192.168.1.100', 'i', 1, 2, freq=1000, gain_db=3.0, q=1.4)
    """
    return _base_config(host, port, cmd_eq_band(ch_type, ch_num, band, freq=freq, gain_db=gain_db, q=q))


def config_mute_group(host: str, groups: list[int | str], port: int = 80) -> dict[str, Any]:
    """output_config para ativar grupos de mute por bitmask.

    Exemplo::

        config_mute_group('192.168.1.100', [1, 2])
    """
    return _base_config(host, port, [cmd_mute_group(groups)])


def config_multi(
    host: str,
    commands: list[str],
    delay_ms: float = 0,
    port: int = 80,
) -> dict[str, Any]:
    """output_config genérico com lista livre de comandos brutos (sem '3:::').

    Útil para combinar vários comandos em uma única chamada ao handler.

    Exemplo::

        config_multi('192.168.1.100', [
            cmd_mute('i', 1, True),
            cmd_fader('i', 1, db=-60),
        ], delay_ms=20)
    """
    return _base_config(host, port, commands, delay_ms)


# ---------------------------------------------------------------------------
# Presets completos (output_config com ramp ou sequence)
# ---------------------------------------------------------------------------

def preset_fade_ramp(
    host: str,
    ch_type: str,
    ch_num: int,
    from_db: float,
    to_db: float,
    duration_ms: int,
    *,
    easing: str = "ease_out",
    fps: int = 30,
    port: int = 80,
) -> dict[str, Any]:
    """output_config do tipo **ramp** para fazer fade de fader via dB.

    O placeholder ``{value}`` é interpolado pelo ramp_handler antes de enviar
    para o UI24R. Use como output_config de uma regra com output_type='ramp'.

    Exemplos::

        preset_fade_ramp('192.168.1.100', 'i', 1, from_db=-60, to_db=0,  duration_ms=3000)
        preset_fade_ramp('192.168.1.100', 'i', 2, from_db=0,   to_db=-60, duration_ms=1500, easing='ease_in')

    Easings disponíveis: 'linear', 'ease_in', 'ease_out', 'ease_in_out'
    """
    return {
        "from_value":  round(db_to_fader(from_db), 5),
        "to_value":    round(db_to_fader(to_db),   5),
        "duration_ms": duration_ms,
        "fps":         fps,
        "easing":      easing,
        "action": {
            "output_type": "ui24r",
            "output_config": {
                "host":     host,
                "port":     port,
                "commands": [f"SETD^{ch_type}.{_idx(ch_num)}.mix^{{value}}"],
            },
        },
    }


def preset_snapshot(
    host: str,
    channels: list[dict[str, Any]],
    port: int = 80,
) -> dict[str, Any]:
    """output_config do tipo **sequence** (paralela) que aplica múltiplos faders de uma vez.

    Cada item de *channels* deve ter: ch_type, ch_num e db (ou value).
    Opcionalmente: delay_before_ms.

    Exemplo::

        preset_snapshot('192.168.1.100', [
            {'ch_type': 'i', 'ch_num': 1, 'db': -6},
            {'ch_type': 'i', 'ch_num': 2, 'db': 0},
            {'ch_type': 'a', 'ch_num': 1, 'db': -3},
        ])
    """
    return {
        "parallel": True,
        "actions": [
            {
                "output_type":    "ui24r",
                "delay_before_ms": ch.get("delay_before_ms", 0),
                "output_config":  config_fader(
                    host, ch["ch_type"], ch["ch_num"],
                    db=ch.get("db"), value=ch.get("value"), port=port,
                ),
            }
            for ch in channels
        ],
    }


def preset_mute_all_inputs(
    host: str,
    ch_count: int = 24,
    muted: bool = True,
    port: int = 80,
) -> dict[str, Any]:
    """output_config de sequence paralela que muta/desmuta todos os canais de input.

    Exemplo::

        preset_mute_all_inputs('192.168.1.100', ch_count=24, muted=True)
    """
    return {
        "parallel": True,
        "actions": [
            {
                "output_type":    "ui24r",
                "delay_before_ms": 0,
                "output_config":  config_mute(host, "i", ch, muted, port=port),
            }
            for ch in range(1, ch_count + 1)
        ],
    }


# ---------------------------------------------------------------------------
# Funções de listagem / introspecção
# ---------------------------------------------------------------------------

def list_channels(model: str = "ui24", ch_type: str | None = None) -> list[dict[str, Any]]:
    """Lista todos os canais disponíveis para um modelo.

    Se *ch_type* for informado, filtra por tipo ('i', 'l', 'a', 'f', 's', 'v', 'p').
    Retorna lista de dicts com label, paths e sends disponíveis.

    Exemplo::

        list_channels('ui24', 'i')
        # [
        #   {'type': 'i', 'num': 1, 'label': 'Input 1',
        #    'path_prefix': 'i.0', 'fader_path': 'i.0.mix',
        #    'mute_path': 'i.0.mute', 'solo_path': 'i.0.solo',
        #    'gain_path': 'hw.0.gain', 'aux_sends': [...], 'fx_sends': [...]},
        #   ...
        # ]
    """
    caps = DEVICE_CAPS.get(model, DEVICE_CAPS["ui24"])
    types_to_list = [ch_type] if ch_type else list(_CH_TYPE_META.keys())
    result = []

    for t in types_to_list:
        meta_key, label_base = _CH_TYPE_META[t]
        count = caps.get(meta_key, 0)
        for n in range(1, count + 1):
            idx = _idx(n)
            info: dict[str, Any] = {
                "type":        t,
                "num":         n,
                "label":       f"{label_base} {n}",
                "path_prefix": f"{t}.{idx}",
                "fader_path":  f"{t}.{idx}.mix",
                "mute_path":   f"{t}.{idx}.mute",
            }
            if t in ("i", "l"):
                info["solo_path"]  = f"{t}.{idx}.solo"
                info["pan_path"]   = f"{t}.{idx}.pan"
                info["eq_path"]    = f"{t}.{idx}.eq"
                info["dyn_path"]   = f"{t}.{idx}.dyn"
                info["gate_path"]  = f"{t}.{idx}.gate"
                info["delay_path"] = f"{t}.{idx}.delay"
            if t == "i":
                hw = f"hw.{idx}" if model == "ui24" else f"i.{idx}"
                info["gain_path"]    = f"{hw}.gain"
                info["phantom_path"] = f"{hw}.phantom"
                info["aux_sends"]    = [f"i.{idx}.aux.{a}.value" for a in range(caps.get("aux", 0))]
                info["fx_sends"]     = [f"i.{idx}.fx.{f}.value"  for f in range(caps.get("fx",  0))]
            result.append(info)

    return result


def list_parameters(ch_type: str, ch_num: int, model: str = "ui24") -> dict[str, Any]:
    """Retorna dict com todos os caminhos de parâmetros de um canal específico.

    Útil para descoberta, documentação e geração de comandos automatizados.

    Exemplo::

        list_parameters('i', 1)
        # {
        #   'fader': 'i.0.mix',
        #   'mute': 'i.0.mute',
        #   'gain': 'hw.0.gain',
        #   'eq': {'b1': {'freq': ..., 'gain': ..., 'q': ...}, ..., 'bypass': '...'},
        #   'dyn': {'threshold': '...', 'ratio': '...', ...},
        #   'gate': {'thresh': '...', ...},
        #   'aux_sends': {'aux1': '...', ...},
        #   'fx_sends':  {'fx1':  '...', ...},
        # }
    """
    caps = DEVICE_CAPS.get(model, DEVICE_CAPS["ui24"])
    idx = _idx(ch_num)
    params: dict[str, Any] = {
        "fader": f"{ch_type}.{idx}.mix",
        "mute":  f"{ch_type}.{idx}.mute",
    }

    if ch_type in ("i", "l"):
        params.update({
            "solo":  f"{ch_type}.{idx}.solo",
            "pan":   f"{ch_type}.{idx}.pan",
            "delay": f"{ch_type}.{idx}.delay",
            "eq": {
                **{
                    f"b{b}": {
                        "freq": f"{ch_type}.{idx}.eq.b{b}.freq",
                        "gain": f"{ch_type}.{idx}.eq.b{b}.gain",
                        "q":    f"{ch_type}.{idx}.eq.b{b}.q",
                    }
                    for b in range(1, 6)
                },
                "hpf":    {
                    "freq":  f"{ch_type}.{idx}.eq.hpf.freq",
                    "slope": f"{ch_type}.{idx}.eq.hpf.slope",
                },
                "lpf":    {
                    "freq":  f"{ch_type}.{idx}.eq.lpf.freq",
                    "slope": f"{ch_type}.{idx}.eq.lpf.slope",
                },
                "bypass": f"{ch_type}.{idx}.eq.bypass",
            },
            "dyn": {
                k: f"{ch_type}.{idx}.dyn.{k}"
                for k in ("threshold", "ratio", "attack", "release",
                           "gain", "outgain", "bypass", "softknee", "autogain")
            },
            "gate": {
                k: f"{ch_type}.{idx}.gate.{k}"
                for k in ("thresh", "attack", "hold", "release", "depth", "bypass", "enabled")
            },
        })

    if ch_type == "i":
        hw = f"hw.{idx}" if model == "ui24" else f"i.{idx}"
        params["gain"]    = f"{hw}.gain"
        params["phantom"] = f"{hw}.phantom"
        params["aux_sends"] = {
            f"aux{a + 1}": f"i.{idx}.aux.{a}.value"
            for a in range(caps.get("aux", 0))
        }
        params["fx_sends"] = {
            f"fx{f + 1}": f"i.{idx}.fx.{f}.value"
            for f in range(caps.get("fx", 0))
        }

    return params


def list_fx_buses(model: str = "ui24") -> list[dict[str, Any]]:
    """Lista os FX buses disponíveis com seus caminhos de parâmetros.

    Exemplo::

        list_fx_buses('ui24')
        # [
        #   {'num': 1, 'label': 'FX 1', 'fader_path': 'f.0.mix',
        #    'mute_path': 'f.0.mute', 'type_path': 'f.0.fxtype',
        #    'bpm_path': 'f.0.bpm', 'params': {'par1': 'f.0.par1', ...}},
        #   ...
        # ]
    """
    caps = DEVICE_CAPS.get(model, DEVICE_CAPS["ui24"])
    return [
        {
            "num":        n,
            "label":      f"FX {n}",
            "fader_path": f"f.{_idx(n)}.mix",
            "mute_path":  f"f.{_idx(n)}.mute",
            "type_path":  f"f.{_idx(n)}.fxtype",
            "bpm_path":   f"f.{_idx(n)}.bpm",
            "params":     {f"par{p}": f"f.{_idx(n)}.par{p}" for p in range(1, 7)},
        }
        for n in range(1, caps.get("fx", 0) + 1)
    ]


def list_aux_buses(model: str = "ui24") -> list[dict[str, Any]]:
    """Lista os AUX buses disponíveis com seus caminhos de parâmetros.

    Exemplo::

        list_aux_buses('ui24')
        # [
        #   {'num': 1, 'label': 'Aux 1', 'fader_path': 'a.0.mix',
        #    'mute_path': 'a.0.mute', 'delay_path': 'a.0.delay', 'pan_path': 'a.0.pan'},
        #   ...
        # ]
    """
    caps = DEVICE_CAPS.get(model, DEVICE_CAPS["ui24"])
    return [
        {
            "num":        n,
            "label":      f"Aux {n}",
            "fader_path": f"a.{_idx(n)}.mix",
            "mute_path":  f"a.{_idx(n)}.mute",
            "delay_path": f"a.{_idx(n)}.delay",
            "pan_path":   f"a.{_idx(n)}.pan",
        }
        for n in range(1, caps.get("aux", 0) + 1)
    ]
