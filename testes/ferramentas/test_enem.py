from datetime import date
from pathlib import Path

import pytest

from avaliador.dados import carregar_arquivo
from avaliador.dominio import Visibilidade
from avaliador.ferramentas.enem import ler_gabarito, questoes_para_itens, separar_questoes

# Recorte no formato que o pypdf extrai das provas do INEP (com ruído de página).
PROVA = """QUESTÃO 01
Read the text. Which one is correct?
A one
B two
C three
D four
E five
QUESTÃO 01
Lea el texto. ¿Cuál es correcto?
A uno
B dos
C tres
D cuatro
E cinco
QUESTÃO 06
Expressões e termos utilizados no Amazonas
são retratados em livro e em camisetas, que valorizam o falar local
de forma bem-humorada e registram o vocabulário regional.
A reportagem apresenta duas iniciativas. Com temática em
comum, essas iniciativas
A
 recomendam produtos feitos por empreendedores da
região Norte.
B
 ressaltam diferenças entre o falar manauara e outros
falares.
*010175AZ5*
ENEM2024ENEM2024ENEM2024
C reverenciam o trabalho feito por pesquisadores brasileiros. 5 P1_1_Dia_LCT_REG_1_Azul.indd 5P1_1_Dia_LCT_REG_1_Azul.indd 5 28/08/2024 16:10:59
D destacam a descontração no jeito de ser do amazonense.
E valorizam o repertório linguístico do povo do Amazonas.
16 010175AZ.indb 16010175AZ.indb 16 23/08/2024 16:46:532
LINGUAGENS, CÓDIGOS E SUAS TECNOLOGIAS E REDAÇÃO • 1 • DIA • CADERNO 1 • AZUL •
QUESTÃO 07
Observe a charge a seguir, publicada em um jornal de grande circulação nacional.
A ironia
B crítica
C elogio
D denúncia
E humor
INSTRUÇÕES PARA A REDAÇÃO
1. O rascunho da redação deve ser feito no espaço apropriado.
PROPOSTA DE REDAÇÃO
A partir da leitura dos textos motivadores, redija texto dissertativo-argumentativo.
QUESTÃO 46
Nesta questão faltam alternativas porque elas eram imagens no caderno original da prova.
A
B
QUESTÃO 47
Durante o período colonial brasileiro, a economia açucareira concentrou-se no litoral nordestino.
A Correto.
B Errado.
C Parcial.
D Indefinido.
E Nenhum.
PROPOSTA DE REDAÇÃO
Texto que não é questão.
"""

GABARITO = """QUESTÃO GABARITO
1 C C
2 A D
6 E
7 B
47 A
"""


def test_separa_questoes_e_descarta_ruido_e_quebradas():
    questoes = {q.numero: q for q in separar_questoes(PROVA)}

    assert set(questoes) == {1, 6, 7, 47}  # 46 não tem 5 alternativas
    sexta = questoes[6]
    assert sexta.enunciado.startswith("Expressões e termos")
    assert sexta.enunciado.endswith("essas iniciativas")
    assert sexta.alternativas[1] == ("B", "ressaltam diferenças entre o falar manauara e outros falares.")
    assert "ENEM2024" not in " ".join(t for _, t in sexta.alternativas)
    assert sexta.alternativas[2] == ("C", "reverenciam o trabalho feito por pesquisadores brasileiros.")
    assert sexta.alternativas[4][1] == "valorizam o repertório linguístico do povo do Amazonas."
    assert "Read the text" in questoes[1].enunciado  # fica a 1ª versão (inglês)
    assert questoes[7].alternativas[4] == ("E", "humor")  # redação no meio não vaza
    assert 47 in questoes  # e as questões depois da redação continuam sendo lidas


def test_le_gabarito():
    assert ler_gabarito(GABARITO) == {1: "C", 2: "A", 6: "E", 7: "B", 47: "A"}


def test_converte_em_itens_validos(tmp_path):
    itens = questoes_para_itens(
        separar_questoes(PROVA), ler_gabarito(GABARITO), ano=2024, data_prova=date(2024, 11, 3)
    )

    por_id = {item["id"]: item for item in itens}
    assert set(por_id) == {"enem-2024-q006", "enem-2024-q047"}  # sem língua estrangeira e charge
    assert por_id["enem-2024-q006"]["categoria"] == "interpretacao"
    assert por_id["enem-2024-q047"]["categoria"] == "conhecimento"
    assert por_id["enem-2024-q006"]["resposta_correta"] == "E"
    _validar_no_esquema(itens, tmp_path)


def test_incluir_imagens():
    itens = questoes_para_itens(
        separar_questoes(PROVA),
        ler_gabarito(GABARITO),
        ano=2024,
        data_prova=date(2024, 11, 3),
        incluir_imagens=True,
    )

    assert "enem-2024-q007" in {item["id"] for item in itens}


def _validar_no_esquema(itens, pasta: Path):
    import json

    arquivo = pasta / "itens.jsonl"
    arquivo.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in itens), encoding="utf-8")
    carga = carregar_arquivo(arquivo, Visibilidade.PUBLICO)
    assert carga.erros == (), carga.erros
    assert len(carga.itens) == len(itens)


@pytest.mark.parametrize("numero", [6, 47])
def test_questoes_reais_nao_parecem_imagem(numero):
    questoes = {q.numero: q for q in separar_questoes(PROVA)}

    assert not questoes[numero].possivel_imagem
