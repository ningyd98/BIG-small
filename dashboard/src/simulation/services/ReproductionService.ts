type ReproductionSignature = {
  source_commit: string;
  source_tree_hash: string;
  config_hash: string;
  environment_hash: string;
  backend: string;
  scenario: string;
  seed: number;
  control_mode: string;
};

export class ReproductionService {
  constructor(private readonly expected: ReproductionSignature) {}

  validate(actual: ReproductionSignature): {
    exact: boolean;
    warnings: string[];
  } {
    const warnings = Object.entries(this.expected)
      .filter(
        ([key, value]) => actual[key as keyof ReproductionSignature] !== value,
      )
      .map(([key]) => `${key} mismatch`);
    return { exact: warnings.length === 0, warnings };
  }
}
