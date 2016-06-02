# Copyright 2016 Google Inc. All Rights Reserved.
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
# ==============================================================================

#!/usr/grte/v4/bin/python2.7
"""Export inception model given existing training checkpoints.
"""

import os.path
import sys
import math

# This is a placeholder for a Google-internal import.

import tensorflow as tf

from inception import inception_model

from tensorflow_serving.session_bundle import exporter


tf.app.flags.DEFINE_string('checkpoint_dir', 'SnapModel/isPerson',
                           """Directory where to read training checkpoints.""")
tf.app.flags.DEFINE_string('export_dir', '/tmp/inception_export',
                           """Directory where to export inference model.""")
tf.app.flags.DEFINE_integer('image_size', 100,
                            """Needs to provide same value as in training.""")
FLAGS = tf.app.flags.FLAGS


NUM_CLASSES = 2
NUM_TOP_CLASSES = 2

def inference_func(images, hidden_units):
  IMAGE_PIXELS = FLAGS.image_size * FLAGS.image_size

  # CREATE HIDDEN LAYERS AS DEFINED IN hidden_units
  hidden = tf.reshape(images, [-1,FLAGS.image_size*FLAGS.image_size])
  hidden_levels = len(hidden_units) - 1
  for i in range(hidden_levels):
    weights = tf.Variable(
        tf.truncated_normal([hidden_units[i], hidden_units[i+1]],
                            stddev=1.0 / math.sqrt(float(IMAGE_PIXELS))),
        name='weights')
    biases = tf.Variable(tf.zeros([hidden_units[i+1]]),
                         name='biases')
    print(hidden.get_shape())
    print(weights.get_shape())
    print(biases.get_shape())
    hidden = tf.nn.relu(tf.matmul(hidden, weights) + biases)
  # FINAL SOFTMAX LAYER
  with tf.name_scope('softmax_linear'):
    weights_softmax = tf.Variable(
        tf.truncated_normal([hidden_units[hidden_levels], NUM_CLASSES],
                            stddev=1.0 / math.sqrt(float(hidden_units[hidden_levels-1]))),
        name='weights')
    biases_softmax = tf.Variable(tf.zeros([NUM_CLASSES]),
                         name='biases')
    logits = tf.nn.softmax(tf.matmul(hidden, weights_softmax) + biases_softmax)
  return logits


def export():
  with tf.Graph().as_default():
    # Build inference model.
    # Please refer to Tensorflow inception model for details.

    # Input transformation.
    # TODO(b/27776734): Add batching support.
    jpegs = tf.placeholder(tf.string, shape=(1))
    image_buffer = tf.squeeze(jpegs, [0])
    # Decode the string as an RGB JPEG.
    # Note that the resulting image contains an unknown height and width
    # that is set dynamically by decode_jpeg. In other words, the height
    # and width of image is unknown at compile-time.
    image = tf.image.decode_jpeg(image_buffer, channels=1)
    # After this point, all image pixels reside in [0,1)
    # until the very end, when they're rescaled to (-1, 1).  The various
    # adjust_* ops all require this range for dtype float.
    image = tf.image.convert_image_dtype(image, dtype=tf.float32)
    # Crop the central region of the image with an area containing 87.5% of
    # the original image.
    image = tf.image.central_crop(image, central_fraction=0.875)
    # Resize the image to the original height and width.
    image = tf.expand_dims(image, 0)
    image = tf.image.resize_bilinear(image,
                                     [FLAGS.image_size, FLAGS.image_size],
                                     align_corners=False)
    image = tf.squeeze(image, [0])
    # Finally, rescale to [-1,1] instead of [0, 1)
    image = tf.sub(image, 0.5)
    image = tf.mul(image, 2.0)
    images = tf.expand_dims(image, 0)

    # Run inference.
    logits = inference_func(images, [FLAGS.image_size*FLAGS.image_size,128, 32])

    # Transform output to topK result.
    values, indices = tf.nn.top_k(logits, NUM_TOP_CLASSES)

    # Restore variables from training checkpoint.
    saver = tf.train.Saver()
    with tf.Session() as sess:
      # Restore variables from training checkpoints.
      ckpt = tf.train.get_checkpoint_state(FLAGS.checkpoint_dir)
      if ckpt and ckpt.model_checkpoint_path:
        saver.restore(sess, ckpt.model_checkpoint_path)
        # Assuming model_checkpoint_path looks something like:
        #   /my-favorite-path/imagenet_train/model.ckpt-0,
        # extract global_step from it.
        #global_step = ckpt.model_checkpoint_path.split('/')[-1].split('-')[-1]
        print('Successfully loaded model from %s at step=%s.' %
              (ckpt.model_checkpoint_path, "00000001"))
      else:
        print('No checkpoint file found at %s' % FLAGS.checkpoint_dir)
        return

      # Export inference model.
      model_exporter = exporter.Exporter(saver)
      signature = exporter.classification_signature(
          input_tensor=jpegs, classes_tensor=indices, scores_tensor=values)
      model_exporter.init(default_graph_signature=signature)
      model_exporter.export(FLAGS.export_dir, tf.constant("00000001"), sess)
      print('Successfully exported model to %s' % FLAGS.export_dir)


def main(unused_argv=None):
  export()


if __name__ == '__main__':
  tf.app.run()
