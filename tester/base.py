import collections
import inspect

import numpy
import paddle
import torch

from .api_config import USE_CACHED_NUMPY, TensorConfig, cached_numpy
from .api_config.log_writer import log_accuracy_tolerance

# Todo: check paddle.linalg.pca_lowrank @cangtianhuang
not_support_api = frozenset(
    [
        "paddle.Tensor.coalesce",
        "paddle.Tensor.index_put",
        "paddle.Tensor.index_sample",
        "paddle.Tensor.is_coalesced",
        "paddle.linalg.pca_lowrank",
    ]
)

# keep rand_apis and stochastic_behavior_apis lists for future reference when checking if new api configs have random behavior @Cutelemon6
rand_apis = frozenset(
    [
        # "paddle.Tensor.__dir__",
        # "paddle.Tensor.bernoulli_",
        # "paddle.Tensor.cauchy_",
        # "paddle.Tensor.exponential_",
        # "paddle.Tensor.geometric_",
        # "paddle.Tensor.log_normal_",
        # "paddle.Tensor.multinomial",
        # "paddle.Tensor.normal_",
        # "paddle.Tensor.uniform_",
        # "paddle.bernoulli_",
        # "paddle.binomial",
        # "paddle.cauchy_",
        # "paddle.empty",
        # "paddle.empty_like",
        # "paddle.geometric_",
        # "paddle.log_normal",
        # "paddle.log_normal_",
        # "paddle.multinomial",
        # "paddle.normal",
        # "paddle.normal_",
        # "paddle.poisson",
        # "paddle.rand",
        # "paddle.randint",
        # "paddle.randint_like",
        # "paddle.randn",
        # "paddle.randperm",
        # "paddle.standard_gamma",
        # "paddle.standard_normal",
        # "paddle.uniform",
    ]
)

stochastic_behavior_apis = frozenset(
    [
        # "paddle.Tensor.top_p_sampling",
        # "paddle.incubate.nn.functional.fused_bias_dropout_residual_layer_norm",
        # "paddle.incubate.nn.functional.fused_dropout_add",
        # "paddle.incubate.nn.functional.fused_multi_head_attention", # If parameter "dropout_rate=0.5, attn_dropout_rate=0.5 (default value)" is not equal to 0.0 or 1.0, the result involves random calculation.
        # "paddle.incubate.nn.functional.moe_dispatch",
        # "paddle.nn.functional.alpha_dropout",
        # "paddle.nn.functional.dropout",
        # "paddle.nn.functional.dropout2d",
        # "paddle.nn.functional.dropout3d",
        # "paddle.nn.functional.feature_alpha_dropout",
        # "paddle.nn.functional.fused_feedforward",
        # "paddle.nn.functional.rrelu", # If parameter "training=True" is set, the result involves random calculation.
        # "paddle.nn.functional.scaled_dot_product_attention", # If parameter "dropout_p=0.0" is not equal to 0.0 or 1.0, the result involves random calculation.
        # "paddle.scatter", # If overwrite is set to True and index contain duplicate values, the result involves random calculation.
        # "paddle.nn.functional.gumbel_softmax",
    ]
)

single_op_no_signature_apis = frozenset(
    [
        "__add__",
        "__div__",
        "__eq__",
        "__floordiv__",
        "__ge__",
        "__gt__",
        "__le__",
        "__lt__",
        "__matmul__",
        "__mod__",
        "__mul__",
        "__ne__",
        "__pow__",
        "__radd__",
        "__rmatmul__",
        "__rmod__",
        "__rmul__",
        "__rpow__",
        "__rsub__",
        "__rtruediv__",
        "__sub__",
        "__truediv__",
    ]
)


def get_arg(api_config, arg_pos, arg_name, default=None):
    if 0 <= arg_pos < len(api_config.args):
        return api_config.args[arg_pos]
    if arg_name in api_config.kwargs:
        return api_config.kwargs[arg_name]
    return default


no_signature_api_mappings = {
    f"paddle.Tensor.{method}": {
        "self": lambda cfg: get_arg(cfg, 0, "self"),
        "y": lambda cfg: get_arg(cfg, 1, "y"),
    }
    for method in single_op_no_signature_apis
}


handle_axes_api = frozenset(
    [
        "paddle.max",
        "paddle.mean",
        "paddle.min",
        "paddle.prod",
        "paddle.sum",
    ]
)

# All configs that report dtype diff when not in not_check_dtype list should be
# copied to tester/api_config/5_accuracy/accuracy_gpu_error_dtype_diff.txt
not_check_dtype = frozenset(
    [
        "paddle.Tensor.cumsum",
        "paddle.Tensor.frexp",
        "paddle.add",
        "paddle.add_n",
        "paddle.atan2",
        "paddle.clip",
        "paddle.copysign",
        "paddle.cummax",
        "paddle.cummin",
        "paddle.cumprod",
        "paddle.cumsum",
        "paddle.floor",
        "paddle.frexp",
        "paddle.histogram",
        "paddle.incubate.nn.functional.fused_layer_norm",
        "paddle.ldexp",
        "paddle.ldexp_",
        "paddle.linalg.lstsq",
        "paddle.nn.functional.adaptive_max_pool1d",
        "paddle.nn.functional.adaptive_max_pool2d",
        "paddle.nn.functional.adaptive_max_pool3d",
        "paddle.nn.functional.conv2d_transpose",
        "paddle.nn.functional.linear",
        "paddle.nn.functional.max_pool1d",
        "paddle.nn.functional.max_pool2d",
        "paddle.nn.functional.max_pool3d",
        "paddle.nn.functional.one_hot",
        "paddle.nn.functional.smooth_l1_loss",
        "paddle.vision.ops.roi_align",
        "paddle.where",
    ]
)

