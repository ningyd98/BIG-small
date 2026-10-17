from pathlib import Path
import json
import hashlib
import base64
import difflib
import signal

def _timeout(_signum, _frame):
    raise TimeoutError("R175 preparation metadata exceeded the authorized 120-second limit")

signal.signal(signal.SIGALRM, _timeout)
signal.alarm(120)

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
PROCESS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
D158 = PROCESS / "round158-p6-stage-b-local-temporal-publication-20261013"
D166 = PROCESS / "round166-p6-t1-legacy-supervision-claim-timing-20261013"
D175 = PROCESS / "round175-p6-t1-transitive-memory-fixture-closure-20261014"
TASK = D158 / "implementation/t1"
PLAN_SHA = "990947b3491a5fdd432c75fbde321cccd417681adf3cec062b4252a8ef100e63"
MD_SHA = "702d470bf1d5d36709c16505a9caabbaa5dbb2c93457cfd4852d5b6ad31e2101"
CANDIDATE_TEST_PIN = {"path":"/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_operational_runtime_closure.py","bytes":135950,"sha256":"bb22fb6abd3f047de06da30252ec8c3aeef83082fba934d249dd54187fd9e688"}
CHANGES = [
  {
    "before": "def _b_legacy_sources(monkeypatch):\n    \"\"\"Use real pure builders/codecs and one real Memory repository; no worker.\"\"\"\n    import importlib\n    from datetime import timedelta\n\n    from cloud_edge_robot_arm.contracts.models import RecoveryBudget\n    from cloud_edge_robot_arm.edge.recovery.verification_router import (\n        VerificationBudget,\n        VerificationBudgetState,\n    )\n    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (\n        InMemoryEventAutonomyRepository,\n    )\n    from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot\n    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation\n    from tests import test_visual_bootstrap as bootstrap_fixture\n    from tests import test_visual_owner_repository as owner_fixture\n    from tests import test_visual_verification_repository as route_fixture\n\n    data = owner_fixture.values()\n    original = data[\"original\"]\n    basis = original.registered_at + timedelta(seconds=0.2)\n    _b_utc(monkeypatch, basis)\n    state = VerificationBudgetState(\n        3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40.0)\n    )\n    retry = RecoveryBudget(\n        budget_id=\"r158-legacy-original-retry\",\n        task_id=original.identity.task_id,\n        task_total_retry_limit=2,\n        per_step_retry_limit=1,\n        per_skill_retry_limit=2,\n        effective_retry_limit=2,\n        remaining_retries=2,\n        retry_deadline=original.verification_deadline_at,\n        scene_version=original.contract.scene_version,\n        created_at=original.registered_at,\n        updated_at=original.registered_at,\n    )\n    # Reuse the existing immutable original builder with the actual lease identity\n    # and the exact role bundle consumed by the supervision definition.\n    lease = WorkerLeaseObservation(\n        original.identity.job_id, original.identity.run_id, original.identity.worker_id,\n        original.identity.lease_id, original.identity.attempt,\n        original.registered_at - timedelta(seconds=1), basis,\n        original.registered_at + timedelta(seconds=90), \"a\" * 64, \"b\" * 64, \"c\" * 64,\n    )\n    cloud = RoleProviderSnapshot(\n        \"CLOUD\", \"software-provider\", \"LOCAL_HOST\", \"software-model\",\n        None, None, None, \"d\" * 64, original.source_hashes,\n    )\n    bundle = RoleModelBundle(cloud, \"software-edge\", \"e\" * 64, \"f\" * 64)\n    owner_module = importlib.import_module(\"cloud_edge_robot_arm.vision.owner_registration\")\n    identity = lease.identity(\n        episode_id=original.identity.episode_id, task_id=original.identity.task_id,\n        plan_id=original.identity.plan_id, robot_id=original.identity.robot_id,\n    )\n    original = owner_module.freeze_original_visual_plan(\n        **{**original.freeze_inputs(), \"identity\": identity, \"role_bundle_hash\": bundle.digest()}\n    )\n    data[\"original\"], data[\"current_identity\"] = original, identity\n    repo = InMemoryEventAutonomyRepository()\n    try:\n        publication = repo.initialize_visual_owner_if_absent(\n            original, data[\"source_checkpoint\"], state, retry\n        )\n        initial_publication = publication\n        data[\"publication\"] = publication\n        owner_module = importlib.import_module(\"cloud_edge_robot_arm.vision.owner_registration\")\n        grounding = owner_module.bind_step_grounding(**{\n            key: value for key, value in data.items() if key != \"publication\"\n        })\n        route_input_v2 = route_fixture.request_for(data)\n        raw_v1 = route_input_v2.to_payload()\n        raw_v1[\"schema_version\"] = \"visual.verification.route-input.v1\"\n        del raw_v1[\"grounding_receipt\"]\n        route_module = route_fixture.api()\n        route_input_v1 = route_module.VisualVerificationRouteInput.from_payload(raw_v1)\n        historical_completion = route_fixture.software_completion(data)\n        route_result = repo.route_visual_verification_if_current(request=route_input_v2)\n        assert route_result is not None, \"legacy fixture must enter the actual source route\"\n        assert route_result.write_disposition == \"NEW_COMMIT\"\n        historical_route_payload = route_result.record.to_payload()\n        assert historical_route_payload[\"input\"] == route_input_v2.to_payload()\n        assert route_input_v2.to_payload()[\"publication\"] == initial_publication.to_payload()\n        current_publication = repo.get_visual_owner_publication(original.identity.task_id)\n        current_pool = repo.get_verification_budget(original.identity.task_id)\n        current_retry = repo.get_retry_budget(original.identity.task_id)\n        current_checkpoint = repo.get_latest_execution_checkpoint(original.identity.task_id)\n        assert all(value is not None for value in (\n            current_publication, current_pool, current_retry, current_checkpoint\n        )), \"actual current task source group must remain complete\"\n        assert current_publication.owner_revision == initial_publication.owner_revision + 1\n        assert current_publication.state_generation == initial_publication.state_generation + 1\n        assert historical_route_payload[\"produced_publication_hash\"] == current_publication.digest()\n        assert historical_route_payload[\"produced_publication\"] == current_publication.to_payload()\n        assert current_publication.identity == original.identity == initial_publication.identity\n        assert current_publication.original_plan_hash == initial_publication.original_plan_hash == original.digest()\n        assert current_pool.content_hash == current_publication.verification_budget.content_hash\n        assert _b_canonical(current_pool.to_payload()) == _b_canonical(\n            current_publication.verification_budget.to_payload()\n        )\n        assert _b_canonical(current_pool.to_payload()) == _b_canonical(\n            historical_route_payload[\"after_verification_budget\"]\n        )\n        assert current_pool.state.remaining_reobservations == (\n            initial_publication.verification_budget.state.remaining_reobservations - 1\n        )\n        assert current_pool.state.remaining_retries == initial_publication.verification_budget.state.remaining_retries\n        assert current_pool.state.limits == initial_publication.verification_budget.state.limits\n        assert current_pool.state.deadline_at == original.verification_deadline_at\n        assert _b_canonical(current_retry.model_dump(mode=\"json\")) == _b_canonical(\n            current_publication.retry_budget.model_dump(mode=\"json\")\n        ) == _b_canonical(retry.model_dump(mode=\"json\"))\n        assert current_checkpoint.checkpoint_hash == current_publication.checkpoint.checkpoint_hash\n        assert current_checkpoint.checkpoint_hash == initial_publication.checkpoint.checkpoint_hash\n        assert grounding.owner_revision == data[\"owner_revision\"]\n        assert grounding.state_generation == data[\"state_generation\"]\n        # The previous request/binding stay historical. Public getters supply\n        # the distinct current snapshot consumed by supervision and exports.\n        publication = current_publication\n        data[\"publication\"] = current_publication\n        completion = historical_completion\n        supervision_module = importlib.import_module(\n            \"cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision\"\n        )\n        supervision_definition = supervision_module.VisualSupervisionDefinition(\n            original=original, publication=publication, lease=lease,\n            task_started_at=original.registered_at, task_timeout_s=60.0,\n            supervision_period_s=0.2, model_snapshot_hash=\"1\" * 64, role_bundle=bundle,\n        )\n        supervision_record = repo.initialize_visual_supervision_if_absent(supervision_definition)\n        supervision_request = supervision_module.VisualSupervisionTransitionInput(\n            record=supervision_record, original=original, publication=publication, lease=lease,\n            robot_state=data[\"online\"].robot_state, step_id=\"move\", cursor=1,\n            kind=\"RESERVE_CAPTURE\", event_key=\"r158-supervision-capture\",\n            model_snapshot_hash=\"1\" * 64, role_bundle=bundle,\n        )\n        supervision_result = repo.transition_visual_supervision_if_current(\n            request=supervision_request\n        )\n        assert supervision_result is not None, \"legacy fixture must reserve a real source claim\"\n        bootstrap_source = bootstrap_fixture.source.__wrapped__()\n        source, bootstrap_record, promoted_original, bootstrap_retry, promotion = (\n            bootstrap_fixture.promotion_sources(bootstrap_source)\n        )\n        bootstrap_request = bootstrap_fixture.api().VisualBootstrapTransitionInput(\n            record=bootstrap_fixture.api().VisualBootstrapRecord.start(source[1]),\n            kind=\"RESERVE_INITIAL_CAPTURE\", event_key=\"r158-bootstrap-initial\",\n            current_lease=source[0], robot_state=data[\"online\"].robot_state,\n        )\n        sources = {\n            \"visual.bootstrap.definition.v1\": source[1],\n            \"visual.bootstrap.record.v1\": bootstrap_record,\n            \"visual.bootstrap.transition.v1\": bootstrap_request,\n            \"visual.bootstrap.promotion.v1\": promotion,\n            \"visual.supervision.definition.v1\": supervision_definition,\n            \"visual.supervision.record.v1\": supervision_result.record,\n            \"visual.supervision.transition.v1\": supervision_request,\n            \"visual.owner.original.v1\": original,\n            \"visual.owner.grounding.v1\": grounding,\n            \"visual.owner.publication.v1\": publication,\n            \"visual.verification.route-input.v1\": route_input_v1,\n            \"visual.verification.route-input.v2\": route_input_v2,\n            \"visual.verification.route.v1\": route_result.record,\n            \"visual.verification.effect-completion.v1\": completion,\n            \"recovery.verification-budget.v1\": current_pool,\n            \"recovery.retry-budget.v1\": current_retry,\n        }\n        return {\n            \"sources\": sources, \"data\": data, \"basis\": basis, \"state\": current_pool.state,\n            \"retry\": current_retry, \"promoted_original\": promoted_original,\n            \"bootstrap_retry\": bootstrap_retry,\n            \"historical_initial_publication\": initial_publication,\n            \"historical_route_input_v1\": route_input_v1,\n            \"historical_route_input_v2\": route_input_v2,\n            \"historical_route_result\": route_result.record,\n            \"historical_grounding\": grounding,\n            \"current_publication\": current_publication,\n            \"current_pool\": current_pool, \"current_checkpoint\": current_checkpoint,\n        }\n    finally:\n        repo.close()",
    "after": "def _b_legacy_sources(monkeypatch):\n    \"\"\"Use real pure builders/codecs and one real Memory repository; no worker.\"\"\"\n    import importlib\n    import json\n    import os\n    import threading\n    import traceback\n    import uuid\n    from pathlib import Path\n    from datetime import timedelta\n\n    from cloud_edge_robot_arm.contracts.models import RecoveryBudget\n    from cloud_edge_robot_arm.edge.recovery.verification_router import (\n        VerificationBudget,\n        VerificationBudgetState,\n    )\n    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (\n        InMemoryEventAutonomyRepository,\n    )\n    from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot\n    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation\n    from tests import test_visual_bootstrap as bootstrap_fixture\n    from tests import test_visual_owner_repository as owner_fixture\n    from tests import test_visual_verification_repository as route_fixture\n\n    original_init = InMemoryEventAutonomyRepository.__init__\n    original_close = InMemoryEventAutonomyRepository.close\n    observed_fields = (\"_events\", \"_budgets\", \"_active_contracts\", \"_checkpoints\")\n    close_required_fields = (\n        \"_lock\", \"_events\", \"_event_hashes\", \"_events_by_task\", \"_budgets\",\n        \"_states\", \"_transitions\", \"_failure_summaries\", \"_failure_hashes\",\n        \"_completion_summaries\", \"_completion_hashes\", \"_replan_requests\",\n        \"_replan_request_hashes\", \"_replan_idempotency\", \"_replan_results\",\n        \"_replan_result_hashes\", \"_outbox\", \"_outbox_hashes\", \"_outbox_idempotency\",\n        \"_plan_versions\", \"_active_contracts\", \"_contract_versions\", \"_checkpoints\",\n        \"_checkpoint_hashes\", \"_checkpoints_by_task\", \"_apply_records\",\n        \"_apply_by_request\", \"_apply_hashes\", \"_acks_by_key\", \"_ack_hashes\", \"_audit\",\n    )\n    call_id = uuid.uuid4().hex\n    call_pid = os.getpid()\n    call_thread = threading.get_ident()\n    current_test = os.environ.get(\"PYTEST_CURRENT_TEST\")\n    records = []\n    tracked = []\n    untracked_close_calls = []\n    failures = []\n    result = None\n\n    def error_details(error):\n        return {\n            \"type\": type(error).__name__, \"message\": str(error),\n            \"traceback\": \"\".join(traceback.format_exception(error)),\n        }\n\n    def record_for(instance):\n        return next((record for candidate, record in tracked if candidate is instance), None)\n\n    def mark_primary(instance):\n        record = record_for(instance)\n        assert record is not None and record[\"initialized\"] is True\n        record[\"role\"] = \"primary\"\n\n    def observed_init(instance, *args, **kwargs):\n        record = {\n            \"object_id\": id(instance), \"class_module\": type(instance).__module__,\n            \"class_qualname\": type(instance).__qualname__, \"role\": \"transitive\",\n            \"init_attempted\": True, \"initialized\": False, \"init_error\": None,\n            \"init_thread\": threading.get_ident(), \"init_native_thread\": threading.get_native_id(),\n            \"close_calls\": [], \"successful_close_observed\": False,\n        }\n        records.append(record)\n        tracked.append((instance, record))\n        try:\n            returned = original_init(instance, *args, **kwargs)\n        except BaseException as error:\n            record[\"init_error\"] = error_details(error)\n            record[\"safe_real_close_available\"] = all(\n                hasattr(instance, name) for name in close_required_fields\n            )\n            raise\n        record[\"initialized\"] = True\n        record[\"init_return_type\"] = type(returned).__name__\n        record[\"safe_real_close_available\"] = all(\n            hasattr(instance, name) for name in close_required_fields\n        )\n        return returned\n\n    def observed_close(instance, *args, **kwargs):\n        record = record_for(instance)\n        attempt = {\n            \"thread\": threading.get_ident(), \"native_thread\": threading.get_native_id(),\n            \"returned\": False, \"successful\": False, \"error\": None,\n            \"post_close_field_counts\": None,\n        }\n        if record is None:\n            untracked_close_calls.append({\"object_id\": id(instance), \"attempt\": attempt})\n        else:\n            record[\"close_calls\"].append(attempt)\n        try:\n            returned = original_close(instance, *args, **kwargs)\n            attempt[\"returned\"] = True\n            attempt[\"return_type\"] = type(returned).__name__\n            attempt[\"return_value\"] = None if returned is None else repr(returned)\n            with instance._lock:\n                counts = {name: len(getattr(instance, name)) for name in observed_fields}\n            attempt[\"post_close_field_counts\"] = counts\n            assert all(count == 0 for count in counts.values()), (\n                \"real Memory close did not clear its four observed fields\", counts\n            )\n            attempt[\"successful\"] = True\n            if record is not None:\n                record[\"successful_close_observed\"] = True\n            return returned\n        except BaseException as error:\n            attempt[\"error\"] = error_details(error)\n            raise\n\n    def build_legacy_sources():\n        data = owner_fixture.values()\n        original = data[\"original\"]\n        basis = original.registered_at + timedelta(seconds=0.2)\n        _b_utc(monkeypatch, basis)\n        state = VerificationBudgetState(\n            3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40.0)\n        )\n        retry = RecoveryBudget(\n            budget_id=\"r158-legacy-original-retry\",\n            task_id=original.identity.task_id,\n            task_total_retry_limit=2,\n            per_step_retry_limit=1,\n            per_skill_retry_limit=2,\n            effective_retry_limit=2,\n            remaining_retries=2,\n            retry_deadline=original.verification_deadline_at,\n            scene_version=original.contract.scene_version,\n            created_at=original.registered_at,\n            updated_at=original.registered_at,\n        )\n        # Reuse the existing immutable original builder with the actual lease identity\n        # and the exact role bundle consumed by the supervision definition.\n        lease = WorkerLeaseObservation(\n            original.identity.job_id, original.identity.run_id, original.identity.worker_id,\n            original.identity.lease_id, original.identity.attempt,\n            original.registered_at - timedelta(seconds=1), basis,\n            original.registered_at + timedelta(seconds=90), \"a\" * 64, \"b\" * 64, \"c\" * 64,\n        )\n        cloud = RoleProviderSnapshot(\n            \"CLOUD\", \"software-provider\", \"LOCAL_HOST\", \"software-model\",\n            None, None, None, \"d\" * 64, original.source_hashes,\n        )\n        bundle = RoleModelBundle(cloud, \"software-edge\", \"e\" * 64, \"f\" * 64)\n        owner_module = importlib.import_module(\"cloud_edge_robot_arm.vision.owner_registration\")\n        identity = lease.identity(\n            episode_id=original.identity.episode_id, task_id=original.identity.task_id,\n            plan_id=original.identity.plan_id, robot_id=original.identity.robot_id,\n        )\n        original = owner_module.freeze_original_visual_plan(\n            **{**original.freeze_inputs(), \"identity\": identity, \"role_bundle_hash\": bundle.digest()}\n        )\n        data[\"original\"], data[\"current_identity\"] = original, identity\n        repo = InMemoryEventAutonomyRepository()\n        mark_primary(repo)\n        try:\n            publication = repo.initialize_visual_owner_if_absent(\n                original, data[\"source_checkpoint\"], state, retry\n            )\n            initial_publication = publication\n            data[\"publication\"] = publication\n            owner_module = importlib.import_module(\"cloud_edge_robot_arm.vision.owner_registration\")\n            grounding = owner_module.bind_step_grounding(**{\n                key: value for key, value in data.items() if key != \"publication\"\n            })\n            route_input_v2 = route_fixture.request_for(data)\n            raw_v1 = route_input_v2.to_payload()\n            raw_v1[\"schema_version\"] = \"visual.verification.route-input.v1\"\n            del raw_v1[\"grounding_receipt\"]\n            route_module = route_fixture.api()\n            route_input_v1 = route_module.VisualVerificationRouteInput.from_payload(raw_v1)\n            historical_completion = route_fixture.software_completion(data)\n            route_result = repo.route_visual_verification_if_current(request=route_input_v2)\n            assert route_result is not None, \"legacy fixture must enter the actual source route\"\n            assert route_result.write_disposition == \"NEW_COMMIT\"\n            historical_route_payload = route_result.record.to_payload()\n            assert historical_route_payload[\"input\"] == route_input_v2.to_payload()\n            assert route_input_v2.to_payload()[\"publication\"] == initial_publication.to_payload()\n            current_publication = repo.get_visual_owner_publication(original.identity.task_id)\n            current_pool = repo.get_verification_budget(original.identity.task_id)\n            current_retry = repo.get_retry_budget(original.identity.task_id)\n            current_checkpoint = repo.get_latest_execution_checkpoint(original.identity.task_id)\n            assert all(value is not None for value in (\n                current_publication, current_pool, current_retry, current_checkpoint\n            )), \"actual current task source group must remain complete\"\n            assert current_publication.owner_revision == initial_publication.owner_revision + 1\n            assert current_publication.state_generation == initial_publication.state_generation + 1\n            assert historical_route_payload[\"produced_publication_hash\"] == current_publication.digest()\n            assert historical_route_payload[\"produced_publication\"] == current_publication.to_payload()\n            assert current_publication.identity == original.identity == initial_publication.identity\n            assert current_publication.original_plan_hash == initial_publication.original_plan_hash == original.digest()\n            assert current_pool.content_hash == current_publication.verification_budget.content_hash\n            assert _b_canonical(current_pool.to_payload()) == _b_canonical(\n                current_publication.verification_budget.to_payload()\n            )\n            assert _b_canonical(current_pool.to_payload()) == _b_canonical(\n                historical_route_payload[\"after_verification_budget\"]\n            )\n            assert current_pool.state.remaining_reobservations == (\n                initial_publication.verification_budget.state.remaining_reobservations - 1\n            )\n            assert current_pool.state.remaining_retries == initial_publication.verification_budget.state.remaining_retries\n            assert current_pool.state.limits == initial_publication.verification_budget.state.limits\n            assert current_pool.state.deadline_at == original.verification_deadline_at\n            assert _b_canonical(current_retry.model_dump(mode=\"json\")) == _b_canonical(\n                current_publication.retry_budget.model_dump(mode=\"json\")\n            ) == _b_canonical(retry.model_dump(mode=\"json\"))\n            assert current_checkpoint.checkpoint_hash == current_publication.checkpoint.checkpoint_hash\n            assert current_checkpoint.checkpoint_hash == initial_publication.checkpoint.checkpoint_hash\n            assert grounding.owner_revision == data[\"owner_revision\"]\n            assert grounding.state_generation == data[\"state_generation\"]\n            # The previous request/binding stay historical. Public getters supply\n            # the distinct current snapshot consumed by supervision and exports.\n            publication = current_publication\n            data[\"publication\"] = current_publication\n            completion = historical_completion\n            supervision_module = importlib.import_module(\n                \"cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision\"\n            )\n            supervision_definition = supervision_module.VisualSupervisionDefinition(\n                original=original, publication=publication, lease=lease,\n                task_started_at=original.registered_at, task_timeout_s=60.0,\n                supervision_period_s=0.2, model_snapshot_hash=\"1\" * 64, role_bundle=bundle,\n            )\n            supervision_record = repo.initialize_visual_supervision_if_absent(supervision_definition)\n            supervision_request = supervision_module.VisualSupervisionTransitionInput(\n                record=supervision_record, original=original, publication=publication, lease=lease,\n                robot_state=data[\"online\"].robot_state, step_id=\"move\", cursor=1,\n                kind=\"RESERVE_CAPTURE\", event_key=\"r158-supervision-capture\",\n                model_snapshot_hash=\"1\" * 64, role_bundle=bundle,\n            )\n            supervision_result = repo.transition_visual_supervision_if_current(\n                request=supervision_request\n            )\n            assert supervision_result is not None, \"legacy fixture must reserve a real source claim\"\n            bootstrap_source = bootstrap_fixture.source.__wrapped__()\n            source, bootstrap_record, promoted_original, bootstrap_retry, promotion = (\n                bootstrap_fixture.promotion_sources(bootstrap_source)\n            )\n            bootstrap_request = bootstrap_fixture.api().VisualBootstrapTransitionInput(\n                record=bootstrap_fixture.api().VisualBootstrapRecord.start(source[1]),\n                kind=\"RESERVE_INITIAL_CAPTURE\", event_key=\"r158-bootstrap-initial\",\n                current_lease=source[0], robot_state=data[\"online\"].robot_state,\n            )\n            sources = {\n                \"visual.bootstrap.definition.v1\": source[1],\n                \"visual.bootstrap.record.v1\": bootstrap_record,\n                \"visual.bootstrap.transition.v1\": bootstrap_request,\n                \"visual.bootstrap.promotion.v1\": promotion,\n                \"visual.supervision.definition.v1\": supervision_definition,\n                \"visual.supervision.record.v1\": supervision_result.record,\n                \"visual.supervision.transition.v1\": supervision_request,\n                \"visual.owner.original.v1\": original,\n                \"visual.owner.grounding.v1\": grounding,\n                \"visual.owner.publication.v1\": publication,\n                \"visual.verification.route-input.v1\": route_input_v1,\n                \"visual.verification.route-input.v2\": route_input_v2,\n                \"visual.verification.route.v1\": route_result.record,\n                \"visual.verification.effect-completion.v1\": completion,\n                \"recovery.verification-budget.v1\": current_pool,\n                \"recovery.retry-budget.v1\": current_retry,\n            }\n            return {\n                \"sources\": sources, \"data\": data, \"basis\": basis, \"state\": current_pool.state,\n                \"retry\": current_retry, \"promoted_original\": promoted_original,\n                \"bootstrap_retry\": bootstrap_retry,\n                \"historical_initial_publication\": initial_publication,\n                \"historical_route_input_v1\": route_input_v1,\n                \"historical_route_input_v2\": route_input_v2,\n                \"historical_route_result\": route_result.record,\n                \"historical_grounding\": grounding,\n                \"current_publication\": current_publication,\n                \"current_pool\": current_pool, \"current_checkpoint\": current_checkpoint,\n            }\n        finally:\n            repo.close()\n\n    try:\n        with monkeypatch.context() as lifetime_patch:\n            lifetime_patch.setattr(InMemoryEventAutonomyRepository, \"__init__\", observed_init)\n            lifetime_patch.setattr(InMemoryEventAutonomyRepository, \"close\", observed_close)\n            try:\n                result = build_legacy_sources()\n            except BaseException as error:\n                failures.append(error)\n            finally:\n                for instance, record in tracked:\n                    if not record[\"successful_close_observed\"]:\n                        required_present = all(\n                            hasattr(instance, name) for name in close_required_fields\n                        )\n                        record[\"safe_real_close_available\"] = required_present\n                        if not required_present:\n                            error = AssertionError(\n                                \"Memory initialization incomplete; genuine close requires missing fields\"\n                            )\n                            record[\"incomplete_cleanup\"] = error_details(error)\n                            failures.append(error)\n                            continue\n                        try:\n                            instance.close()\n                        except BaseException as error:\n                            failures.append(error)\n                instance = record = None\n    except BaseException as error:\n        failures.append(error)\n    finally:\n        restored = {\n            \"__init__\": InMemoryEventAutonomyRepository.__init__ is original_init,\n            \"close\": InMemoryEventAutonomyRepository.close is original_close,\n        }\n        counts = {\n            \"allocation_attempts\": sum(record[\"init_attempted\"] for record in records),\n            \"initialized\": sum(record[\"initialized\"] for record in records),\n            \"init_failed\": sum(record[\"init_error\"] is not None for record in records),\n            \"primary\": sum(record[\"role\"] == \"primary\" for record in records),\n            \"transitive\": sum(record[\"role\"] == \"transitive\" for record in records),\n            \"close_attempts\": sum(len(record[\"close_calls\"]) for record in records),\n            \"close_returns\": sum(attempt[\"returned\"] for record in records for attempt in record[\"close_calls\"]),\n            \"close_errors\": sum(attempt[\"error\"] is not None for record in records for attempt in record[\"close_calls\"]),\n            \"initialized_successfully_closed\": sum(\n                record[\"initialized\"] and record[\"successful_close_observed\"] for record in records\n            ),\n        }\n        local_checks = {\n            \"all_initialized_successfully_closed\": counts[\"initialized\"] == counts[\"initialized_successfully_closed\"],\n            \"no_init_failures\": counts[\"init_failed\"] == 0,\n            \"no_close_errors\": counts[\"close_errors\"] == 0,\n            \"primary_exactly_one\": counts[\"primary\"] == 1,\n            \"transitive_at_least_one\": counts[\"transitive\"] >= 1,\n            \"methods_restored\": all(restored.values()),\n        }\n        for name, passed in local_checks.items():\n            if not passed:\n                failures.append(AssertionError(\"R175 Memory lifecycle check failed: \" + name))\n        observation = {\n            \"schema_version\": \"bigsmall.r175-memory-lifecycle.v1\",\n            \"call_id\": call_id, \"pid\": call_pid, \"thread\": call_thread,\n            \"native_thread\": threading.get_native_id(), \"PYTEST_CURRENT_TEST\": current_test,\n            \"nodeid\": None if current_test is None else current_test.rsplit(\" (\", 1)[0],\n            \"repository_class_module\": InMemoryEventAutonomyRepository.__module__,\n            \"repository_class_qualname\": InMemoryEventAutonomyRepository.__qualname__,\n            \"original_method_ids\": {\"__init__\": id(original_init), \"close\": id(original_close)},\n            \"restored_method_ids\": {\n                \"__init__\": id(InMemoryEventAutonomyRepository.__init__),\n                \"close\": id(InMemoryEventAutonomyRepository.close),\n            },\n            \"observed_fields\": list(observed_fields), \"counts\": counts,\n            \"objects\": records, \"untracked_close_calls\": untracked_close_calls,\n            \"methods_restored\": restored, \"local_checks\": local_checks,\n            \"failures\": [error_details(error) for error in failures],\n            \"success\": not failures and all(local_checks.values()),\n            \"unobserved\": {\"worker_lifecycles\": None, \"broker_threads\": None,\n                \"heartbeat_threads\": None, \"model_calls\": None, \"network_calls\": None,\n                \"GPU_native_calls\": None},\n            \"scope\": \"Only actual Memory allocation/init/close and method restoration observed.\",\n        }\n        try:\n            sink = os.environ.get(\"BIGSMALL_R175_RESOURCE_DIR\")\n            if sink:\n                directory = Path(sink)\n                assert directory.is_absolute() and directory.is_dir() and not directory.is_symlink()\n                assert all(not parent.is_symlink() for parent in directory.parents)\n                sidecar = directory / (call_id + \".json\")\n                encoded = (json.dumps(observation, allow_nan=False, sort_keys=True,\n                    ensure_ascii=False, indent=2) + \"\\n\").encode()\n                with sidecar.open(\"xb\") as stream:\n                    stream.write(encoded)\n        except BaseException as error:\n            failures.append(error)\n        finally:\n            tracked.clear()\n            instance = record = None\n    if failures:\n        if len(failures) == 1:\n            raise failures[0]\n        raise BaseExceptionGroup(\"R175 Memory fixture lifecycle failures\", failures)\n    return result"
  }
]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

