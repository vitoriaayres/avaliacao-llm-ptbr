"""Linha de comando do benchmark. Rode `avaliador --help` para ver os comandos."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import click
import pandas as pd
import typer
from dotenv import find_dotenv, load_dotenv

from avaliador.analise import (
    acerto_antes_e_depois_do_corte,
    placar,
    relatorio_de_concordancia,
    tabela_de_pontuacoes,
)
from avaliador.configuracao import (
    ConfigModelo,
    Configuracao,
    ErroDeConfiguracao,
    carregar_configuracao,
)
from avaliador.dados import validar_dataset
from avaliador.dominio import Categoria, Formato, Item, Visibilidade
from avaliador.execucao import Executor, ResumoExecucao, carregar_templates, ler_respostas
from avaliador.execucao.executor import NOME_ARQUIVO_RESPOSTAS
from avaliador.ferramentas import enem, leaderboard
from avaliador.ferramentas.novo_item import ItemRecusado, adicionar_item, proximo_id
from avaliador.infraestrutura import CacheRespostas, CotaDiariaEsgotada, configurar_registro
from avaliador.pontuacao import (
    NOME_ARQUIVO_PONTUACOES,
    Pontuador,
    PontuadorExato,
    PontuadorJuiz,
    carregar_templates_do_juiz,
    com_variantes,
    ler_pontuacoes,
    pontuar_respostas,
    reconstruir_variantes,
    salvar_pontuacoes,
)
from avaliador.pontuacao.vies import consistencia_entre_variantes, vies_de_posicao
from avaliador.provedores import ClienteLLM, criar_limitadores

app = typer.Typer(help="Benchmark de LLMs em português brasileiro.", no_args_is_help=True)

PASTA_DADOS = Path("dados")
PASTA_RESULTADOS = Path("resultados")
CAMINHO_CACHE = PASTA_RESULTADOS / "cache.sqlite"
NOME_ARQUIVO_PLACAR = "placar.csv"

OpcaoDados = Annotated[Path, typer.Option(help="Pasta com publico/ e privado/.")]
ArgumentoExecucao = Annotated[str, typer.Argument(help="Nome da pasta em resultados/.")]


@app.callback()
def principal(
    verboso: Annotated[
        bool, typer.Option("--verboso", "-v", help="Mostra logs de depuração.")
    ] = False,
) -> None:
    load_dotenv(find_dotenv(usecwd=True))
    configurar_registro(logging.DEBUG if verboso else logging.INFO)


@app.command()
def validar(dados: OpcaoDados = PASTA_DADOS) -> None:
    """Confere esquema, ids repetidos e pastas de todos os itens."""
    relatorio = validar_dataset(dados)
    for erro in relatorio.erros:
        typer.echo(f"erro: {erro}", err=True)
    typer.echo(f"{len(relatorio.itens)} itens: {relatorio.contagem_por_categoria()}")
    if not relatorio.valido:
        raise typer.Exit(1)


@app.command()
def modelos() -> None:
    """Lista os modelos configurados, se têm chave e quanta cota resta hoje."""
    configuracao = carregar_configuracao()
    with CacheRespostas(CAMINHO_CACHE) as cache:
        limitadores = criar_limitadores(configuracao.provedores, cache)
    for modelo in configuracao.modelos:
        provedor = configuracao.provedor_de(modelo)
        restantes = limitadores[provedor.nome].restantes_hoje
        typer.echo(
            f"{modelo.id:38} {'ok' if provedor.disponivel else 'sem chave':10} "
            f"cota hoje: {'sem limite' if restantes is None else restantes:<10} "
            f"{'treina com os dados' if provedor.treina_com_dados else ''}"
        )


@app.command()
def executar(
    modelo: Annotated[
        list[str] | None,
        typer.Option("--modelo", "-m", help="Id do modelo; repita para vários. Padrão: todos."),
    ] = None,
    categoria: Annotated[
        list[Categoria] | None,
        typer.Option("--categoria", "-c", help="Repita para várias. Padrão: todas."),
    ] = None,
    limite: Annotated[
        int | None, typer.Option(min=1, help="Máximo de itens por categoria.")
    ] = None,
    repeticoes: Annotated[int, typer.Option(min=1, help="Respostas por item e modelo.")] = 1,
    variantes: Annotated[
        int, typer.Option(min=0, help="Versões com alternativas giradas por questão.")
    ] = 0,
    nome: Annotated[
        str | None, typer.Option(help="Pasta em resultados/. Padrão: data e hora.")
    ] = None,
    dados: OpcaoDados = PASTA_DADOS,
) -> None:
    """Gera as respostas dos modelos para os itens do dataset."""
    itens = com_variantes(_filtrar_itens(_itens_validos(dados), categoria, limite), variantes)
    configuracao = carregar_configuracao()
    try:
        escolhidos = (
            [configuracao.modelo(id_modelo) for id_modelo in modelo]
            if modelo
            else list(configuracao.modelos)
        )
    except ErroDeConfiguracao as erro:
        typer.echo(str(erro), err=True)
        raise typer.Exit(1) from erro

    destino = PASTA_RESULTADOS / (nome or datetime.now().strftime("%Y%m%d-%H%M%S"))
    with CacheRespostas(CAMINHO_CACHE) as cache:
        cliente = _cliente(configuracao, cache)
        executor = Executor(
            configuracao, cliente, cache, carregar_templates(), repeticoes=repeticoes
        )
        resumo = executor.executar(itens, escolhidos, destino / NOME_ARQUIVO_RESPOSTAS)

    _mostrar_resumo(len(itens), escolhidos, resumo, destino / NOME_ARQUIVO_RESPOSTAS)


@app.command()
def pontuar(
    execucao: ArgumentoExecucao,
    sem_juiz: Annotated[
        bool, typer.Option("--sem-juiz", help="Pontua só as questões objetivas.")
    ] = False,
    juiz: Annotated[
        str | None, typer.Option(help="Id do juiz. Padrão: o primeiro de juizes.yaml.")
    ] = None,
    prefixo_item: Annotated[
        str | None, typer.Option(help="Pontua só os itens cujo id começa com este prefixo.")
    ] = None,
    dados: OpcaoDados = PASTA_DADOS,
) -> None:
    """Pontua as respostas de uma execução e mostra o placar com intervalo de confiança."""
    pasta = PASTA_RESULTADOS / execucao
    arquivo_respostas = pasta / NOME_ARQUIVO_RESPOSTAS
    if not arquivo_respostas.exists():
        typer.echo(f"não encontrei {arquivo_respostas}; rode `avaliador executar` antes", err=True)
        raise typer.Exit(1)
    respostas = ler_respostas(arquivo_respostas)
    if prefixo_item:
        respostas = [r for r in respostas if r.item_id.startswith(prefixo_item)]
        if not respostas:
            typer.echo(f"nenhuma resposta com o prefixo {prefixo_item}", err=True)
            raise typer.Exit(1)
    itens = reconstruir_variantes(_itens_validos(dados), (r.item_id for r in respostas))
    configuracao = carregar_configuracao()

    with CacheRespostas(CAMINHO_CACHE) as cache:
        pontuadores = _pontuadores(configuracao, cache, juiz_id=juiz, usar_juiz=not sem_juiz)
        try:
            resultado = pontuar_respostas(itens, respostas, pontuadores)
        except CotaDiariaEsgotada as erro:
            typer.echo(f"{erro}. As avaliações já feitas estão no cache; rode amanhã.", err=True)
            raise typer.Exit(1) from erro
    salvar_pontuacoes(resultado.pontuacoes, pasta / NOME_ARQUIVO_PONTUACOES)

    tabela = tabela_de_pontuacoes(resultado.pontuacoes, itens)
    resultado_placar = placar(tabela)
    if not resultado_placar.empty:
        resultado_placar.to_csv(pasta / NOME_ARQUIVO_PLACAR)
    typer.echo(_formatar_placar(resultado_placar))
    _mostrar_vieses(tabela, configuracao)
    if resultado.sem_pontuador:
        typer.echo(f"\n{resultado.sem_pontuador} respostas abertas/redações aguardam o juiz")
    if resultado.ids_sem_item:
        typer.echo(f"itens que não estão mais no dataset: {', '.join(resultado.ids_sem_item)}")
    typer.echo(f"\npontuações em {pasta / NOME_ARQUIVO_PONTUACOES}")


@app.command()
def exportar(
    execucao: ArgumentoExecucao,
    destino: Annotated[Path, typer.Option(help="Pasta do leaderboard.")] = (
        leaderboard.PASTA_PUBLICADOS
    ),
    dados: OpcaoDados = PASTA_DADOS,
) -> None:
    """Gera o leaderboard.json (só números agregados) para o painel e o README."""
    arquivo = PASTA_RESULTADOS / execucao / NOME_ARQUIVO_PONTUACOES
    if not arquivo.exists():
        typer.echo(f"não encontrei {arquivo}; rode `avaliador pontuar {execucao}` antes", err=True)
        raise typer.Exit(1)
    pontuacoes = ler_pontuacoes(arquivo)
    itens = reconstruir_variantes(_itens_validos(dados), (p.item_id for p in pontuacoes))
    tabela = tabela_de_pontuacoes(pontuacoes, itens)
    configuracao = carregar_configuracao()
    nomes = {modelo.id: modelo.nome for modelo in configuracao.modelos}
    usados = tabela.drop_duplicates("item_base")
    conteudo = leaderboard.montar_leaderboard(
        placar(tabela),
        execucao=execucao,
        itens_por_categoria=dict(Counter(usados["categoria"])),
        nomes=nomes,
    )
    typer.echo(f"leaderboard em {leaderboard.salvar_leaderboard(conteudo, destino)}")


@app.command("extrair-enem")
def extrair_enem(
    prova: Annotated[Path, typer.Argument(exists=True, help="PDF do caderno de questões.")],
    gabarito: Annotated[Path, typer.Argument(exists=True, help="PDF do gabarito.")],
    ano: Annotated[int, typer.Option(help="Ano da prova.")],
    data_prova: Annotated[
        datetime, typer.Option(formats=["%Y-%m-%d"], help="Dia da prova (AAAA-MM-DD).")
    ],
    incluir_imagens: Annotated[
        bool, typer.Option(help="Mantém questões que parecem depender de imagem.")
    ] = False,
    dados: OpcaoDados = PASTA_DADOS,
) -> None:
    """Converte os PDFs do INEP em itens de múltipla escolha."""
    questoes = enem.separar_questoes(enem.extrair_texto_pdf(prova))
    respostas = enem.ler_gabarito(enem.extrair_texto_pdf(gabarito))
    itens = enem.questoes_para_itens(
        questoes, respostas, ano=ano, data_prova=data_prova.date(), incluir_imagens=incluir_imagens
    )
    por_categoria: dict[str, list[dict]] = defaultdict(list)
    for item in itens:
        por_categoria[item["categoria"]].append(item)
    for categoria_item, lista in por_categoria.items():
        destino = dados / Visibilidade.PUBLICO.value / categoria_item / f"enem_{ano}.jsonl"
        destino.parent.mkdir(parents=True, exist_ok=True)
        linhas = (json.dumps(item, ensure_ascii=False) for item in lista)
        destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        typer.echo(f"{len(lista)} itens em {destino}")
    typer.echo(f"{len(questoes)} questões lidas; {len(itens)} viraram itens")


@app.command("novo-item")
def novo_item(
    privado: Annotated[
        bool, typer.Option(help="Guarda em dados/privado (held-out, fora do git).")
    ] = False,
    dados: OpcaoDados = PASTA_DADOS,
) -> None:
    """Cria um item respondendo perguntas no terminal."""
    categoria = typer.prompt("Categoria", type=click.Choice([c.value for c in Categoria]))
    formato = typer.prompt("Formato", type=click.Choice([f.value for f in Formato]))
    bruto: dict = {
        "id": proximo_id(categoria, {item.id for item in validar_dataset(dados).itens}),
        "categoria": categoria,
        "formato": formato,
        "enunciado": typer.prompt("Enunciado"),
    }
    texto_base = typer.prompt("Texto base (Enter para nenhum)", default="", show_default=False)
    if texto_base:
        bruto["texto_base"] = texto_base
    if formato == Formato.MULTIPLA_ESCOLHA:
        bruto["alternativas"] = [
            {"letra": letra, "texto": typer.prompt(f"Alternativa {letra}")} for letra in "ABCDE"
        ]
        bruto["resposta_correta"] = typer.prompt("Letra correta", type=click.Choice(list("ABCDE")))
    elif formato == Formato.CLASSIFICACAO:
        rotulos = [r.strip() for r in typer.prompt("Rótulos separados por vírgula").split(",")]
        bruto["rotulos"] = rotulos
        bruto["resposta_correta"] = typer.prompt("Rótulo correto", type=click.Choice(rotulos))
    elif formato == Formato.RESPOSTA_ABERTA:
        bruto["resposta_referencia"] = typer.prompt("Resposta de referência")
    bruto["fonte"] = typer.prompt("Fonte", default="autoria própria")
    bruto["data_referencia"] = typer.prompt("Data de referência", default=date.today().isoformat())

    visibilidade = Visibilidade.PRIVADO if privado else Visibilidade.PUBLICO
    try:
        destino = adicionar_item(bruto, dados, visibilidade)
    except ItemRecusado as erro:
        typer.echo(f"item recusado: {erro}", err=True)
        raise typer.Exit(1) from erro
    typer.echo(f"item {bruto['id']} salvo em {destino}")


@app.command("validar-juiz")
def validar_juiz(
    arquivo: Annotated[
        Path, typer.Argument(exists=True, help="CSV com as colunas `humano` e `juiz`.")
    ],
) -> None:
    """Mede a concordância entre as notas do juiz e notas humanas do mesmo conjunto."""
    notas = pd.read_csv(arquivo)
    for chave, valor in relatorio_de_concordancia(notas["humano"], notas["juiz"]).items():
        typer.echo(f"{chave:22} {valor:.3f}" if isinstance(valor, float) else f"{chave:22} {valor}")


def _pontuadores(
    configuracao: Configuracao, cache: CacheRespostas, *, juiz_id: str | None, usar_juiz: bool
) -> dict[Formato, Pontuador]:
    exato = PontuadorExato()
    pontuadores: dict[Formato, Pontuador] = {
        Formato.MULTIPLA_ESCOLHA: exato,
        Formato.CLASSIFICACAO: exato,
    }
    if not usar_juiz or not configuracao.juizes:
        return pontuadores
    modelo_juiz = configuracao.modelo(juiz_id) if juiz_id else configuracao.juizes[0]
    provedor = configuracao.provedor_de(modelo_juiz)
    if not provedor.disponivel:
        typer.echo(f"juiz {modelo_juiz.id} sem chave no .env; redações ficam sem nota", err=True)
        return pontuadores
    cliente = _cliente(configuracao, cache)
    juiz = PontuadorJuiz(cliente, modelo_juiz, provedor, carregar_templates_do_juiz(), cache)
    return {**pontuadores, Formato.REDACAO: juiz, Formato.RESPOSTA_ABERTA: juiz}


def _cliente(configuracao: Configuracao, cache: CacheRespostas) -> ClienteLLM:
    modelos = (*configuracao.modelos, *configuracao.juizes)
    limitadores = criar_limitadores(configuracao.provedores, cache, modelos)
    return ClienteLLM(configuracao.provedores, limitadores)


def _itens_validos(dados: Path) -> tuple[Item, ...]:
    relatorio = validar_dataset(dados)
    if not relatorio.valido:
        typer.echo("dataset inválido; rode `avaliador validar` para ver os erros", err=True)
        raise typer.Exit(1)
    return relatorio.itens


def _formatar_placar(resultado: pd.DataFrame) -> str:
    if resultado.empty:
        return "nenhuma resposta pontuada"
    porcentagens = ["geral", "ic_inferior", "ic_superior"] + [
        c.value for c in Categoria if c.value in resultado.columns
    ]
    exibicao = resultado.copy()
    exibicao[porcentagens] = (exibicao[porcentagens] * 100).round(1)
    return "placar (% de acerto, IC de 95%)\n" + exibicao.to_string(na_rep="-")


def _mostrar_vieses(tabela: pd.DataFrame, configuracao: Configuracao) -> None:
    consistencia = consistencia_entre_variantes(tabela)
    if not consistencia.empty:
        typer.echo("\nconsistência entre variantes (mesmo resultado em todas as versões):")
        typer.echo((consistencia * 100).round(1).to_string())
        typer.echo("\nletras escolhidas (%):\n" + vies_de_posicao(tabela).to_string())
    cortes = {m.id: m.data_corte for m in configuracao.modelos if m.data_corte}
    contaminacao = acerto_antes_e_depois_do_corte(tabela, cortes)
    if not contaminacao.empty:
        typer.echo("\nacerto antes x depois da data de corte do treino:")
        typer.echo(contaminacao.to_string(index=False))


def _filtrar_itens(
    itens: Sequence[Item], categorias: Sequence[Categoria] | None, limite: int | None
) -> list[Item]:
    por_categoria: dict[Categoria, list[Item]] = defaultdict(list)
    for item in itens:
        if not categorias or item.categoria in categorias:
            por_categoria[item.categoria].append(item)
    return [item for lista in por_categoria.values() for item in lista[:limite]]


def _mostrar_resumo(
    total_itens: int, modelos: Sequence[ConfigModelo], resumo: ResumoExecucao, arquivo: Path
) -> None:
    typer.echo(
        f"\n{total_itens} itens x {len(modelos)} modelos -> {resumo.respondidas} respostas "
        f"({resumo.do_cache} do cache, {resumo.com_erro} com erro)"
    )
    if resumo.bloqueadas_por_privacidade:
        typer.echo(
            f"{resumo.bloqueadas_por_privacidade} itens privados não enviados "
            "a provedores que treinam com os dados"
        )
    if resumo.modelos_sem_chave:
        typer.echo(f"sem chave no .env: {', '.join(resumo.modelos_sem_chave)}")
    if resumo.provedores_sem_cota:
        typer.echo(
            f"cota esgotada em {', '.join(sorted(resumo.provedores_sem_cota))}: "
            f"{resumo.puladas_sem_cota} chamadas ficaram para amanhã"
        )
    typer.echo(f"respostas em {arquivo}")
