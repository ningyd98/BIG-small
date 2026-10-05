class _ScopedFormat:
    def _visual_original_locked(self, task_id: str, plan_version: int) -> VisualOriginalPlan | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            original_from_payload,
        )

        row = self._conn.execute(
            "SELECT * FROM visual_original_plans WHERE task_id=? AND plan_version=?",
            (task_id, plan_version),
        ).fetchone()
        if row is None:
            return None
        original = original_from_payload(json.loads(row["payload_json"]))
        if (
            original.digest() != row["original_hash"]
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
            row = self._conn.execute(
                "SELECT * FROM visual_owner_publications WHERE task_id=? "
                "ORDER BY owner_revision DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM visual_owner_publications WHERE task_id=? AND owner_revision=?",
                (task_id, revision),
            ).fetchone()
        if row is None:
            return None
        result = VisualOwnerPublicationRecord.from_payload(json.loads(row["payload_json"]))
        if (
            result.identity.task_id != task_id
            or result.owner_revision != row["owner_revision"]
            or result.identity.owner_epoch != row["owner_epoch"]
            or result.state_generation != row["state_generation"]
            or result.digest() != row["publication_hash"]
        ):
            raise ValueError("stored publication columns/hash differ")
        return result

    def _visual_group_locked(self, task_id: str) -> tuple[Any, Any, Any, Any]:
        active = None
        row = self._conn.execute(
            "SELECT * FROM active_task_contracts WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is not None:
            active = ActiveTaskContractRecord.model_validate_json(row["record_json"])
            if any(
                getattr(active, name) != row[name]
                for name in (
                    "task_id",
                    "plan_id",
                    "robot_id",
                    "plan_version",
                    "command_seq",
                    "scene_version",
                    "contract_hash",
                )
            ):
                raise ValueError("active source columns differ")
        checkpoint = None
        row = self._conn.execute(
            "SELECT * FROM execution_checkpoints WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is not None:
            checkpoint = ExecutionCheckpoint.model_validate_json(row["payload_json"])
            if any(
                getattr(checkpoint, name) != row[name]
                for name in (
                    "checkpoint_id",
                    "task_id",
                    "plan_id",
                    "robot_id",
                    "plan_version",
                    "command_seq",
                    "execution_state",
                    "checkpoint_hash",
                )
            ):
                raise ValueError("checkpoint source columns differ")
        return (
            active,
            checkpoint,
            self.get_verification_budget(task_id),
            self.get_retry_budget(task_id),
        )

    def _visual_versions_match(self, original: VisualOriginalPlan) -> bool:
        row = self._conn.execute(
            "SELECT plan_version,command_seq FROM plan_versions WHERE task_id=?",
            (original.identity.task_id,),
        ).fetchone()
        active = self._conn.execute(
            "SELECT record_json FROM active_task_contracts WHERE task_id=?",
            (original.identity.task_id,),
        ).fetchone()
        version = self._conn.execute(
            "SELECT record_json,contract_hash,plan_id,robot_id,command_seq,scene_version "
            "FROM task_contract_versions WHERE task_id=? AND plan_version=?",
            (original.identity.task_id, original.contract.plan_version),
        ).fetchone()
        if row is None or active is None or version is None:
            return False
        active_payload, version_payload = (
            json.loads(active["record_json"]),
            json.loads(version["record_json"]),
        )
        return (
            (row["plan_version"], row["command_seq"])
            == (original.contract.plan_version, original.contract.command_seq)
            and active_payload == version_payload
            and all(
                version_payload[name] == version[name]
                for name in ("contract_hash", "plan_id", "robot_id", "command_seq", "scene_version")
            )
        )

    def _visual_store_record_locked(self, record: VisualOwnerPublicationRecord) -> None:
        self._conn.execute(
            "INSERT INTO visual_owner_publications VALUES (?,?,?,?,?,?)",
            (
                record.identity.task_id,
                record.owner_revision,
                record.identity.owner_epoch,
                record.state_generation,
                self._json(record.to_payload()),
                record.digest(),
            ),
        )

    def _visual_store_checkpoint_locked(self, checkpoint: ExecutionCheckpoint) -> None:
        row = self._conn.execute(
            "SELECT checkpoint_hash FROM execution_checkpoints WHERE checkpoint_id=?",
            (checkpoint.checkpoint_id,),
        ).fetchone()
        if row is not None:
            _same_or_conflict(
                "ExecutionCheckpoint",
                checkpoint.checkpoint_id,
                row["checkpoint_hash"],
                checkpoint.checkpoint_hash,
            )
            return
        self._conn.execute(
            """INSERT INTO execution_checkpoints (
            checkpoint_id,task_id,plan_id,robot_id,plan_version,command_seq,execution_state,
            completed_step_ids_json,payload_json,checkpoint_hash,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                checkpoint.checkpoint_id,
                checkpoint.task_id,
                checkpoint.plan_id,
                checkpoint.robot_id,
                checkpoint.plan_version,
                checkpoint.command_seq,
                checkpoint.execution_state,
                self._json(checkpoint.completed_step_ids),
                checkpoint.model_dump_json(),
                checkpoint.checkpoint_hash,
                checkpoint.created_at.isoformat(),
                checkpoint.updated_at.isoformat(),
            ),
        )

    def _visual_store_retry_locked(self, retry: RecoveryBudget) -> None:
        self._conn.execute(
            """INSERT INTO recovery_budgets (
            budget_id,task_id,per_step_retry_limit,per_skill_retry_limit,task_total_retry_limit,
            retry_count_used,task_retry_count,step_retry_counts_json,skill_retry_counts_json,event_retry_counts_json,
            retry_cooldown_ms,retry_deadline,retry_backoff_policy,effective_retry_limit,remaining_retries,
            scene_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                retry.budget_id,
                retry.task_id,
                retry.per_step_retry_limit,
                retry.per_skill_retry_limit,
                retry.task_total_retry_limit,
                retry.retry_count_used,
                retry.task_retry_count,
                self._json(retry.step_retry_counts),
                self._json(retry.skill_retry_counts),
                self._json(retry.event_retry_counts),
                retry.retry_cooldown_ms,
                retry.retry_deadline.isoformat() if retry.retry_deadline else None,
                retry.retry_backoff_policy,
                retry.effective_retry_limit,
                retry.remaining_retries,
                retry.scene_version,
                retry.created_at.isoformat(),
                retry.updated_at.isoformat(),
            ),
        )

    def get_visual_original_plan(
        self, task_id: str, plan_version: int
    ) -> VisualOriginalPlan | None:
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
            return self._visual_original_locked(task_id, plan_version)

    def get_visual_owner_publication(self, task_id: str) -> VisualOwnerPublicationRecord | None:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
            current_publication,
        )

        with self._write_lock, self._conn:
            self._conn.execute("BEGIN")
            record = self._visual_record_locked(task_id)
            if record is None:
                return None
            original = self._visual_original_locked(task_id, record.checkpoint.plan_version)
            if original is None or not self._visual_versions_match(original):
                return None
            previous = (
                self._visual_record_locked(task_id, record.owner_revision - 1)
                if record.owner_revision > 1
                else None
            )
            try:
                group = self._visual_group_locked(task_id)
            except (ValueError, TypeError):
                return None
            return (
                record.detached()
                if current_publication(record, original, *group, previous=previous)
                else None
            )

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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            first = self._visual_record_locked(task, 1)
            if first is not None:
                _same_or_conflict(
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
            if self._conn.execute(
                "SELECT 1 FROM visual_original_plans WHERE task_id=?", (task,)
            ).fetchone():
                raise IdempotencyConflictError("original sidecar exists without publication")
            try:
                active, prior_checkpoint, prior_pool, prior_retry = self._visual_group_locked(task)
            except (ValueError, TypeError) as error:
                raise IdempotencyConflictError("existing visual source differs") from error
            present = [
                item is not None for item in (active, prior_checkpoint, prior_pool, prior_retry)
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
                if (
                    self._conn.execute(
                        "SELECT 1 FROM task_contract_versions WHERE task_id=?", (task,)
                    ).fetchone()
                    or self._conn.execute(
                        "SELECT 1 FROM plan_versions WHERE task_id=?", (task,)
                    ).fetchone()
                ):
                    raise IdempotencyConflictError("partial existing contract/version history")
                if self._conn.execute(
                    "SELECT 1 FROM execution_checkpoints WHERE checkpoint_id=?",
                    (checkpoint.checkpoint_id,),
                ).fetchone():
                    raise IdempotencyConflictError(
                        "initial checkpoint identity already belongs to a source"
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
            if not any(present):
                self._save_active_contract_locked(
                    original.contract,
                    plan_id=original.identity.plan_id,
                    robot_id=original.identity.robot_id,
                    status="ACTIVE",
                    based_on_plan_version=None,
                    correlation_id="",
                    commit=False,
                )
                self._visual_store_checkpoint_locked(checkpoint)
                self._visual_store_retry_locked(retry)
                self._conn.execute(
                    "INSERT INTO verification_budgets VALUES (?,?,?,?)",
                    (
                        task,
                        pool.revision,
                        self._json(pool.to_payload()),
                        pool.content_hash,
                    ),
                )
            self._conn.execute(
                "INSERT INTO visual_original_plans VALUES (?,?,?,?)",
                (
                    task,
                    original.contract.plan_version,
                    canonical(original.to_payload()),
                    original.digest(),
                ),
            )
            self._visual_store_record_locked(saved)
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
        with self._write_lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
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
            try:
                active, current, pool, retry = self._visual_group_locked(task_id)
            except (ValueError, TypeError):
                return None
            if (
                original is None
                or any(item is None for item in (active, current, pool, retry))
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
            row = self._conn.execute(
                "SELECT payload_json,checkpoint_hash FROM execution_checkpoints "
                "WHERE checkpoint_id=?",
                (next_checkpoint.checkpoint_id,),
            ).fetchone()
            if row is not None and (
                row["checkpoint_hash"] != next_checkpoint.checkpoint_hash
                or canonical(json.loads(row["payload_json"]))
                != canonical(next_checkpoint.model_dump(mode="json"))
            ):
                return None
            self._visual_store_checkpoint_locked(next_checkpoint)
            self._visual_store_record_locked(saved)
            return saved.detached()
