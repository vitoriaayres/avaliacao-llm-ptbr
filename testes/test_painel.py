from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from avaliador.ferramentas.leaderboard import montar_leaderboard, salvar_leaderboard

APP = str(Path(__file__).resolve().parents[1] / "painel" / "app.py")


def test_painel_sem_leaderboard(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADERBOARD", str(tmp_path / "nao-existe.json"))

    app = AppTest.from_file(APP, default_timeout=30).run()

    assert not app.exception
    assert "Nenhum leaderboard" in app.info[0].value


def test_painel_com_leaderboard(tmp_path, monkeypatch):
    placar = pd.DataFrame(
        {
            "geral": [0.8, 0.6],
            "ic_inferior": [0.7, 0.5],
            "ic_superior": [0.9, 0.7],
            "n_itens": [70, 70],
            "empata_com_lider": [True, False],
            "conhecimento": [0.8, 0.6],
        },
        index=pd.Index(["groq/a", "groq/b"], name="modelo"),
    )
    conteudo = montar_leaderboard(
        placar, execucao="teste", itens_por_categoria={"conhecimento": 70}, nomes={}
    )
    monkeypatch.setenv("LEADERBOARD", str(salvar_leaderboard(conteudo, tmp_path)))

    app = AppTest.from_file(APP, default_timeout=30).run()

    assert not app.exception
    assert app.metric[0].value == "groq/a"
    assert app.metric[1].value == "80.0%"
