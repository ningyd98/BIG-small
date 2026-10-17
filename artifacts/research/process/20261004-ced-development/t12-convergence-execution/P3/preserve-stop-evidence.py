"""Preserve P3 public protocol discrepancy without tests or product edits."""
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

repo = Path.cwd()
out = Path(__file__).resolve().parent
base = Path("artifacts/research/process/20261004-qwen38max-closed-loop")
hand = Path("artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007")
stamp = datetime.now(timezone.utc).isoformat()


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(name, data):
    with (out / name).open("x") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


owned = ["configs/research/ced_roles.yaml", "src/cloud_edge_robot_arm/vision/role_models.py",
         "tests/test_rgbd_role_models.py", "tests/test_ced_runtime_binding.py"]
for name in owned:
    source = Path(name)
    assert source.read_bytes() == (out / "source-before" / name).read_bytes()
    destination = out / "source-after" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
(out / "source.diff").write_bytes(b"")
prepared = json.loads((hand / "p3-prepared-inputs.json").read_text())
after = [{**pin(Path(row["path"])), "matches_original": pin(Path(row["path"]))["sha256"] == row["sha256"]}
         for row in prepared["input_pins"]]
assert len(after) == 9 and all(row["matches_original"] for row in after)
save("input-check-after.json", after)
freeze = {"time_utc": stamp, "status": "SOURCE_UNCHANGED_AND_STATIC_NEEDS_ASTRA",
          "owned": [pin(Path(name)) for name in owned],
          "protected_cost_ledger": pin(Path("src/cloud_edge_robot_arm/research/cost_ledger.py"))}
save("source-freeze.json", freeze)
req_path = base / "run-v2/cases/case-07/api/01/request.json"
receipt_path = base / "run-v2/cases/case-07/api/01/receipt.json"
request = json.loads(req_path.read_text())
receipt = json.loads(receipt_path.read_text())
assert receipt["ok"] and receipt["http_status"] == 200
assert receipt["request_sha256"] == pin(req_path)["sha256"]
model = json.loads((base / "run-v2/model.json").read_text())
protocol = json.loads((base / "run-v2/protocol.json").read_text())
verification = json.loads((base / "verification.json").read_text())
assert request["enable_thinking"] is False and model["coordinate_system"] == "normalized_1000"
assert verification["valid"] is True
source = Path("src/cloud_edge_robot_arm/vision/planner.py")
tree = ast.parse(source.read_text(), type_comments=True)
method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_request_visual")
compatible_body = next(node.value for node in ast.walk(method) if isinstance(node, ast.Assign)
                       and isinstance(node.value, ast.Dict)
                       and {key.value for key in node.value.keys if isinstance(key, ast.Constant)} ==
                       {"model", "messages", "temperature", "max_tokens", "response_format"})
fields = [key.value for key in compatible_body.keys]
assert "enable_thinking" not in fields
segment = "\n".join(source.read_text().splitlines()[method.lineno-1:method.end_lineno]) + "\n"
(out / "planner-request-visual-source.txt").write_text(segment)
public = {"request_pin": pin(req_path), "receipt_pin": pin(receipt_path),
          "receipt_request_hash_matches": True, "receipt_http_status": 200,
          "actual_public_fields": {key: request[key] for key in (
              "model", "temperature", "max_tokens", "enable_thinking", "response_format")},
          "image_count": sum(part["type"] == "image_url" for message in request["messages"]
                             if isinstance(message["content"], list) for part in message["content"]),
          "model_public_settings": model, "verification": {key: verification[key] for key in (
              "valid", "model_calls", "invoice_cost_cny", "formal_g1")},
          "pins": [pin(base / name) for name in (
              "acceptance.md", "verification.json", "run-v2/model.json", "run-v2/protocol.json")],
          "secrets_read_copied_printed": False}