def file_pin(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def canonical(raw):
    assert isinstance(raw, str) and raw.strip(), ("nonempty path", raw)
    relative = Path(raw)
    assert ".." not in relative.parts, ("parent traversal forbidden", raw)
    path = relative if relative.is_absolute() else ROOT / relative
    assert path.is_relative_to(ROOT), ("outside fixed repository root", raw)
    assert not path.is_symlink(), ("symlink forbidden", raw)
    for parent in path.parents:
        assert not parent.is_symlink(), ("symlink parent forbidden", raw)
        if parent == ROOT:
            break
    return str(path)

def coordinates(raw_paths):
    result = [canonical(raw) for raw in raw_paths]
    assert len(result) == len(set(result)), ("duplicate canonical paths", raw_paths)
    return result

def checked_pin(record):
    path = Path(canonical(record["path"]))
    receipt = file_pin(path)
    assert receipt["bytes"] == record["bytes"], ("pinned bytes", str(path))
    assert receipt["sha256"] == record["sha256"], ("pinned SHA256", str(path))
    return receipt

def parent_ledger_guard(path, role, command_ids):
    document = json.loads(path.read_bytes())
    if role == "author":
        assert document["schema_version"] == "bigsmall.r158-author-command-ledger.v1"
    commands = document["commands"]
    assert type(commands) is dict and len(commands) == 15 and set(commands) == set(command_ids)
    for name, entry in commands.items():
        for key in ("authorized", "used", "remaining"):
            assert type(entry[key]) is int
        assert entry["authorized"] == 1
        assert entry["cwd"] == str(ROOT)
        assert type(entry["argv"]) is list
        if name in ("mypy_baseline", "t1_red", "t1_green"):
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected_state = "SPENT" if role == "author" else (
                "SPENT_ACTUAL_DIAGNOSTIC_CENSUS" if name == "mypy_baseline"
                else "SPENT_ACTUAL_UNEXPECTED_LEGACY_CONTROL_FAILURE" if name == "t1_red"
                else "SPENT_ACTUAL_UNEXPECTED_T1_GREEN_FAILURE"
            )
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            expected_state = "HELD" if role == "author" else "HELD_PENDING_ROOT_GATE"
        assert entry["state"] == expected_state, ("role-specific state", role, name)
    assert sum(entry["used"] for entry in commands.values()) == 3
    assert sum(entry["remaining"] for entry in commands.values()) == 12
    return file_pin(path)


def local_ledger_guard(document, role, plan, selected, selected_used):
    schema = "bigsmall.r175-command-ledger.v1" if role == "author" else "bigsmall.r175-root-command-ledger.v1"
    assert document["schema_version"] == schema and document["round"] == "R175"
    assert document["role"] == role and document["no_retry"] is True
    assert document["plan_sha256"] == PLAN_SHA
    commands = document["commands"]
    assert set(commands) == {"preparation_metadata","recovery7","ROOT_settlement_metadata"}
    for name, entry in commands.items():
        contract = plan["command_budget"][name]
        assert entry["authorized"] == entry["max_attempts"] == 1
        assert entry["timeout_seconds"] == contract["timeout_seconds"]
        assert entry["argv"] == contract.get("argv")
        assert entry["outer_runner_argv"] == contract.get("outer_runner_argv")
        assert entry["cwd"] == str(ROOT)
        if name == selected and selected_used:
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected = "SPENT" if role == "author" else "RESERVED_BY_ROOT"
            assert entry["state"] == expected
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            assert entry["state"] == ("HELD" if role == "author" else "HELD_PENDING_ROOT_GATE")

assert Path.cwd() == ROOT
plan_bytes = (D175/"plan.json").read_bytes()
md_bytes = (D175/"plan.md").read_bytes()
assert sha(plan_bytes) == PLAN_SHA and sha(md_bytes) == MD_SHA
plan = json.loads(plan_bytes)
contract = plan["command_budget"]["preparation_metadata"]
assert contract["timeout_seconds"] == 120
assert canonical(__file__) == canonical(contract["argv"][1])
gate_bytes = (D175/"script-gate.json").read_bytes()
gate_document = json.loads(gate_bytes)
assert gate_document["schema_version"] == "bigsmall.r175-script-gate.v1"
gate = gate_document["commands"]["preparation_metadata"]
assert gate["state"] == "APPROVED"
assert gate["argv"] == contract["argv"] and gate["cwd"] == str(ROOT)
assert gate["timeout_seconds"] == 120
assert gate["candidate_test_pin"] == CANDIDATE_TEST_PIN
assert CANDIDATE_TEST_PIN["path"] == plan["scope"]["owned_test"]
checked_pin(gate["source_pin"])
assert canonical(gate["source_pin"]["path"]) == canonical(__file__)
checked_pin(gate["runner_pin"])
assert canonical(gate["runner_pin"]["path"]) == canonical(plan["preparation"]["scripts"][1])
root_ledger_path = D175/"root-command-ledger.json"
author_ledger_path = D175/"command-ledger.json"
root_ledger_bytes = root_ledger_path.read_bytes()
author_ledger_bytes = author_ledger_path.read_bytes()
root_ledger = json.loads(root_ledger_bytes)
author_ledger = json.loads(author_ledger_bytes)
local_ledger_guard(root_ledger,"root",plan,"preparation_metadata",True)
local_ledger_guard(author_ledger,"author",plan,"preparation_metadata",False)
assert isinstance(root_ledger["commands"]["preparation_metadata"]["reservation_id"],str)
entry = author_ledger["commands"]["preparation_metadata"]
entry.update({"used":1,"remaining":0,"state":"SPENT",
    "reservation_id":root_ledger["commands"]["preparation_metadata"]["reservation_id"],
    "attempts":1,"retries":0})
spent_author_bytes = encode(author_ledger)
# Consume the independent author allowance before all preparation work; uncertainty stays spent.
assert author_ledger_path.read_bytes() == author_ledger_bytes
author_ledger_path.write_bytes(spent_author_bytes)
assert author_ledger_path.read_bytes() == spent_author_bytes

assert len(plan["inputs"]) == 62
coordinates([item["path"] for item in plan["inputs"]])
test_path = Path(plan["scope"]["owned_test"])
report_records = plan["preparation"]["archive_reports"]
assert len(report_records) == 13
report_paths = coordinates([item["path"] for item in report_records])
allowed_initial_delta = {str(test_path)}
static_records = [item for item in plan["inputs"] if canonical(item["path"]) not in allowed_initial_delta]
assert len(static_records) == 61
for item in static_records:
    checked_pin(item)
checked_pin(CANDIDATE_TEST_PIN)
r174_directory = PROCESS / "round174-p6-t1-legacy-condition-json-normalization-20261014"
old_root = json.loads((r174_directory/"root-command-ledger.json").read_bytes())
old_author = json.loads((r174_directory/"command-ledger.json").read_bytes())
for role, document in (("root",old_root),("author",old_author)):
    assert document["schema_version"] == ("bigsmall.r174-root-command-ledger.v1" if role == "root" else "bigsmall.r174-command-ledger.v1")
    assert document["commands"]["preparation_metadata"]["state"] == "SPENT"
    for name in ("preparation_metadata","recovery7"):
        assert document["commands"][name]["used"] == 1 and document["commands"][name]["remaining"] == 0
    assert document["commands"]["recovery7"]["state"] == ("RESERVED_BY_ROOT" if role == "root" else "SPENT")
    old_settlement = document["commands"]["ROOT_settlement_metadata"]
    assert old_settlement["used"] == 0 and old_settlement["remaining"] == 1
    assert old_settlement["state"] == ("HELD_PENDING_ROOT_GATE" if role == "root" else "HELD")
disposition_bytes = (D175/"prior-slot-disposition.json").read_bytes()
assert sha(disposition_bytes) == "fdf0a5d732f13588c571e1884f35b677d5d917c168c18c3c01096ab0aa3bba0d"
r174_actual = json.loads((r174_directory/"implementation/recovery7/result.json").read_bytes())
assert r174_actual["product_exit"] == r174_actual["runner_exit"] == 0
assert all(r174_actual["junit"][key] == value for key,value in {"tests":7,"passes":7,"failures":0,"errors":0,"skipped":0}.items())
old_runner = file_pin(r174_directory/"implementation/run-recovery7.py")
assert old_runner["bytes"] == 19080 and old_runner["sha256"] == "f06ab633ad758ee9b0cb9ebeaa6a79b842f385562f01c86b3c5aae1786761287"

pre_report_bytes = {canonical(item["path"]):Path(canonical(item["path"])).read_bytes() for item in report_records}
old_semantic = json.loads(pre_report_bytes[str(TASK/"semantic.json")])
old_sources = {}
r174_snapshot_path = PROCESS / "round174-p6-t1-legacy-condition-json-normalization-20261014/implementation/candidate-snapshot.json"
checked_pin(next(item for item in plan["inputs"] if item["path"] == str(r174_snapshot_path)))
r174_snapshot = json.loads(r174_snapshot_path.read_bytes())
for item in r174_snapshot["sources"]:
    raw = base64.b64decode(item["base64"],validate=True)
    assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
    old_sources[canonical(item["path"])] = raw
assert len(old_sources) == 24 and str(test_path) in old_sources
test_before = old_sources[str(test_path)]
test_before_pin = next(item for item in plan["inputs"] if item["path"] == str(test_path))
assert len(test_before) == test_before_pin["bytes"] and sha(test_before) == test_before_pin["sha256"]
test_after = test_path.read_bytes()
start = plan["scope"]["only_source_region"]["start"]
end = plan["scope"]["only_source_region"]["end_before"]
before_text, after_text = test_before.decode(), test_after.decode()
assert before_text.count(start) == after_text.count(start) == 1
assert before_text.count(end) == after_text.count(end) == 1
ba, bb = before_text.index(start), before_text.index(end)
aa, ab = after_text.index(start), after_text.index(end)
assert before_text[:ba] == after_text[:aa] and before_text[bb:] == after_text[ab:]
expected_helper = before_text[ba:bb]
for change in CHANGES:
    assert expected_helper.count(change["before"]) == 1
    expected_helper = expected_helper.replace(change["before"],change["after"],1)
assert after_text[aa:ab] == expected_helper
for path_string, raw in old_sources.items():
    if path_string != str(test_path):
        assert Path(path_string).read_bytes() == raw
assert sha(test_after[:80556]) == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"
assert test_after[:80556] == test_before[:80556]
test_tail = b'@pytest.mark.parametrize("family", ["bootstrap", "supervision", "owner_grounding", "route_completion_budget"])'
assert test_before.count(test_tail) == test_after.count(test_tail) == 1
assert test_before[test_before.index(test_tail):] == test_after[test_after.index(test_tail):]
parent_plan = json.loads((D158/"plan.json").read_bytes())
manifest = json.loads((D158/"input-pins.json").read_bytes())
before_path = TASK/"before.json"
before_bytes = before_path.read_bytes()
before = json.loads(before_bytes)
owned = coordinates(parent_plan["scope"]["owned_paths"])
t1_owned = set(coordinates(parent_plan["tasks"][0]["owned_paths"]))
new_owned = set(coordinates(parent_plan["scope"]["new_paths"]))
original = {canonical(item["path"]):item for item in before["sources"]}
assert len(owned) == 24 and len(original) == 23 and len(t1_owned) == 9
assert len(new_owned) == 1 and set(owned)-set(original) == new_owned
assert set(owned) == set(old_sources)
snapshots, source_index, full_diff, later = [], [], [], []
for path_string in owned:
    raw = Path(path_string).read_bytes()
    record = original.get(path_string)
    old = b"" if record is None else base64.b64decode(record["base64"],validate=True)
    if record is not None:
        assert len(old) == record["bytes"] and sha(old) == record["sha256"]
    else:
        assert path_string in new_owned
    if path_string not in t1_owned:
        assert raw == old
        later.append(path_string)
    snapshots.append({"path":path_string,"relative_path":str(Path(path_string).relative_to(ROOT)),
        "bytes":len(raw),"sha256":sha(raw),"changed":raw != old,"T1_owned":path_string in t1_owned,
        "before_bytes":None if record is None else len(old),
        "before_sha256":None if record is None else sha(old),
        "base64":base64.b64encode(raw).decode()})
    lines = raw.decode().splitlines()
    source_index.append({"path":path_string,"sha256":sha(raw),"lines":len(lines),
        "text_declarations":[{"line":number,"indent":len(line)-len(line.lstrip()),"declaration":line.lstrip()}
            for number,line in enumerate(lines,1) if line.lstrip().startswith(("def ","class "))]})
    if raw != old:
        full_diff.extend(difflib.unified_diff(old.decode().splitlines(keepends=True),raw.decode().splitlines(keepends=True),
            fromfile=path_string+" (original R158 before)",tofile=path_string+" (after R175 helper)",n=3))
assert len(later) == 15
assert {item["path"] for item in snapshots if item["changed"]} == t1_owned
source_pins = [{key:value for key,value in item.items() if key != "base64"} for item in snapshots]
assert len(manifest["protected"]) == 211
coordinates([item["path"] for item in manifest["protected"]])
protected = [checked_pin(item) for item in manifest["protected"]]
ledger_pins = [parent_ledger_guard(D158/"command-ledger.json","author",parent_plan["commands"]),
    parent_ledger_guard(D158/"root-command-ledger.json","root",parent_plan["commands"])]
golden = checked_pin(next(item for item in plan["inputs"] if item["path"].endswith("/implementation/legacy_control/legacy-goldens.json")))
assert golden["bytes"] == 121893 and golden["sha256"] == "10452e376a00b1672d540fc1332c6beeeaa42b6cff44f03f425531e26a5d0c38"
assert len(json.loads(Path(golden["path"]).read_bytes())) == 16
for item in plan["inputs"]:
    if item["path"].endswith("/golden-provenance.json"):
        checked_pin(item)
assert not (D158/"implementation/t1_red/legacy-goldens.json").exists()
implementation = D175/"implementation"
outputs = plan["evidence_outputs"]["preparation"]
written_paths = [path for path in outputs if not path.endswith(("preparation-actual-tool-return.json","preparation-stdout.txt","preparation-stderr.txt"))]
assert len(written_paths) == 6 and all(not Path(path).exists() for path in written_paths)
helper_diff = "".join(difflib.unified_diff(before_text.splitlines(keepends=True),after_text.splitlines(keepends=True),
    fromfile=str(test_path)+" (before R175)",tofile=str(test_path)+" (R175 helper)",n=3)).encode()
full_diff_bytes = "".join(full_diff).encode()
usage = dict(old_semantic["usage"])
usage.update({"R174_preparation_metadata_used":1,"R174_preparation_metadata_remaining":0,
    "R174_recovery7_used":1,"R174_recovery7_remaining":0,"R174_recovery7_state":"SPENT_ACTUAL_7PASS_RESOURCE_GAP",
    "R174_ROOT_settlement_metadata_used":0,"R174_ROOT_settlement_metadata_remaining":1,
    "R174_ROOT_settlement_metadata_effective":"HELD_SUPERSEDED_BY_R175_NO_EXECUTION"})
usage.update({"R158_used":3,"R158_remaining":12,"R158_remaining_state":"HELD",
    "t1_green_used":1,"t1_green_remaining":0,"t1_green_state":"SPENT",
    "R175_preparation_metadata_used":1,"R175_preparation_metadata_remaining":0,
    "R175_recovery7_used":0,"R175_recovery7_remaining":1,"R175_recovery7_state":"HELD",
    "R175_ROOT_settlement_metadata_used":0,"R175_ROOT_settlement_metadata_remaining":1})
r174_scope_pin = {"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round174-p6-t1-legacy-condition-json-normalization-20261014/implementation/scope-proof.json","bytes":61009,"sha256":"b1812cd66c03751e23efc111aef0492f636f4acd6c0599f1d7553d5545975fdb"}
expected_original_raw = [{"bytes":1356,"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green/result.json","sha256":"ae25624d036d081350fae5884bb92b774f42adc98db39ad4ee7ec0850edc2104"},{"bytes":3504,"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green/invocation.json","sha256":"24fc0b5a774ecf65469fd0360cf6bdd1786fbd3c3c574d38d841511a8c5f66fa"},{"bytes":7587,"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green/stdout.txt","sha256":"ad64dd236c12ff25f26072397194bb704ed6bca959338f9ac1980d6f566227ed"},{"bytes":0,"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green/stderr.txt","sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},{"bytes":8191,"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green/junit.xml","sha256":"8edd752cc997cd8c53ede765862edbe40c0e6a6bce17b088ddce93482b51eebb"},{"bytes":3821,"path":"/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green/actual-tool-return.json","sha256":"3c16ccf19217093315f664aaee5f72d2626415ce9d7a537a4b8c738382d84da5"}]
checked_pin(r174_scope_pin)
r174_scope_bytes = Path(r174_scope_pin["path"]).read_bytes()
r174_scope = json.loads(r174_scope_bytes)
assert type(r174_scope) is dict and type(r174_scope["original_green"]) is dict
original_green = r174_scope["original_green"]
assert type(original_green["raw_preserved"]) is list and len(original_green["raw_preserved"]) == 6
assert original_green["raw_preserved"] == expected_original_raw
assert all(original_green[key] == value for key,value in {
    "tests":7,"passes":5,"failures":2,"errors":0,"skips":0,"product_exit":1,
    "runner_tool_exit":2,"used":1,"remaining":0,"overall_pass":False}.items())
auxiliary_records = [r174_scope_pin]+original_green["raw_preserved"]
assert len(coordinates([item["path"] for item in auxiliary_records])) == 7
auxiliary_receipts = [checked_pin(item) for item in auxiliary_records]
prior_r174 = {"product_exit":0,"runner_exit":0,"tests":7,"passes":7,"failures":0,"errors":0,"skipped":0,
    "Memory_lifecycle_observed":False,"ROOT_settlement_effective":"HELD_SUPERSEDED_BY_R175_NO_EXECUTION",
    "raw_preserved":True}
coverage = {"targeted_R173_accessor_execution":False,"R175_recovery7_executed":False,
    "Memory_lifecycle_observer_executed":False,
    "limit":"Scope/text proof only. R174 seven passes do not execute this new observer or establish transitive Memory closure."}
checks = dict(old_semantic["checks"])
checks.update({"ledger_pins":ledger_pins,"owned_current_snapshot_count":24,
    "protected_pins":protected,"protected_count":211,"unchanged_later_owned_count":15,
    "unchanged_later_owned":later,"original_23_before_preserved":file_pin(before_path),
    "A80556_sha256":sha(test_after[:80556]),"seven_T1_test_bodies_and_decorators_unchanged":True,
    "current_test_equals_accepted_R170_after_pin":False,
    "current_test_is_R175_approved_helper_only_delta":True,"current_test":CANDIDATE_TEST_PIN})
scope = {"schema_version":"bigsmall.r175-scope-proof.v1","candidate_only":True,
    "test_before":test_before_pin,"test_after":CANDIDATE_TEST_PIN,"helper_bounds":[start,end],
    "exact_replacements":CHANGES,"test_outside_helper_byte_identical":True,
    "R176_auxiliary_immutable_inputs":auxiliary_receipts,
    "R174_JSON_boundary_helper_byte_identical":True,"observer_contract":plan["repair_contract"],
    "production_23_byte_identical_to_settled_snapshot":True,"seven_bodies_unchanged":True,
    "A80556_unchanged":True,"checks":checks,"usage":usage,"original_green":original_green,"prior_R174":prior_r174,"coverage":coverage}
snapshot = {"schema_version":"bigsmall.r175-candidate-snapshot.v1","sources":snapshots,
    "source_text_index":source_index,"source_pins":source_pins,"protected":protected,
    "parent_ledger_pins":ledger_pins,"runner_pin":gate["runner_pin"],
    "R176_auxiliary_immutable_inputs":auxiliary_receipts,
    "old_runner_pin":checked_pin(next(item for item in plan["inputs"] if item["path"] == str(D158/"implementation/run-budgeted-command.py"))),
    "checks":checks,"usage":usage,"original_green":original_green,"prior_R174":prior_r174,"coverage":coverage}
archive = {"schema_version":"bigsmall.r175-before-t1-reports.v1","records":[
    {**item,"base64":base64.b64encode(pre_report_bytes[item["path"]]).decode()} for item in report_records]}
documents = {name:json.loads(pre_report_bytes[str(TASK/(name+".json"))]) for name in
    ["semantic","final-freeze","change-report","fixture-map","budget-report","step-report"]}
r175_fact = {"status":"PREPARATION_ONLY_RECOVERY_HELD","original_green":original_green,"prior_R174":prior_r174,
    "coverage":coverage,"scope_proof":str(implementation/"scope-proof.json"),
    "source_snapshot":str(implementation/"candidate-snapshot.json"),
    "old_reports_archive":str(implementation/"before-t1-reports.json"),"observer_contract":plan["repair_contract"],"usage":usage}
for document in documents.values():
    document["usage"] = usage
    document["R175"] = r175_fact
    if "checks" in document:
        document["checks"] = checks
    if "source_pins" in document:
        document["source_pins"] = source_pins
    document["status"] = "R175_CANDIDATE_PREPARATION_ORIGINAL_GREEN_FAILED_RECOVERY_HELD"
    if "test_first_prerequisites" in document:
        document["test_first_prerequisites"]["original_T1_GREEN"] = original_green
        document["test_first_prerequisites"]["current_T1_candidate"] = "R175_RECOVERY_HELD_NOT_EXECUTED"
documents["semantic"]["sources"] = snapshots
documents["semantic"]["source_text_index"] = source_index
documents["semantic"]["previous_current_metadata_preserved"] = {"archive":str(implementation/"before-t1-reports.json"),"records":report_records}
documents["change-report"]["complete_candidate_diff"] = {"path":str(TASK/"limited.diff"),
    "bytes":len(full_diff_bytes),"sha256":sha(full_diff_bytes)}
documents["step-report"]["pending"] = ["ROOT preparation settlement","one independent R175 recovery7 gate and run",
    "ROOT independent settlement metadata","unused original fresh T1 review","T2 and T3"]
refreshed = {}
for name, document in documents.items():
    refreshed[str(TASK/(name+".json"))] = encode(document)
    refreshed[str(TASK/(name+".md"))] = (
        "# R158 T1 "+name+" after R175 preparation\n\n"
        "Original T1 GREEN is spent 1/0 with actual 5 PASS, 2 FAIL, 0 ERROR, 0 SKIP. "
        "Parent budget is 3 spent / 12 HELD. Old raw and all thirteen pre-refresh reports remain preserved.\n\n"
        "Only _b_legacy_sources gains real Memory init/close observation and helper-wide cleanup. R174 JSON normalization remains byte-identical. All 23 production sources, "
        "211 protected files, A80556, seven test bodies, real 16-tag golden/provenance and old runner remain unchanged.\n\n"
        "Old R174 recovery is actual 7PASS with the source cleanup gap retained; its unused ROOT settlement is effectively superseded without changing old ledger bytes. Independent R175 recovery7 is HELD 0/1. This preparation is bytes/text/hash evidence only. "
        "R173 history accessor targeted execution remains false; no T1/B9/T12/native/actual/formal acceptance.\n").encode()
refreshed[str(TASK/"limited.diff")] = full_diff_bytes
assert set(refreshed) == set(report_paths)
payloads = {str(implementation/"before-test.py"):test_before,
    str(implementation/"before-t1-reports.json"):encode(archive),
    str(implementation/"limited.diff"):helper_diff,
    str(implementation/"scope-proof.json"):encode(scope),
    str(implementation/"candidate-snapshot.json"):encode(snapshot)}
immutable_records = [item for item in static_records if item["path"] not in report_paths]
assert len(immutable_records) == 48

def recheck():
    for item in auxiliary_records:
        checked_pin(item)
    assert Path(r174_scope_pin["path"]).read_bytes() == r174_scope_bytes
    for item in immutable_records:
        checked_pin(item)
    for item in protected:
        checked_pin(item)
    for item in source_pins:
        checked_pin(item)
    assert before_path.read_bytes() == before_bytes
    assert (D175/"plan.json").read_bytes() == plan_bytes
    assert (D175/"plan.md").read_bytes() == md_bytes
    assert (D175/"script-gate.json").read_bytes() == gate_bytes
    assert root_ledger_path.read_bytes() == root_ledger_bytes
    assert author_ledger_path.read_bytes() == spent_author_bytes
    checked_pin(gate["source_pin"])
    checked_pin(gate["runner_pin"])
    checked_pin(old_runner)
    assert (D175/"prior-slot-disposition.json").read_bytes() == disposition_bytes
    assert not (D158/"implementation/t1_red/legacy-goldens.json").exists()

recheck()
for item in report_records:
    checked_pin(item)
assert all(not Path(path).exists() for path in written_paths)
implementation.mkdir(parents=True,exist_ok=True)
for path in (str(implementation/"before-test.py"),str(implementation/"before-t1-reports.json")):
    with Path(path).open("xb") as stream:
        stream.write(payloads[path])
    assert Path(path).read_bytes() == payloads[path]
for path, raw in payloads.items():
    if path not in (str(implementation/"before-test.py"),str(implementation/"before-t1-reports.json")):
        with Path(path).open("xb") as stream:
            stream.write(raw)
        assert Path(path).read_bytes() == raw
for path, raw in refreshed.items():
    assert Path(path).read_bytes() == pre_report_bytes[path]
    Path(path).write_bytes(raw)
    assert Path(path).read_bytes() == raw
for path, raw in payloads.items():
    assert Path(path).read_bytes() == raw
for path, raw in refreshed.items():
    assert Path(path).read_bytes() == raw
recheck()
artifact_pins = [file_pin(Path(path)) for path in list(payloads)+list(refreshed)]
summary = {"schema_version":"bigsmall.r175-preparation-result.v1","status":"METADATA_PREPARATION_ONLY",
    "artifact_pins":artifact_pins,"test_before":test_before_pin,"test_after":CANDIDATE_TEST_PIN,
    "counts":{"plan_inputs":62,"pre_refresh_fixed_inputs":61,"post_refresh_fixed_inputs":48,
        "owned":24,"production_unchanged":23,"original_before":23,"later_unchanged":15,
        "protected":211,"reports_archived":13,"reports_refreshed":13,"test_nodes":7,"golden_tags":16},
    "usage":usage,"original_green":original_green,"coverage":coverage,"acceptance":old_semantic["acceptance"]}
result_path = implementation/"preparation-result.json"
result_bytes = encode(summary)
with result_path.open("xb") as stream:
    stream.write(result_bytes)
assert result_path.read_bytes() == result_bytes
for path, raw in payloads.items():
    assert Path(path).read_bytes() == raw
for path, raw in refreshed.items():
    assert Path(path).read_bytes() == raw
recheck()
summary["preparation_result_pin"] = file_pin(result_path)
receipt = json.dumps({"status":summary["status"],"result":summary["preparation_result_pin"],
    "counts":summary["counts"],"candidate_test":CANDIDATE_TEST_PIN,
    "R175_preparation_metadata":{"used":1,"remaining":0}},sort_keys=True)
assert len(receipt) < 1500
print(receipt)
