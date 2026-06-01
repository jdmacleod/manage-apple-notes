# AWS Infrastructure — EC2 Ollama Endpoint

This document covers deploying and tearing down an EC2-hosted Ollama instance via the Python AWS CDK. The instance provides a local LLM endpoint for the manage-apple-notes pipeline, used via the existing `OLLAMA_BASE_URL` environment variable.

## Architecture

```
Your Mac                 AWS (us-east-1 or your region)
─────────                ──────────────────────────────
notes classify           EC2 g5.xlarge (1× NVIDIA A10G GPU)
  │                         └─ Ollama (port 11434, localhost only)
  │  OLLAMA_BASE_URL            └─ Security group: port 22 only
  │  http://localhost:11434           from deployer IP
  │                         IAM role (no access keys on instance)
  └─── SSH tunnel ──────────────────────────────────────────────
```

Port 11434 (Ollama) is never exposed to the internet. Access is exclusively via SSH port forwarding. The security group opens only port 22, restricted to your public IP at deploy time.

## Prerequisites

1. **AWS account** with an IAM user or role that has permissions to create EC2, IAM, S3, and CloudFormation resources.

2. **EC2 g5.xlarge quota** — the default service quota for G-family GPU instances is 0 vCPUs in most accounts. Request a quota increase before deploying:
   - AWS Console → Service Quotas → Amazon EC2 → "Running On-Demand G and VT instances"
   - Request at least 4 vCPUs (one g5.xlarge = 4 vCPUs)
   - Approval typically takes 24–48 hours.

3. **AWS CLI configured** — credentials via `~/.aws/credentials` or environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`). Never store credentials in the repo.

   ```bash
   aws configure   # or use SSO: aws sso login --profile <profile>
   aws sts get-caller-identity  # verify credentials work
   ```

4. **AWS CDK CLI** (Node.js-based):

   ```bash
   npm install -g aws-cdk
   cdk --version  # verify
   ```

5. **EC2 key pair** in your target region. Create one in the AWS Console (EC2 → Key Pairs → Create key pair) or via the CLI:

   ```bash
   aws ec2 create-key-pair --key-name my-ollama-key \
     --query 'KeyMaterial' --output text > ~/.ssh/my-ollama-key.pem
   chmod 400 ~/.ssh/my-ollama-key.pem
   ```

6. **Python CDK dependencies** — install in a virtualenv inside `infra/`:

   ```bash
   cd infra
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Configuration

Add an `aws:` block to `config/settings.local.yaml` (copy from the commented example in `settings.example.yaml`):

```yaml
aws:
  region: "us-east-1"
  instance_type: "g5.xlarge"          # adjust for cost vs performance
  key_pair_name: "my-ollama-key"      # name of the key pair in AWS
  ssh_key_path: "~/.ssh/my-ollama-key.pem"  # local path to the private key
  model: "gpt-oss:20b"                # Ollama model to pre-pull on launch
  persistent_model_storage: false     # see "Model Persistence" section below
  s3_model_bucket: ""                 # set after first deploy if persistent_model_storage: true
  allowed_cidr: ""                    # leave empty to auto-detect your public IP
```

