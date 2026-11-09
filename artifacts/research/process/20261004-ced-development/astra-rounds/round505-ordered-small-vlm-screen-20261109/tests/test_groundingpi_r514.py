import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
from preflight_groundingpi_jit_r514 import cumulative


def test_prior_generation_and_current_indices():
    assert cumulative(1,99,101)==101
    with pytest.raises(ValueError):cumulative(1,100,101)


def test_third_load_rejected():
    assert cumulative(1,0,2)==2
    with pytest.raises(ValueError):cumulative(1,1,2)
