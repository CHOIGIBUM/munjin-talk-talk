param(
  [string]$InputPath = "evaluation\ir\data\eval_cases.json",
  [string]$OutputDir = "",
  [int]$TopK = 20,
  [switch]$FullPipeline,
  [switch]$SkipFastIr
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $OutputDir = "evaluation\ir\outputs\baseline_$stamp"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "[1/3] Validate evaluation dataset"
python evaluation\ir\validate_eval_data.py `
  --input $InputPath `
  --summary-output (Join-Path $OutputDir "dataset_summary.json")

if (-not $SkipFastIr) {
  Write-Host "[2/3] Fast IR candidate baseline, no LLM linker"
  python evaluation\ir\run_ir_eval.py `
    --input $InputPath `
    --output-dir (Join-Path $OutputDir "ir_candidate_only") `
    --top-k $TopK `
    --variants C `
    --skip-llm-judge

  Write-Host "[2/3] Oracle upper-bound IR baseline"
  python evaluation\ir\run_ir_eval.py `
    --input $InputPath `
    --output-dir (Join-Path $OutputDir "ir_oracle_upper_bound") `
    --top-k $TopK `
    --variants O `
    --skip-llm-judge
} else {
  Write-Host "[2/3] Fast IR baseline skipped"
}

if ($FullPipeline) {
  Write-Host "[3/3] Full pipeline baseline with Bedrock extraction/linker"
  python evaluation\ir\run_eval_suite.py `
    --input $InputPath `
    --output-dir (Join-Path $OutputDir "full_pipeline") `
    --top-k $TopK
} else {
  Write-Host "[3/3] Full pipeline skipped. Add -FullPipeline to run Bedrock extraction/linker."
}

Write-Host "Baseline output: $OutputDir"
