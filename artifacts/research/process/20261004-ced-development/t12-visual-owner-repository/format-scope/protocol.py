class _ScopedFormat:
    def initialize_visual_owner_if_absent(
        self,
        original: VisualOriginalPlan,
        checkpoint: ExecutionCheckpoint,
        verification_state: VerificationBudgetState,
        retry_budget: RecoveryBudget,
    ) -> VisualOwnerPublicationRecord:
        """Atomically register a durable source only, preserving complete existing pools."""
        ...

    def get_visual_original_plan(
        self, task_id: str, plan_version: int
    ) -> VisualOriginalPlan | None: ...

    def get_visual_owner_publication(self, task_id: str) -> VisualOwnerPublicationRecord | None:
        """Coherent current durable source; stale/expired publications remain unavailable."""
        ...

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
        """CAS checkpoint/publication only, with no physical or mode authority."""
        ...
