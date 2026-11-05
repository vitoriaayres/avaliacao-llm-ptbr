import pytest

from avaliador.dominio import Pontuacao, Resposta, UsoTokens


class TestResposta:
    def test_resposta_com_texto(self):
        resposta = Resposta("item-1", "groq/gpt-oss-120b", texto="B", latencia_ms=320.0)
        assert resposta.sucesso

    def test_resposta_com_erro(self):
        resposta = Resposta("item-1", "m", texto=None, latencia_ms=0.0, erro="timeout")
        assert not resposta.sucesso

    def test_texto_e_erro_juntos(self):
        with pytest.raises(ValueError, match="OU"):
            Resposta("item-1", "m", texto="B", latencia_ms=1.0, erro="timeout")

    def test_sem_texto_e_sem_erro(self):
        with pytest.raises(ValueError, match="OU"):
            Resposta("item-1", "m", texto=None, latencia_ms=1.0)

    def test_tentativa_comeca_em_um(self):
        with pytest.raises(ValueError, match="tentativa"):
            Resposta("item-1", "m", texto="B", latencia_ms=1.0, tentativa=0)

    def test_tokens_negativos(self):
        with pytest.raises(ValueError, match="negativa"):
            UsoTokens(entrada=-1)


class TestPontuacao:
    @pytest.mark.parametrize("nota", [0.0, 0.5, 1.0])
    def test_notas_validas(self, nota):
        assert Pontuacao("item-1", "m", "exato", nota).nota == nota

    @pytest.mark.parametrize("nota", [-0.01, 1.01, 840])
    def test_nota_fora_do_intervalo(self, nota):
        with pytest.raises(ValueError, match="entre 0 e 1"):
            Pontuacao("item-1", "m", "exato", nota)
