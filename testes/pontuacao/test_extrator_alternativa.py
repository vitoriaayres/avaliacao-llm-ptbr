import pytest

from avaliador.pontuacao import extrair_opcao

LETRAS = ("A", "B", "C", "D", "E")
ROTULOS = ("irônica", "literal")


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("O INEP aplica o exame.\n\nResposta: B", "B"),
        ("Explicação longa...\n\n**Resposta: B**", "B"),  # gpt-oss-120b usa negrito
        ("Resposta: (C)", "C"),
        ("Resposta: d) CAPES", "D"),
        ("Resposta: A - MEC", "A"),
        ("Resposta: letra E.", "E"),
        ("RESPOSTA FINAL: alternativa b", "B"),
        ("Portanto, a resposta correta é a letra C.", "C"),
        ("Primeiro pensei Resposta: A\nmas revendo...\nResposta: B", "B"),  # vale a última
        ("B", "B"),  # texto que é só a letra
        ("Pensando...\n\nB)", "B"),
        ("Resposta: F", None),  # letra que não existe no item
        ("Resposta: INEP", None),  # escreveu o texto em vez da letra
        ("Acho que é a B, mas pode ser a C.", None),  # sem 'Resposta:' e ambíguo: não chuta
        ("Desculpe, só posso responder perguntas de programação.", None),
        ("", None),
    ],
)
def test_letras(texto, esperada):
    assert extrair_opcao(texto, LETRAS) == esperada


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("Ela usa o oposto do que sente.\n\nResposta: irônica", "irônica"),
        ("Resposta: Irônica.", "irônica"),
        ("Resposta: ironica", "irônica"),  # sem acento
        ("Resposta: a fala é irônica", "irônica"),
        ("literal", "literal"),
        ("Resposta: nem irônica nem literal", None),  # cita os dois: ambíguo
        ("Resposta: sarcástica", None),
    ],
)
def test_rotulos(texto, esperada):
    assert extrair_opcao(texto, ROTULOS) == esperada


def test_rotulo_que_contem_outro():
    rotulos = ("irônica", "não irônica")

    assert extrair_opcao("Resposta: não irônica", rotulos) == "não irônica"
    assert extrair_opcao("Resposta: irônica", rotulos) == "irônica"
