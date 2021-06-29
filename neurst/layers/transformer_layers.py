# Copyright 2020 ByteDance Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import tensorflow as tf

from neurst.layers.attentions.multi_head_attention import MultiHeadAttention, MultiHeadSelfAttention
from neurst.layers.common_layers import PrePostProcessingWrapper, TransformerFFN
from neurst.utils import compat


class TransformerEncoderLayer(tf.keras.layers.Layer):
    """ Defines one transformer layer. """

    def __init__(self,
                 hidden_size,
                 num_attention_heads,
                 filter_size,
                 ffn_activation="relu",
                 attention_dropout_rate=0.,
                 attention_type="dot_product",
                 ffn_dropout_rate=0.,
                 layer_postprocess_dropout_rate=0.,
                 layer_postprocess_epsilon=1e-6,
                 post_normalize=False,
                 name=None):
        """ Initializes the transformer encoder layer.

        Args:
            hidden_size: The number of hidden units.
            num_attention_heads: The number of self attention heads.
            filter_size: The filter size of ffn layer.
            ffn_activation: The activation function of ffn layer.
            ffn_dropout_rate: The dropout rate for ffn layer.
            attention_dropout_rate: The dropout rate for ffn layer.
            attention_type: The self attention type.
            layer_postprocess_dropout_rate: The dropout rate for each layer post process.
            layer_postprocess_epsilon: The epsilon for layer norm.
            post_normalize: Whether to apply layernorm after each block.
            name: The name of this encoder.
        """
        super(TransformerEncoderLayer, self).__init__(name=name)
        self._hidden_size = hidden_size
        self._num_attention_heads = num_attention_heads
        self._filter_size = filter_size
        self._ffn_activation = ffn_activation
        self._attention_dropout_rate = attention_dropout_rate
        self._attention_type = attention_type
        self._ffn_dropout_rate = ffn_dropout_rate
        self._layer_postprocess_dropout_rate = layer_postprocess_dropout_rate
        self._layer_postprocess_epsilon = layer_postprocess_epsilon
        self._post_normalize = post_normalize
        self._lightseq_enabled = compat.check_lightseq_enabled()

    def _build_tf_components(self):
        self._selfatt_layer = PrePostProcessingWrapper(
            layer=MultiHeadSelfAttention(
                num_heads=self._num_attention_heads,
                num_units=self._hidden_size,
                attention_dropout_rate=self._attention_dropout_rate,
                attention_type=self._attention_type,
                name="self_attention"),
            dropout_rate=self._layer_postprocess_dropout_rate,
            epsilon=self._layer_postprocess_epsilon,
            pre_norm=(not self._post_normalize),
            res_conn_factor=1.,
            name="self_attention_prepost_wrapper")
        self._ffn_layer = PrePostProcessingWrapper(
            layer=TransformerFFN(
                filter_size=self._filter_size,
                output_size=self._hidden_size,
                dropout_rate=self._ffn_dropout_rate,
                activation=self._ffn_activation,
                name="ffn"),
            dropout_rate=self._layer_postprocess_dropout_rate,
            epsilon=self._layer_postprocess_epsilon,
            pre_norm=(not self._post_normalize),
            res_conn_factor=1.,
            name="ffn_prepost_wrapper"
        )

    def _forward_tf(self, x, x_bias, is_training=True):
        y = self._selfatt_layer(
            x,  # x as query
            bias=x_bias,
            is_training=is_training)
        # ffn
        y = self._ffn_layer(y, is_training=is_training)
        return y

    def _build_lightseq_components(self):
        from lightseq import LSTransformerEncoderLayer
        self._encoder_layer = LSTransformerEncoderLayer(
            intermediate_size=self._filter_size,
            hidden_size=self._hidden_size,
            ffn_dropout_ratio=self._ffn_dropout_rate,
            attn_dropout_ratio=self._attention_dropout_rate,
            hidden_dropout_ratio=self._layer_postprocess_dropout_rate,
            epsilon=self._layer_postprocess_epsilon,
            trainable=True,
            name="encoder_layer",
            heads=self._num_attention_heads,
            pre_or_postLayerNorm=(not self._post_normalize)
        )

    def _forward_lightseq(self, x, x_bias, is_training=True):
        y = self._encoder_layer(
            x,
            inputs_mask=x_bias,
            is_training=is_training)
        return y

    def build(self, input_shape):
        if self._lightseq_enabled:
            self._build_lightseq_components()
        else:
            self._build_tf_components()
        super(TransformerEncoderLayer, self).build(input_shape)

    def call(self, x, x_bias, is_training=True):
        return (self._forward_lightseq(x, x_bias, is_training=is_training) if self._lightseq_enabled
                else self._forward_tf(x, x_bias, is_training=is_training))