forward_only_apis = frozenset(
    [
        "__and__",
        "__eq__",
        "__floordiv__",
        "__ge__",
        "__gt__",
        "__invert__",
        "__le__",
        "__lshift__",
        "__lt__",
        "__ne__",
        "__or__",
        "__rand__",
        "__rand__",
        "__rfloordiv__",
        "__rlshift__",
        "__ror__",
        "__ror__",
        "__rrshift__",
        "__rshift__",
        "__rxor__",
        "__rxor__",
        "__xor__",
        "accuracy",
        "accuracy_check",
        "adadelta_",
        "adagrad_",
        "adam_",
        "adamax_",
        "adamw_",
        "add_act_xpu",
        "add_act_xpu",
        "add_group_norm_silu",
        "add_group_norm_silu",
        "add_layernorm_xpu",
        "add_layernorm_xpu",
        "add_n",
        "addcmul_xpu",
        "addcmul_xpu",
        "all",
        "all_reduce",
        "allclose",
        "any",
        "apply_per_channel_scale",
        "arange",
        "argmax",
        "argmin",
        "asgd_",
        "assign_pos",
        "assign_value",
        "assign_value_",
        "atleast_1d",
        "atleast_2d",
        "atleast_3d",
        "auc",
        "average_accumulates_",
        "barrier",
        "batch_fc",
        "bernoulli",
        "bincount",
        "binomial",
        "bipartite_match",
        "bitwise_and",
        "bitwise_invert",
        "bitwise_left_shift",
        "bitwise_not",
        "bitwise_or",
        "bitwise_right_shift",
        "bitwise_xor",
        "blha_get_max_len",
        "blha_get_max_len",
        "block_multihead_attention",
        "block_multihead_attention_",
        "block_multihead_attention_",
        "block_multihead_attention_xpu",
        "block_multihead_attention_xpu",
        "bn_act_xpu",
        "bn_act_xpu",
        "box_clip",
        "box_coder",
        "bucketize",
        "c_allgather",
        "c_allreduce_avg",
        "c_allreduce_max",
        "c_allreduce_min",
        "c_allreduce_prod",
        "c_allreduce_sum",
        "c_broadcast",
        "c_concat",
        "c_identity",
        "c_reduce_avg",
        "c_reduce_max",
        "c_reduce_min",
        "c_reduce_prod",
        "c_reduce_sum",
        "c_reducescatter",
        "c_scatter",
        "c_split",
        "c_sync_calc_stream",
        "c_sync_comm_stream",
        "check_finite_and_unscale_",
        "check_numerics",
        "chunk_eval",
        "class_center_sample",
        "clip_by_norm",
        "coalesce",
        "coalesce_tensor",
        "coalesce_tensor_",
        "conv1d_xpu",
        "conv1d_xpu",
        "conv2d_transpose_bias",
        "conv2d_transpose_xpu",
        "conv2d_transpose_xpu",
        "conv2d_xpu",
        "conv2d_xpu",
        "conv3d_implicit_gemm",
        "copy_to",
        "crf_decoding",
        "cross_attention_xpu",
        "cross_attention_xpu",
        "ctc_align",
        "data",
        "decayed_adagrad",
        "decode_jpeg",
        "depend",
        "dequantize_abs_max",
        "dequantize_linear",
        "dequantize_log",
        "dequantize_xpu",
        "dequantize_xpu",
        "detection_map",
        "dgc",
        "dgc_momentum",
        "diag_embed",
        "diff",
        "dirichlet",
        "distribute_fpn_proposals",
        "distributed_fused_lamb",
        "distributed_fused_lamb_init",
        "distributed_fused_lamb_init",
        "distributed_lookup_table",
        "distributed_push_sparse",
        "dpsgd",
        "edit_distance",
        "eigh",
        "eigvals",
        "embedding_grad_dense",
        "embedding_with_eltwise_add_xpu",
        "embedding_with_eltwise_add_xpu",
        "empty",
        "empty_like",
        "equal",
        "equal_all",
        "eye",
        "fake_channel_wise_dequantize_max_abs",
        "fake_channel_wise_quantize_abs_max",
        "fake_dequantize_max_abs",
        "fake_quantize_abs_max",
        "fake_quantize_moving_average_abs_max",
        "fake_quantize_range_abs_max",
        "fast_layernorm_xpu",
        "fast_layernorm_xpu",
        "fast_where_xpu",
        "fast_where_xpu",
        "fc",
        "fc",
        "fc_xpu",
        "fc_xpu",
        "feed",
        "fetch",
        "floor_divide",
        "fp8_fp8_half_gemm_fused",
        "ftrl",
        "full",
        "full_",
        "full_batch_size_like",
        "full_int_array",
        "full_like",
        "full_with_tensor",
        "fused_adam_",
        "fused_bias_act",
        "fused_bias_act",
        "fused_bias_residual_layernorm",
        "fused_bias_residual_layernorm",
        "fused_conv2d_add_act",
        "fused_conv2d_add_act",
        "fused_dconv_drelu_dbn",
        "fused_dconv_drelu_dbn",
        "fused_elementwise_add",
        "fused_elementwise_add",
        "fused_elementwise_div",
        "fused_elementwise_div",
        "fused_elementwise_mul",
        "fused_elementwise_mul",
        "fused_elementwise_sub",
        "fused_elementwise_sub",
        "fused_embedding_eltwise_layernorm",
        "fused_embedding_eltwise_layernorm",
        "fused_embedding_fc_lstm",
        "fused_fc_elementwise_layernorm",
        "fused_fc_elementwise_layernorm",
        "fused_layer_norm",
        "fused_linear_param_grad_add",
        "fused_linear_param_grad_add",
        "fused_moe",
        "fused_multi_transformer",
        "fused_multi_transformer_",
        "fused_multi_transformer_int8_xpu",
        "fused_multi_transformer_int8_xpu",
        "fused_multi_transformer_xpu",
        "fused_multi_transformer_xpu",
        "fused_scale_bias_add_relu",
        "fused_scale_bias_add_relu",
        "fused_scale_bias_relu_conv_bn",
        "fused_scale_bias_relu_conv_bn",
        "fused_token_prune",
        "fused_token_prune",
        "fusion_group",
        "fusion_group",
        "fusion_gru",
        "fusion_gru",
        "fusion_lstm",
        "fusion_lstm",
        "fusion_repeated_fc_relu",
        "fusion_repeated_fc_relu",
        "fusion_seqconv_eltadd_relu",
        "fusion_seqconv_eltadd_relu",
        "fusion_seqexpand_concat_fc",
        "fusion_seqpool_concat",
        "fusion_seqpool_cvm_concat",
        "fusion_seqpool_cvm_concat",
        "fusion_squared_mat_sub",
        "fusion_squared_mat_sub",
        "fusion_transpose_flatten_concat",
        "fusion_transpose_flatten_concat",
        "gather_tree",
        "gaussian",
        "gemm_epilogue",
        "gemm_epilogue",
        "generate_proposals",
        "generate_sequence_xpu",
        "generate_sequence_xpu",
        "get_tensor_from_selected_rows",
        "graph_khop_sampler",
        "graph_sample_neighbors",
        "greater_equal",
        "greater_than",
        "group_norm_silu_xpu",
        "group_norm_silu_xpu",
        "histogram",
        "histogram_bin_edges",
        "histogramdd",
        "increment",
        "indices",
        "is_empty",
        "isclose",
        "isfinite",
        "isin",
        "isinf",
        "isnan",
        "isneginf",
        "isposinf",
        "isreal",
        "lamb_",
        "lars_momentum",
        "layer_norm_act_xpu",
        "layer_norm_act_xpu",
        "layer_norm_relu_xpu",
        "less",
        "less_equal",
        "less_than",
        "limit_by_capacity",
        "linspace",
        "llm_int8_linear",
        "load_combine",
        "lod_array_length",
        "logical_and",
        "logical_not",
        "logical_or",
        "logical_xor",
        "logspace",
        "lower",
        "lstsq",
        "mask_adaptive_xpu",
        "mask_adaptive_xpu",
        "masked_multihead_attention",
        "masked_multihead_attention_",
        "matrix_nms",
        "matrix_rank",
        "matrix_rank_tol",
        "memcpy",
        "memcpy_d2h",
        "memcpy_h2d",
        "merge_selected_rows",
        "merged_adam_",
        "merged_momentum_",
        "moe",
        "momentum_",
        "moving_average_abs_max_scale",
        "multi_encoder_xpu",
        "multi_encoder_xpu",
        "multiclass_nms3",
        "multihead_matmul",
        "multihead_matmul",
        "multinomial",
        "nadam_",
        "nextafter",
        "nms",
        "nonzero",
        "nop",
        "not_equal",
        "npu_identity",
        "number_count",
        "numel",
        "one_hot",
        "onednn_to_paddle_layout",
        "ones",
        "ones_like",
        "pad2d_xpu",
        "pad2d_xpu",
        "partial_allgather",
        "partial_recv",
        "partial_send",
        "print",
        "prior_box",
        "prune_gate_by_capacity",
        "pull_box_sparse",
        "push_dense",
        "push_sparse_v2",
        "qkv_attention_xpu",
        "qkv_attention_xpu",
        "qkv_unpack_mha",
        "qkv_unpack_mha",
        "qr",
        "quantize_linear",
        "quantize_xpu",
        "quantize_xpu",
        "radam_",
        "randint",
        "random_routing",
        "randperm",
        "read_file",
        "recv_v2",
        "reindex_graph",
        "remainder",
        "rmsprop_",
        "roformer_relative_embedding_xpu",
        "roformer_relative_embedding_xpu",
        "row_conv",
        "rprop_",
        "sample_neighbors",
        "save_combine",
        "searchsorted",
        "seed",
        "self_dp_attention",
        "self_dp_attention",
        "send_and_recv",
        "send_v2",
        "sequence_mask",
        "sequence_unpad_xpu",
        "sequence_unpad_xpu",
        "sgd_",
        "shadow_feed",
        "shadow_feed_tensors",
        "shape",
        "shard_index",
        "share_data_",
        "sine_pos_xpu",
        "sine_pos_xpu",
        "skip_layernorm",
        "skip_layernorm",
        "sparse_momentum",
        "spatial_transformer_resblock_xpu",
        "spatial_transformer_resblock_xpu",
        "squeeze_excitation_block",
        "squeeze_excitation_block",
        "standard_gamma",
        "standard_normal",
        "svd_lowrank",
        "tdm_child",
        "tdm_sampler",
        "to_sparse_csr",
        "top_p_sampling",
        "tril_indices",
        "triu_indices",
        "truncated_gaussian_random",
        "uniform",
        "uniform_random_batch_size_like",
        "unique",
        "unique_consecutive",
        "update_loss_scaling_",
        "upper",
        "vander",
        "variable_length_memory_efficient_attention",
        "variable_length_memory_efficient_attention",
        "viterbi_decode",
        "weight_dequantize",
        "weight_only_linear_xpu",
        "weight_only_linear_xpu",
        "weight_quantize",
        "weighted_sample_neighbors",
        "write_to_array",
        "yolo_box",
        "yolo_box_head",
        "yolo_box_post",
        "yolo_box_xpu",
        "yolo_box_xpu",
        "zeros",
        "zeros_like",
    ]
)

