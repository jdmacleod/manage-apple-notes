"""CDK stack tests for AwsLlmStack using aws_cdk.assertions."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the infra directory is on the path so aws_llm_stack can be imported directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


_MIN_CONFIG = {
    "region": "us-east-1",
    "instance_type": "g5.xlarge",
    "key_pair_name": "test-key",
    "ssh_key_path": "~/.ssh/test-key.pem",
    "model": "llama3",
    "persistent_model_storage": False,
    "allowed_cidr": "1.2.3.4/32",
}


@pytest.fixture()
def assertions():
    """Return the aws_cdk.assertions module (skips test if not installed)."""
    return pytest.importorskip("aws_cdk.assertions", reason="aws-cdk-lib not installed")


@pytest.fixture()
def stack_template(assertions):
    """Synthesise the stack with minimal config and return an aws_cdk.assertions.Template."""
    aws_cdk = pytest.importorskip("aws_cdk", reason="aws-cdk-lib not installed")
    from aws_llm_stack import AwsLlmStack

    app = aws_cdk.App()
    with patch("aws_llm_stack._detect_public_ip", return_value="1.2.3.4/32"):
        stack = AwsLlmStack(
            app,
            "TestStack",
            aws_config=_MIN_CONFIG,
            env=aws_cdk.Environment(account="123456789012", region="us-east-1"),
        )
    return assertions.Template.from_stack(stack)


class TestSecurityGroup:
    def test_only_port_22_inbound(self, stack_template) -> None:
        stack_template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "SecurityGroupIngress": [
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "CidrIp": "1.2.3.4/32",
                    }
                ]
            },
        )

    def test_port_11434_not_open(self, stack_template) -> None:
        resources = stack_template.find_resources("AWS::EC2::SecurityGroup")
        for resource in resources.values():
            for rule in resource.get("Properties", {}).get("SecurityGroupIngress", []):
                assert rule.get("FromPort") != 11434, "Port 11434 must not be exposed"


class TestIamRole:
    def test_ec2_principal(self, stack_template) -> None:
        stack_template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "AssumeRolePolicyDocument": {
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "ec2.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ]
                }
            },
        )

    def test_ssm_managed_policy_attached(self, stack_template) -> None:
        stack_template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "ManagedPolicyArns": [
                    {
                        "Fn::Join": [
                            "",
                            [
                                "arn:",
                                {"Ref": "AWS::Partition"},
                                ":iam::aws:policy/AmazonSSMManagedInstanceCore",
                            ],
                        ]
                    }
                ]
            },
        )


class TestS3Bucket:
    def test_no_bucket_when_persistent_storage_false(self, stack_template) -> None:
        stack_template.resource_count_is("AWS::S3::Bucket", 0)

    def test_bucket_created_when_persistent_storage_true(self) -> None:
        aws_cdk = pytest.importorskip("aws_cdk")
        assertions = pytest.importorskip("aws_cdk.assertions")
        from aws_llm_stack import AwsLlmStack

        config = {**_MIN_CONFIG, "persistent_model_storage": True}
        app = aws_cdk.App()
        with patch("aws_llm_stack._detect_public_ip", return_value="1.2.3.4/32"):
            stack = AwsLlmStack(
                app,
                "TestStackS3",
                aws_config=config,
                env=aws_cdk.Environment(account="123456789012", region="us-east-1"),
            )
        tmpl = assertions.Template.from_stack(stack)
        tmpl.resource_count_is("AWS::S3::Bucket", 1)

    def test_bucket_has_retain_policy(self) -> None:
        aws_cdk = pytest.importorskip("aws_cdk")
        assertions = pytest.importorskip("aws_cdk.assertions")
        from aws_llm_stack import AwsLlmStack

        config = {**_MIN_CONFIG, "persistent_model_storage": True}
        app = aws_cdk.App()
        with patch("aws_llm_stack._detect_public_ip", return_value="1.2.3.4/32"):
            stack = AwsLlmStack(
                app,
                "TestStackRetain",
                aws_config=config,
                env=aws_cdk.Environment(account="123456789012", region="us-east-1"),
            )
        tmpl = assertions.Template.from_stack(stack)
        tmpl.has_resource("AWS::S3::Bucket", {"DeletionPolicy": "Retain"})


class TestOutputs:
    def test_ssh_tunnel_command_output_exists(self, stack_template) -> None:
        stack_template.has_output("SshTunnelCommand", {})

    def test_instance_ip_output_exists(self, stack_template) -> None:
        stack_template.has_output("InstancePublicIp", {})

    def test_ollama_env_hint_output_exists(self, stack_template) -> None:
        stack_template.has_output("OllamaEnvHint", {})


class TestTags:
    def test_project_tag_on_ec2_instance(self, stack_template, assertions) -> None:
        stack_template.has_resource_properties(
            "AWS::EC2::Instance",
            {
                "Tags": assertions.Match.array_with(
                    [{"Key": "Project", "Value": "manage-apple-notes"}]
                )
            },
        )

    def test_project_tag_on_security_group(self, stack_template, assertions) -> None:
        stack_template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "Tags": assertions.Match.array_with(
                    [{"Key": "Project", "Value": "manage-apple-notes"}]
                )
            },
        )

    def test_project_tag_on_iam_role(self, stack_template, assertions) -> None:
        stack_template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "Tags": assertions.Match.array_with(
                    [{"Key": "Project", "Value": "manage-apple-notes"}]
                )
            },
        )

    def test_project_tag_on_s3_bucket(self, assertions) -> None:
        aws_cdk = pytest.importorskip("aws_cdk")
        from aws_llm_stack import AwsLlmStack

        config = {**_MIN_CONFIG, "persistent_model_storage": True}
        app = aws_cdk.App()
        with patch("aws_llm_stack._detect_public_ip", return_value="1.2.3.4/32"):
            stack = AwsLlmStack(
                app,
                "TestStackTagS3",
                aws_config=config,
                env=aws_cdk.Environment(account="123456789012", region="us-east-1"),
            )
        tmpl = assertions.Template.from_stack(stack)
        tmpl.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "Tags": assertions.Match.array_with(
                    [{"Key": "Project", "Value": "manage-apple-notes"}]
                )
            },
        )
