from copy import deepcopy
from pathlib import Path
import runpy

import numpy as np
import pytest


def code():
    return runpy.run_path(str(Path(__file__).with_name("static_screen.py")))


def test_mount_identification_rejects_wrong_asset_and_wrong_transform():
    c=code()
    geometry=c["registrations"]()[30]
    c["check_registration"](geometry,30)
    old=deepcopy(geometry);old["pose_marker"]["marked_asset_sha256"]=c["radial"].details(15)["asset_sha256"]
    with pytest.raises(ValueError): c["check_registration"](old,30)
    old=deepcopy(geometry);old["development_dual"]["markers"]["8"]["object_T_marker"][3]=.115
    with pytest.raises(ValueError): c["check_registration"](old,30)
    old=deepcopy(geometry);old["development_dual"]["markers"]["7"]["marker_id"]=8
    with pytest.raises(ValueError): c["check_registration"](old,30)


def test_entire_contact_matrix_covers_robot_versus_support_region_and_object():
    c=code();g=c["registrations"]()[30];m=c["old"].checked_model(c["ROOT"]/g["asset_path"],g)
    pairs={(a,b):gate for a,b,_,_,gate in c["pairs"](m)}
    for arm in c["old"].cam.arm_geometries(m).values():
        for partner in ["table","target_region_geom","object_geom",*c["old"].PARTS]:
            h=next(key for key in pairs if set(key)=={arm,partner})
            assert pairs[h] is (partner!="object_geom" or arm not in c["old"].FINGERS)
    assert pairs["object_geom","table"] is False

