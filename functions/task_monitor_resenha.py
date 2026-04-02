import json
import os
import discord
 
# Caminho do arquivo gerado pelo Selenium
DATA_PATH = r'data\dados_jogos.json'
 
# Estado anterior dos jogos: chave = "mandante_visitante", valor = dict com situação e placar
_estado_anterior: dict[str, dict] = {}
 
 
def _is_rival(team_name: str, rival_teams: list[str]) -> bool:
    name = team_name.lower().strip()
    return any(r.lower().strip() in name or name in r.lower().strip() for r in rival_teams)
 
 
def _parse_placar(placar: str) -> tuple[int, int] | None:
    """
    Converte '2 x 1' em (2, 1).
    Retorna None se o placar for 'x' (jogo ainda não começou).
    """
    partes = placar.strip().split("x")
    if len(partes) != 2:
        return None
    try:
        return int(partes[0].strip()), int(partes[1].strip())
    except ValueError:
        return None  # placar = "x" — jogo não iniciado
 
 
def _is_live(status: str) -> bool:
    """
    Jogo ao vivo: status NÃO contém 'Ontem', 'Encerrado', 'Intervalo' e
    NÃO é apenas um horário futuro ("Hoje — HH:MM").
    O Selenium marca como ao vivo quando há placar numérico E não é Ontem/encerrado.
    Detectamos pelo que NÃO está no status.
    """
    s = status.lower()
    if "ontem" in s:
        return False
    if "encerrado" in s:
        return False
    # Horário futuro: "Hoje — 19:00" — sem placar ainda
    # Será descartado pelo _parse_placar retornar None (placar = "x")
    return True
 
 
def _is_finished(status: str) -> bool:
    s = status.lower()
    return "ontem" in s or "encerrado" in s
 
 
def _situacao_rival(placar: tuple[int, int], rival_is_home: bool) -> str:
    """Retorna 'winning', 'drawing' ou 'losing' do ponto de vista do rival."""
    rival_g = placar[0] if rival_is_home else placar[1]
    opp_g   = placar[1] if rival_is_home else placar[0]
    if rival_g > opp_g:
        return "winning"
    if rival_g == opp_g:
        return "drawing"
    return "losing"
 
 
def _chave(jogo: dict) -> str:
    return f"{jogo['mandante'].strip().lower()}_{jogo['visitante'].strip().lower()}"
 
 
