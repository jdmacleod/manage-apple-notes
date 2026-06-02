"""CDK stack: EC2 g5.xlarge running Ollama, accessible via SSH tunnel."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


def _detect_public_ip() -> str:
    """Return the caller's public IP as a /32 CIDR, for the SSH security group rule."""
    try:
        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return f"{data['ip']}/32"
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise RuntimeError(
            "Could not auto-detect your public IP for the security group.\n"
            "Set 'aws.allowed_cidr' in config/settings.local.yaml (e.g. '1.2.3.4/32')."
        ) from exc


def _load_user_data(model: str, persistent_bucket: str) -> str:
    script_path = Path(__file__).parent / "user_data" / "setup.sh"
    template = script_path.read_text()
    return template.replace("__MODEL__", model).replace("__PERSISTENT_BUCKET__", persistent_bucket)


class AwsLlmStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        aws_config: dict,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        instance_type = aws_config.get("instance_type", "g5.xlarge")
        key_pair_name: str = aws_config["key_pair_name"]
        # update for new AWS keyPair replacing keyName
        keyPair = ec2.KeyPair.from_key_pair_name(self, "KeyPair", key_pair_name)
        ssh_key_path: str = os.path.expanduser(
            os.environ.get("AWS_SSH_KEY_PATH") or aws_config.get("ssh_key_path", "~/.ssh/id_rsa")
        )
        model: str = aws_config.get("model", "llama3")
        persistent_storage: bool = bool(aws_config.get("persistent_model_storage", False))
        s3_bucket_name: str = aws_config.get("s3_model_bucket", "")
        allowed_cidr: str = (
            os.environ.get("AWS_ALLOWED_CIDR") or aws_config.get("allowed_cidr", "") or _detect_public_ip()
        )

        # ── VPC ───────────────────────────────────────────────────────────────
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # ── Security group: SSH only from deployer IP ─────────────────────────
        sg = ec2.SecurityGroup(
            self,
            "LlmSg",
            vpc=vpc,
            description="Ollama LLM instance, SSH only from deployer",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(allowed_cidr),
            connection=ec2.Port.tcp(22),
            description=f"SSH from deployer ({allowed_cidr})",
        )

        # ── IAM role ──────────────────────────────────────────────────────────
        role = iam.Role(
            self,
            "LlmInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )

        # ── Optional S3 model cache ────────────────────────────────────────────
        model_bucket: s3.Bucket | None = None
        bucket_name_for_userdata = ""

        if persistent_storage:
            if s3_bucket_name:
                # Re-use an existing bucket (e.g. retained from a prior deploy)
                existing = s3.Bucket.from_bucket_name(self, "ModelBucket", s3_bucket_name)
                existing.grant_read_write(role)
                bucket_name_for_userdata = s3_bucket_name
                cdk.CfnOutput(self, "ModelBucketName", value=s3_bucket_name)
            else:
                model_bucket = s3.Bucket(
                    self,
                    "ModelBucket",
                    encryption=s3.BucketEncryption.S3_MANAGED,
                    block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                    enforce_ssl=True,
                    removal_policy=cdk.RemovalPolicy.RETAIN,
                )
                model_bucket.grant_read_write(role)
                bucket_name_for_userdata = model_bucket.bucket_name
                cdk.CfnOutput(
                    self,
                    "ModelBucketName",
                    value=model_bucket.bucket_name,
                    description=(
                        "S3 bucket storing Ollama models, NOT deleted by cdk destroy. "
                        "Set aws.s3_model_bucket to this name to reuse on next deploy."
                    ),
                )

        # ── AMI: AWS Deep Learning AMI (Amazon Linux 2023) — NVIDIA drivers included ──
        ami = ec2.MachineImage.from_ssm_parameter(
            "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-amazon-linux-2023/latest/ami-id",
            os=ec2.OperatingSystemType.LINUX,
        )

        # ── User data ─────────────────────────────────────────────────────────
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(_load_user_data(model, bucket_name_for_userdata))

        # ── EC2 instance ──────────────────────────────────────────────────────
        instance = ec2.Instance(
            self,
            "LlmInstance",
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ami,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg,
            role=role,
            key_pair=keyPair,
            user_data=user_data,
            propagate_tags_to_volume_on_creation=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        100,  # GB — enough for several large models
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True,
                    ),
                )
            ],
        )

        # ── Cost-tracking tags (applied to all resources in this stack) ───────
        cdk.Tags.of(self).add("Project", "manage-apple-notes")

        # ── Outputs ───────────────────────────────────────────────────────────
        tunnel_cmd = (
            f"ssh -i {ssh_key_path} -N -L 11434:localhost:11434 "
            f"ec2-user@{instance.instance_public_ip}"
        )

        cdk.CfnOutput(self, "InstancePublicIp", value=instance.instance_public_ip)
        cdk.CfnOutput(
            self,
            "SshTunnelCommand",
            value=tunnel_cmd,
            description=(
                "Run this once per session to forward Ollama to localhost:11434. "
                "Then set OLLAMA_BASE_URL=http://localhost:11434 in your .env file."
            ),
        )
        cdk.CfnOutput(
            self,
            "OllamaEnvHint",
            value="export OLLAMA_BASE_URL=http://localhost:11434",
            description="Add to your .env after starting the SSH tunnel",
        )
        cdk.CfnOutput(
            self,
            "ModelPullLog",
            value=f"ssh -i {ssh_key_path} ec2-user@{instance.instance_public_ip} "
            "tail -f /var/log/ollama-pull.log",
            description="Watch model pre-pull progress on the instance",
        )