class TransformerDecoderLayer(tf.keras.layers.Layer):
    """ Defines one transformer layer. """

    def __init__(self,
                 hidden_size,
                 num_attention_heads,
                 filter_size,
                 ffn_activation="relu",
                 attention_dropout_rate=0.,
                 attention_type="dot_product",
                 ffn_dropout_rate=0.,
                 layer_postprocess_dropout_rate=0.,
                 layer_postprocess_epsilon=1e-6,
                 post_normalize=False,
                 with_cross_attention=True,
                 name=None):
        """ Initializes the transformer encoder layer.

        Args:
            hidden_size: The number of hidden units.
            num_attention_heads: The number of self attention heads.
            filter_size: The filter size of ffn layer.
            ffn_activation: The activation function of ffn layer.
            ffn_dropout_rate: The dropout rate for ffn layer.
            attention_dropout_rate: The dropout rate for ffn layer.
            attention_type: The self attention type.
            layer_postprocess_dropout_rate: The dropout rate for each layer post process.
            layer_postprocess_epsilon: The epsilon for layer norm.
            post_normalize: Whether to apply layernorm after each block.
            with_cross_attention: Whether to involve cross attention.
            name: The name of this encoder.
        """
        super(TransformerDecoderLayer, self).__init__(name=name)
        self._hidden_size = hidden_size
        self._num_attention_heads = num_attention_heads
        self._filter_size = filter_size
        self._ffn_activation = ffn_activation
        self._attention_dropout_rate = attention_dropout_rate
        self._attention_type = attention_type
        self._ffn_dropout_rate = ffn_dropout_rate
        self._layer_postprocess_dropout_rate = layer_postprocess_dropout_rate
        self._layer_postprocess_epsilon = layer_postprocess_epsilon
        self._post_normalize = post_normalize
        self._with_cross_attention = with_cross_attention
        self._lightseq_enabled = compat.check_lightseq_enabled()

    def _create_tf_cache(self, decode_padded_length=None):
        num_units_per_head = self._hidden_size // self._num_attention_heads
        return {
            "self_attention": {
                "keys": tf.zeros([decode_padded_length or 0, self._num_attention_heads, num_units_per_head],
                                 dtype=compat.CUSTOM_GLOBAL_FLOATX),
                "values": tf.zeros([decode_padded_length or 0, self._num_attention_heads, num_units_per_head],
                                   dtype=compat.CUSTOM_GLOBAL_FLOATX)},
        }

    def _create_lightseq_cache(self, decode_padded_length=None):
        num_units_per_head = self._hidden_size // self._num_attention_heads
        return {
            "self_attention": {
                "keys": tf.zeros([self._num_attention_heads, decode_padded_length or 0, num_units_per_head],
                                  dtype=compat.CUSTOM_GLOBAL_FLOATX),
                "values": tf.zeros([self._num_attention_heads, decode_padded_length or 0, num_units_per_head],
                                    dtype=compat.CUSTOM_GLOBAL_FLOATX)},
        }

    def _build_tf_components(self):
        self._selfatt_layer = PrePostProcessingWrapper(
            layer=MultiHeadSelfAttention(
                num_heads=self._num_attention_heads,
                num_units=self._hidden_size,
                attention_dropout_rate=self._attention_dropout_rate,
                attention_type=self._attention_type,
                name="self_attention"),
            dropout_rate=self._layer_postprocess_dropout_rate,
            epsilon=self._layer_postprocess_epsilon,
            pre_norm=(not self._post_normalize),
            res_conn_factor=1.,
            name="self_attention_prepost_wrapper")
        if self._with_cross_attention:
            self._crossatt_layer = PrePostProcessingWrapper(
                layer=MultiHeadAttention(
                    num_heads=self._num_attention_heads,
                    num_units=self._hidden_size,
                    attention_dropout_rate=self._attention_dropout_rate,
                    attention_type=self._attention_type,
                    name="encdec_attention"),
                dropout_rate=self._layer_postprocess_dropout_rate,
                epsilon=self._layer_postprocess_epsilon,
                pre_norm=(not self._post_normalize),
                res_conn_factor=1.,
                name="encdec_attention_prepost_wrapper")
        self._ffn_layer = PrePostProcessingWrapper(
            layer=TransformerFFN(
                filter_size=self._filter_size,
                output_size=self._hidden_size,
                dropout_rate=self._ffn_dropout_rate,
                activation=self._ffn_activation,
                name="ffn"),
            dropout_rate=self._layer_postprocess_dropout_rate,
            epsilon=self._layer_postprocess_epsilon,
            pre_norm=(not self._post_normalize),
            res_conn_factor=1.,
            name="ffn_prepost_wrapper"
        )

    def _forward_tf(self, x, x_bias, cache, memory=None, memory_bias=None,
                    is_training=True, decode_loop_step=None):
        selfatt_cache = None if cache is None else cache["self_attention"]
        y = self._selfatt_layer(
            x,  # x as query
            bias=x_bias,
            cache=selfatt_cache,
            is_training=is_training,
            decode_loop_step=decode_loop_step)
        # enc-dec attention layer
        if self._with_cross_attention:
            y = self._crossatt_layer(
                y,  # x as query
                memory=memory,  # None indicates self-attention
                memory_bias=memory_bias,
                is_training=is_training)
        # ffn
        y = self._ffn_layer(y, is_training=is_training)
        return y

    def _build_lightseq_components(self):
        from lightseq import LSTransformerDecoderLayer
        self._decoder_layer = LSTransformerDecoderLayer(
            num_heads=self._num_attention_heads,
            hidden_size=self._hidden_size,
            intermediate_size=self._filter_size,
            attn_prob_dropout_ratio=self._attention_dropout_rate,
            activation_dropout_ratio=self._ffn_dropout_rate,
            hidden_dropout_ratio=self._layer_postprocess_dropout_rate,
            pre_or_postLayerNorm=(not self._post_normalize),
            trainable=True,
            predict=False,
            epsilon=1e-8,
            name="decoder_layer")
    def _forward_lightseq(self, dec_input, x_bias, cache, enc_output=None, enc_mask=None,
                          is_training=True, decode_loop_step=None):
        if cache is None:
            cached_k =  tf.zeros([0], dtype=dec_input.dtype)
            cached_v =  tf.zeros([0], dtype=dec_input.dtype)
            (out, cached_k_new, cached_v_new) = self._decoder_layer(dec_input, enc_output, enc_mask, cached_k, cached_v, is_training=True, predict=False)
        else:
            cached_k =  cache["self_attention"]["keys"]
            cached_v =  cache["self_attention"]["values"]
            (out, cached_k_new, cached_v_new) = self._decoder_layer(dec_input, enc_output, enc_mask, cached_k, cached_v, is_training=False, predict=True)
            cache["self_attention"]["keys"] = cached_k_new
            cache["self_attention"]["values"] = cached_v_new
        return out


    def create_decoding_internal_cache(self, decode_padded_length=None):
        if self._lightseq_enabled:
            return self._create_lightseq_cache(decode_padded_length)
        return self._create_tf_cache(decode_padded_length)

    def build(self, input_shape):
        if self._lightseq_enabled:
            self._build_lightseq_components()
        else:
            self._build_tf_components()
        super(TransformerDecoderLayer, self).build(input_shape)

    def call(self, x, x_bias, cache,
             memory=None, memory_bias=None,
             is_training=True, decode_loop_step=None):
        return (self._forward_lightseq(x, x_bias, cache, memory, memory_bias,
                                       is_training=is_training,
                                       decode_loop_step=decode_loop_step) if self._lightseq_enabled
                else self._forward_tf(x, x_bias, cache, memory, memory_bias,
                                      is_training=is_training, decode_loop_step=decode_loop_step))