async def verificar_resenha(bot: discord.ext.commands.Bot, alert_channel_id: int, rival_teams: list[str]) -> None:
    """
    Lê dados_jogos.json, compara com estado anterior e envia alertas
    apenas quando a situação do rival muda.
    Deve ser chamada dentro de um loop periódico (tasks.loop).
 
    Formato esperado do JSON:
    {
        "mandante": "Palmeiras",
        "visitante": "Grêmio",
        "placar": "1 x 0",          # "x" quando não iniciado
        "status": "Arena Barueri — Hoje — 21:30"   # "Ontem" = encerrado
    }
    """
    global _estado_anterior
 
    # Lê o arquivo
    try:
        if not os.path.exists(DATA_PATH):
            print("[Resenha] Arquivo de dados não encontrado.")
            return
 
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            jogos: list[dict] = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Resenha] Erro ao ler JSON: {e}")
        return
 
    channel = bot.get_channel(alert_channel_id)
    if channel is None:
        print(f"[Resenha] Canal {alert_channel_id} não encontrado.")
        return
 
    for jogo in jogos:
        mandante   = jogo.get("mandante", "").strip()
        visitante  = jogo.get("visitante", "").strip()
        placar_str = jogo.get("placar", "").strip()
        status     = jogo.get("status", "").strip()
 
        # Descarta encerrados e ainda não iniciados
        if _is_finished(status):
            continue
 
        placar = _parse_placar(placar_str)
        if placar is None:
            # placar = "x" → jogo agendado, ainda não começou
            continue
 
        # Só monitora se tem rival no jogo
        rival_is_home = _is_rival(mandante, rival_teams)
        rival_is_away = _is_rival(visitante, rival_teams)
 
        if not rival_is_home and not rival_is_away:
            continue
        if rival_is_home and rival_is_away:
            continue  # ambos rivais — ignora
 
        rival    = mandante if rival_is_home else visitante
        opponent = visitante if rival_is_home else mandante
 
        sit_atual   = _situacao_rival(placar, rival_is_home)
        chave       = _chave(jogo)
        anterior    = _estado_anterior.get(chave, {})
        sit_prev    = anterior.get("sit")
        placar_prev = anterior.get("placar")
 
        situacao_mudou = sit_atual != sit_prev
        placar_mudou   = placar_str != placar_prev
 
        if situacao_mudou or (placar_mudou and sit_atual in ("losing", "drawing")):
 
            # ── ALERTA: rival começou a perder ou empatou saindo de vitória ──
            if sit_atual in ("losing", "drawing") and sit_prev == "winning":
                if sit_atual == "losing":
                    descricao = f"😂 **{rival}** está **PERDENDO** para **{opponent}**!"
                else:
                    descricao = f"😬 **{rival}** **EMPATOU** com **{opponent}**!"
 
                embed = discord.Embed(
                    title="🚨 POSSÍVEL RESENHA! 🚨",
                    description=(
                        f"@everyone\n\n"
                        f"{descricao}\n\n"
                        f"⚔️ **{mandante} {placar_str} {visitante}**\n"
                        f"📍 {status}"
                    ),
                    color=0xFF4444,
                )
                embed.set_footer(text="Brasileirão • ao vivo")
                await channel.send(content="@everyone", embed=embed)
                print(f"[Resenha] RESENHA | {mandante} {placar_str} {visitante}")
 
            # ── ALERTA: rival ainda não tinha estado → entrou perdendo/empatando ──
            elif sit_atual in ("losing", "drawing") and sit_prev is None:
                if sit_atual == "losing":
                    descricao = f"😂 **{rival}** já está **PERDENDO** para **{opponent}**!"
                else:
                    descricao = f"😬 **{rival}** começa **EMPATADO** com **{opponent}**."
 
                embed = discord.Embed(
                    title="🚨 POSSÍVEL RESENHA! 🚨",
                    description=(
                        f"@everyone\n\n"
                        f"{descricao}\n\n"
                        f"⚔️ **{mandante} {placar_str} {visitante}**\n"
                        f"📍 {status}"
                    ),
                    color=0xFF4444,
                )
                embed.set_footer(text="Brasileirão • ao vivo")
                await channel.send(content="@everyone", embed=embed)
                print(f"[Resenha] RESENHA (início) | {mandante} {placar_str} {visitante}")
 
            # ── ALERTA: rival virou o jogo ────────────────────────────────────
            elif sit_atual == "winning" and sit_prev in ("losing", "drawing"):
                embed = discord.Embed(
                    title="✅ RESENHA CANCELADA",
                    description=(
                        f"@everyone\n\n"
                        f"😒 **{rival}** virou o jogo contra **{opponent}**. Acabou a festa.\n\n"
                        f"⚔️ **{mandante} {placar_str} {visitante}**\n"
                        f"📍 {status}"
                    ),
                    color=0x44BB44,
                )
                embed.set_footer(text="Brasileirão • ao vivo")
                await channel.send(content="@everyone", embed=embed)
                print(f"[Resenha] CANCELADA | {mandante} {placar_str} {visitante}")
 
            # ── Placar mudou mas rival continua sofrendo (gol a mais) ─────────
            elif sit_atual in ("losing", "drawing") and placar_mudou and sit_prev in ("losing", "drawing"):
                if sit_atual == "losing":
                    descricao = f"😂 **{rival}** continua **PERDENDO** — tomou mais um!"
                else:
                    descricao = f"😬 **{rival}** segue **EMPATADO** com **{opponent}**."
 
                embed = discord.Embed(
                    title="🚨 RESENHA CONTINUA! 🚨",
                    description=(
                        f"@everyone\n\n"
                        f"{descricao}\n\n"
                        f"⚔️ **{mandante} {placar_str} {visitante}**\n"
                        f"📍 {status}"
                    ),
                    color=0xFF8800,
                )
                embed.set_footer(text="Brasileirão • ao vivo")
                await channel.send(content="@everyone", embed=embed)
                print(f"[Resenha] GOL NO RIVAL | {mandante} {placar_str} {visitante}")
 
        # Atualiza estado
        _estado_anterior[chave] = {"sit": sit_atual, "placar": placar_str}
 
    # Limpa do estado jogos encerrados ou que sumiram do JSON
    chaves_ativas = {
        _chave(j) for j in jogos
        if not _is_finished(j.get("status", "")) and _parse_placar(j.get("placar", "")) is not None
    }
    for chave in list(_estado_anterior.keys()):
        if chave not in chaves_ativas:
            _estado_anterior.pop(chave, None)
 