Also set `context_size` for the Ollama provider in your `llm:` block. The recommended value for `gpt-oss:20b` on the g5.xlarge is **8192 tokens** — see [VRAM and context window](#vram-and-context-window) below:

```yaml
llm:
  provider: "ollama"
  model: "gpt-oss:20b"
  batch_size: 10
  context_size:
    ollama: 8192    # safe for gpt-oss:20b on 24 GB VRAM; see VRAM section below
```

## VRAM and Context Window

The g5.xlarge instance has one **NVIDIA A10G GPU with 24 GB GDDR6 VRAM**.

For `gpt-oss:20b` at Q4_K_M quantization:

| Component | VRAM usage |
|-----------|-----------|
| Model weights (20B params, Q4_K_M) | ~12 GB |
| CUDA runtime + framework overhead | ~1 GB |
| Available for KV cache | ~11 GB |

With ~11 GB available for the KV cache, the instance comfortably supports an **8,192-token (8K) context window**. Higher values up to 16K are possible depending on the model's exact layer/head configuration, but 8K is the tested and recommended default. Set `context_size.ollama` in `settings.local.yaml` to adjust.

> To check how much VRAM Ollama is currently using on the instance:
> ```bash
> ssh -i ~/.ssh/my-ollama-key.pem ec2-user@<ip> nvidia-smi
> ```

## Bootstrap (first time only)

```bash
cd infra
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
# e.g.: cdk bootstrap aws://123456789012/us-east-1
```

This creates a CDK toolkit stack (S3 bucket + ECR repo) used for asset staging. Required once per account/region.

## Deploy

```bash
cd infra
cdk deploy
```

CDK will:
1. Auto-detect your public IP (or use `allowed_cidr` from settings)
2. Create the security group, IAM role, EC2 instance, and optional S3 bucket
3. Run the user-data bootstrap script on the instance (installs Ollama, pulls the model)
4. Output connection details

Example output:
```
Outputs:
  AwsLlmStack.InstancePublicIp     = 54.210.100.42
  AwsLlmStack.SshTunnelCommand     = ssh -i ~/.ssh/my-ollama-key.pem -N -L 11434:localhost:11434 ec2-user@54.210.100.42
  AwsLlmStack.OllamaEnvHint        = export OLLAMA_BASE_URL=http://localhost:11434
  AwsLlmStack.ModelPullLog         = ssh -i ~/.ssh/... ec2-user@54.210.100.42 tail -f /var/log/ollama-pull.log
```

## Connecting (each session)

1. Open a terminal and run the `SshTunnelCommand` from the CDK output:

   ```bash
   ssh -i ~/.ssh/my-ollama-key.pem -N -L 11434:localhost:11434 ec2-user@54.210.100.42
   ```

   Keep this terminal open. The `-N` flag means "no command, just forward."

2. Set `OLLAMA_BASE_URL` in your `.env`:

   ```
   OLLAMA_BASE_URL=http://localhost:11434
   ```

3. Verify the connection:

   ```bash
   curl http://localhost:11434/api/tags
   ```

4. Run any pipeline command as usual:

   ```bash
   uv run notes classify --dry-run
   ```

## Model Pull Progress

The model is pulled in the background during instance launch. To watch progress:

```bash
# Use the ModelPullLog command from CDK output, e.g.:
ssh -i ~/.ssh/my-ollama-key.pem ec2-user@54.210.100.42 tail -f /var/log/ollama-pull.log
```

Allow 15–30 minutes for `gpt-oss:20b` (~12 GB) on first launch. The instance is connectable via SSH immediately; model pull runs in the background.

## Model Persistence (Optional S3 Cache)

By default, models are stored on the instance's EBS volume and lost when the instance is terminated. To persist models across deployments:

1. Set `persistent_model_storage: true` in `config/settings.local.yaml`
2. Run `cdk deploy` — CDK creates an S3 bucket and outputs its name
3. Copy the bucket name from `AwsLlmStack.ModelBucketName` into `s3_model_bucket` in settings
4. On subsequent deploys, models are synced from S3 on startup (~2–5 min vs ~15 min re-download)

**Important:** The S3 bucket has a `RETAIN` deletion policy. Running `cdk destroy` will NOT delete the bucket or its models. To clean up manually:

```bash
aws s3 rm s3://<bucket-name>/ --recursive
aws s3api delete-bucket --bucket <bucket-name>
```

## Destroying Infrastructure

```bash
cd infra
cdk destroy
```

This terminates the EC2 instance and removes the security group, IAM role, and CloudFormation stack. If `persistent_model_storage: true`, the S3 bucket is **retained** (see above).

## Cost

Approximate on-demand pricing (us-east-1, 2025):

| Resource | Cost |
|----------|------|
| g5.xlarge EC2 | ~$1.006/hr |
| 100 GB gp3 EBS | ~$0.008/hr |
| Data transfer (minimal) | ~$0.00/hr |
| **Total while running** | **~$1.01/hr** |

**Stop the instance when not in use** to avoid charges. The CDK stack can be destroyed and redeployed; with S3 model persistence, redeploy time is ~5 minutes vs ~20 minutes.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `cdk deploy` fails with quota error | Request EC2 g-instance quota increase |
| SSH connection refused | Instance may still be booting; wait 2–3 min |
| `ollama: command not found` via SSH | Bootstrap still running; check `/var/log/cloud-init-output.log` |
| Model not found in Ollama | Check `/var/log/ollama-pull.log`; re-run `ollama pull <model>` via SSH |
| `allowed_cidr` auto-detect fails | Set it explicitly: `allowed_cidr: "1.2.3.4/32"` |
