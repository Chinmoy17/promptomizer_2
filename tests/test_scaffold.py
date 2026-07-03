"""Scaffold sanity: package imports and config defaults resolve."""

from fdpo import __version__
from fdpo.config import ExperimentConfig, build_arg_parser


def test_version():
    assert __version__


def test_arg_parser_defaults():
    args = build_arg_parser().parse_args([])
    assert args.method == "fdpo"
    assert args.dataset == "gsm8k"
    assert args.budget_usd == ExperimentConfig().budget_usd


def test_config_to_dict_hides_keys():
    cfg = ExperimentConfig()
    d = cfg.to_dict()
    assert "api_key" not in str(d)