# paddle errors which will be ignored and considered as pass
paddle_error_dismiss = {
    # "API": "error_message",
    # "API": ("error_msg1", "error_msg2"),
    "paddle.nn.functional.conv1d": "(PreconditionNotMet) The element size of ",
    "paddle.nn.functional.conv1d_transpose": "(PreconditionNotMet) The element size of ",
    "paddle.nn.functional.conv2d": "(PreconditionNotMet) The element size of ",
    "paddle.nn.functional.conv2d_transpose": "(PreconditionNotMet) The element size of ",
    "paddle.nn.functional.conv3d": "(PreconditionNotMet) The element size of ",
    "paddle.nn.functional.conv3d_transpose": "(PreconditionNotMet) The element size of ",
    "paddle.vision.ops.distribute_fpn_proposals": ("(PreconditionNotMet) The number of proposals in FPN ", "(PreconditionNotMet) The number of images ", ),
}

# some accuracy error can be considered tolerable
special_accuracy_atol_rtol = {
    # "API": (atol, rtol),
    "paddle.cumsum": (1.0, 1.0),
    "paddle.Tensor.cumsum": (1.0, 1.0),
    "paddle.logcumsumexp": (1.0, 1.0),
    "paddle.Tensor.logcumsumexp": (1.0, 1.0),
    "paddle.incubate.nn.functional.fused_bias_act": (1, 1e-2),
}

torch_error_skip = frozenset(
    [
        'paddle.kthvalue(Tensor([4294967295],"float32"), 1, )',  # torch error
        'paddle.kthvalue(Tensor([4294967295],"float32"), k=2, )',
        'paddle.nn.functional.log_softmax(Tensor([1, 4294967297],"float16"), )',  # torch error for fp16
        'paddle.cumsum(Tensor([10, 429496730],"float16"), dtype="float16", )',  # torch error for fp16
        'paddle.cumsum(Tensor([357913942, 12],"float16"), dtype="float16", )',
        'paddle.cumsum(Tensor([4, 1073741825],"float16"), axis=1, )',
        'paddle.cumsum(x=Tensor([1, 16, 8388609, 32],"float16"), axis=2, )',
        'paddle.cumsum(x=Tensor([4294967297],"float16"), )',
        'paddle.cumsum(x=Tensor([715827883, 2, 1, 3],"float16"), axis=-4, )',
        'paddle.cumsum(x=Tensor([715827883, 2, 1, 3],"float16"), axis=Tensor([1],"float16"), )',
        'paddle.cumsum(x=Tensor([87382, 16, 96, 32],"float16"), axis=2, )',
        'paddle.logcumsumexp(Tensor([10, 429496730],"float16"), dtype="float16", axis=1, )',  # torch error for fp16
        'paddle.logcumsumexp(Tensor([10, 429496730],"float16"), dtype="float16", axis=None, )',
        'paddle.logcumsumexp(Tensor([357913942, 12],"float16"), dtype="float16", axis=None, )',
        'paddle.logcumsumexp(Tensor([1073741824, 4],"float32"), )',  # torch CUDA 700
        'paddle.logcumsumexp(Tensor([1073741824, 4],"float32"), dtype="float32", )',
    ]
)

