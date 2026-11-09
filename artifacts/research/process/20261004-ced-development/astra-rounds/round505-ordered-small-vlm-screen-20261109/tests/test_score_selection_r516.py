import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import pytest
SOURCE=Path(__file__).resolve().parents[1]/"implementation/score_candidate.py"
sys.path.insert(0,str(SOURCE.parent))
spec=importlib.util.spec_from_file_location("score_selection_test",SOURCE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(module,"HERE",tmp_path)
    out=tmp_path/"candidates/03-lens";out.mkdir(parents=True)
    protocol=out/"protocol.json";protocol.write_text('{}')
    run=out/"run-01.json";run.write_text(json.dumps({"protocol_sha256":hashlib.sha256(protocol.read_bytes()).hexdigest()}))
    return out


def test_default_and_explicit_selection(tmp_path,monkeypatch):
    out=fixture(tmp_path,monkeypatch)
    run,protocol,output=module.resolve_score_inputs("03-lens",None,None,"score-03.json")
    assert (run,protocol,output)==(out/"run-01.json",out/"protocol.json",out/"score-03.json")
    (out/"run-02.json").write_bytes(run.read_bytes());(out/"protocol-r514.json").write_bytes(protocol.read_bytes())
    selected=module.resolve_score_inputs("03-lens",out/"run-02.json",out/"protocol-r514.json","score-next.json")
    assert selected[0].name=="run-02.json" and selected[1].name=="protocol-r514.json"


@pytest.mark.parametrize("name",["../score.json","score..json","run-01.json","active.local.json"])
def test_output_unsafe_or_existing_rejected(tmp_path,monkeypatch,name):
    out=fixture(tmp_path,monkeypatch)
    if name=="active.local.json":(out/name).write_text('original')
    with pytest.raises((ValueError,FileExistsError)):
        module.resolve_score_inputs("03-lens",None,None,name)


def test_pair_and_hash_required(tmp_path,monkeypatch):
    out=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):module.resolve_score_inputs("03-lens",out/"run-01.json",None,"x.json")
    (out/"protocol.json").write_text('{"changed":true}')
    with pytest.raises(ValueError):module.resolve_score_inputs("03-lens",None,None,"x.json")


def test_cross_candidate_and_progress_rejected(tmp_path,monkeypatch):
    out=fixture(tmp_path,monkeypatch);other=tmp_path/"candidates/elsewhere";other.mkdir();p=other/"run.json";p.write_text('{}')
    with pytest.raises(ValueError):module.resolve_score_inputs("03-lens",p,out/"protocol.json","x.json")
    progress=out/"run-progress.local.json";progress.write_text('{}')
    with pytest.raises(ValueError):module.resolve_score_inputs("03-lens",progress,out/"protocol.json","x.json")
