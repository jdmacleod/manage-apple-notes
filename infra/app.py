#!/usr/bin/env python3
"""CDK app entry point for the AWS LLM infrastructure."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import aws_cdk as cdk
import yaml
from aws_llm_stack import AwsLlmStack

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _load_settings() -> dict:
    for name in ("settings.local.yaml", "settings.example.yaml"):
        path = CONFIG_DIR / name
        if path.exists():
            return yaml.safe_load(path.read_text()) or {}
    return {}


def main() -> None:
    settings = _load_settings()
    aws_config: dict = settings.get("aws", {})

    if not aws_config:
        print(
            "Error: no 'aws:' section found in config/settings.local.yaml.\n"
            "Copy the commented-out aws block from config/settings.example.yaml,\n"
            "uncomment it, fill in your values, and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not aws_config.get("key_pair_name"):
        print(
            "Error: aws.key_pair_name is required.\n"
            "Create an EC2 key pair in your target region and set its name in settings.",
            file=sys.stderr,
        )
        sys.exit(1)

    region = aws_config.get("region", "us-east-1")

    app = cdk.App()
    AwsLlmStack(
        app,
        "AwsLlmStack",
        aws_config=aws_config,
        env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=region),
    )
    app.synth()


if __name__ == "__main__":
    main()
