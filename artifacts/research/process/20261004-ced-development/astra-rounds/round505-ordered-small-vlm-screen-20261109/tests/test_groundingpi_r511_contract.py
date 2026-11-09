import io
import sys
import tarfile
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"implementation"))
from prepare_groundingpi_r511 import extract_regular


def archive(path,name="LICENSE",kind=tarfile.REGTYPE):
    with tarfile.open(path,"w") as tar:
        info=tarfile.TarInfo(name);info.type=kind;data=b"proof";info.size=len(data) if kind==tarfile.REGTYPE else 0
        tar.addfile(info,io.BytesIO(data) if info.size else None)


def test_rootless_archive_uses_exact_destination(tmp_path):
    path=tmp_path/"test.tar";archive(path);destination=tmp_path/"vendor/transformers"
    extract_regular(path,destination,{"LICENSE":__import__('hashlib').sha256(b"proof").hexdigest()})
    assert (destination/"LICENSE").read_bytes()==b"proof" and not (tmp_path/"vendor/LICENSE").exists()


@pytest.mark.parametrize("name,kind",[("/escape",tarfile.REGTYPE),("../escape",tarfile.REGTYPE),("a/../escape",tarfile.REGTYPE),("link",tarfile.SYMTYPE),("hard",tarfile.LNKTYPE),("fifo",tarfile.FIFOTYPE)])
def test_bad_members_rejected_before_any_write(tmp_path,name,kind):
    path=tmp_path/"bad.tar";archive(path,name,kind);destination=tmp_path/"vendor/transformers"
    with pytest.raises(ValueError):extract_regular(path,destination,{})
    assert not destination.exists()
