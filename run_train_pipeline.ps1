[CmdletBinding()]
param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$ConfigPath = "configs\rtx4060ti_8gb_mail_agent.yaml",
    [string]$LogLevel = "INFO",
    [switch]$ForceDownloadSampleData,
    [switch]$SkipTrain,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TrainArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

function Resolve-RepoPath {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return Join-Path $repoRoot $PathValue
}

$resolvedPythonExe = Resolve-RepoPath $PythonExe
$resolvedConfigPath = Resolve-RepoPath $ConfigPath
$rawTrainPath = Join-Path $repoRoot "data\raw\train.jsonl"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("==> " + $Message) -ForegroundColor Cyan
}

function Invoke-PythonStep {
    param(
        [string]$StepName,
        [string[]]$Arguments
    )

    Write-Step $StepName
    & $resolvedPythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $StepName (exit code $LASTEXITCODE)"
    }
}

if (-not (Test-Path $resolvedPythonExe)) {
    throw "Python interpreter not found: $resolvedPythonExe"
}

if (-not $SkipTrain -and -not (Test-Path $resolvedConfigPath)) {
    throw "Training config not found: $resolvedConfigPath"
}

$shouldDownloadSampleData = $ForceDownloadSampleData.IsPresent -or -not (Test-Path $rawTrainPath) -or (Get-Item $rawTrainPath).Length -eq 0

if ($shouldDownloadSampleData) {
    Invoke-PythonStep `
        -StepName "Downloading sample raw train data" `
        -Arguments @(
            "-X", "utf8",
            "src/download_sample_data.py",
            "--log_level", $LogLevel
        )
} else {
    Write-Step "Using existing raw train data at data\raw\train.jsonl"
}

Invoke-PythonStep `
    -StepName "Validating labeled real Gmail records" `
    -Arguments @(
        "-X", "utf8",
        "scripts/validate_labels.py",
        "--input", "data/labeled/emails_labeled.jsonl"
    )

Invoke-PythonStep `
    -StepName "Curating general raw train data" `
    -Arguments @(
        "-X", "utf8",
        "src/curate_data.py",
        "--input_path", "data/raw/train.jsonl",
        "--output_path", "data/curated/train_curated.jsonl",
        "--review_path", "data/curated/review_candidates.jsonl",
        "--report_path", "data/curated/curation_report.json",
        "--log_level", $LogLevel
    )

Invoke-PythonStep `
    -StepName "Building real Gmail train and eval datasets" `
    -Arguments @(
        "-X", "utf8",
        "src/build_gmail_real_dataset.py",
        "--input_path", "data/labeled/emails_labeled.jsonl",
        "--output_path", "data/curated/gmail_real_labeled_curated.jsonl",
        "--eval_output_path", "data/eval/gmail_real_gold.jsonl",
        "--log_level", $LogLevel
    )

Invoke-PythonStep `
    -StepName "Building mixed chat and real Gmail training dataset" `
    -Arguments @(
        "-X", "utf8",
        "src/build_dataset.py",
        "--target_profile", "gmail_real_v1",
        "--output_path", "data/curated/gmail_real_train.jsonl",
        "--log_level", $LogLevel
    )

Invoke-PythonStep `
    -StepName "Preparing SFT train and validation datasets" `
    -Arguments @(
        "-X", "utf8",
        "src/prepare_data.py",
        "--input_path", "data/curated/gmail_real_train.jsonl",
        "--output_path", "data/processed/train_sft_gmail_real.jsonl",
        "--val_output_path", "data/processed/val_sft_gmail_real.jsonl",
        "--log_level", $LogLevel
    )

if ($SkipTrain) {
    Write-Step "Skipping train_lora because -SkipTrain was provided"
    exit 0
}

$trainCommand = @(
    "-u", "-X", "utf8",
    "src/train_lora.py",
    "--config", $resolvedConfigPath,
    "--log_level", $LogLevel
)

if ($TrainArgs) {
    $trainCommand += $TrainArgs
}

Invoke-PythonStep `
    -StepName "Training LoRA adapter" `
    -Arguments $trainCommand

Write-Step "Pipeline finished successfully"
