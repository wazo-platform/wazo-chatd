# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later


def update_model_instance(model_instance, model_instance_data):
    for attribute_name, attribute_value in model_instance_data.items():
        if not hasattr(model_instance, attribute_name):
            raise TypeError(
                '{} has no attribute {}'.format(
                    model_instance.__class__.__name__,
                    attribute_name,
                )
            )
        setattr(model_instance, attribute_name, attribute_value)