save("original-success-public-evidence.json", public)
gap = {"status": "NEEDS_ASTRA_P3_COMPATIBLE_WIRE_THINKING_FIELD",
       "discovered_by": "read-only public payload and current source AST comparison",
       "original_request": public["request_pin"], "original_enable_thinking": False,
       "current_planner": pin(source), "method": "RGBDPlannerAdapter._request_visual",
       "method_lines": [method.lineno, method.end_lineno],
       "compatible_body_lines": [compatible_body.lineno, compatible_body.end_lineno],
       "current_wire_keys": fields, "enable_thinking_present": False,
       "method_exact_source": pin(out / "planner-request-visual-source.txt"),
       "method_AST": ast.dump(method, include_attributes=False),
       "scope_expansion_required": str(source),
       "repair_not_attempted": True, "dynamic_counterexample_runs": 0,
       "note": "Static protocol gap; no executed failure or new provider response claimed. Existing generation kwargs do not serialize an enable_thinking wire field."}
save("failure-receipt.json", gap)
relevant = [*owned[:2], "src/cloud_edge_robot_arm/vision/planner.py",
            "src/cloud_edge_robot_arm/vision/model_resolver.py", "src/cloud_edge_robot_arm/vision/messages.py",
            "src/cloud_edge_robot_arm/vision/runtime_binding.py", "scripts/probe_rgbd_roles.py"]
source_delta = [{"path": name, "old_success_source_sha256": protocol["source_sha256"].get(name),
                 "current": pin(Path(name)),
                 "old_and_current_match": protocol["source_sha256"].get(name) == pin(Path(name))["sha256"]}
                for name in relevant]
delta = {"status": gap["status"], "prior_success_availability_supported": True,
         "current_source_role_probe_qualified": False,
         "coordinate_system": {"prior": "normalized_1000", "current": "pixel", "software_fix_applied": False},
         "image_size": {"prior": [320, 240], "current": [320, 240], "prior_request_images": public["image_count"]},
         "model_family": {"prior": "qwen3.8-max", "current": "qwen3.8-max", "immutable_weight_hash": None},
         "successful_request_config": public["actual_public_fields"],
         "current_generation_binding": "Profile temperature/max_tokens are consumed by original factory; no real profile/secret opened",
         "thinking": {"prior_wire": False, "current_wire_field": "ABSENT", "next": "actual Astra must authorize minimal planner scope"},
         "grasp_profile": {"prior": model["grasp_profile"], "current": "mujoco_upright_box_v2", "old_acceptance_reused_for_new_profile": False},
         "role_source_delta": source_delta,
         "cost": {"old_actual_invoice_cny": None, "ledger_modified": False, "new_sent_model_requests": 0,
                  "all_sent_timeout_retry_rule_preserved": "Read-only current implementation, new named CPU test not yet run"},
         "actual": {"authorized": False, "request_count": 0, "renderer_calls": 0,
                    "future_contract": "cold + 3warm =4 only after P8 affected sources static and separate ROOT dispatch"}}
save("role-delta.json", delta)
ledger = {"RED": 0, "owned_GREEN": 0, "formatter": 0, "ruff": 0, "mypy": 0,
          "new_CPU_test_cases": 0, "new_CPU_fixture_files": 0, "actual_model_requests": 0,
          "new35call_runs": 0, "actual_render_or_physics": 0, "network": 0, "Git": 0, "subagents": 0,
          "product_or_test_edits": 0, "stop_before": "writing three named tests/RED; planner out-of-scope wire gap discovered while reading prerequisites"}
save("run-ledger.json", ledger)
report = {"status": gap["status"], "author": "/root/sol_t12_p1", "requested_model": "gpt-6.1-sol",
          "requested_reasoning_effort": "high", "runtime_model_independently_verified": False,
          "software_verified": False, "independent_review_passed": False, "formal_accepted": False,
          "all9_inputs_unchanged": True, "source_freeze": freeze,
          "gap": {key: value for key, value in gap.items() if key != "method_AST"},
          "public_success_evidence": "original-success-public-evidence.json", "delta": "role-delta.json",
          "run_ledger": ledger, "source_diff_empty": True,
          "next": "ROOT actual Astra plan; do not implement until P4 actual/readout terminal and new ROOT dispatch",
          "P4_stability": "All shared product sources unchanged and static; ROOT may prepare existing-source P4",
          "secrets": "No existing credential/profile store inspected; only public original request/config/source evidence",
          "tests_not_written_or_run": ["test_ced_max_reuses_successful_normalized_transport",
                                       "test_existing_max_success_is_not_new_source_freeze",
                                       "test_role_cost_delta_preserves_all_sent_requests"]}