class APITestBase:
    def __init__(self, api_config):
        self.api_config = api_config
        self.outputs_grad_numpy = []
        torch.set_num_threads(8)
        torch.set_printoptions(threshold=100, linewidth=120)

    def need_skip(self, paddle_only=False):
        # not support
        if "sparse" in self.api_config.api_name:
            return True
        # if self.api_config.api_name in not_support_api:
        #     return True
        # if not paddle_only and self.api_config.api_name in rand_apis:
        #     return True
        # if not paddle_only and self.api_config.api_name in stochastic_behavior_apis:
        #     return True
        if not paddle_only and self.api_config.config in torch_error_skip:
            return True
        for i in range(len(self.api_config.args)):
            if isinstance(self.api_config.args[i], TensorConfig):
                if self.api_config.args[i].dtype in ["float8_e5m2", "float8_e4m3fn"]:
                    return True
            elif isinstance(self.api_config.args[i], list):
                for j in range(len(self.api_config.args[i])):
                    if isinstance(self.api_config.args[i][j], TensorConfig):
                        if self.api_config.args[i][j].dtype in ["float8_e5m2", "float8_e4m3fn"]:
                            return True
            elif isinstance(self.api_config.args[i], tuple):
                for j in range(len(self.api_config.args[i])):
                    if isinstance(self.api_config.args[i][j], TensorConfig):
                        if self.api_config.args[i][j].dtype in ["float8_e5m2", "float8_e4m3fn"]:
                            return True
            elif self.api_config.args[i] in [paddle.base.core.DataType.FLOAT8_E4M3FN, paddle.base.core.DataType.FLOAT8_E5M2, "float8_e5m2", "float8_e4m3fn"]:
                return True

        for key, arg_config in self.api_config.kwargs.items():
            if isinstance(arg_config, TensorConfig):
                if arg_config.dtype in ["float8_e5m2", "float8_e4m3fn"]:
                    return True
            elif isinstance(arg_config, list):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        if arg_config[i].dtype in ["float8_e5m2", "float8_e4m3fn"]:
                            return True
            elif isinstance(arg_config, tuple):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        if arg_config[i].dtype in ["float8_e5m2", "float8_e4m3fn"]:
                            return True
            elif arg_config in [paddle.base.core.DataType.FLOAT8_E4M3FN, paddle.base.core.DataType.FLOAT8_E5M2, "float8_e5m2", "float8_e4m3fn"]:
                return True

        return False

    def need_check_grad(self):
        if self.is_forward_only():
            return False

        if self.api_config.api_name == "paddle.assign":
            has_list_arg = len(self.paddle_args) and isinstance(
                self.paddle_args[0], list
            )
            has_second_arg = (
                len(self.paddle_args) > 1 and self.paddle_args[1] is not None
            )
            if has_list_arg or has_second_arg:
                return False

        return True

        # This part seems unused in any case:
        #
        # valid_dtypes = {'float32', 'float64', 'float16', 'complex64', 'complex128', 'bfloat16'}
        # if len(self.api_config.args) > 0 and isinstance(self.api_config.args[0], TensorConfig):
        #     dtype = self.api_config.args[0].dtype
        #     if dtype in valid_dtypes:
        #         return True
        # return True

        # Original implementation:
        #
        # if not self.is_forward_only() and not (self.api_config.api_name == "paddle.assign" and len(self.paddle_args_config) and isinstance(self.paddle_args_config[0], list)) and not (self.api_config.api_name == "paddle.assign" and len(self.paddle_args_config) > 1 and self.paddle_args_config[1] is not None):
        #     if len(self.api_config.args) > 0 and isinstance(self.api_config.args[0], TensorConfig):
        #         dtype = self.api_config.args[0].dtype
        #         if dtype in ['float32', 'float64', 'float16', 'complex64', 'complex128', 'bfloat16']:
        #             return True
        #     return True
        # return False

    def ana_api_info(self):
        return self.ana_paddle_api_info() and self.ana_torch_api_info()

    def ana_paddle_api_info(self):
        self.paddle_api = eval(self.api_config.api_name)
        self.paddle_args_config = self.api_config.args
        self.paddle_kwargs_config = self.api_config.kwargs
        return True

    def ana_torch_api_info(self):
        self.torch_args_config = []
        self.torch_kwargs_config = collections.OrderedDict()
        self.paddle_merged_kwargs_config = collections.OrderedDict()

        api_name = self.api_config.api_name
        if (
            api_name == "paddle.Tensor.__getitem__"
            or api_name == "paddle.Tensor.__setitem__"
        ):
            self.torch_args_config = self.api_config.args
            return True

        if api_name not in no_signature_api_mappings:
            # For APIs with signatures, use paddle_sig.bind to get arguments
            paddle_sig = inspect.signature(self.paddle_api)
            paddle_bound_args = paddle_sig.bind(*self.api_config.args, **self.api_config.kwargs)
            paddle_args_dict = paddle_bound_args.arguments
            # fix paddle.arange wrong binding
            if self.api_config.api_name == "paddle.arange":
                # if end is not provided, use the 'start' kwargs as end
                if "end" not in paddle_args_dict:
                    paddle_args_dict["end"] = paddle_args_dict["start"]
                    paddle_args_dict["start"] = 0
        else:
            # For APIs without signatures, use the external mapping dict
            mapping = no_signature_api_mappings[api_name]
            paddle_args_dict = {}
            for key, get_value_func in mapping.items():
                paddle_args_dict[key] = get_value_func(self.api_config)

        self.paddle_merged_kwargs_config = paddle_args_dict
        self.torch_kwargs_config.update(paddle_args_dict)
        self.torch_kwargs_config.pop('name', None)

        return True

    def _handle_list_or_tuple(self, config_items, is_tuple=False, index=None, key=None, list_index=[]):
        """处理 list 或 tuple """

        need_axes_handling = self.api_config.api_name in handle_axes_api
        need_indices_handling = self.api_config.api_name == "paddle.index_put"

        if need_indices_handling and (index == 1 or key == "indices"):
            return self._handle_indices_arg(config_items, is_tuple)
        elif need_axes_handling and (index == 1 or key == "axis"):
            return self._handle_axis_arg(config_items, is_tuple)

        tmp = []
        for i, item in enumerate(config_items):
            current_list_index = list_index + [i]
            if isinstance(item, (list, tuple)):
                is_nested_tuple = isinstance(item, tuple)
                processed_item = self._handle_list_or_tuple(
                    item, 
                    is_tuple=is_nested_tuple, 
                    index=index, 
                    key=key, 
                    list_index=current_list_index
                )
            elif isinstance(item, TensorConfig):
                processed_item = item.get_numpy_tensor(
                    self.api_config,
                    index=index,
                    key=key,
                    list_index=current_list_index
                )
            else:
                processed_item = item
            tmp.append(processed_item)
        return tuple(tmp) if is_tuple else tmp

    def _handle_axis_arg(self, config_items, is_tuple=False):
        """处理 axis 参数"""
        x = self.paddle_args_config[0] if len(self.paddle_args_config) > 0 else self.paddle_kwargs_config["x"]
        max_dim = max(len(x.shape), 1) # scalar

        tmp = []
        used_axes = set()
        tensor_configs = []

        for item in config_items:
            if isinstance(item, TensorConfig):
                if item.shape not in [[], [1]] or item.dtype not in ["int32", "int64"]:
                    raise ValueError(f"Invalid TensorConfig for axis: shape {item.shape} or dtype {item.dtype}")
                tensor_configs.append(item)
                tmp.append(0) # placeholder
            elif isinstance(item, int):
                if not (-max_dim <= item < max_dim):
                    raise ValueError(f"Axis value {item} out of range [-{max_dim}, {max_dim})")
                positive_axis = item + max_dim if item < 0 else item
                if positive_axis in used_axes:
                    raise ValueError(f"Duplicate axis value: {item}")
                used_axes.add(positive_axis)
                tmp.append(item)
            else:
                raise ValueError(f"Invalid item type for axis: {type(item)}")

        if tensor_configs:
            available_dims = list(set(range(max_dim)) - used_axes)
            if len(available_dims) < len(tensor_configs):
                raise ValueError(f"Not enough available dimensions ({len(available_dims)}) for {len(tensor_configs)} TensorConfig items")
            selected_dims = numpy.random.choice(available_dims, size=len(tensor_configs), replace=False)
            mask = numpy.random.randint(0, 2, size=len(tensor_configs)).astype(bool)
            final_dims = numpy.where(mask, selected_dims - max_dim, selected_dims)
            tensor_idx = 0
            for i, item in enumerate(config_items):
                if isinstance(item, TensorConfig):
                    item.fill_numpy_tensor(final_dims[tensor_idx])
                    tmp[i] = item.get_numpy_tensor(self.api_config)
                    tensor_idx += 1
        return tuple(tmp) if is_tuple else tmp

    def _handle_indices_arg(self, config_items, is_tuple=False):
        x = self.paddle_args_config[0] if len(self.paddle_args_config) > 0 else self.paddle_kwargs_config["x"]
        value = self.paddle_args_config[2] if len(self.paddle_args_config) > 2 else self.paddle_kwargs_config["value"]
        x_shape = x.shape
        value_shape = value.shape

        tmp = []
        matched_axis = 0
        indices_shape_len = 0
        for item in config_items:
            if item.dtype != "bool":
                matched_axis += 1
                indices_shape_len = max(indices_shape_len, len(item.shape))

        expected = indices_shape_len + len(x_shape) - matched_axis
        reduced = expected - len(value_shape)
        x_shape_index = 0
        value_shape_index = indices_shape_len

        for item in config_items:
            if item.dtype == "bool":
                true_needed = []
                for i in range(len(item.shape)):
                    if reduced > 0:
                        reduced -= 1
                        true_needed.append(1)
                    else:
                        true_needed.append(value_shape[value_shape_index])
                        value_shape_index += 1
                for i in range(len(true_needed) - 1, 0, -1):
                    if true_needed[i] > item.shape[i]:
                        true_needed[i - 1] *= true_needed[i] // item.shape[i]
                        true_needed[i] = item.shape[i]
                mask = numpy.zeros(item.shape, dtype=bool)
                indices = [
                    numpy.random.choice(dim_size, size=needed, replace=False)
                    for dim_size, needed in zip(item.shape, true_needed)
                ]
                mask[numpy.ix_(*indices)] = True
                item.numpy_tensor = mask
                x_shape_index += len(item.shape)
            else:
                x_dim = x_shape[x_shape_index]
                item.numpy_tensor = numpy.random.randint(-x_dim, x_dim, size=item.shape, dtype=item.dtype)
                x_shape_index += 1
            tmp.append(item.get_numpy_tensor(self.api_config))
        return tuple(tmp) if is_tuple else tmp

    def gen_numpy_input(self):
        for i, arg_config in enumerate(self.paddle_args_config):
            if isinstance(arg_config, (list, tuple)):
                is_tuple = isinstance(arg_config, tuple)
                self._handle_list_or_tuple(arg_config, is_tuple=is_tuple, index=i)
            elif isinstance(arg_config, TensorConfig):
                arg_config.get_numpy_tensor(self.api_config, index=i)
        for key, kwarg_config in self.paddle_kwargs_config.items():
            if isinstance(kwarg_config, (list, tuple)):
                is_tuple = isinstance(kwarg_config, tuple)
                self._handle_list_or_tuple(kwarg_config, is_tuple=is_tuple, key=key)
            elif isinstance(kwarg_config, TensorConfig):
                kwarg_config.get_numpy_tensor(self.api_config, key=key)
        return True

    def _handle_list_or_tuple_paddle(self, config_items, is_tuple=False):
        """处理 list 或 tuple """
        tmp = []
        for item in config_items:
            if isinstance(item, (list, tuple)):
                is_nested_tuple = isinstance(item, tuple)
                processed_item = self._handle_list_or_tuple_paddle(
                    item, 
                    is_tuple=is_nested_tuple)
            elif isinstance(item, TensorConfig):
                processed_item = item.get_paddle_tensor(self.api_config)
                item.clear_paddle_tensor()
            else:
                processed_item = item
            tmp.append(processed_item)
        return tuple(tmp) if is_tuple else tmp

    def gen_paddle_input(self):
        """
        generate paddle input by config, for tensor config initlize paddle tensor by get_paddle_tensor()
        
        be sure to call gen_numpy_input() before use gen_paddle_input() since gen_paddle_input() do not pass index or key to get_paddle_tensor() or get_numpy_tensor() while gen_numpy_input() pass.
        """

        self.paddle_args = []
        self.paddle_kwargs = collections.OrderedDict()
        self.paddle_merged_kwargs = collections.OrderedDict()

        for arg_config in self.paddle_args_config:
            if isinstance(arg_config, TensorConfig):
                self.paddle_args.append(arg_config.get_paddle_tensor(self.api_config))
                arg_config.clear_paddle_tensor()
            elif isinstance(arg_config, (list, tuple)):
                is_tuple = isinstance(arg_config, tuple)
                self.paddle_args.append(self._handle_list_or_tuple_paddle(arg_config, is_tuple))
            else:
                self.paddle_args.append(arg_config)

        for key, kwarg_config in self.paddle_kwargs_config.items():
            if isinstance(kwarg_config, TensorConfig):
                self.paddle_kwargs[key] = kwarg_config.get_paddle_tensor(self.api_config)
                kwarg_config.clear_paddle_tensor()
            elif isinstance(kwarg_config, (list, tuple)):
                is_tuple = isinstance(kwarg_config, tuple)
                self.paddle_kwargs[key] = self._handle_list_or_tuple_paddle(kwarg_config, is_tuple)
            else:
                self.paddle_kwargs[key] = kwarg_config

        if len(self.paddle_args) == 0 and self.api_config.api_name.startswith("paddle.Tensor."):
            self.paddle_args.append(self.paddle_kwargs.popitem(last=False)[1])

        if self.api_config.api_name == "paddle.linalg.lstsq" and 'gpu' in paddle.device.get_device():
            if len(self.paddle_args) > 3:
                self.paddle_args[3] = "gels"
            elif "driver" in self.paddle_kwargs:
                self.paddle_kwargs["driver"] = "gels"

        if self.need_check_grad():
            if (self.api_config.api_name[-1] == "_" and self.api_config.api_name[-2:] != "__") or self.api_config.api_name == "paddle.Tensor.__setitem__":
                self.paddle_args, self.paddle_kwargs = self.copy_paddle_input()

        return True

    def copy_paddle_input(self):

        def _deep_copy(data):
            if isinstance(data, paddle.Tensor):
                return paddle.assign(data)
            elif isinstance(data, (list, tuple)):
                return type(data)(_deep_copy(x) for x in data)
            return data

        args = [_deep_copy(arg) for arg in self.paddle_args]
        kwargs = collections.OrderedDict(
            (k, _deep_copy(v)) for k, v in self.paddle_kwargs.items()
        )
        return args, kwargs

    def get_paddle_input_list(self):
        result = []

        for arg in self.paddle_args:
            if isinstance(arg, paddle.Tensor):
                result.append(arg)
            elif isinstance(arg, (tuple, list)):
                result.extend(item for item in arg if isinstance(item, paddle.Tensor))

        # 按 merged_kwargs 顺序遍历，确保 paddle 关键字参数与 torch 参数顺序一致，避免反向比较无法对应
        # torch 参数顺序通过 paddle_sig.bind 绑定，见 ana_torch_api_info()
        if hasattr(self, "paddle_merged_kwargs_config"):
            for key in self.paddle_merged_kwargs_config:
                if key in self.paddle_kwargs:
                    value = self.paddle_kwargs[key]
                    if isinstance(value, paddle.Tensor):
                        result.append(value)
                    elif isinstance(value, (tuple, list)):
                        result.extend(
                            item for item in value if isinstance(item, paddle.Tensor)
                        )
        else:  #  paddle_only
            for key, value in self.paddle_kwargs.items():
                if isinstance(value, paddle.Tensor):
                    result.append(value)
                elif isinstance(value, (tuple, list)):
                    result.extend(
                        item for item in value if isinstance(item, paddle.Tensor)
                    )

        return result

    def get_torch_input_list(self):
        result = []
        for i in range(len(self.torch_args)):
            if isinstance(self.torch_args[i], torch.Tensor):
                result.append(self.torch_args[i])
            elif isinstance(self.torch_args[i], (tuple, list)):
                for item in self.torch_args[i]:
                    if isinstance(item, torch.Tensor):
                        result.append(item)

        for key, value in self.torch_kwargs.items():
            if isinstance(value, torch.Tensor):
                result.append(value)
            elif isinstance(value, (tuple, list)):
                for item in value:
                    if isinstance(item, torch.Tensor):
                        result.append(item)
        return result

    def get_cached_numpy(self, dtype, shape):
        numel = 1
        for i in shape:
            numel = numel * i

        start = (4300000000 - numel - 100) if (4300000000 - numel - 100) > 0 else 0
        if dtype in cached_numpy:
            tensor = cached_numpy[dtype][start:start+numel].reshape(shape)
        else:
            if "int" in dtype:
                cached_numpy[dtype] = numpy.random.randint(-65535, 65535, size=4300000000, dtype="int64").astype(dtype)
                tensor = cached_numpy[dtype][start:start+numel].reshape(shape)
            else:
                cached_numpy[dtype] = (numpy.random.random([4300000000]) - 0.5).astype(dtype)
                tensor = cached_numpy[dtype][start:start+numel].reshape(shape)
        return tensor

    def gen_paddle_output_and_output_grad(self, outputs):
        result_outputs = []
        if isinstance(outputs, paddle.Tensor):
            result_outputs.append(outputs)
        elif isinstance(outputs, list) and len(outputs) > 0 and isinstance(outputs[0], paddle.Tensor):
            result_outputs = outputs
        elif isinstance(outputs, paddle.autograd.autograd.Hessian) or \
                isinstance(outputs, paddle.autograd.autograd.Jacobian):
            result_outputs.append(outputs[:])
        elif isinstance(outputs, tuple):
            for output in outputs:
                if isinstance(output, paddle.Tensor):
                    result_outputs.append(output)
                elif isinstance(output, list):
                    for item in output:
                        if isinstance(item, paddle.Tensor):
                            result_outputs.append(item)
                    else:
                        raise ValueError("outputs format not support")
                elif isinstance(output, paddle.autograd.autograd.Hessian) or \
                        isinstance(output, paddle.autograd.autograd.Jacobian):
                    result_outputs.extend(output[:])
                elif isinstance(output, tuple) and len(output) > 0 and \
                        (isinstance(output[0], paddle.autograd.autograd.Hessian) or \
                        isinstance(output[0], paddle.autograd.autograd.Jacobian)):
                    for lazy_obj in output:
                        result_outputs.append(lazy_obj[:])
                else:
                    raise ValueError("outputs format not support")
                # elif isinstance(output, list) and len(output) > 0 and isinstance(output[0], paddle.Tensor):
                #     result_outputs.append(output)
                # elif isinstance(output, tuple) and len(output) > 0 and isinstance(output[0], paddle.Tensor):
                #     result_outputs.append(output)

        result_outputs_grads = []

        if len(self.outputs_grad_numpy) == 0:
            for output in result_outputs:
                dtype = str(output.dtype)[7:]
                if USE_CACHED_NUMPY:
                    dtype = "float32" if dtype == "bfloat16" else dtype
                    numpy_tensor = self.get_cached_numpy(dtype, output.shape)
                else:
                    if "int" in dtype:
                        numpy_tensor = (numpy.random.randint(-65535, 65535, size=output.shape)).astype(dtype)
                    else:
                        dtype = "float32" if dtype == "bfloat16" else dtype
                        numpy_tensor = (numpy.random.random(output.shape) - 0.5).astype(dtype)
                self.outputs_grad_numpy.append(numpy_tensor)
        for numpy_tensor in self.outputs_grad_numpy:
            dtype = str(numpy_tensor.dtype)
            result_output_grad = paddle.to_tensor(
                numpy_tensor,
                dtype=dtype if dtype != 'bfloat16' else "float32",
            )
            result_output_grad.stop_gradient = False
            if dtype == "bfloat16":
                result_output_grad = paddle.cast(result_output_grad, dtype="uint16")
            result_outputs_grads.append(result_output_grad)
        return result_outputs, result_outputs_grads

    def convert_dtype_to_torch_type(self, dtype):
        # for python built-in types, mappings are int -> torch.int64, bool -> torch.bool, float -> torch.float64, complex -> torch.complex128, None -> None
        if dtype in ['float32', numpy.float32, paddle.float32, paddle.base.libpaddle.VarDesc.VarType.FP32]:
            return torch.float32
        elif dtype in ['float16', numpy.float16, paddle.float16, paddle.base.libpaddle.VarDesc.VarType.FP16]:
            return torch.float16
        elif dtype in ['float64', 'float', 'double', numpy.float64, paddle.float64, paddle.base.libpaddle.VarDesc.VarType.FP64, float]:
            return torch.float64
        elif dtype in ['int16', numpy.int16, paddle.int16, paddle.base.libpaddle.VarDesc.VarType.INT16]:
            return torch.int16
        elif dtype in ['int8', numpy.int8, paddle.int8, paddle.base.libpaddle.VarDesc.VarType.INT8]:
            return torch.int8
        elif dtype in ['bool', numpy.bool_, paddle.bool, paddle.base.libpaddle.VarDesc.VarType.BOOL, bool]:
            return torch.bool
        elif dtype in ['bfloat16','uint16', numpy.uint16, paddle.bfloat16, paddle.base.libpaddle.VarDesc.VarType.BF16]:
            return torch.bfloat16
        elif dtype in ['uint8', numpy.uint8, paddle.uint8, paddle.base.libpaddle.VarDesc.VarType.UINT8]:
            return torch.uint8
        elif dtype in ['int32', numpy.int32, paddle.int32, paddle.base.libpaddle.VarDesc.VarType.INT32]:
            return torch.int32
        elif dtype in ['int64', "int", numpy.int64, paddle.int64, paddle.base.libpaddle.VarDesc.VarType.INT64, int]:
            return torch.int64
        elif dtype in ['complex64', numpy.complex64, paddle.complex64, paddle.base.libpaddle.VarDesc.VarType.COMPLEX64]:
            return torch.complex64
        elif dtype in ['complex128', numpy.complex128, paddle.complex128, paddle.base.libpaddle.VarDesc.VarType.COMPLEX128, complex]:
            return torch.complex128
        elif dtype is None:
            return None
        else:
            raise ValueError(f'Unsupport dtype: {dtype}')

    def gen_torch_output_and_output_grad(self, outputs):
        result_outputs = []
        if isinstance(outputs, torch.Tensor):
            result_outputs.append(outputs)
        elif isinstance(outputs, torch.Size):
            result_outputs.append(torch.tensor(outputs))
        elif isinstance(outputs, list) and len(outputs) > 0 and isinstance(outputs[0], torch.Tensor):
            result_outputs = outputs
        elif isinstance(outputs, tuple):
            for output in outputs:
                if isinstance(output, torch.Tensor):
                    result_outputs.append(output)
                else:
                    raise ValueError("outputs format not support")
                # elif isinstance(output, list) and len(output) > 0 and isinstance(output[0], torch.Tensor):
                #     result_outputs.append(output)
                # elif isinstance(output, tuple) and len(output) > 0 and isinstance(output[0], torch.Tensor):
                #     result_outputs.append(output)

        result_outputs_grads = []
        if len(self.outputs_grad_numpy) == 0:
            for output in result_outputs:
                dtype = str(output.dtype)[6:]
                if USE_CACHED_NUMPY:
                    dtype = "float32" if dtype == "bfloat16" else dtype
                    numpy_tensor = self.get_cached_numpy(dtype, output.shape)
                else:
                    if "int" in dtype:
                        numpy_tensor = (numpy.random.randint(-65535, 65535, size=output.shape)).astype(dtype)
                    else:
                        dtype = "float32" if dtype == "bfloat16" else dtype
                        numpy_tensor = (numpy.random.random(output.shape) - 0.5).astype(dtype)
                self.outputs_grad_numpy.append(numpy_tensor)
        for numpy_tensor in self.outputs_grad_numpy:
            dtype = str(numpy_tensor.dtype)
            result_output_grad = torch.tensor(
                numpy_tensor,
                dtype=self.convert_dtype_to_torch_type(dtype)
                if dtype != 'bfloat16'
                else torch.float32,
            )

            if dtype == "bfloat16":
                result_output_grad = result_output_grad.to(dtype=torch.bfloat16)
            result_outputs_grads.append(result_output_grad)

        return result_outputs, result_outputs_grads

    def gen_paddle_input_with_merged_kwargs(self):
        self.paddle_args = []
        self.paddle_kwargs = collections.OrderedDict()
        self.paddle_merged_kwargs = collections.OrderedDict()

        for i in range(len(self.paddle_args_config)):
            if isinstance(self.paddle_args_config[i], TensorConfig):
                self.paddle_args.append(self.paddle_args_config[i].get_paddle_tensor(self.api_config))
            elif isinstance(self.paddle_args_config[i], list):
                tmp = []
                for j in range(len(self.paddle_args_config[i])):
                    if isinstance(self.paddle_args_config[i][j], TensorConfig):
                        tmp.append(self.paddle_args_config[i][j].get_paddle_tensor(self.api_config))
                    else:
                        tmp.append(self.paddle_args_config[i][j])
                self.paddle_args.append(tmp)
            elif isinstance(self.paddle_args_config[i], tuple):
                tmp = []
                for j in range(len(self.paddle_args_config[i])):
                    if isinstance(self.paddle_args_config[i][j], TensorConfig):
                        tmp.append(self.paddle_args_config[i][j].get_paddle_tensor(self.api_config))
                    else:
                        tmp.append(self.paddle_args_config[i][j])
                self.paddle_args.append(tuple(tmp))
            else:
                self.paddle_args.append(self.paddle_args_config[i])

        for key, arg_config in self.paddle_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                self.paddle_kwargs[key] = arg_config.get_paddle_tensor(self.api_config)
            elif isinstance(arg_config, list):
                value = []
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        value.append(arg_config[i].get_paddle_tensor(self.api_config))
                    else:
                        value.append(arg_config[i])
                self.paddle_kwargs[key] = value
            elif isinstance(arg_config, tuple):
                tmp = []
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        tmp.append(arg_config[i].get_paddle_tensor(self.api_config))
                    else:
                        tmp.append(arg_config[i])
                self.paddle_kwargs[key] = tuple(tmp)
            else:
                self.paddle_kwargs[key] = arg_config

        for key, arg_config in self.paddle_merged_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                self.paddle_merged_kwargs[key] = arg_config.get_paddle_tensor(self.api_config)
            elif isinstance(arg_config, list):
                value = []
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        value.append(arg_config[i].get_paddle_tensor(self.api_config))
                    else:
                        value.append(arg_config[i])
                self.paddle_merged_kwargs[key] = value
            elif isinstance(arg_config, tuple):
                tmp = []
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        tmp.append(arg_config[i].get_paddle_tensor(self.api_config))
                    else:
                        tmp.append(arg_config[i])
                self.paddle_merged_kwargs[key] = tuple(tmp)
            else:
                self.paddle_merged_kwargs[key] = arg_config
        return True

    def copy_torch_input(self):

        def _deep_copy(data):
            if isinstance(data, torch.Tensor):
                return torch.clone(data)
            elif isinstance(data, (list, tuple)):
                return type(data)(_deep_copy(x) for x in data)
            return data

        args = [_deep_copy(arg) for arg in self.torch_args]
        kwargs = collections.OrderedDict(
            (k, _deep_copy(v)) for k, v in self.torch_kwargs.items()
        )
        return args, kwargs

    def _handle_list_or_tuple_torch(self, config_items, is_tuple=False):
        """处理 list 或 tuple """
        tmp = []
        for item in config_items:
            if isinstance(item, (list, tuple)):
                is_nested_tuple = isinstance(item, tuple)
                processed_item = self._handle_list_or_tuple_torch(
                    item, 
                    is_tuple=is_nested_tuple)
            elif isinstance(item, TensorConfig):
                processed_item = item.get_torch_tensor(self.api_config)
                item.clear_torch_tensor()
            else:
                processed_item = item
            tmp.append(processed_item)
        return tuple(tmp) if is_tuple else tmp

    def gen_torch_input(self):
        """
        generate torch input by config, for tensor config initlize torch tensor by get_torch_tensor()
        
        be sure to call gen_numpy_input() before use gen_torch_input() since gen_torch_input() do not pass index or key to get_torch_tensor() or get_numpy_tensor() while gen_numpy_input() pass.
        """

        self.torch_args = []
        self.torch_kwargs = collections.OrderedDict()
        for arg_config in self.torch_args_config:
            if isinstance(arg_config, TensorConfig):
                self.torch_args.append(arg_config.get_torch_tensor(self.api_config))
                arg_config.clear_torch_tensor()
            elif isinstance(arg_config, (list, tuple)):
                is_tuple = isinstance(arg_config, tuple)
                self.torch_args.append(self._handle_list_or_tuple_torch(arg_config, is_tuple))
            elif isinstance(arg_config, paddle.dtype) or isinstance(arg_config, paddle.base.libpaddle.VarDesc.VarType):
                self.torch_args.append(self.convert_dtype_to_torch_type(arg_config))
            else:
                self.torch_args.append(arg_config)

        for key, arg_config in self.torch_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                self.torch_kwargs[key] = arg_config.get_torch_tensor(self.api_config)
                arg_config.clear_torch_tensor()
            elif isinstance(arg_config, (list, tuple)):
                is_tuple = isinstance(arg_config, tuple)
                self.torch_kwargs[key] = self._handle_list_or_tuple_torch(arg_config, is_tuple)
            elif isinstance(arg_config, paddle.dtype) or isinstance(arg_config, paddle.base.libpaddle.VarDesc.VarType) or key == "dtype":
                self.torch_kwargs[key] = self.convert_dtype_to_torch_type(arg_config)
            else:
                self.torch_kwargs[key] = arg_config

        if self.need_check_grad():
            if (self.api_config.api_name[-1] == "_" and self.api_config.api_name[-2:] != "__") or self.api_config.api_name == "paddle.Tensor.__setitem__":
                self.torch_args, self.torch_kwargs = self.copy_torch_input()

        torch.cuda.empty_cache()
        return True

    def np_assert_accuracy(self, np_paddle, np_torch, atol=1e-2, rtol=1e-2):
        if np_paddle.dtype == numpy.bool_:
            numpy.testing.assert_equal(np_paddle, np_torch)
            return

        if self.api_config.api_name in special_accuracy_atol_rtol:
            atol, rtol = special_accuracy_atol_rtol[self.api_config.api_name]

        numpy.testing.assert_allclose(
            np_paddle,
            np_torch,
            rtol=rtol,
            atol=atol,
            equal_nan=True,
        )

    def torch_assert_accuracy(self, paddle_tensor, torch_tensor, atol=1e-2, rtol=1e-2):
        is_check_dtype = self.api_config.api_name not in not_check_dtype

        if not paddle_tensor.is_contiguous():
            paddle_tensor = paddle_tensor.contiguous()
        paddle_tensor = paddle_tensor.cpu().detach()

        if not torch_tensor.is_contiguous():
            torch_tensor = torch_tensor.contiguous()
        torch_tensor = torch_tensor.cpu().detach()

        paddle_dlpack = paddle.utils.dlpack.to_dlpack(paddle_tensor)  # type: ignore
        converted_paddle_tensor = torch.utils.dlpack.from_dlpack(paddle_dlpack)  # type: ignore

        def error_msg(msg):
            return (
                f"Not equal to tolerance rtol={rtol}, atol={atol}\n"
                f"{msg}\n"
                f"ACTUAL: (shape={converted_paddle_tensor.shape}, dtype={converted_paddle_tensor.dtype})\n"
                f"{converted_paddle_tensor}\n"
                f"DESIRED: (shape={torch_tensor.shape}, dtype={torch_tensor.dtype})\n"
                f"{torch_tensor}"
            )

        if self.api_config.api_name in special_accuracy_atol_rtol:
            atol, rtol = special_accuracy_atol_rtol[self.api_config.api_name]

        test_tol = getattr(self, "test_tol", False)
        is_backward = getattr(self, "is_backward", False)
        if test_tol:
            atol, rtol = 0.0, 0.0

        try:
            torch.testing.assert_close(
                converted_paddle_tensor,
                torch_tensor,
                rtol=rtol,
                atol=atol,
                equal_nan=True,
                check_dtype=is_check_dtype,
                msg=error_msg,
            )
            if test_tol:
                api_name = self.api_config.api_name
                config = self.api_config.config[:120000]
                log_accuracy_tolerance(
                    "Identical",
                    api_name,
                    config,
                    str(paddle_tensor.dtype),
                    is_backward,
                )
        except Exception as e:
            error_str = str(e)
            if error_str.startswith("Comparing"):
                print(f"torch_assert failed, try np_assert", flush=True)
                self.np_assert_accuracy(
                    paddle_tensor.numpy(),
                    torch_tensor.numpy(),
                    atol,
                    rtol,
                )
            elif test_tol:
                error_info = (
                    error_str.split("\n", maxsplit=2)[1] if "\n" in error_str else None
                )
                if error_info and (
                    error_info.startswith("Tensor-likes")
                    or error_info.startswith("Scalars")
                ):
                    api_name = self.api_config.api_name
                    config = self.api_config.config[:120000]
                    log_accuracy_tolerance(
                        error_str,
                        api_name,
                        config,
                        str(paddle_tensor.dtype),
                        is_backward,
                    )
            else:
                raise

    def test(self):
        pass

    def clear_tensor(self):
        if not hasattr(self, "torch_kwargs_config"):
            return
        for key, arg_config in self.torch_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                arg_config.clear_tensor()
            elif isinstance(arg_config, list):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_tensor()
            elif isinstance(arg_config, tuple):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_tensor()
        torch.cuda.empty_cache()
        paddle.device.cuda.empty_cache()

    def clear_paddle_tensor(self):
        if not hasattr(self, "torch_kwargs_config"):
            return
        for key, arg_config in self.torch_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                arg_config.clear_paddle_tensor()
            elif isinstance(arg_config, list):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_paddle_tensor()
            elif isinstance(arg_config, tuple):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_paddle_tensor()
        paddle.device.cuda.empty_cache()

    def clear_torch_tensor(self):
        if not hasattr(self, "torch_kwargs_config"):
            return
        for key, arg_config in self.torch_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                arg_config.clear_torch_tensor()
            elif isinstance(arg_config, list):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_torch_tensor()
            elif isinstance(arg_config, tuple):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_torch_tensor()
        torch.cuda.empty_cache()

    def clear_numpy_tensor(self):
        if not hasattr(self, "torch_kwargs_config"):
            return
        for key, arg_config in self.torch_kwargs_config.items():
            if isinstance(arg_config, TensorConfig):
                arg_config.clear_numpy_tensor()
            elif isinstance(arg_config, list):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_numpy_tensor()
            elif isinstance(arg_config, tuple):
                for i in range(len(arg_config)):
                    if isinstance(arg_config[i], TensorConfig):
                        arg_config[i].clear_numpy_tensor()

    def is_forward_only(self):
        api = self.api_config.api_name[self.api_config.api_name.rindex(".")+1:]
        return api in forward_only_apis

    def should_ignore_paddle_error(self, error_msg):
        dismiss_errors = paddle_error_dismiss.get(self.api_config.api_name, None)
        if dismiss_errors is None:
            return False
        if isinstance(dismiss_errors, str):
            return dismiss_errors in error_msg
        elif isinstance(dismiss_errors, (list, tuple)):
            return any(error in error_msg for error in dismiss_errors)
        return False
