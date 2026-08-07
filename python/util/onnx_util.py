"""Thin re-export shim -- the real implementations now live in onnx_inference_manager.py
(see its "ONNX logging/provider helpers" section). Every onnx_*.py script in this project
already called these exclusively through self.onnx_util.X() (the base class attribute),
never a direct module-level onnx_util.X() call, so this module itself became dead weight
for all of them -- confirmed by grepping every script before removing it.

This file still exists only because tox/haxlib/ml/onnx/MovenetONNX.py (the legacy,
pre-ONNXInferenceManager script kept as a comparison baseline) looks 'onnx_util' up
directly via TD's DAT-based mod() mechanism, not a plain Python import, and calls
onnx_util.log_onnx_options()/providers()/log_model_details() on it directly. If that
script is ever retired, this file can go with it.
"""
from onnx_inference_manager import printONNX, log_onnx_options, providers, log_model_details, check_providers
