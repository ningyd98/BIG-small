class _ScopedFormat:
    def _visual_original_locked(self, task_id: str, plan_version: int) -> VisualOriginalPlan | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            original_from_payload,
        )

        stored = self._visual_originals.get((task_id, plan_version))
        if stored is None:
            return None
        original = original_from_payload(json.loads(stored[0]))
        if (
            original.digest() != stored[1]
            or original.identity.task_id != task_id
            or original.contract.plan_version != plan_version
        ):
            raise ValueError("stored original key/hash differs")
        return original

    def _visual_record_locked(
        self, task_id: str, revision: int | None = None
    ) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            VisualOwnerPublicationRecord,
        )

        if revision is None:
            revisions = [version for task, version in self._visual_publications if task == task_id]
            if not revisions:
                return None
            revision = max(revisions)
        raw = self._visual_publications.get((task_id, revision))
        if raw is None:
            return None
        record = VisualOwnerPublicationRecord.from_payload(json.loads(raw))
        if record.identity.task_id != task_id or record.owner_revision != revision:
            raise ValueError("stored publication key differs")
        return record

    def _visual_group_locked(self, task_id: str) -> tuple[Any, Any, Any, Any]:
        ids = self._checkpoints_by_task.get(task_id, [])
        return (
            self._active_contracts.get(task_id),
            self._checkpoints.get(ids[-1]) if ids else None,
            self._verification_budgets.get(task_id),
            self._budgets.get(task_id),
        )

    def _visual_versions_match(self, original: VisualOriginalPlan) -> bool:
        task, contract = original.identity.task_id, original.contract
        version = self._version_record(task, contract.plan_version)
        active = self._active_contracts.get(task)
        return (
            self._plan_versions.get(task) == (contract.plan_version, contract.command_seq)
            and version is not None
            and active is not None
            and version.model_dump(mode="json") == active.model_dump(mode="json")
        )

    def get_visual_original_plan(
        self, task_id: str, plan_version: int
    ) -> VisualOriginalPlan | None:
        with self._lock:
            return self._visual_original_locked(task_id, plan_version)

    def get_visual_owner_publication(self, task_id: str) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            current_publication,
        )

        with self._lock:
            record = self._visual_record_locked(task_id)
            if record is None:
                return None
            original = self._visual_original_locked(task_id, record.checkpoint.plan_version)
            previous = (
                self._visual_record_locked(task_id, record.owner_revision - 1)
                if record.owner_revision > 1
                else None
            )
            if (
                original is None
                or not self._visual_versions_match(original)
                or not current_publication(
                    record, original, *self._visual_group_locked(task_id), previous=previous
                )
            ):
                return None
            return record.detached()

    def initialize_visual_owner_if_absent(
        self,
        original: VisualOriginalPlan,
        checkpoint: ExecutionCheckpoint,
        verification_state: VerificationBudgetState,
        retry_budget: RecoveryBudget,
    ) -> VisualOwnerPublicationRecord:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            canonical,
            current_publication,
            initial_inputs,
            publication,
            retry_definition,
            validate_group,
            verification_definition,
        )

        original, checkpoint, pool, retry, key = initial_inputs(
            original, checkpoint, verification_state, retry_budget
        )
        task = original.identity.task_id
        with self._lock:
            first = self._visual_record_locked(task, 1)
            if first is not None:
                self._ensure_same_hash(
                    "VisualOwnerInitial", task, first.to_payload()["operation_hash"], key
                )
                existing = self._visual_record_locked(task)
                stored_original = self._visual_original_locked(task, original.contract.plan_version)
                previous = (
                    self._visual_record_locked(task, existing.owner_revision - 1)
                    if existing and existing.owner_revision > 1
                    else None
                )
                if (
                    existing is None
                    or stored_original is None
                    or stored_original.digest() != original.digest()
                    or not self._visual_versions_match(original)
                    or not current_publication(
                        existing,
                        stored_original,
                        *self._visual_group_locked(task),
                        previous=previous,
                    )
                ):
                    raise IdempotencyConflictError(
                        "visual source currently unavailable; fresh publication required"
                    )
                return existing.detached()
            if any(name == task for name, _ in self._visual_originals):
                raise IdempotencyConflictError("original sidecar exists without publication")
            active, prior_checkpoint, prior_pool, prior_retry = self._visual_group_locked(task)
            present = [
                value is not None for value in (active, prior_checkpoint, prior_pool, prior_retry)
            ]
            if any(present):
                if not all(present):
                    raise IdempotencyConflictError("partial existing visual task group")
                try:
                    validate_group(original, active, prior_checkpoint, prior_pool, prior_retry)
                    if (
                        canonical(prior_checkpoint.model_dump(mode="json"))
                        != canonical(checkpoint.model_dump(mode="json"))
                        or not self._visual_versions_match(original)
                        or verification_definition(prior_pool) != verification_definition(pool)
                        or retry_definition(prior_retry) != retry_definition(retry)
                    ):
                        raise ValueError("existing source definition differs")
                except (ValueError, TypeError) as error:
                    raise IdempotencyConflictError("existing visual source differs") from error
                pool, retry = prior_pool.detached(), prior_retry.model_copy(deep=True)
            else:
                if self._contract_versions.get(task) or self._plan_versions.get(task):
                    raise IdempotencyConflictError("partial existing contract/version history")
                if checkpoint.checkpoint_id in self._checkpoints:
                    raise IdempotencyConflictError(
                        "initial checkpoint identity already belongs to a source"
                    )
                now = _utc_now()
                active = ActiveTaskContractRecord(
                    task_id=task,
                    plan_id=original.identity.plan_id,
                    robot_id=original.identity.robot_id,
                    plan_version=original.contract.plan_version,
                    command_seq=original.contract.command_seq,
                    scene_version=original.contract.scene_version,
                    contract=original.contract,
                    status="ACTIVE",
                    created_at=now,
                    activated_at=now,
                    contract_hash=_contract_hash(original.contract),
                )
            saved = publication(
                original,
                checkpoint,
                pool,
                retry,
                revision=1,
                generation=0,
                source_revision=None,
                operation_hash=key,
            )
            # All validation completed before the first mutation under this lock.
            if not any(present):
                self._active_contracts[task] = active
                self._contract_versions[task] = [active]
                self._plan_versions[task] = (active.plan_version, active.command_seq)
                self._checkpoints[checkpoint.checkpoint_id] = checkpoint
                self._checkpoint_hashes[checkpoint.checkpoint_id] = checkpoint.checkpoint_hash
                self._checkpoints_by_task[task] = [checkpoint.checkpoint_id]
                self._verification_budgets[task] = pool
                self._budgets[task] = retry
            self._visual_originals[(task, original.contract.plan_version)] = (
                canonical(original.to_payload()),
                original.digest(),
            )
            self._visual_publications[(task, 1)] = canonical(saved.to_payload())
            return saved.detached()

    def publish_visual_boundary_if_current(
        self,
        *,
        task_id: str,
        owner_epoch: str,
        expected_owner_revision: int,
        expected_contract_hash: str,
        expected_checkpoint_hash: str,
        checkpoint: ExecutionCheckpoint,
        grounding: StepGroundingBinding | None,
        state_generation: int,
    ) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            canonical,
            counter,
            monotonic_pools,
            operation_hash,
            publication,
            record_binding_valid,
            validate_checkpoint,
            validate_grounding,
            validate_group,
        )

        counter(expected_owner_revision)
        counter(state_generation)
        key = operation_hash(
            task_id=task_id,
            owner_epoch=owner_epoch,
            expected_owner_revision=expected_owner_revision,
            expected_contract_hash=expected_contract_hash,
            expected_checkpoint_hash=expected_checkpoint_hash,
            checkpoint=checkpoint,
            grounding=grounding,
            state_generation=state_generation,
        )
        with self._lock:
            duplicate = self._visual_record_locked(task_id, expected_owner_revision + 1)
            if duplicate is not None and duplicate.to_payload()["operation_hash"] == key:
                return duplicate.detached()
            previous = self._visual_record_locked(task_id)
            if (
                previous is None
                or previous.owner_revision != expected_owner_revision
                or previous.identity.owner_epoch != owner_epoch
                or state_generation <= previous.state_generation
            ):
                return None
            original = self._visual_original_locked(task_id, previous.checkpoint.plan_version)
            active, current, pool, retry = self._visual_group_locked(task_id)
            if (
                original is None
                or any(value is None for value in (active, current, pool, retry))
                or not self._visual_versions_match(original)
                or active.contract_hash != expected_contract_hash
                or current.checkpoint_hash != expected_checkpoint_hash
                or current.checkpoint_hash != previous.checkpoint.checkpoint_hash
            ):
                return None
            try:
                ancestor = (
                    self._visual_record_locked(task_id, previous.owner_revision - 1)
                    if previous.owner_revision > 1
                    else None
                )
                if not record_binding_valid(previous, original, ancestor):
                    return None
                validate_group(original, active, current, pool, retry)
                if not monotonic_pools(previous, pool, retry):
                    return None
                next_checkpoint = validate_checkpoint(original, checkpoint, current)
                bound = validate_grounding(
                    original, previous, next_checkpoint, grounding, state_generation
                )
                saved = publication(
                    original,
                    next_checkpoint,
                    pool,
                    retry,
                    revision=previous.owner_revision + 1,
                    generation=state_generation,
                    source_revision=previous.owner_revision,
                    operation_hash=key,
                    grounding=bound,
                )
            except (ValueError, TypeError):
                return None
            collision = self._checkpoints.get(next_checkpoint.checkpoint_id)
            if collision is not None and canonical(collision.model_dump(mode="json")) != canonical(
                next_checkpoint.model_dump(mode="json")
            ):
                return None
            self._checkpoints[next_checkpoint.checkpoint_id] = next_checkpoint
            self._checkpoint_hashes[next_checkpoint.checkpoint_id] = next_checkpoint.checkpoint_hash
            ids = self._checkpoints_by_task.setdefault(task_id, [])
            if next_checkpoint.checkpoint_id not in ids:
                ids.append(next_checkpoint.checkpoint_id)
            self._visual_publications[(task_id, saved.owner_revision)] = canonical(
                saved.to_payload()
            )
            return saved.detached()
