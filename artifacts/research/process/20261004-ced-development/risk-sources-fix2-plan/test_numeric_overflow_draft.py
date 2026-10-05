"""Unexecuted draft to append only after ROOT's post-review fix2 handoff."""


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("location", ["actuator", "dt"])
def test_oversized_integer_returns_typed_invalid_with_complete_inventory(
    tmp_path: Path, sign: int, location: str
) -> None:
    case, directory = fixture_case(tmp_path)
    value = sign * 10**500
    if location == "actuator":
        path = directory / "raw-actuators.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[5]["pre_gravity_bias_nm"][0] = value
        rewrite_jsonl(path, rows)
        case = replace(case, original_file_hashes=hashes(directory))
    else:
        case = replace(case, context={**plain(case.context), "physics_dt_s": value})
    result = registered(tmp_path, case).audit("fixture", scope="RAW_EXECUTION")
    assert result.status == "INVALID"
    assert result.counts["allocated"] == result.counts["unknown"] == 1
    assert result.counts["reconstructed"] == result.counts["physical_success"] == 0
    assert dict(result.original_file_hashes) == {
        f"{case.case_id}/{name}": digest for name, digest in case.original_file_hashes.items()
    }
    assert not result.verified_original_file_hashes
    assert result.formal_source_eligible is False