save("step-report.json", report)
(out / "step-report.md").write_text(f"""# P3 软件实施停点

状态：`{gap['status']}`。9输入pins与brief/dispatch匹配；4owned前后字节完全相同，source.diff为空，尚未写测试或改配置/产品。

旧成功case07真实HTTP200请求明确包含enable_thinking=false（request SHA {public['request_pin']['sha256']}）。现行planner.py SHA {gap['current_planner']['sha256']} 的_request_visual兼容分支在{compatible_body.lineno}–{compatible_body.end_lineno}行只构造model/messages/temperature/max_tokens/response_format，没有thinking字段；完整方法原文和AST/行号已保存。既有role工厂仅绑定profile temperature/num_predict，其注解或hash不能使缺失wire字段出现。

planner.py不属于当前四owned，满足Task3“保留成功thinkingfalse”需要先由实际Astra制定最小扩源修复/验证计划。已即时告ROOT，未写wrapper、未伪造thinkingfalse、未执行动态探针或请求。ROOT确认保持停止，并将修复派单排在P4actual/readout终态之后。

原成功可用性、35请求与独立valid=true原件只读引用，不当现行source/角色冻结。坐标pixel→normalized_1000尚未实施；320×240双图不变；grasp v1→当前v2差异保留，旧成功不授新域资格。公开差异及相关source索引见role-delta.json。实际profile/secret不读取；最终cold+3warm四请求待P8源码静止与ROOT单独调度。

RED/GREEN/formatter/static/mypy及新增CPU节点/fixture分母全0；模型/网络/渲染/physics/Git/子代理新增0。成本ledger保持只读，所有sent/超时/retry与未知账单null规则未改，未声称新测试通过。所有失败/历史证据不覆盖。源码静止，P3软件和正式验收未完成；交ROOT→实际Astra。
""")
(out / "public-delta.md").write_text("""# 旧成功→现行T12公开差异

| 项目 | 原成功公开值 | 现行或边界 |
|---|---|---|
| 模型 | qwen3.8-max，35真实请求/独立valid | 别名仍Max；不猜服务端不可变权重 |
| RGB-D | 两图320×240 | ced.roles相同，未新实际调用 |
| 坐标 | normalized_1000 | ced.roles为pixel，待实施 |
| 温度/token | 0/512 | 原工厂消费既有profile；未打开实际profile |
| thinking | wire enable_thinking=false | compatible wire字段缺失，超出四owned，NEEDS_ASTRA |
| 抓取域 | mujoco_upright_box_v1 | 当前v2；旧成功不能当v2实证 |
| source/角色 | 历史source索引 | 当前source逐项差异见JSON，旧成功不当新冻结 |
| 成本 | invoice null | ledger只读，sent/timeout/retry不能删，未新发送 |
| 角色actual | 历史连接/操作成功 | cold+3warm需P8源静止与ROOT后续实际调度 |
""")
with (out / "progress.md").open("a") as stream:
    stream.write("\n发现新wire合同差异：旧request enable_thinking:false，现行planner compatible分支无该字段；planner不在四owned。立即停告ROOT，ROOT确认下一实际Astra最小扩源并排P4actual/readout后。NEEDS_ASTRA报告/实际字段/sourcepin/原文/AST/差异表/前后件/空diff/9pins复核/账本保存。产品和测试0改写，RED/GREEN/static均0；全部共享源静止。\n")
bounded = sorted(path for path in out.rglob("*") if path.is_file())
delivery = [str(path) for path in bounded] + [str(out / name) for name in ("delivery-paths.txt", "report-evidence-pins.json")]
(out / "delivery-paths.txt").write_text("\n".join(sorted(set(delivery))) + "\n")
save("report-evidence-pins.json", {"bounded_files": [pin(path) for path in bounded],
                                 "delivery_index": pin(out / "delivery-paths.txt"),
                                 "product_delivery_files": [], "CPU_or_actual_originals_generated": 0})
print(json.dumps({"status": gap["status"], "request": public["request_pin"],
                  "planner": gap["current_planner"], "body_lines": gap["compatible_body_lines"],
                  "source_freeze": pin(out / "source-freeze.json"),
                  "report": pin(out / "step-report.json")}, ensure_ascii=False))
